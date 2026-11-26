"""Regresiones del límite diario y exclusiones de ponderación de SGR."""
from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from organization.models import Delegation, Employee, PositionFunction
from planning_measurements.models import Goal, Period
from registration_validation.models import (
    Activity, ActivityType, Evidence, Validation,
)
from monitoring_traceability.services import recalculate_indicator_for_goal
from registration_validation.test_resolved_attention_support import link_resolved_attention


class ActivityRulesSGRTests(TestCase):
    def setUp(self):
        today = timezone.localdate()
        self.day = today
        self.delegation = Delegation.objects.create(
            name="Delegación de prueba", status="Active", scope="Local"
        )
        self.position = PositionFunction.objects.create(
            position_name="Funcionario de prueba", measurable_items="Atenciones",
            services="Atención", weightings="100",
            validity_start=date(today.year - 1, 1, 1),
            validity_end=date(today.year + 1, 12, 31),
        )
        self.employee = Employee.objects.create(
            delegation=self.delegation, position=self.position,
            name="Funcionario registrado", roles="Gestor", status="Active",
        )
        self.delegate = Employee.objects.create(
            delegation=self.delegation, position=self.position,
            name="Delegado municipal", roles="Delegado", status="Active",
        )
        self.delegation.responsible = self.delegate
        self.delegation.save(update_fields=["responsible", "updated_at"])
        self.period = Period.objects.create(
            start_date=date(today.year, 1, 1),
            end_date=date(today.year, 12, 31),
            computable_days=200, status="Active",
            thresholds="Verde: 100, Amarillo: 80, Rojo: 60, Tope: 120",
            parameters_version="v1",
        )
        self.goal = Goal.objects.create(
            period=self.period, employee=self.employee, position=self.position,
            item="Atenciones de prueba", objective_value=1,
            weight=100, unit="unidades",
        )
        self.goal2 = Goal.objects.create(
            period=self.period, employee=self.employee, position=self.position,
            item="Segunda meta", objective_value=1,
            weight=100, unit="unidades",
        )

    def activity(self, *, contact="Vecino Solicitante", phone="123456789",
                 goal=None, day=None, activity_type=None, action="Atención"):
        activity = Activity.objects.create(
            goal=goal or self.goal, author=self.employee, date=day or self.day,
            contact=contact, phone=phone, action=action,
            request_problem="Solicitud de prueba", activity_type=activity_type,
        )
        link_resolved_attention(activity)
        return activity

    def approve(self, activity, *, verifier=None, document=False):
        evidence = Evidence.objects.create(
            activity=activity, author=self.employee,
            date=timezone.now(), review_status="Pending",
            file_link="respaldo/formal.pdf" if document else "",
        )
        Validation.objects.create(
            evidence=evidence, verifier=verifier or self.employee,
            decision="Approved", result="Approved", date=timezone.now(),
        )
        return evidence

    def test_septima_si_octava_no_incluso_distintas_metas(self):
        for index in range(7):
            self.activity(goal=self.goal if index % 2 == 0 else self.goal2)
        self.assertEqual(Activity.objects.filter(
            author=self.employee, date=self.day, deleted_at__isnull=True
        ).count(), 7)
        with self.assertRaises(ValidationError):
            self.activity(goal=self.goal2)

    def test_archivada_libera_cupo_y_editar_existente_no_lo_consume(self):
        activities = [self.activity() for _ in range(7)]
        first = activities[0]
        first.action = "Nueva observación sin cambiar fecha"
        first.save(update_fields=["action", "updated_at"])
        first.deleted_at = timezone.now()
        first.save(update_fields=["deleted_at", "updated_at"])
        self.activity()

    def test_modificar_fecha_a_dia_lleno_no_puede(self):
        day_before = self.day - timedelta(days=1)
        moving = self.activity(day=day_before)
        for _ in range(7):
            self.activity()
        moving.date = self.day
        with self.assertRaises(ValidationError):
            moving.save(update_fields=["date", "updated_at"])
        moving.refresh_from_db()
        self.assertEqual(moving.date, day_before)

    def test_actividad_normal_aprobada_pondera(self):
        activity = self.activity()
        self.approve(activity)
        indicator = recalculate_indicator_for_goal(self.goal)
        self.assertEqual(indicator.actual_progress, Decimal("1"))

    def test_sin_nombre_o_telefono_no_pondera(self):
        activity = self.activity(contact="", phone="")
        self.approve(activity)
        indicator = recalculate_indicator_for_goal(self.goal)
        self.assertEqual(indicator.actual_progress, Decimal("0"))

    def test_nombre_de_solicitante_no_excluye_si_actividad_es_de_otro(self):
        activity = self.activity(contact="Delegado municipal")
        self.approve(activity)
        indicator = recalculate_indicator_for_goal(self.goal)
        self.assertEqual(indicator.actual_progress, Decimal("1"))

    def test_delegado_registra_actividad_de_maria_y_no_pondera(self):
        activity = self.activity(contact="Vecino Solicitante")
        activity.created_by_employee = self.delegate
        activity.save(update_fields=["created_by_employee", "updated_at"])
        self.approve(activity)
        indicator = recalculate_indicator_for_goal(self.goal)
        self.assertEqual(indicator.actual_progress, Decimal("0"))
        self.assertEqual(indicator.approved_evidences, 0)

    def test_coordinacion_preparatoria_no_pondera(self):
        activity_type = ActivityType.objects.create(
            code="COORD-PREP", name="Coordinación preparatoria", is_preparatory_coordination=True
        )
        activity = self.activity(activity_type=activity_type)
        self.approve(activity)
        indicator = recalculate_indicator_for_goal(self.goal)
        self.assertEqual(indicator.actual_progress, Decimal("0"))

    def test_felicitacion_no_se_respalda_solo_eligiendo_verificador_delegado(self):
        activity_type = ActivityType.objects.create(
            code="FELICIT", name="Felicitaciones", is_congratulation=True,
        )
        activity = self.activity(activity_type=activity_type)
        evidence = self.approve(activity, document=True)
        self.assertEqual(recalculate_indicator_for_goal(self.goal).actual_progress, Decimal("0"))
        Validation.objects.create(
            evidence=evidence, verifier=self.delegate, decision="Approved",
            result="Approved", version=2, date=timezone.now() + timedelta(seconds=1),
        )
        self.assertEqual(recalculate_indicator_for_goal(self.goal).actual_progress, Decimal("0"))

    def test_felicitacion_sin_documento_no_pondera_aunque_valide_delegado(self):
        kind = ActivityType.objects.create(
            code="FELIC-SIN-DOC", name="Felicitación de vecinos",
            is_congratulation=True,
        )
        activity = self.activity(action="Recibimos felicitación ciudadana", activity_type=kind)
        self.approve(activity, verifier=self.delegate, document=False)
        indicator = recalculate_indicator_for_goal(self.goal)
        self.assertEqual(indicator.actual_progress, Decimal("0"))
