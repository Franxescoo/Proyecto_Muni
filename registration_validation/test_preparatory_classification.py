"""Pruebas de la clasificación explícita de coordinaciones preparatorias."""
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from monitoring_traceability.services import recalculate_indicator_for_goal
from organization.models import Delegation, Employee, PositionFunction
from planning_measurements.models import Goal, Period
from registration_validation.activity_rules import activity_qualifies_for_goal
from registration_validation.forms import ActivityTypeForm
from registration_validation.models import Activity, ActivityType, Evidence, Validation


class PreparatoryClassificationTests(TestCase):
    def setUp(self):
        today = timezone.localdate()
        self.today = today
        self.delegation = Delegation.objects.create(
            name="Delegación clasificación preparatoria", status="Active", scope="Local"
        )
        self.position = PositionFunction.objects.create(
            position_name="Gestor clasificación", measurable_items="Atenciones",
            services="Atención", weightings="100",
            validity_start=date(today.year-1, 1, 1),
            validity_end=date(today.year+1, 12, 31),
        )
        self.employee = Employee.objects.create(
            delegation=self.delegation, position=self.position,
            name="Funcionario de clasificación", roles="Gestión", status="Active",
        )
        self.period = Period.objects.create(
            start_date=date(today.year, 1, 1),
            end_date=date(today.year, 12, 31),
            computable_days=200, status="Active",
            thresholds="Verde: 100, Amarillo: 80, Rojo: 60, Tope: 120",
            parameters_version="v1",
        )
        self.goal = Goal.objects.create(
            period=self.period, employee=self.employee, position=self.position,
            item="Atenciones de clasificación", objective_value=1,
            weight=100, unit="unidades",
        )

    def make_approved_activity(self, activity_type):
        activity = Activity.objects.create(
            goal=self.goal, author=self.employee, date=self.today,
            contact="Vecino de prueba", phone="123456789",
            action="Atención realizada", request_problem="Prueba",
            activity_type=activity_type,
        )
        evidence = Evidence.objects.create(
            activity=activity, author=self.employee, date=timezone.now(),
            review_status="Pending",
        )
        Validation.objects.create(
            evidence=evidence, verifier=self.employee,
            decision="Approved", result="Approved", date=timezone.now(),
        )
        return activity

    def test_el_nombre_no_es_el_criterio(self):
        item = ActivityType.objects.create(
            code="COORD-PREP", name="Coordinación preparatoria",
            is_preparatory_coordination=False,
        )
        activity = self.make_approved_activity(item)
        self.assertTrue(activity_qualifies_for_goal(activity, lambda evidence: True))
        self.assertEqual(recalculate_indicator_for_goal(self.goal).actual_progress, Decimal("1"))

    def test_texto_preparatorio_no_clasifica_por_si_solo(self):
        item = ActivityType.objects.create(
            code="X-TEXTO", name="Coordinación preparatoria",
            is_preparatory_coordination=False,
        )
        activity = self.make_approved_activity(item)
        activity.action = "Reunión preparatoria de atención"
        activity.save(update_fields=["action", "updated_at"])
        self.assertTrue(activity_qualifies_for_goal(activity, lambda evidence: True))
        self.assertEqual(recalculate_indicator_for_goal(self.goal).actual_progress, Decimal("1"))

    def test_bandera_excluye_incluso_si_nombre_es_distinto(self):
        item = ActivityType.objects.create(
            code="X-001", name="Reunión técnica con vecinos",
            is_preparatory_coordination=True,
        )
        activity = self.make_approved_activity(item)
        self.assertFalse(activity_qualifies_for_goal(activity, lambda evidence: True))
        self.assertEqual(recalculate_indicator_for_goal(self.goal).actual_progress, Decimal("0"))
        item.name = "Preparación operativa renombrada"
        item.code = "X-RENOMBRADA"
        item.save()
        activity.refresh_from_db()
        self.assertEqual(recalculate_indicator_for_goal(self.goal).actual_progress, Decimal("0"))

    def test_modificar_clasificacion_recalcula_meta_activa(self):
        item = ActivityType.objects.create(
            code="V-001", name="Visita domiciliaria",
            is_preparatory_coordination=False,
        )
        self.make_approved_activity(item)
        self.assertEqual(recalculate_indicator_for_goal(self.goal).actual_progress, Decimal("1"))
        item.is_preparatory_coordination = True
        item.save()
        self.assertEqual(recalculate_indicator_for_goal(self.goal).actual_progress, Decimal("0"))
        item.is_preparatory_coordination = False
        item.save()
        self.assertEqual(recalculate_indicator_for_goal(self.goal).actual_progress, Decimal("1"))

    def test_formulario_acepta_casilla_y_la_muestra(self):
        form = ActivityTypeForm(data={
            "code": "PRUEBA-TIPO",
            "name": "Reunión previa",
            "description": "Previo a la atención",
            "status": "True",
            "is_preparatory_coordination": "on",
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.cleaned_data["is_preparatory_coordination"])
        self.assertIn("form-check-input", form.fields["is_preparatory_coordination"].widget.attrs.get("class", ""))

    def test_no_marcar_casilla_no_bloquea_creacion(self):
        form = ActivityTypeForm(data={
            "code": "PRUEBA-NORMAL", "name": "Atención presencial",
            "status": "True",
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(form.cleaned_data["is_preparatory_coordination"])
