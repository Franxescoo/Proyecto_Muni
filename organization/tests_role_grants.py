"""Regresión de RNF-005: no conceder permisos superiores desde Roles y Permisos."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase

from organization.forms import OrganizationRoleForm


class RoleGrantSecurityTests(TestCase):
    def setUp(self):
        self.view_employee = Permission.objects.get(
            content_type__app_label="organization", codename="view_employee"
        )
        self.delete_employee = Permission.objects.get(
            content_type__app_label="organization", codename="delete_employee"
        )
        self.actor = get_user_model().objects.create_user(
            username="gestor_limitado", password="clave-de-prueba"
        )
        self.actor_group = Group.objects.create(name="Gestores limitados")
        self.actor_group.permissions.add(self.view_employee)
        self.actor.groups.add(self.actor_group)

    def payload(self, *permissions, name="Rol de consulta"):
        return {
            "name": name,
            "description": "Rol de prueba con permisos controlados.",
            "permissions": [str(permission.pk) for permission in permissions],
        }

    def test_only_authorized_permissions_are_visible(self):
        form = OrganizationRoleForm(actor=self.actor)
        ids = set(form.fields["permissions"].queryset.values_list("pk", flat=True))
        self.assertIn(self.view_employee.pk, ids)
        self.assertNotIn(self.delete_employee.pk, ids)

    def test_tampered_post_cannot_grant_forbidden_permission(self):
        form = OrganizationRoleForm(
            self.payload(self.view_employee, self.delete_employee), actor=self.actor
        )
        self.assertFalse(form.is_valid())
        self.assertIn("permissions", form.errors)
        self.assertFalse(Group.objects.filter(name="Rol de consulta").exists())

    def test_authorized_grant_is_saved(self):
        form = OrganizationRoleForm(
            self.payload(self.view_employee), actor=self.actor
        )
        self.assertTrue(form.is_valid(), form.errors.as_text())
        new_group = form.save()
        self.assertEqual(
            set(new_group.permissions.values_list("pk", flat=True)),
            {self.view_employee.pk},
        )

    def test_existing_privileged_role_cannot_be_edited_by_limited_admin(self):
        protected = Group.objects.create(name="Rol protegido")
        protected.permissions.add(self.view_employee, self.delete_employee)
        form = OrganizationRoleForm(
            self.payload(self.view_employee, name="Rol protegido actualizado"),
            group=protected,
            actor=self.actor,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("fuera de tu autorización", form.errors.as_text())
        self.assertEqual(protected.name, "Rol protegido")
        self.assertEqual(protected.permissions.count(), 2)

    def test_authorized_admin_can_manage_both_permissions(self):
        self.actor_group.permissions.add(self.delete_employee)
        # Permisos de Django pueden cachearse; usar instancia actualizada.
        self.actor = get_user_model().objects.get(pk=self.actor.pk)
        form = OrganizationRoleForm(
            self.payload(self.view_employee, self.delete_employee), actor=self.actor
        )
        self.assertTrue(form.is_valid(), form.errors.as_text())
        new_group = form.save()
        self.assertEqual(new_group.permissions.count(), 2)
