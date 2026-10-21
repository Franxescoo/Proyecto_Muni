"""Contratos de la interfaz unificada; utilizan la base temporal de Django."""
from datetime import date, timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from organization.models import Delegation, Employee, PositionFunction


class AdministrativePaginationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser(
            "admin-ui-test", "ui-admin@example.com", "secure-test-only"
        )
        cls.delegation = Delegation.objects.create(name="Delegación UI", scope="Regional", status="Active")
        cls.positions = []
        for n in range(11):
            position = PositionFunction.objects.create(
                position_name=f"Cargo UI {n:02d}", measurable_items="", services="",
                weightings="", validity_start=date.today()-timedelta(days=1),
                validity_end=date.today()+timedelta(days=100)
            )
            cls.positions.append(position)
            Employee.objects.create(
                name=f"Empleado UI {n:02d}", delegation=cls.delegation,
                position=position, roles="Funciones", status="Active"
            )

    def setUp(self):
        self.client.force_login(self.admin)

    def test_employee_and_position_page_navigation_preserves_search(self):
        pref_url = reverse("organization:set_page_size")
        self.client.post(pref_url, {"page_size":"10", "next":reverse("organization:employee_list")})
        for name, context_key, label in (
            ("organization:employee_list", "employees", "empleados"),
            ("organization:position_list", "position_page", "cargos"),
        ):
            url=reverse(name)
            response=self.client.get(url)
            self.assertEqual(response.status_code,200)
            page=response.context[context_key]
            self.assertEqual(page.paginator.count,11)
            self.assertEqual(len(page.object_list),10)
            self.assertContains(response,"1 / 2")
            self.assertContains(response,"Guardar preferencia")
            self.assertContains(response,"Limpiar")
            self.assertContains(response,"Modificar")
            self.assertContains(response,"Eliminar")
            self.assertContains(response,"?page=2")
            response=self.client.get(url,{"page":"2"})
            self.assertEqual(len(response.context[context_key].object_list),1)
            self.assertContains(response,"2 / 2")

    def test_single_page_keeps_centered_navigation(self):
        response=self.client.get(reverse("organization:delegation_list"))
        self.assertContains(response,"1 / 1")
        self.assertContains(response,"Anterior")
        self.assertContains(response,"Siguiente")
        self.assertContains(response,'justify-content-center')
