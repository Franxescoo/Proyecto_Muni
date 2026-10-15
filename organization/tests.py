from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from accounts.models import UserProfile

from .models import Delegation, Employee, PositionFunction


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
		Employee.objects.create(
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
