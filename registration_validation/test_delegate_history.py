"""Regresiones de responsable histórico de delegación (no superusuarios)."""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from organization.models import (
    Delegation, DelegationResponsibilityLog, Employee, PositionFunction,
)
from planning_measurements.models import Goal, Period
from registration_validation.models import Activity, Evidence, Validation
from monitoring_traceability.services import recalculate_indicator_for_goal
from registration_validation.test_resolved_attention_support import link_resolved_attention


class DelegateHistoricalAttributionTests(TestCase):
    def setUp(self):
        today = timezone.localdate()
        self.today = today
        self.delegation = Delegation.objects.create(
            name="Delegacion historica", status="Active", scope="Comunal",
        )
        self.position = PositionFunction.objects.create(
            position_name="Cargo de prueba historica",
            measurable_items="Atenciones", services="Atencion", weightings="100%",
            validity_start=date(today.year - 1, 1, 1),
            validity_end=date(today.year + 1, 12, 31),
        )
        self.worker = Employee.objects.create(
            name="Funcionaria de prueba", roles="Gestion", status="Active",
            delegation=self.delegation, position=self.position,
        )
        self.delegate = Employee.objects.create(
            name="Responsable historico", roles="Direccion", status="Active",
            delegation=self.delegation, position=self.position,
        )
        self.other_delegate = Employee.objects.create(
            name="Responsable reemplazante", roles="Direccion", status="Active",
            delegation=self.delegation, position=self.position,
        )
        self.user = get_user_model().objects.create_user(
            username="auditor-delegaciones-prueba", password="Test-Password-791!",
        )
        self.period = Period.objects.create(
            start_date=date(today.year, 1, 1),
            end_date=date(today.year, 12, 31),
            computable_days=200, status="Active",
            thresholds="Verde: 100, Amarillo: 80, Rojo: 60, Tope: 120",
            parameters_version="v1",
        )
        self.goal = Goal.objects.create(
            period=self.period, employee=self.worker, position=self.position,
            item="Meta responsable historico", objective_value=1,
            weight=100, unit="unidades", required_evidence_count=1,
        )

    def activity(self, *, day=None, contact=None, action="Atencion vecinal",
                 registered_by=None):
        activity = Activity.objects.create(
            goal=self.goal, author=self.worker, date=day or self.today,
            contact=contact or self.delegate.name, phone="999999999",
            action=action, request_problem="Consulta registrada",
            created_by_employee=registered_by,
        )
        link_resolved_attention(activity)
        return activity

    def approve(self, activity, *, verifier=None, formal=False):
        evidence = Evidence.objects.create(
            activity=activity, author=self.worker, date=timezone.now(),
            review_status="Approved",
            file_link="https://example.test/respaldo.pdf" if formal else "",
        )
        Validation.objects.create(
            evidence=evidence, verifier=verifier or self.worker,
            decision="Approved", result="Approved", date=timezone.now(),
        )
        return evidence

    def change_responsible(self, from_employee, to_employee, *, days_ago=None):
        record = DelegationResponsibilityLog.objects.create(
            delegation=self.delegation,
            previous_responsible=from_employee, new_responsible=to_employee,
            changed_by=self.user,
        )
        if days_ago is not None:
            instant = timezone.now() - timedelta(days=days_ago)
            DelegationResponsibilityLog.objects.filter(pk=record.pk).update(
                changed_at=instant,
            )
            record.refresh_from_db()
        self.delegation.responsible = to_employee
        self.delegation.save(update_fields=["responsible", "updated_at"])
        return record

    def test_existing_activity_remains_counted_after_new_delegate_assignment(self):
        activity = self.activity(day=self.today - timedelta(days=3))
        self.approve(activity)
        self.change_responsible(None, self.delegate)
        indicator = recalculate_indicator_for_goal(self.goal)
        self.assertEqual(indicator.approved_evidences, 1)
        self.assertEqual(indicator.actual_progress, 1)

    def test_delegate_requester_on_historical_day_remains_excluded_after_removal(self):
        self.change_responsible(None, self.delegate, days_ago=4)
        activity = self.activity(day=self.today - timedelta(days=2), registered_by=self.delegate)
        self.approve(activity)
        self.change_responsible(self.delegate, None)
        indicator = recalculate_indicator_for_goal(self.goal)
        self.assertEqual(indicator.approved_evidences, 0)
        self.assertEqual(indicator.actual_progress, 0)

    def test_former_delegate_requester_can_count_after_replacement(self):
        self.change_responsible(None, self.delegate, days_ago=5)
        self.change_responsible(self.delegate, self.other_delegate, days_ago=2)
        activity = self.activity(day=self.today, contact=self.delegate.name, registered_by=self.delegate)
        self.approve(activity)
        indicator = recalculate_indicator_for_goal(self.goal)
        self.assertEqual(indicator.actual_progress, 1)

    def test_direct_assignment_without_history_preserves_legacy_behavior(self):
        self.delegation.responsible = self.delegate
        self.delegation.save(update_fields=["responsible", "updated_at"])
        activity = self.activity(registered_by=self.delegate)
        self.approve(activity)
        self.assertEqual(recalculate_indicator_for_goal(self.goal).actual_progress, 0)

    def test_same_day_assignment_after_registration_does_not_rewrite_activity(self):
        activity = self.activity(day=self.today, registered_by=self.delegate)
        self.approve(activity)
        self.change_responsible(None, self.delegate)
        self.assertEqual(recalculate_indicator_for_goal(self.goal).actual_progress, 1)

    def test_formal_congratulation_stays_approved_after_delegate_change(self):
        from accounts.models import UserProfile
        from registration_validation.forms import ValidationForm
        from registration_validation.models import ActivityType
        self.change_responsible(None, self.delegate, days_ago=2)
        profile = UserProfile.objects.create(
            user=self.user, employee=self.delegate,
            employee_code="HIST-RESP-DELEGADO", delegation=self.delegation,
        )
        profile.authorized_delegations.add(self.delegation)
        from django.contrib.auth.models import Permission
        self.user.user_permissions.add(Permission.objects.get(
            content_type__app_label="registration_validation",
            codename="add_validation",
        ))
        kind = ActivityType.objects.create(
            code="HIST-FELIC", name="Reconocimiento", is_congratulation=True,
        )
        activity = Activity.objects.create(
            goal=self.goal, author=self.worker, date=self.today,
            contact="Vecina de prueba", phone="999999999", activity_type=kind,
            action="Reconocimiento vecinal", request_problem="Carta de felicitación",
        )
        link_resolved_attention(activity)
        evidence = Evidence.objects.create(
            activity=activity, author=self.worker, date=timezone.now(),
            review_status="Pending", file_link="https://example.test/respaldo.pdf",
        )
        form = ValidationForm(data={
            "evidence": evidence.pk, "verifier": self.delegate.pk,
            "decision": "Approved", "result": "Approved", "version": "1",
            "observation": "Documento revisado y refrendado por delegado",
            "formal_delegate_endorsement": "on",
        }, user=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        approval = form.save(commit=False)
        approval.date = timezone.now()
        approval.save()
        self.change_responsible(self.delegate, None)
        self.assertEqual(recalculate_indicator_for_goal(self.goal).actual_progress, 1)
