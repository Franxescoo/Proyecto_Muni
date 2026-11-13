"""Pruebas de permisos reales heredados de cargos, sin superusuario."""
from datetime import date
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.test import TestCase
from accounts.models import UserProfile
from accounts.services import sync_employee, sync_position, sync_user_groups
from organization.models import Delegation, Employee, OrganizationRole, PositionFunction


class CargoRoleInheritanceTests(TestCase):
    def setUp(self):
        self.delegation = Delegation.objects.create(name="Centro", status="Active", scope="Urbano")
        self.other_delegation = Delegation.objects.create(name="Sur", status="Active", scope="Rural")
        self.role_a = self.make_role("Funcionario", self.delegation)
        self.role_b = self.make_role("Evaluador", self.delegation)
        self.position_a = self.make_position("Atención")
        self.position_a.role_groups.add(self.role_a)
        self.position_b = self.make_position("Coordinación")
        self.position_b.role_groups.add(self.role_b)
        self.employee = Employee.objects.create(
            name="Funcionario prueba", delegation=self.delegation,
            position=self.position_a, roles="Atención de solicitudes", status="Active",
        )
        self.user = get_user_model().objects.create_user(username="empleado_prueba", password="test-only-password")
        self.profile = UserProfile.objects.create(
            user=self.user, employee=self.employee, employee_code="EMP-TEST-01",
            delegation=self.delegation,
        )
        self.profile.authorized_delegations.add(self.delegation)

    def make_role(self, name, delegation):
        group = Group.objects.create(name=name)
        role = OrganizationRole.objects.create(group=group, delegation=delegation, description=name)
        role.application_delegations.add(delegation)
        return group

    def make_position(self, name):
        return PositionFunction.objects.create(
            position_name=name, measurable_items="Atenciones", services="Atención",
            weightings="100%", validity_start=date(2026, 1, 1),
            validity_end=date(2027, 12, 31),
        )

    def test_initial_role_is_taken_from_position_not_user(self):
        self.user.groups.set([self.role_b])
        sync_user_groups(self.user)
        self.assertEqual(set(self.user.groups.all()), {self.role_a})
        self.assertEqual(set(self.employee.assigned_groups.all()), {self.role_a})

    def test_changing_position_revokes_previous_roles(self):
        sync_employee(self.employee)
        self.employee.position = self.position_b
        self.employee.save(update_fields=["position", "updated_at"])
        sync_employee(self.employee)
        self.assertEqual(set(self.user.groups.all()), {self.role_b})
        self.assertEqual(set(self.employee.assigned_groups.all()), {self.role_b})

    def test_changing_position_roles_updates_linked_employee(self):
        sync_employee(self.employee)
        self.position_a.role_groups.set([self.role_b])
        sync_position(self.position_a)
        self.assertEqual(set(self.user.groups.all()), {self.role_b})

    def test_direct_permissions_are_revoked(self):
        content_type = ContentType.objects.get_for_model(Employee)
        permission, _ = Permission.objects.get_or_create(
            content_type=content_type, codename="test_direct_perm",
            defaults={"name": "Test direct permission"},
        )
        self.user.user_permissions.add(permission)
        sync_employee(self.employee)
        self.assertFalse(self.user.user_permissions.exists())

    def test_role_is_not_restricted_by_legacy_delegation_scope(self):
        foreign_role = self.make_role("Rol institucional", self.other_delegation)
        self.position_a.role_groups.set([foreign_role])
        sync_employee(self.employee)
        self.assertEqual(set(self.user.groups.all()), {foreign_role})

    def test_employee_primary_delegation_must_be_authorized(self):
        self.profile.authorized_delegations.clear()
        self.profile.authorized_delegations.add(self.other_delegation)
        with self.assertRaises(ValidationError):
            sync_employee(self.employee)

    def test_permissions_only_apply_in_user_authorized_delegations(self):
        from accounts.permissions import allowed_delegation_ids
        permission = Permission.objects.get(
            content_type__app_label="organization", codename="view_employee"
        )
        self.role_a.permissions.add(permission)
        self.role_a.organization_role.application_delegations.set([self.other_delegation])
        sync_employee(self.employee)
        self.assertEqual(
            allowed_delegation_ids(
                self.user, "organization.view_employee", active_only=False
            ),
            {self.delegation.pk},
        )

    def test_inactive_employee_loses_roles(self):
        sync_employee(self.employee)
        self.employee.status = "Inactive"
        self.employee.save(update_fields=["status", "updated_at"])
        sync_employee(self.employee)
        self.assertFalse(self.user.groups.exists())
