"""Pruebas SGR: creador real del registro frente a funcionario, solicitante y verificador."""
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from accounts.models import UserProfile
from organization.models import Delegation, DelegationResponsibilityLog, Employee, PositionFunction
from planning_measurements.models import Goal, Period
from registration_validation.models import Activity, Evidence, Validation
from registration_validation.views import ActivityCreateView
from monitoring_traceability.services import recalculate_indicator_for_goal


class CreatorDelegateSGRTests(TestCase):
    def setUp(self):
        today = timezone.localdate()
        self.today = today
        self.delegation = Delegation.objects.create(
            name="Delegación municipal de prueba", status="Active", scope="Comunal",
        )
        self.position = PositionFunction.objects.create(
            position_name="Cargo de prueba", measurable_items="Atenciones",
            services="Atención", weightings="100%",
            validity_start=date(today.year - 1, 1, 1),
            validity_end=date(today.year + 1, 12, 31),
        )
        self.worker = Employee.objects.create(
            name="María ejemplo", delegation=self.delegation, position=self.position,
            status="Active", roles="Funcionaria",
        )
        self.delegate = Employee.objects.create(
            name="Marcos ejemplo", delegation=self.delegation, position=self.position,
            status="Active", roles="Delegado municipal",
        )
        self.delegation.responsible = self.delegate
        self.delegation.save(update_fields=["responsible", "updated_at"])
        self.period = Period.objects.create(
            start_date=date(today.year, 1, 1), end_date=date(today.year, 12, 31),
            computable_days=200, status="Active",
            thresholds="Verde: 100, Amarillo: 80, Rojo: 60, Tope: 120",
            parameters_version="v1",
        )
        self.goal = Goal.objects.create(
            period=self.period, employee=self.worker, position=self.position,
            item="Meta María", objective_value=2, weight=100,
            unit="unidades", required_evidence_count=2,
        )
        self.delegate_account = self._account("cuenta_delegado", self.delegate, "CUENTA-DEL-1")
        self.worker_account = self._account("cuenta_trabajadora", self.worker, "CUENTA-TRA-1")

    def _account(self, username, employee, code):
        user = get_user_model().objects.create_user(username=username, password="Demo-SGR-2026!")
        profile = UserProfile.objects.create(
            user=user, employee=employee, delegation=self.delegation, employee_code=code,
        )
        profile.authorized_delegations.add(self.delegation)
        return user

    def _activity(self, creator_employee=None, name="Pablo Cortés"):
        return Activity.objects.create(
            goal=self.goal, author=self.worker, date=self.today,
            contact=name, phone="999999999", action="Atención vecinal",
            request_problem="Solicitud de vecino",
            created_by_employee=creator_employee,
        )

    def _approve(self, activity, verifier=None):
        e = Evidence.objects.create(
            activity=activity, author=self.worker, review_status="Approved",
            date=timezone.now(),
        )
        Validation.objects.create(
            evidence=e, verifier=verifier or self.worker,
            decision="Approved", result="Approved", date=timezone.now(),
        )
        return e

    def test_creator_delegado_no_pondera_aunque_la_meta_sea_de_maria(self):
        activity = self._activity(self.delegate)
        self._approve(activity)
        indicator = recalculate_indicator_for_goal(self.goal)
        self.assertEqual(indicator.approved_evidences, 0)
        self.assertEqual(indicator.actual_progress, 0)

    def test_creador_maria_si_pondera_aunque_el_delegado_valide(self):
        activity = self._activity(self.worker)
        self._approve(activity, verifier=self.delegate)
        indicator = recalculate_indicator_for_goal(self.goal)
        self.assertEqual(indicator.approved_evidences, 1)
        self.assertEqual(indicator.actual_progress, 1)

    def test_solicitante_con_nombre_delegado_no_es_motivo_exclusion(self):
        activity = self._activity(self.worker, name=self.delegate.name)
        self._approve(activity)
        self.assertEqual(recalculate_indicator_for_goal(self.goal).approved_evidences, 1)

    def test_sin_creador_historico_no_inventa_identidad(self):
        activity = self._activity(creator_employee=None, name=self.delegate.name)
        self._approve(activity)
        self.assertEqual(recalculate_indicator_for_goal(self.goal).approved_evidences, 1)

    def test_creacion_desde_vista_guarda_cuenta_y_funcionario_autenticados(self):
        class FormStub:
            def __init__(self, instance):
                self.instance = instance
            def save(self):
                self.instance.save()
                return self.instance

        activity = Activity(
            goal=self.goal, author=self.worker, date=self.today,
            contact="Vecino", phone="999999999",
            request_problem="Solicitud", action="Atención",
        )
        view = ActivityCreateView()
        view.request = SimpleNamespace(user=self.delegate_account)
        with patch("registration_validation.views.messages.success"):
            response = view.form_valid(FormStub(activity))
        self.assertEqual(response.status_code, 302)
        activity.refresh_from_db()
        self.assertEqual(activity.created_by_user_id, self.delegate_account.pk)
        self.assertEqual(activity.created_by_employee_id, self.delegate.pk)
        self._approve(activity)
        self.assertEqual(recalculate_indicator_for_goal(self.goal).approved_evidences, 0)

    def test_cambio_de_responsable_posterior_no_rehabilita_actividad(self):
        activity = self._activity(self.delegate)
        self._approve(activity)
        DelegationResponsibilityLog.objects.create(
            delegation=self.delegation,
            previous_responsible=self.delegate,
            new_responsible=None,
            changed_by=self.worker_account,
        )
        self.delegation.responsible = None
        self.delegation.save(update_fields=["responsible", "updated_at"])
        self.assertEqual(recalculate_indicator_for_goal(self.goal).approved_evidences, 0)

    def test_designacion_posterior_no_anula_actividad_previa(self):
        self.delegation.responsible = None
        self.delegation.save(update_fields=["responsible", "updated_at"])
        activity = self._activity(self.delegate)
        self._approve(activity)
        DelegationResponsibilityLog.objects.create(
            delegation=self.delegation,
            previous_responsible=None,
            new_responsible=self.delegate,
            changed_by=self.worker_account,
        )
        self.delegation.responsible = self.delegate
        self.delegation.save(update_fields=["responsible", "updated_at"])
        self.assertEqual(recalculate_indicator_for_goal(self.goal).approved_evidences, 1)
