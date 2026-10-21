"""Verifica que las vistas de listados sigan renderizando la paginación uniforme."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class AdministrativeListSmokeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser("ui-smoke", "smoke@example.com", "test-pass-not-real")

    def setUp(self):
        self.client.force_login(self.admin)

    def test_list_pages_render_common_navigation(self):
        urls = (
            "organization:employee_list", "organization:position_list",
            "organization:delegation_list", "organization:role_list", "organization:user_list",
            "planning:period_list", "planning:goal_list", "planning:item_list",
            "registration:activity_list", "registration:activity_type_list", "registration:evidence_list",
            "registration:service_list", "registration:validation_list", "registration:attention_entry_list",
            "registration:attention_type_list", "registration:sub_attention_list",
        )
        for named_url in urls:
            with self.subTest(named_url=named_url):
                response = self.client.get(reverse(named_url))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Anterior")
                self.assertContains(response, "Siguiente")
                self.assertContains(response, 'aria-current="page"')
