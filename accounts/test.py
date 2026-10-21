
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.forms import AccountCreateForm, AccountEditForm
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

    def test_create_account_cannot_assign_roles_manually(self):
        other_role = Group.objects.create(
            name="Rol no autorizado"
        )

        response = self.client.post(
            self.create_url,
            self.account_data(
                groups=[other_role.pk]
            ),
        )

        self.assertRedirects(response, self.home_url)

        user = get_user_model().objects.get(
            username="usuario_prueba"
        )

        self.assertIn(self.role, user.groups.all())
        self.assertNotIn(other_role, user.groups.all())

        self.assertNotIn(
            other_role,
            self.employee.assigned_groups.all(),
        )

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

    def test_account_edit_updates_data_without_changing_roles(self):
        user = self.create_account()

        other_role = Group.objects.create(
            name="Rol enviado manualmente"
        )

        edit_url = reverse(
            "accounts:account_edit",
            args=[user.pk],
        )

        response = self.client.post(
            edit_url,
            {
                "username": user.username,
                "email": "nuevo_correo@example.com",
                "is_active": "on",
                "groups": [other_role.pk],
            },
        )

        self.assertRedirects(response, self.home_url)

        user.refresh_from_db()

        self.assertEqual(
            user.email,
            "nuevo_correo@example.com",
        )
        self.assertIn(self.role, user.groups.all())
        self.assertNotIn(other_role, user.groups.all())

        self.assertIn(
            self.role,
            self.employee.assigned_groups.all(),
        )

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
