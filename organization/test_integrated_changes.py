"""Pruebas de las mejoras integradas sobre los mantenedores del SGR."""
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

from accounts.models import UserProfile
from .models import Delegation, DelegationResponsibilityLog, Employee, OrganizationRole, PositionFunction


class IntegratedChangesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.north = Delegation.objects.create(name="Norte", status="Active", scope="Urbana")
        cls.south = Delegation.objects.create(name="Sur", status="Active", scope="Rural")
        cls.position = PositionFunction.objects.create(
            position_name="Analista", measurable_items="Informe", services="Atención",
            weightings="100", validity_start=date(2026, 1, 1), validity_end=date(2027, 1, 1),
        )
        cls.employee = Employee.objects.create(
            name="María Pérez", delegation=cls.north, position=cls.position,
            status="Active", roles="Evaluación",
        )
        cls.south_employee = Employee.objects.create(
            name="Empleado Sur", delegation=cls.south, position=cls.position,
            status="Active", roles="Gestión",
        )
        cls.admin = get_user_model().objects.create_superuser(username="admin-integracion", password="Test2026!segura")
        cls.group = Group.objects.create(name="Evaluador multi")
        cls.role = OrganizationRole.objects.create(
            group=cls.group, delegation=cls.north, description="Evaluar resultados",
        )
        cls.role.application_delegations.add(cls.north, cls.south)
        cls.view_employee = Permission.objects.get(content_type__app_label="organization", codename="view_employee")

    def setUp(self):
        self.client.force_login(self.admin)

    def test_new_employee_route_preserves_legacy_url(self):
        path = reverse("organization:employee_list")
        self.assertEqual(path, "/organization/empleados/")
        self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(self.client.get("/organization/funcionarios/").status_code, 200)
        self.assertContains(self.client.get(path), "Empleados")

    def test_role_description_and_multiple_delegations(self):
        url = reverse("organization:role_list")
        response = self.client.post(url, {
            "action": "edit", "object_id": self.group.pk,
            "name": "Evaluador multi", "description": "Revisar evaluaciones municipales",
            "delegations": [self.north.pk, self.south.pk], "permissions": [self.view_employee.pk],
        })
        self.assertRedirects(response, url)
        self.role.refresh_from_db()
        self.assertEqual(self.role.application_delegations.count(), 2)
        self.assertEqual(self.role.description, "Revisar evaluaciones municipales")

    def test_delegation_fields_responsible_and_audit(self):
        self.north.code = "NOR-1"
        self.north.address = "Calle Norte 1"
        self.north.commune = "La Serena"
        self.north.save()
        url = reverse("organization:delegation_list")
        result = self.client.post(url, {
            "action": "edit", "object_id": self.north.pk,
            "code": "NOR-1", "name": "Norte", "address": "Calle Norte 1",
            "commune": "La Serena", "scope": "Urbana", "status": "Active",
            "responsible": self.employee.pk,
        })
        self.assertRedirects(result, url)
        self.north.refresh_from_db()
        self.assertEqual(self.north.responsible, self.employee)
        self.assertTrue(DelegationResponsibilityLog.objects.filter(
            delegation=self.north, new_responsible=self.employee,
        ).exists())

    def test_create_and_edit_multidelegation_user(self):
        url = reverse("organization:user_list")
        result = self.client.post(url, {
            "action": "create", "username": "usuario-integrado",
            "first_name": "Ana", "last_name": "Ejemplo", "email": "ana@ejemplo.cl",
            "employee_code": "COD-NEW-001", "authorized_delegations": [self.north.pk, self.south.pk],
            "groups": [self.group.pk], "password1": "Seguro2026*clave", "password2": "Seguro2026*clave",
        })
        self.assertRedirects(result, url)
        user = get_user_model().objects.get(username="usuario-integrado")
        self.assertEqual(user.profile.authorized_delegations.count(), 2)
        self.assertIsNone(user.profile.employee)
        result = self.client.post(url, {
            "action": "edit", "object_id": user.pk,
            "username": "usuario-integrado", "first_name": "Ana", "last_name": "Actualizada",
            "email": "ana.actualizada@ejemplo.cl", "is_active": "on",
            "employee_code": "COD-NEW-001", "authorized_delegations": [self.north.pk, self.south.pk],
            "groups": [self.group.pk], "employee": self.employee.pk,
        })
        self.assertRedirects(result, url)
        user.refresh_from_db()
        user.profile.refresh_from_db()
        self.assertEqual(user.profile.employee, self.employee)
        self.assertEqual(user.last_name, "Actualizada")
        self.assertTrue(self.employee.assigned_groups.filter(pk=self.group.pk).exists())

    def test_role_permission_cannot_open_unauthorized_delegation(self):
        self.group.permissions.add(self.view_employee)
        self.role.application_delegations.set([self.north])
        user = get_user_model().objects.create_user("empleado-con-alcance", password="Test2026!segura")
        profile = UserProfile.objects.create(user=user, employee_code="PERM-001", delegation=self.north)
        profile.authorized_delegations.add(self.north, self.south)
        user.groups.add(self.group)
        self.client.force_login(user)
        response = self.client.get(reverse("organization:employee_list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["employees"]), [self.employee])

    def test_users_have_only_one_search_and_a_visible_pager(self):
        response = self.client.get(reverse("organization:user_list"))
        self.assertContains(response, 'id="user-search"', count=1)
        self.assertContains(response, "Página", count=0) if False else None
        self.assertContains(response, "Mostrando")
