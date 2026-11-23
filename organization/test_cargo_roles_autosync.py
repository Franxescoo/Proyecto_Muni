"""Regresión para reparación segura de herencia Cargo -> Roles, sin superusuario."""
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

from accounts.models import UserProfile
from organization.models import Delegation, Employee, OrganizationRole, PositionFunction


class CargoRoleSelfSyncTests(TestCase):
    def setUp(self):
        self.delegation = Delegation.objects.create(
            name="Delegacion de prueba", status="Active", scope="Comunal",
        )
        self.position = PositionFunction.objects.create(
            position_name="Administrador de prueba",
            measurable_items="Gestion", services="Atencion", weightings="100%",
            validity_start=date(2026, 1, 1), validity_end=date(2027, 12, 31),
        )
        self.role = Group.objects.create(name="Rol administrador existente")
        OrganizationRole.objects.create(group=self.role)
        self.role.permissions.add(*Permission.objects.filter(
            content_type__app_label="organization",
            codename__in=["view_positionfunction", "change_positionfunction"],
        ))
        self.employee = Employee.objects.create(
            delegation=self.delegation, position=self.position,
            name="Operador autorizado", roles="Administrador", status="Active",
        )
        self.user = get_user_model().objects.create_user(
            username="cargo-autosync-admin", password="Test-password-7357!",
        )
        self.user.groups.add(self.role)
        self.profile = UserProfile.objects.create(
            user=self.user, employee=self.employee, delegation=self.delegation,
            employee_code="AUTOSYNC-01",
        )
        self.profile.authorized_delegations.add(self.delegation)
        self.client.force_login(self.user)

    def _post(self, role_ids):
        return self.client.post(reverse("organization:position_list"), {
            "action": "edit",
            "object_id": str(self.position.pk),
            "position_name": self.position.position_name,
            "role_groups": [str(i) for i in role_ids],
            "weightings": "100%",
            "validity_start": "2026-01-01",
            "validity_end": "2027-12-31",
        })

    def test_self_cargo_can_reconcile_roles_already_held_by_account(self):
        self.assertFalse(self.position.role_groups.exists())
        self.assertTrue(self.user.groups.filter(pk=self.role.pk).exists())
        response = self._post([self.role.pk])
        self.assertEqual(response.status_code, 302)
        self.position.refresh_from_db()
        self.assertEqual(
            set(self.position.role_groups.values_list("pk", flat=True)),
            {self.role.pk},
        )
        self.user.refresh_from_db()
        self.assertEqual(set(self.user.groups.values_list("pk", flat=True)), {self.role.pk})
        self.employee.refresh_from_db()
        self.assertEqual(set(self.employee.assigned_groups.values_list("pk", flat=True)), {self.role.pk})

    def test_self_cargo_cannot_add_other_role_even_with_same_permissions(self):
        other = Group.objects.create(name="Otro rol no poseido")
        OrganizationRole.objects.create(group=other)
        other.permissions.set(self.role.permissions.all())
        response = self._post([self.role.pk, other.pk])
        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.position.role_groups.exists())

    def test_self_cargo_cannot_replace_existing_role_with_unheld_role(self):
        other = Group.objects.create(name="Otro rol ajeno")
        OrganizationRole.objects.create(group=other)
        response = self._post([other.pk])
        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.position.role_groups.exists())

    def test_cargo_edit_without_role_change_does_not_trigger_self_block(self):
        self.position.role_groups.add(self.role)
        response = self._post([self.role.pk])
        self.assertEqual(response.status_code, 302)
