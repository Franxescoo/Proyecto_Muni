
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.forms import AccountCreateForm, AccountEditForm
from accounts.permission_audit import direct_permission_inventory
from accounts.models import UserProfile
from organization.models import (
    Delegation,
    Employee,
    OrganizationRole,
    PositionFunction,
)


class AccountTests(TestCase):

    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username="admin_accounts",
            password="Admin-Test-9271!",
        )
        self.client.force_login(self.admin)

        self.delegation = Delegation.objects.create(
            name="Delegación de Prueba",
            scope="Urbano",
            status="Active",
        )

        self.position = PositionFunction.objects.create(
            position_name="Analista de prueba",
            measurable_items="Informes",
            services="Gestión",
            weightings="100%",
            validity_start=date(2026, 1, 1),
            validity_end=date(2026, 12, 31),
        )

        self.employee = Employee.objects.create(
            name="Funcionario de Prueba",
            delegation=self.delegation,
            position=self.position,
            roles="Análisis",
            status="Active",
        )

        self.role = Group.objects.create(
            name="Rol de prueba"
        )
        OrganizationRole.objects.create(
            group=self.role,
            delegation=self.delegation,
        )

        self.employee.assigned_groups.add(self.role)

        self.create_url = reverse("accounts:account_create")
        self.home_url = reverse("accounts:access_home")

    def account_data(self, **changes):
        data = {
            "username": "usuario_prueba",
            "email": "usuario@example.com",
            "employee": self.employee.pk,
            "employee_code": "ACC-TEST-001",
            "authorized_delegations": [self.delegation.pk],
            "groups": [self.role.pk],
            "password1": "Clave-Segura-9271!",
            "password2": "Clave-Segura-9271!",
        }
        data.update(changes)
        return data

    def create_account(self):
        response = self.client.post(
            self.create_url,
            self.account_data(),
        )

        self.assertRedirects(response, self.home_url)

        return get_user_model().objects.get(
            username="usuario_prueba"
        )

    def test_create_form_allows_roles_and_delegations(self):
        form = AccountCreateForm()

        self.assertIn("groups", form.fields)
        self.assertIn("authorized_delegations", form.fields)
        self.assertIn("employee", form.fields)
        self.assertIn("username", form.fields)

    def test_edit_form_allows_roles_and_delegations(self):
        user = get_user_model().objects.create_user(
            username="usuario_editar_formulario",
            password="Clave-Segura-9271!",
        )

        form = AccountEditForm(instance=user)

        self.assertIn("groups", form.fields)
        self.assertIn("authorized_delegations", form.fields)
        self.assertIn("username", form.fields)
        self.assertIn("email", form.fields)
        self.assertIn("is_active", form.fields)

    def test_user_cannot_change_own_roles_from_account_form(self):
        user = self.create_account()
        other_role = Group.objects.create(name="Otro rol")
        form = AccountEditForm(
            data={
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email,
                "is_active": "on",
                "employee": user.profile.employee_id,
                "employee_code": user.profile.employee_code,
                "authorized_delegations": [self.delegation.pk],
                "groups": [self.role.pk, other_role.pk],
            },
            instance=user,
            actor=user,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("groups", form.errors)

    def test_user_form_does_not_assign_individual_permissions(self):
        user = self.create_account()
        special = Permission.objects.get(
            content_type__app_label="planning_measurements",
            codename="delete_closed_period",
        )
        user.user_permissions.add(special)

        form = AccountEditForm(instance=user, actor=self.admin)
        self.assertNotIn("can_delete_closed_period", form.fields)
        self.assertNotIn("can_delete_closed_period_inherited", form.fields)

        form = AccountEditForm(
            data={
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email,
                "is_active": "on",
                "employee": user.profile.employee_id,
                "employee_code": user.profile.employee_code,
                "authorized_delegations": [self.delegation.pk],
                "groups": [self.role.pk],
            },
            instance=user,
            actor=self.admin,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        user.refresh_from_db()

        self.assertTrue(user.user_permissions.filter(pk=special.pk).exists())

    def test_role_permissions_are_inherited_by_user(self):
        user = self.create_account()
        special = Permission.objects.get(
            content_type__app_label="planning_measurements",
            codename="delete_closed_period",
        )
        self.role.permissions.add(special)

        user.refresh_from_db()

        self.assertTrue(user.has_perm("planning_measurements.delete_closed_period"))

    def test_direct_permission_inventory_identifies_uncovered_permissions(self):
        user = self.create_account()
        special = Permission.objects.get(
            content_type__app_label="planning_measurements",
            codename="delete_closed_period",
        )
        user.user_permissions.add(special)

        rows = direct_permission_inventory(get_user_model())

        row = next(
            item for item in rows
            if item["username"] == user.username
            and item["direct_permission"]
            == "planning_measurements.delete_closed_period"
        )
        self.assertFalse(row["covered_by_role"])
        self.assertEqual(row["roles"], [self.role.name])

    def test_direct_permission_audit_command_is_read_only(self):
        user = self.create_account()
        special = Permission.objects.get(
            content_type__app_label="planning_measurements",
            codename="delete_closed_period",
        )
        user.user_permissions.add(special)

        from io import StringIO

        output = StringIO()
        call_command("audit_direct_permissions", stdout=output)

        self.assertIn(user.username, output.getvalue())
        user.refresh_from_db()
        self.assertTrue(user.user_permissions.filter(pk=special.pk).exists())

    def test_create_account_inherits_employee_roles(self):
        user = self.create_account()

        self.assertEqual(
            user.profile.employee_id,
            self.employee.pk,
        )
        self.assertEqual(
            user.profile.delegation_id,
            self.delegation.pk,
        )
        self.assertIn(
            self.role,
            user.groups.all(),
        )

        self.assertFalse(user.is_superuser)
        self.assertFalse(user.is_staff)
        self.assertTrue(user.is_active)

    def test_new_user_password_is_secure(self):
        user = self.create_account()

        self.assertTrue(
            user.check_password("Clave-Segura-9271!")
        )
        self.assertNotEqual(
            user.password,
            "Clave-Segura-9271!",
        )

    def test_create_account_rejects_role_without_organization_scope(self):
        other_role = Group.objects.create(name="Rol no autorizado")
        response = self.client.post(
            self.create_url, self.account_data(groups=[other_role.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("groups", response.context["form"].errors)
        self.assertFalse(get_user_model().objects.filter(username="usuario_prueba").exists())

    def test_invalid_password_confirmation_prevents_creation(self):
        response = self.client.post(
            self.create_url,
            self.account_data(
                password2="Clave-Diferente-9271!"
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "password2",
            response.context["form"].errors,
        )

        self.assertFalse(
            get_user_model().objects.filter(
                username="usuario_prueba"
            ).exists()
        )

    def test_account_edit_rejects_role_outside_authorized_scope(self):
        user = self.create_account()
        unauthorized = Group.objects.create(name="Rol enviado manualmente")
        edit_url = reverse("accounts:account_edit", args=[user.pk])
        payload = {
            "username": user.username,
            "email": "nuevo_correo@example.com",
            "is_active": "on",
            "employee": self.employee.pk,
            "employee_code": "ACC-TEST-001",
            "authorized_delegations": [self.delegation.pk],
            "groups": [unauthorized.pk],
        }
        response = self.client.post(edit_url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertIn("groups", response.context["form"].errors)
        user.refresh_from_db()
        self.assertNotEqual(user.email, payload["email"])
        self.assertNotIn(unauthorized, user.groups.all())
        payload["groups"] = [self.role.pk]
        response = self.client.post(edit_url, payload)
        self.assertRedirects(response, self.home_url)
        user.refresh_from_db()
        self.assertEqual(user.email, payload["email"])
        self.assertIn(self.role, user.groups.all())
        self.assertIn(self.role, self.employee.assigned_groups.all())

    def test_inactive_account_cannot_login(self):
        user = self.create_account()

        edit_url = reverse(
            "accounts:account_edit",
            args=[user.pk],
        )

        response = self.client.post(
            edit_url,
            {
                "username": user.username,
                "email": user.email,
                "employee": self.employee.pk,
                "employee_code": "ACC-TEST-001",
                "authorized_delegations": [self.delegation.pk],
                "groups": [self.role.pk],
            },
        )

        self.assertRedirects(response, self.home_url)

        user.refresh_from_db()
        self.assertFalse(user.is_active)

        self.client.logout()

        logged_in = self.client.login(
            username="usuario_prueba",
            password="Clave-Segura-9271!",
        )

        self.assertFalse(logged_in)

    def test_deleted_account_cannot_be_edited(self):
        user = self.create_account()

        user.is_active = False
        user.save(update_fields=["is_active"])

        profile = user.profile
        profile.deleted_at = timezone.now()
        profile.save(update_fields=["deleted_at"])

        edit_url = reverse(
            "accounts:account_edit",
            args=[user.pk],
        )

        response = self.client.get(edit_url)

        self.assertEqual(response.status_code, 404)

        response = self.client.post(
            edit_url,
            {
                "username": user.username,
                "email": "reactivado@example.com",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 404)

        user.refresh_from_db()
        self.assertFalse(user.is_active)

        profile.refresh_from_db()
        self.assertIsNotNone(profile.deleted_at)
