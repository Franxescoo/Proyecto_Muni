from datetime import date
from io import BytesIO
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
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
			"organization:delegation_list",
			"organization:position_list",
		)
		for route_name in route_names:
			with self.subTest(route_name=route_name):
				self.assertEqual(self.client.get(reverse(route_name)).status_code, 200)

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
		self.assertEqual(roles_card["href"], reverse("organization:role_list"))

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
		self.assertTrue(Group.objects.filter(pk=protected_role.pk).exists())

	def test_account_creation_assigns_selected_role_to_linked_employee(self):
		role = Group.objects.create(name="Cuenta territorial")
		OrganizationRole.objects.create(
			group=role,
			delegation=self.delegation,
		)
		response = self.client.post(
			reverse("accounts:account_create"),
			{
				"username": "new_role_account",
				"email": "new-role@example.com",
				"employee": self.employee.pk,
				"employee_code": "ORG-NEW-ACCOUNT-001",
				"groups": [role.pk],
				"password1": "Org-Role-Test-9271!",
				"password2": "Org-Role-Test-9271!",
			},
		)
		self.assertRedirects(response, reverse("accounts:access_home"))
		user = get_user_model().objects.get(username="new_role_account")
		self.assertIn(role, user.groups.all())
		self.assertIn(role, self.employee.assigned_groups.all())

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

		self.assertRedirects(response, reverse("accounts:access_home"))
		self.assertIn(role, user.groups.all())

	def test_employee_roles_sync_with_linked_account_in_both_directions(self):
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
		self.assertQuerySetEqual(user.groups.all(), [role], transform=lambda item: item)

		response = self.client.post(
			reverse("accounts:account_edit", args=[user.pk]),
			{
				"username": user.username,
				"email": "linked@example.com",
				"is_active": "on",
				"groups": [other_role.pk],
			},
		)
		self.assertRedirects(response, reverse("accounts:access_home"))
		self.employee.refresh_from_db()
		self.assertQuerySetEqual(
			self.employee.assigned_groups.all(),
			[other_role],
			transform=lambda item: item,
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

	def test_account_cannot_receive_role_from_another_delegation(self):
		role = Group.objects.create(name="Cuenta del Sur")
		OrganizationRole.objects.create(
			group=role,
			delegation=self.other_delegation,
		)

		response = self.client.post(
			reverse("accounts:account_create"),
			{
				"username": "wrong_delegation_account",
				"email": "wrong-role@example.com",
				"employee": self.employee.pk,
				"employee_code": "ORG-WRONG-ROLE-001",
				"groups": [role.pk],
				"password1": "Org-Role-Test-9271!",
				"password2": "Org-Role-Test-9271!",
			},
		)

		self.assertEqual(response.status_code, 200)
		self.assertIn("groups", response.context["form"].errors)
		self.assertFalse(
			get_user_model().objects.filter(
				username="wrong_delegation_account"
			).exists()
		)

	def test_employee_actions_follow_status_column_and_edit_has_confirmation(self):
		response = self.client.get(reverse("organization:employee_list"))
		self.assertContains(response, '<th class="text-end">Acciones</th>')

		edit_response = self.client.get(
			reverse("organization:employee_list"),
			{"modal": "edit", "id": Employee.objects.first().pk},
		)
		self.assertContains(edit_response, "¿Desea modificar el Funcionario?")
		self.assertContains(edit_response, 'data-action="edit"')
		self.assertContains(edit_response, "data-edit-confirmation=")

	def test_employee_profile_photo_is_saved_and_displayed_in_list(self):
		employee_url = reverse("organization:employee_list")
		create_response = self.client.get(
			employee_url,
			{"modal": "create"},
		)
		self.assertContains(create_response, 'enctype="multipart/form-data"')
		self.assertContains(create_response, "data-profile-photo-input")

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
		user.user_permissions.add(permission, position_permission)
		self.client.force_login(user)

		response = self.client.get(reverse("organization:employee_list"))

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
				"name": "Delegación Nueva",
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
				"name": "Delegación Modificada",
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
		position = PositionFunction.objects.get(position_name="Cargo Nuevo")

		response = self.client.post(
			position_url,
			{
				"action": "edit",
				"object_id": position.pk,
				**{**position_data, "position_name": "Cargo Modificado"},
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
		self.assertTrue(response.context["form"].non_field_errors())
		self.assertFalse(
			PositionFunction.objects.filter(
				position_name="Cargo Inválido"
			).exists()
		)
		self.assertContains(response, 'data-has-errors="true"')

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
		self.assertIn("name", invalid_delegation.context["form"].errors)
		self.assertIn("status", invalid_delegation.context["form"].errors)

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
		self.assertIn("name", invalid_employee.context["form"].errors)
		self.assertIn("roles", invalid_employee.context["form"].errors)
		self.assertIn("status", invalid_employee.context["form"].errors)

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
		self.assertIn("position_name", response.context["form"].errors)
		self.assertIn("measurable_items", response.context["form"].errors)
		self.assertIn("services", response.context["form"].errors)
		self.assertIn("weightings", response.context["form"].errors)

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
		self.assertFalse(Employee.objects.filter(name="No Autorizado").exists())
