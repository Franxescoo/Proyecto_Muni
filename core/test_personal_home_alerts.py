"""Inicio: las alertas no se filtran por la delegación completa."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserProfile
from monitoring_traceability.models import Commitment
from organization.models import Delegation, Employee, PositionFunction


class PersonalHomeAlertsTests(TestCase):
    def setUp(self):
        delegation = Delegation.objects.create(
            name="Pruebas Inicio", status="Active", scope="Sector prueba",
        )
        position = PositionFunction.objects.create(
            position_name="Gestor de inicio", measurable_items="Atención",
            services="Municipal", weightings="100",
            validity_start=timezone.localdate() - timedelta(days=30),
            validity_end=timezone.localdate() + timedelta(days=360),
        )
        self.owner = Employee.objects.create(
            delegation=delegation, position=position, name="Funcionario titular",
            roles="Gestor", status="Active",
        )
        self.other = Employee.objects.create(
            delegation=delegation, position=position, name="Compañero",
            roles="Gestor", status="Active",
        )
        self.user = get_user_model().objects.create_user(
            username="personal_inicio", password="demoPassword123",
        )
        self.profile = UserProfile.objects.create(
            user=self.user, employee_code="PERSONAL-INICIO-01",
            delegation=delegation, employee=self.owner,
        )
        self.profile.authorized_delegations.add(delegation)
        self.client.force_login(self.user)
        self.companion_commitment = Commitment.objects.create(
            delegation=delegation, responsible=self.other,
            origin="Aviso exclusivo compañero", requester="Vecino",
            territory="Centro", commitment_date=timezone.localdate() - timedelta(days=2),
            status="Pending",
        )

    def grant(self, *codes):
        self.user.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="monitoring_traceability", codename__in=codes,
        ))

    def test_does_not_show_colleague_alert_with_same_delegation(self):
        self.grant("view_commitment")
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["personal_alerts"])
        self.assertNotContains(response, "Aviso exclusivo compañero")

    def test_shows_only_own_commitment(self):
        self.grant("view_commitment")
        Commitment.objects.create(
            delegation=self.owner.delegation, responsible=self.owner,
            origin="Reparación que me corresponde", requester="Vecino",
            territory="Centro", commitment_date=timezone.localdate() - timedelta(days=1),
            status="Pending",
        )
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Mis alertas de seguimiento")
        self.assertContains(response, "Reparación que me corresponde")
        self.assertNotContains(response, "Aviso exclusivo compañero")
        self.assertEqual(response.context["personal_alerts"][0]["count"], 1)
        self.assertTrue(response.context["has_personal_alerts"])

    def test_without_read_permission_hides_own_commitment(self):
        Commitment.objects.create(
            delegation=self.owner.delegation, responsible=self.owner,
            origin="Compromiso sin permiso", requester="Vecino",
            territory="Centro", commitment_date=timezone.localdate() - timedelta(days=1),
            status="Pending",
        )
        response = self.client.get(reverse("home"))
        self.assertFalse(response.context["personal_alerts"])
        self.assertNotContains(response, "Compromiso sin permiso")

    def test_account_without_employee_does_not_inherit_delegation_alerts(self):
        self.grant("view_commitment")
        self.profile.employee = None
        self.profile.save(update_fields=["employee"])
        response = self.client.get(reverse("home"))
        self.assertFalse(response.context["personal_alerts"])
        self.assertNotContains(response, "Aviso exclusivo compañero")

    def test_completed_commitment_does_not_remain_personal_alert(self):
        self.grant("view_commitment")
        Commitment.objects.create(
            delegation=self.owner.delegation, responsible=self.owner,
            origin="Caso finalizado", requester="Vecino",
            territory="Centro", commitment_date=timezone.localdate() - timedelta(days=1),
            status="Completed",
        )
        response = self.client.get(reverse("home"))
        self.assertFalse(response.context["personal_alerts"])
        self.assertNotContains(response, "Caso finalizado")
