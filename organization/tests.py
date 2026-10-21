
from datetime import date
from io import BytesIO
from tempfile import TemporaryDirectory

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from accounts.models import UserProfile
from core.views import build_sections

from .models import (
    Delegation,
    Employee,
    OrganizationRole,
    PositionFunction,
)


class OrganizationListTests(TestCase):

    def setUp(self):
        self.delegation = Delegation.objects.create(
            name="Centro",
            status="Active",
            scope="Urbano",
        )
        self.other_delegation = Delegation.objects.create(
            name="Sur",
            status="Active",
            scope="Rural",
        )
        self.position = PositionFunction.objects.create(
            position_name="Analista",
            measurable_items="Informes",
            services="Gestión",
            weightings="100%",
            validity_start=date(2026, 1, 1),
            validity_end=date(2026, 12, 31),
        )
        self.employee = Employee.objects.create(
            name="Funcionario Centro",
            delegation=self.delegation,
            position=self.position,
            roles="Análisis de gestión",
            status="Active",
        )
        Employee.objects.create(
            name="Funcionario Sur",
            delegation=self.other_delegation,
            position=self.position,
            roles="Atención territorial",
            status="Active",
        )

        self.admin = get_user_model().objects.create_superuser(
            username="organization_admin",
            password="test-password-123",
        )
        self.client.force_login(self.admin)

    def test_organization_cards_open_list_pages(self):
        route_names = (
            "organization:employee_list",
            "organization:user_list",
            "organization:delegation_list",
            "organization:position_list",
        )

        for route_name in route_names:
            with self.subTest(route_name=route_name):
                self.assertEqual(
                    self.client.get(reverse(route_name)).status_code,
                    200,
                )

        home = self.client.get(reverse("home"))
        for route_name in route_names:
            self.assertContains(home, reverse(route_name))

    def test_all_organization_lists_show_crud_controls(self):
        for route_name in (
            "organization:employee_list",
            "organization:delegation_list",
            "organization:position_list",
        ):
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))
                self.assertContains(response, "?modal=create")
                self.assertContains(response, "data-organization-delete")
                self.assertContains(response, "?modal=edit&amp;id=")

    def test_roles_permissions_card_is_only_visible_to_superusers(self):
        organization_section = next(
            section
            for section in build_sections(self.admin)
            if section["title"] == "Organización"
        )
        roles_card = next(
            card
            for card in organization_section["cards"]
            if card["title"] == "Roles y Permisos"
        )
        self.assertEqual(
            roles_card["href"],
            reverse("organization:role_list"),
        )

        user = get_user_model().objects.create_user(
            username="organization_manager",
            password="test-password-123",
        )
        user.user_permissions.set(
            Permission.objects.filter(
                content_type__app_label="organization",
                codename__in=[
                    "view_employee",
                    "view_delegation",
                    "view_positionfunction",
                ],
            )
        )

        sections = build_sections(user)
        organization_section = next(
            section
            for section in sections
            if section["title"] == "Organización"
        )
        self.assertNotIn(
            "Roles y Permisos",
            [card["title"] for card in organization_section["cards"]],
        )

    def test_role_page_is_admin_only_and_manages_permissions(self):
        role_url = reverse("organization:role_list")
        user = get_user_model().objects.create_user(
            username="non_admin",
            password="test-password-123",
        )
        self.client.force_login(user)
        self.assertEqual(self.client.get(role_url).status_code, 403)

        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(role_url).status_code, 200)

        permission = Permission.objects.get(
            content_type__app_label="organization",
            codename="view_employee",
        )
        response = self.client.post(
            role_url,
            {
                "action": "create",
                "name": "Gestor Territorial",
                "delegation": self.delegation.pk,
                "permissions": [permission.pk],
            },
        )
        self.assertRedirects(response, role_url)

        role = Group.objects.get(name="Gestor Territorial")
        self.assertIn(permission, role.permissions.all())

        response = self.client.post(
            role_url,
            {
                "action": "edit",
                "object_id": role.pk,
                "name": "Gestor de Delegación",
                "delegation": self.delegation.pk,
                "permissions": [permission.pk],
            },
        )
        self.assertRedirects(response, role_url)

        role.refresh_from_db()
        self.assertEqual(role.name, "Gestor de Delegación")

        response = self.client.post(
            role_url,
            {"action": "delete", "object_id": role.pk},
        )
        self.assertRedirects(response, role_url)
        self.assertFalse(Group.objects.filter(pk=role.pk).exists())

        protected_role = Group.objects.create(name="Rol protegido")
        OrganizationRole.objects.create(
            group=protected_role,
            delegation=self.delegation,
        )
        PositionFunction.objects.filter(pk=self.position.pk).update(
            group=protected_role
        )

        response = self.client.post(
            role_url,
            {"action": "delete", "object_id": protected_role.pk},
        )
        self.assertRedirects(response, role_url)
        self.assertTrue(
            Group.objects.filter(pk=protected_role.pk).exists()
        )

    def test_account_creation_inherits_employee_roles_without_selecting_them(self):
        role = Group.objects.create(name="Cuenta territorial")
        OrganizationRole.objects.create(
            group=role,
            delegation=self.delegation,
        )

        self.employee.assigned_groups.add(role)

        response = self.client.post(
            reverse("accounts:account_create"),
            {
                "username": "new_role_account",
                "email": "new-role@example.com",
                "employee": self.employee.pk,
                "employee_code": "ORG-NEW-ACCOUNT-001",
                "password1": "Org-Role-Test-9271!",
                "password2": "Org-Role-Test-9271!",
            },
        )

        self.assertRedirects(
            response,
            reverse("accounts:access_home"),
        )

        user = get_user_model().objects.get(
            username="new_role_account"
        )

        self.assertEqual(
            user.profile.employee_id,
            self.employee.pk,
        )
        self.assertEqual(
            user.profile.delegation_id,
            self.delegation.pk,
        )
        self.assertQuerySetEqual(
            user.groups.all(),
            [role],
            transform=lambda group: group,
        )
        self.assertQuerySetEqual(
            self.employee.assigned_groups.all(),
            [role],
            transform=lambda group: group,
        )

    def test_linking_profile_applies_employee_roles_to_account(self):
        role = Group.objects.create(name="Rol al vincular")
        OrganizationRole.objects.create(
            group=role,
            delegation=self.delegation,
        )

        self.employee.assigned_groups.add(role)

        user = get_user_model().objects.create_user(
            username="profile_to_link",
            password="test-password-123",
        )
        profile = UserProfile.objects.create(
            user=user,
            employee_code="ORG-LINK-PROFILE-001",
        )

        response = self.client.post(
            reverse("accounts:profile_link", args=[profile.pk]),
            {"employee": self.employee.pk},
        )

        self.assertRedirects(
            response,
            reverse("accounts:access_home"),
        )
        self.assertIn(role, user.groups.all())

    def test_employee_roles_sync_and_account_roles_are_independent(self):
        role = Group.objects.create(name="Analista con acceso")
        other_role = Group.objects.create(name="Revisor")

        OrganizationRole.objects.create(
            group=role,
            delegation=self.delegation,
        )
        OrganizationRole.objects.create(
            group=other_role,
            delegation=self.delegation,
        )

        user = get_user_model().objects.create_user(
            username="linked_employee",
            password="test-password-123",
        )
        UserProfile.objects.create(
            user=user,
            employee=self.employee,
            employee_code="ORG-LINK-001",
            delegation=self.delegation,
        )

        employee_url = reverse("organization:employee_list")

        response = self.client.post(
            employee_url,
            {
                "action": "edit",
                "object_id": self.employee.pk,
                "name": self.employee.name,
                "delegation": self.delegation.pk,
                "position": self.position.pk,
                "roles": self.employee.roles,
                "status": self.employee.status,
                "assigned_groups": [role.pk],
            },
        )

        self.assertRedirects(response, employee_url)
        self.assertQuerySetEqual(
            user.groups.all(),
            [role],
            transform=lambda group: group,
        )

        # Intentar enviar otro rol desde la edición de cuenta
        # no debe modificar los permisos del funcionario.
        response = self.client.post(
            reverse("accounts:account_edit", args=[user.pk]),
            {
                "username": user.username,
                "email": "linked@example.com",
                "is_active": "on",
                "groups": [other_role.pk],
            },
        )

        self.assertRedirects(
            response,
            reverse("accounts:access_home"),
        )

        user.refresh_from_db()
        self.assertEqual(user.email, "linked@example.com")

        self.assertQuerySetEqual(
            user.groups.all(),
            [other_role],
            transform=lambda group: group,
        )
        self.assertQuerySetEqual(
            self.employee.assigned_groups.all(),
            [role],
            transform=lambda group: group,
        )

    def test_employee_cannot_receive_role_from_another_delegation(self):
        role = Group.objects.create(name="Rol del Sur")
        OrganizationRole.objects.create(
            group=role,
            delegation=self.other_delegation,
        )

        response = self.client.post(
            reverse("organization:employee_list"),
            {
                "action": "create",
                "name": "Funcionario con ámbito cruzado",
                "delegation": self.delegation.pk,
                "position": self.position.pk,
                "roles": "Análisis territorial",
                "status": "Active",
                "assigned_groups": [role.pk],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "assigned_groups",
            response.context["form"].errors,
        )
        self.assertFalse(
            Employee.objects.filter(
                name="Funcionario con ámbito cruzado"
            ).exists()
        )

    def test_account_ignores_injected_role_outside_employee_delegation(self):
        correct_role = Group.objects.create(name="Cuenta Centro")
        wrong_role = Group.objects.create(name="Cuenta del Sur")

        OrganizationRole.objects.create(
            group=correct_role,
            delegation=self.delegation,
        )
        OrganizationRole.objects.create(
            group=wrong_role,
            delegation=self.other_delegation,
        )

        self.employee.assigned_groups.add(correct_role)

        response = self.client.post(
            reverse("accounts:account_create"),
            {
                "username": "wrong_delegation_account",
                "email": "wrong-role@example.com",
                "employee": self.employee.pk,
                "employee_code": "ORG-WRONG-ROLE-001",
                "groups": [wrong_role.pk],
                "password1": "Org-Role-Test-9271!",
                "password2": "Org-Role-Test-9271!",
            },
        )

        self.assertRedirects(
            response,
            reverse("accounts:access_home"),
        )

        user = get_user_model().objects.get(
            username="wrong_delegation_account"
        )

        self.assertQuerySetEqual(
            user.groups.all(),
            [correct_role],
            transform=lambda group: group,
        )
        self.assertNotIn(
            wrong_role,
            self.employee.assigned_groups.all(),
        )

    def test_employee_actions_follow_status_column_and_edit_has_confirmation(self):
        response = self.client.get(
            reverse("organization:employee_list")
        )
        self.assertContains(
            response,
            '<th class="text-end">Acciones</th>',
        )

        edit_response = self.client.get(
            reverse("organization:employee_list"),
            {"modal": "edit", "id": Employee.objects.first().pk},
        )
        self.assertContains(
            edit_response,
            "¿Desea modificar el Funcionario?",
        )
        self.assertContains(
            edit_response,
            'data-action="edit"',
        )
        self.assertContains(
            edit_response,
            "data-edit-confirmation=",
        )

    def test_employee_profile_photo_is_saved_and_displayed_in_list(self):
        employee_url = reverse("organization:employee_list")

        create_response = self.client.get(
            employee_url,
            {"modal": "create"},
        )
        self.assertContains(
            create_response,
            'enctype="multipart/form-data"',
        )
        self.assertContains(
            create_response,
            "data-profile-photo-input",
        )

        image_content = BytesIO()
        Image.new("RGB", (2, 2), color="blue").save(
            image_content,
            format="PNG",
        )

        photo = SimpleUploadedFile(
            "funcionario.png",
            image_content.getvalue(),
            content_type="image/png",
        )

        with TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                response = self.client.post(
                    employee_url,
                    {
                        "action": "create",
                        "name": "Funcionario con foto",
                        "delegation": self.delegation.pk,
                        "position": self.position.pk,
                        "roles": "Atención ciudadana",
                        "status": "Active",
                        "profile_photo": photo,
                    },
                )

                self.assertRedirects(response, employee_url)

                employee = Employee.objects.get(
                    name="Funcionario con foto"
                )
                self.assertEqual(
                    employee.profile_photo.name,
                    "profile_photos/funcionario.png",
                )

                listing = self.client.get(employee_url)
                self.assertContains(
                    listing,
                    'alt="Foto de Funcionario con foto"',
                )

    def test_employee_list_is_limited_to_users_delegation(self):
        user = get_user_model().objects.create_user(
            username="delegation_user",
            password="test-password-123",
        )
        UserProfile.objects.create(
            user=user,
            employee_code="ORG-USER-001",
            delegation=self.delegation,
        )

        permission = Permission.objects.get(
            content_type__app_label="organization",
            codename="view_employee",
        )
        position_permission = Permission.objects.get(
            content_type__app_label="organization",
            codename="view_positionfunction",
        )

        user.user_permissions.add(
            permission,
            position_permission,
        )
        self.client.force_login(user)

        response = self.client.get(
            reverse("organization:employee_list")
        )
        self.assertContains(response, "Funcionario Centro")
        self.assertNotContains(response, "Funcionario Sur")

        positions_response = self.client.get(
            reverse("organization:position_list")
        )
        position = positions_response.context["positions"].get()
        self.assertEqual(position.employee_count, 1)

    def test_admin_can_create_update_and_archive_records(self):
        employee_url = reverse("organization:employee_list")

        response = self.client.post(
            employee_url,
            {
                "action": "create",
                "name": "Funcionario Nuevo",
                "delegation": self.delegation.pk,
                "position": self.position.pk,
                "roles": "Gestión documental",
                "status": "Active",
            },
        )
        self.assertRedirects(response, employee_url)
        employee = Employee.objects.get(name="Funcionario Nuevo")

        response = self.client.post(
            employee_url,
            {
                "action": "edit",
                "object_id": employee.pk,
                "name": "Funcionario Actualizado",
                "delegation": self.delegation.pk,
                "position": self.position.pk,
                "roles": "Gestión documental",
                "status": "Inactive",
            },
        )
        self.assertRedirects(response, employee_url)

        employee.refresh_from_db()
        self.assertEqual(employee.name, "Funcionario Actualizado")

        response = self.client.post(
            employee_url,
            {"action": "delete", "object_id": employee.pk},
        )
        self.assertRedirects(response, employee_url)

        employee.refresh_from_db()
        self.assertIsNotNone(employee.deleted_at)

        delegation_url = reverse("organization:delegation_list")

        response = self.client.post(
            delegation_url,
            {
                "action": "create",
                "code": "DEL-NUEVA",
                "name": "Delegación Nueva",
                "address": "Avenida Costera 100",
                "commune": "La Serena",
                "scope": "Costero",
                "status": "Active",
            },
        )
        self.assertRedirects(response, delegation_url)
        delegation = Delegation.objects.get(name="Delegación Nueva")

        response = self.client.post(
            delegation_url,
            {
                "action": "edit",
                "object_id": delegation.pk,
                "code": "DEL-MOD",
                "name": "Delegación Modificada",
                "address": "Avenida Costera 200",
                "commune": "Coquimbo",
                "scope": "Costero",
                "status": "Inactive",
            },
        )
        self.assertRedirects(response, delegation_url)

        delegation.refresh_from_db()
        self.assertEqual(delegation.name, "Delegación Modificada")

        response = self.client.post(
            delegation_url,
            {"action": "delete", "object_id": delegation.pk},
        )
        self.assertRedirects(response, delegation_url)

        delegation.refresh_from_db()
        self.assertIsNotNone(delegation.deleted_at)

        position_url = reverse("organization:position_list")
        position_data = {
            "position_name": "Cargo Nuevo",
            "measurable_items": "Informes",
            "services": "Gestión",
            "weightings": "100%",
            "validity_start": "2026-01-01",
            "validity_end": "2026-12-31",
        }

        response = self.client.post(
            position_url,
            {"action": "create", **position_data},
        )
        self.assertRedirects(response, position_url)
        position = PositionFunction.objects.get(
            position_name="Cargo Nuevo"
        )

        response = self.client.post(
            position_url,
            {
                "action": "edit",
                "object_id": position.pk,
                **{
                    **position_data,
                    "position_name": "Cargo Modificado",
                },
            },
        )
        self.assertRedirects(response, position_url)

        position.refresh_from_db()
        self.assertEqual(position.position_name, "Cargo Modificado")

        response = self.client.post(
            position_url,
            {"action": "delete", "object_id": position.pk},
        )
        self.assertRedirects(response, position_url)

        position.refresh_from_db()
        self.assertIsNotNone(position.deleted_at)

    def test_invalid_position_dates_keep_modal_open(self):
        response = self.client.post(
            reverse("organization:position_list"),
            {
                "action": "create",
                "position_name": "Cargo Inválido",
                "measurable_items": "Informes",
                "services": "Gestión",
                "weightings": "100%",
                "validity_start": "2026-12-31",
                "validity_end": "2026-01-01",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["modal_open"])
        self.assertTrue(
            response.context["form"].non_field_errors()
        )
        self.assertFalse(
            PositionFunction.objects.filter(
                position_name="Cargo Inválido"
            ).exists()
        )
        self.assertContains(
            response,
            'data-has-errors="true"',
        )

    def test_delegation_and_employee_fields_are_validated(self):
        delegation_url = reverse("organization:delegation_list")

        invalid_delegation = self.client.post(
            delegation_url,
            {
                "action": "create",
                "name": "Centro",
                "scope": "Urbano",
                "status": "Unknown",
            },
        )
        self.assertEqual(invalid_delegation.status_code, 200)
        self.assertIn(
            "name",
            invalid_delegation.context["form"].errors,
        )
        self.assertIn(
            "status",
            invalid_delegation.context["form"].errors,
        )

        employee_url = reverse("organization:employee_list")
        invalid_employee = self.client.post(
            employee_url,
            {
                "action": "create",
                "name": "A",
                "delegation": self.delegation.pk,
                "position": self.position.pk,
                "roles": "  ",
                "status": "Unknown",
            },
        )

        self.assertEqual(invalid_employee.status_code, 200)
        self.assertIn(
            "name",
            invalid_employee.context["form"].errors,
        )
        self.assertIn(
            "roles",
            invalid_employee.context["form"].errors,
        )
        self.assertIn(
            "status",
            invalid_employee.context["form"].errors,
        )

    def test_position_name_must_be_unique_and_required_text_valid(self):
        response = self.client.post(
            reverse("organization:position_list"),
            {
                "action": "create",
                "position_name": self.position.position_name.upper(),
                "measurable_items": "X",
                "services": " ",
                "weightings": "1",
                "validity_start": "2026-01-01",
                "validity_end": "2026-12-31",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "position_name",
            response.context["form"].errors,
        )
        self.assertIn(
            "measurable_items",
            response.context["form"].errors,
        )
        self.assertIn(
            "services",
            response.context["form"].errors,
        )
        self.assertIn(
            "weightings",
            response.context["form"].errors,
        )

    def test_create_requires_add_permission(self):
        user = get_user_model().objects.create_user(
            username="view_only_user",
            password="test-password-123",
        )
        UserProfile.objects.create(
            user=user,
            employee_code="ORG-USER-002",
            delegation=self.delegation,
        )

        permission = Permission.objects.get(
            content_type__app_label="organization",
            codename="view_employee",
        )
        user.user_permissions.add(permission)
        self.client.force_login(user)

        response = self.client.post(
            reverse("organization:employee_list"),
            {
                "action": "create",
                "name": "No Autorizado",
                "delegation": self.delegation.pk,
                "position": self.position.pk,
                "roles": "Sin permiso",
                "status": "Active",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            Employee.objects.filter(
                name="No Autorizado"
            ).exists()
        )


class OrganizationUserMaintenanceTests(TestCase):
    """Pruebas del mantenedor Usuarios de Organización."""

    def setUp(self):
        self.delegation = Delegation.objects.create(
            name="Costa",
            status="Active",
            scope="Urbano",
        )
        self.other_delegation = Delegation.objects.create(
            name="Cordillera",
            status="Active",
            scope="Rural",
        )
        self.position = PositionFunction.objects.create(
            position_name="Gestor de atención",
            measurable_items="Casos",
            services="Atención",
            weightings="100%",
            validity_start=date(2026, 1, 1),
            validity_end=date(2026, 12, 31),
        )
        self.employee = Employee.objects.create(
            name="María de Prueba",
            delegation=self.delegation,
            position=self.position,
            roles="Atención ciudadana",
            status="Active",
        )

        self.role = Group.objects.create(
            name="Ver períodos Costa"
        )
        OrganizationRole.objects.create(
            group=self.role,
            delegation=self.delegation,
        )
        self.employee.assigned_groups.add(self.role)

        self.admin = get_user_model().objects.create_superuser(
            username="user_maintenance_admin",
            password="Admin-Test-9271!",
        )
        self.client.force_login(self.admin)

        self.url = reverse("organization:user_list")

    def account_payload(self, **changes):
        payload = {
            "action": "create",
            "username": "cuenta_prueba",
            "email": "cuenta@example.com",
            "employee": self.employee.pk,
            "employee_code": "TEST-USR-001",
            "password1": "Clave-Fuerte-9271!",
            "password2": "Clave-Fuerte-9271!",
        }
        payload.update(changes)
        return payload

    def create_account(self):
        response = self.client.post(
            self.url,
            self.account_payload(),
        )
        self.assertRedirects(response, self.url)

        return get_user_model().objects.get(
            username="cuenta_prueba"
        )

    def test_users_card_is_visible_only_for_admin(self):
        sections = build_sections(self.admin)
        organization = next(
            section
            for section in sections
            if section["title"] == "Organización"
        )
        self.assertIn(
            "Usuarios",
            [card["title"] for card in organization["cards"]],
        )

        user = get_user_model().objects.create_user(
            username="ordinary_card_user",
            password="Test-9271!",
        )
        sections = build_sections(user)
        organization = next(
            (
                section
                for section in sections
                if section["title"] == "Organización"
            ),
            None,
        )

        if organization is not None:
            self.assertNotIn(
                "Usuarios",
                [card["title"] for card in organization["cards"]],
            )

    def test_modal_create_uses_no_group_field(self):
        response = self.client.get(
            self.url,
            {"modal": "create"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["modal_open"])
        self.assertIn("groups", response.context["form"].fields)
        self.assertIn(
            "employee",
            response.context["form"].fields,
        )

    def test_new_account_inherits_roles_and_is_not_admin(self):
        user = self.create_account()

        self.assertTrue(user.is_active)
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.is_staff)
        self.assertTrue(
            user.check_password("Clave-Fuerte-9271!")
        )
        self.assertEqual(
            user.profile.employee_id,
            self.employee.pk,
        )
        self.assertEqual(
            user.profile.delegation_id,
            self.delegation.pk,
        )
        self.assertQuerySetEqual(
            user.groups.all(),
            [self.role],
            transform=lambda group: group,
        )

    def test_creation_cannot_override_employee_roles_with_post_data(self):
        foreign_role = Group.objects.create(
            name="Otro ámbito"
        )
        OrganizationRole.objects.create(
            group=foreign_role,
            delegation=self.other_delegation,
        )

        payload = self.account_payload(
            groups=[foreign_role.pk]
        )
        response = self.client.post(self.url, payload)

        self.assertRedirects(response, self.url)

        user = get_user_model().objects.get(
            username="cuenta_prueba"
        )
        self.assertQuerySetEqual(
            user.groups.all(),
            [self.role],
            transform=lambda group: group,
        )
        self.assertNotIn(
            foreign_role,
            user.groups.all(),
        )
        self.assertNotIn(
            foreign_role,
            self.employee.assigned_groups.all(),
        )

    def test_user_creation_succeeds_even_without_employee_roles(self):
        self.employee.assigned_groups.clear()

        user = self.create_account()

        self.assertEqual(user.groups.count(), 0)
        self.assertEqual(
            user.profile.employee_id,
            self.employee.pk,
        )

    def test_invalid_creation_keeps_modal_open_without_new_account(self):
        existing_count = get_user_model().objects.count()

        response = self.client.post(
            self.url,
            self.account_payload(
                password2="No coincide"
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["modal_open"])
        self.assertIn(
            "password2",
            response.context["form"].errors,
        )
        self.assertEqual(
            get_user_model().objects.count(),
            existing_count,
        )

    def test_edit_updates_email_without_altering_employee_roles(self):
        user = self.create_account()
        new_role = Group.objects.create(
            name="Rol ajeno"
        )

        response = self.client.get(
            self.url,
            {"modal": "edit", "id": user.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("groups", response.context["form"].fields)

        response = self.client.post(
            self.url,
            {
                "action": "edit",
                "object_id": user.pk,
                "username": user.username,
                "email": "correo_nuevo@example.com",
                "is_active": "on",
                "groups": [new_role.pk],
            },
        )
        self.assertRedirects(response, self.url)

        user.refresh_from_db()
        self.assertEqual(
            user.email,
            "correo_nuevo@example.com",
        )
        self.assertQuerySetEqual(
            user.groups.all(),
            [self.role],
            transform=lambda group: group,
        )
        self.assertQuerySetEqual(
            self.employee.assigned_groups.all(),
            [self.role],
            transform=lambda group: group,
        )

    def test_edit_toggles_active_without_changing_roles(self):
        user = self.create_account()

        base_payload = {
            "action": "edit",
            "object_id": user.pk,
            "username": user.username,
            "email": user.email,
        }

        # Desactivar
        response = self.client.post(
            self.url,
            base_payload,
        )
        self.assertRedirects(response, self.url)

        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertIsNone(
            authenticate(
                username=user.username,
                password="Clave-Fuerte-9271!",
            )
        )

        # Activar nuevamente
        response = self.client.post(
            self.url,
            {**base_payload, "is_active": "on"},
        )
        self.assertRedirects(response, self.url)

        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertQuerySetEqual(
            user.groups.all(),
            [self.role],
            transform=lambda group: group,
        )

    def test_employee_role_changes_are_synchronized_to_linked_account(self):
        user = self.create_account()

        new_role = Group.objects.create(
            name="Nuevo rol Costa"
        )
        OrganizationRole.objects.create(
            group=new_role,
            delegation=self.delegation,
        )

        response = self.client.post(
            reverse("organization:employee_list"),
            {
                "action": "edit",
                "object_id": self.employee.pk,
                "name": self.employee.name,
                "delegation": self.delegation.pk,
                "position": self.position.pk,
                "roles": self.employee.roles,
                "status": self.employee.status,
                "assigned_groups": [new_role.pk],
            },
        )
        self.assertRedirects(
            response,
            reverse("organization:employee_list"),
        )

        user.refresh_from_db()
        self.assertQuerySetEqual(
            user.groups.all(),
            [new_role],
            transform=lambda group: group,
        )

    def test_soft_delete_retains_account_profile_and_employee(self):
        user = self.create_account()
        profile_pk = user.profile.pk

        response = self.client.post(
            self.url,
            {
                "action": "delete",
                "object_id": user.pk,
            },
        )
        self.assertRedirects(response, self.url)

        user.refresh_from_db()
        profile = UserProfile.objects.get(pk=profile_pk)

        self.assertFalse(user.is_active)
        self.assertIsNotNone(profile.deleted_at)
        self.assertEqual(
            profile.employee_id,
            self.employee.pk,
        )
        self.assertTrue(
            Employee.objects.filter(
                pk=self.employee.pk
            ).exists()
        )
        self.assertTrue(
            get_user_model().objects.filter(
                pk=user.pk
            ).exists()
        )
        self.assertTrue(
            self.employee.assigned_groups.filter(
                pk=self.role.pk
            ).exists()
        )

        listing = self.client.get(self.url)
        self.assertNotIn(
            user,
            list(listing.context["users"]),
        )

        self.client.logout()
        self.assertFalse(
            self.client.login(
                username=user.username,
                password="Clave-Fuerte-9271!",
            )
        )

    def test_deleted_account_is_not_editable_from_either_interface(self):
        user = self.create_account()

        self.client.post(
            self.url,
            {
                "action": "delete",
                "object_id": user.pk,
            },
        )

        edit_get = self.client.get(
            self.url,
            {"modal": "edit", "id": user.pk},
        )
        self.assertEqual(edit_get.status_code, 404)

        edit_post = self.client.post(
            self.url,
            {
                "action": "edit",
                "object_id": user.pk,
                "username": user.username,
                "email": "wrong@example.com",
                "is_active": "on",
            },
        )
        self.assertEqual(edit_post.status_code, 404)

        old_edit = self.client.get(
            reverse(
                "accounts:account_edit",
                args=[user.pk],
            )
        )
        self.assertEqual(old_edit.status_code, 404)

        user.refresh_from_db()
        self.assertFalse(user.is_active)

    def test_non_admin_cannot_view_create_edit_or_delete_users(self):
        user = self.create_account()

        non_admin = get_user_model().objects.create_user(
            username="staff_no_permissions",
            password="Test-9271!",
        )
        self.client.force_login(non_admin)

        self.assertEqual(
            self.client.get(self.url).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                self.url,
                {"modal": "create"},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                self.url,
                self.account_payload(
                    username="not_allowed"
                ),
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                self.url,
                {
                    "action": "edit",
                    "object_id": user.pk,
                    "username": user.username,
                    "email": "wrong@example.com",
                    "is_active": "on",
                },
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                self.url,
                {
                    "action": "delete",
                    "object_id": user.pk,
                },
            ).status_code,
            403,
        )

        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertIsNone(user.profile.deleted_at)
