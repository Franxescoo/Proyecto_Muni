"""Regression tests for the SGR monitoring safeguards (temporary test DB only)."""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserProfile
from organization.models import Delegation, Employee, PositionFunction
from planning_measurements.models import Goal, Period
from registration_validation.models import Activity

from .forms import CommitmentForm
from .models import Audit, Commitment, CommitmentAlert, CommitmentReassignment, CommitmentStatusHistory, Indicator
from .services import synchronize_commitment_alerts


class CommitmentHardeningTests(TestCase):
    def setUp(self):
        self.north = Delegation.objects.create(name="Norte", status="Active", scope="Norte")
        self.south = Delegation.objects.create(name="Sur", status="Active", scope="Sur")
        self.position = PositionFunction.objects.create(
            position_name="Gestor", measurable_items="Gestión", services="Atención",
            weightings="100", validity_start=date(2026, 1, 1), validity_end=date(2027, 12, 31),
        )
        self.owner = Employee.objects.create(
            delegation=self.north, position=self.position, name="Original",
            roles="Gestor", status="Active",
        )
        self.replacement = Employee.objects.create(
            delegation=self.north, position=self.position, name="Reemplazo",
            roles="Gestor", status="Active",
        )
        self.outsider = Employee.objects.create(
            delegation=self.south, position=self.position, name="Ajeno",
            roles="Gestor", status="Active",
        )
        self.period = Period.objects.create(
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
            computable_days=250, thresholds="Verde: 100, Amarillo: 60", parameters_version="v1",
        )
        self.goal = Goal.objects.create(
            period=self.period, employee=self.owner, position=self.position,
            item="Atenciones", objective_value=10, weight=100, unit="units",
        )
        self.activity = Activity.objects.create(
            goal=self.goal, author=self.owner, date=date(2026, 6, 2),
            request_problem="Vecino", action="Orientación", contact="Vecino", phone="123",
        )
        self.user = get_user_model().objects.create_user(username="operador_m", password="aStrongPass123!")
        profile = UserProfile.objects.create(
            user=self.user, employee_code="M-HARD-1", employee=self.owner,
            delegation=self.north,
        )
        profile.authorized_delegations.add(self.north)
        self.path = reverse("monitoring:commitment_list")
        self.client.force_login(self.user)
        self.grant("view_commitment")

    def grant(self, *names):
        self.user.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="monitoring_traceability", codename__in=names,
        ))

    def commitment(self, *, overdue=False, status="Pending"):
        due_date = timezone.localdate() - timedelta(days=2) if overdue else timezone.localdate() + timedelta(days=15)
        return Commitment.objects.create(
            delegation=self.north, responsible=self.owner, activity=self.activity,
            requester="Vecino", origin="Atenciones", territory="Norte",
            commitment_date=due_date, status=status,
        )

    def test_create_and_edit_reject_view_only_user(self):
        commitment = self.commitment()
        self.assertEqual(self.client.get(self.path + "?open_modal=create").status_code, 403)
        self.assertEqual(self.client.post(self.path, {"action": "create_commitment"}).status_code, 403)
        self.assertEqual(self.client.get(self.path + f"?open_modal=edit&commitment_id={commitment.pk}").status_code, 403)
        self.assertEqual(self.client.post(self.path, {
            "action": "edit_commitment", "commitment_id": commitment.pk,
        }).status_code, 403)

    def test_normal_edit_is_forbidden_even_with_change_permission(self):
        # Tener permiso para cambiar el estado NO autoriza a editar el compromiso.
        self.grant("change_commitment")
        commitment = self.commitment()
        original_date = commitment.commitment_date
        original_observation = commitment.observation
        self.assertEqual(
            self.client.get(
                reverse("monitoring:commitment_edit", args=[commitment.pk])
            ).status_code, 403,
        )
        self.assertEqual(
            self.client.get(
                self.path + f"?open_modal=edit&commitment_id={commitment.pk}"
            ).status_code, 403,
        )
        response = self.client.post(self.path, {
            "action": "edit_commitment", "commitment_id": commitment.pk,
            "delegation": self.south.pk, "responsible": self.outsider.pk,
            "activity": "", "status": "Validated", "commitment_date": "2099-01-01",
            "territory": "Territorio ajustado", "observation": "Nueva observación",
        })
        self.assertEqual(response.status_code, 403)
        commitment.refresh_from_db()
        self.assertEqual(commitment.responsible_id, self.owner.pk)
        self.assertEqual(commitment.activity_id, self.activity.pk)
        self.assertEqual(commitment.delegation_id, self.north.pk)
        self.assertEqual(commitment.commitment_date, original_date)
        self.assertEqual(commitment.status, "Pending")
        self.assertEqual(commitment.territory, "Norte")
        self.assertEqual(commitment.observation, original_observation)
        self.assertFalse(commitment.reassignments.exists())

    def test_non_overdue_active_no_reassign_but_inactive_yes(self):
        self.grant("change_commitment")
        commitment = self.commitment()
        uri = self.path + f"?open_modal=reassign&commitment_id={commitment.pk}"
        self.assertEqual(self.client.get(uri).status_code, 403)
        denied = self.client.post(self.path, {
            "action": "reassign", "commitment_id": commitment.pk,
            "cause": "absence", "responsible": self.replacement.pk,
            "reason": "No hay licencia registrada",
        })
        self.assertEqual(denied.status_code, 403)
        self.assertFalse(commitment.reassignments.exists())
        self.owner.status = "Inactive"
        self.owner.save(update_fields=["status", "updated_at"])
        commitment.refresh_from_db()
        self.assertEqual(self.client.get(uri).status_code, 200)
        response = self.client.post(self.path, {
            "action": "reassign", "commitment_id": commitment.pk,
            "cause": "absence", "responsible": self.replacement.pk,
            "reason": "Funcionario inactivo, queda encargado el reemplazo",
        })
        self.assertEqual(response.status_code, 302)
        commitment.refresh_from_db()
        self.assertEqual(commitment.responsible_id, self.replacement.pk)
        entry = CommitmentReassignment.objects.get(commitment=commitment)
        self.assertEqual(entry.changed_by_id, self.user.pk)
        self.assertIn("Ausencia del funcionario", entry.reason)

    def test_overdue_reassignment_is_logged_atomically(self):
        self.grant("change_commitment")
        commitment = self.commitment(overdue=True)
        response = self.client.post(self.path, {
            "action": "reassign", "commitment_id": commitment.pk,
            "cause": "overdue", "responsible": self.replacement.pk,
            "reason": "Compromiso vencido y sin completar",
        })
        self.assertEqual(response.status_code, 302)
        commitment.refresh_from_db()
        self.assertEqual(commitment.responsible_id, self.replacement.pk)
        entry = CommitmentReassignment.objects.get(commitment=commitment)
        self.assertEqual(entry.previous_responsible_id, self.owner.pk)
        self.assertEqual(entry.new_responsible_id, self.replacement.pk)
        self.assertEqual(entry.changed_by_id, self.user.pk)
        self.assertIn("Compromiso vencido", entry.reason)

    def test_cross_delegation_reassignment_is_not_accepted(self):
        self.grant("change_commitment")
        commitment = self.commitment(overdue=True)
        response = self.client.post(self.path, {
            "action": "reassign", "commitment_id": commitment.pk,
            "cause": "overdue", "responsible": self.outsider.pk,
            "reason": "Intento ajeno",
        })
        self.assertEqual(response.status_code, 200)
        commitment.refresh_from_db()
        self.assertEqual(commitment.responsible_id, self.owner.pk)
        self.assertFalse(commitment.reassignments.exists())

    def test_new_commitment_can_keep_manual_date_or_default(self):
        shared = {
            "delegation": self.north.pk, "activity": self.activity.pk,
            "territory": "Lugar acordado", "observation": "Test",
        }
        qs = Activity.objects.filter(pk=self.activity.pk)
        form = CommitmentForm(
            {**shared, "commitment_date": "2026-12-05"},
            employees=Employee.objects.filter(pk=self.owner.pk),
            delegations=Delegation.objects.filter(pk=self.north.pk), activities=qs,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["commitment_date"], date(2026, 12, 5))
        self.assertEqual(form.cleaned_data["status"], "Pending")
        blank_form = CommitmentForm(
            shared,
            employees=Employee.objects.filter(pk=self.owner.pk),
            delegations=Delegation.objects.filter(pk=self.north.pk), activities=qs,
        )
        self.assertTrue(blank_form.is_valid(), blank_form.errors)
        self.assertEqual(blank_form.cleaned_data["commitment_date"], self.period.end_date)

    def test_changing_status_from_view_records_history(self):
        self.grant("change_commitment")
        commitment = self.commitment()
        res = self.client.post(self.path, {
            "action": "status", "commitment_id": commitment.pk,
            "status": "In progress", "observation": "En gestión",
        })
        self.assertEqual(res.status_code, 302)
        commitment.refresh_from_db()
        self.assertEqual(commitment.status, "In progress")
        history = CommitmentStatusHistory.objects.filter(commitment=commitment).first()
        self.assertEqual(history.observation, "En gestión")
        self.assertEqual(history.changed_by_id, self.user.pk)

    def test_status_filter_and_export_use_commitment_status(self):
        self.commitment(status="In progress")
        res = self.client.get(self.path + "?status=In+progress")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context["commitments"].count(), 1)
        export = self.client.get(reverse("monitoring:commitment_export") + "?status=In+progress")
        self.assertEqual(export.status_code, 200)

    def test_cancelled_commitment_does_not_raise_overdue_alert(self):
        commitment = self.commitment(overdue=True, status="Cancelled")
        self.assertFalse(commitment.is_overdue)
        synchronize_commitment_alerts([commitment])
        self.assertFalse(CommitmentAlert.objects.filter(
            commitment=commitment, resolved_at__isnull=True,
        ).exists())

    def test_adjustment_requires_reason_and_tracks_change(self):
        self.grant("view_indicator", "change_indicator")
        indicator = Indicator.objects.filter(goal=self.goal).first()
        if indicator is None:
            from .services import recalculate_indicator_for_goal
            indicator = recalculate_indicator_for_goal(self.goal)
        url = reverse("monitoring:indicator_list")
        self.client.post(url, {"indicator_id": indicator.pk, "adjustment": "12"})
        indicator.refresh_from_db()
        self.assertEqual(indicator.adjustment, 0)
        self.client.post(url, {
            "indicator_id": indicator.pk, "adjustment": "12",
            "reason": "Ajuste aprobado por revisión",
        })
        indicator.refresh_from_db()
        self.assertEqual(indicator.adjustment, Decimal("12"))
        audit = Audit.objects.filter(entity="Indicator", object_identifier=str(indicator.pk), event="Adjusted Indicator").first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.new_value["reason"], "Ajuste aprobado por revisión")
        self.assertEqual(audit.new_value["editado_por"], self.user.username)
