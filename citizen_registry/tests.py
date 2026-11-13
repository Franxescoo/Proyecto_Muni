from django.test import TestCase
from django.contrib.auth.models import User, Permission
from django.urls import reverse
from .forms import CitizenForm
from .models import Citizen
from .rut import normalize_rut, validate_rut
from django.core.exceptions import ValidationError


class CitizenTest(TestCase):
    def test_normalization(self):
        self.assertEqual(normalize_rut("12.345.678-5"), "123456785")
        validate_rut("12.345.678-5")
        with self.assertRaises(ValidationError):
            validate_rut("12.345.678-0")

    def test_store_unique_and_age(self):
        a = Citizen.objects.create(rut="12.345.678-5", full_name="Vecina", address="Dirección")
        self.assertEqual(a.rut, "123456785")
        self.assertIsNone(a.age)
        self.assertFalse(Citizen.objects.filter(rut="123456785", is_active=False).exists())

    def test_missing_organization(self):
        f = CitizenForm(data={"rut": "12.345.678-5", "full_name": "Vecino", "address": "Domicilio", "is_neighborhood_member": "on"})
        self.assertFalse(f.is_valid())
        self.assertIn("neighborhood_group", f.errors)

    def test_lookup_requires_authenticated_authorized_user(self):
        url = reverse("citizen_registry:lookup")
        response = self.client.get(url, {"rut": "12.345.678-5"})
        self.assertEqual(response.status_code, 302)
        u = User.objects.create_user(username="usuario", password="demo12345")
        self.client.force_login(u)
        self.assertEqual(self.client.get(url, {"rut": "12.345.678-5"}).status_code, 403)
        u.user_permissions.add(Permission.objects.get(content_type__app_label="citizen_registry", codename="view_citizen"))
        self.assertEqual(self.client.get(url, {"rut": "12.345.678-5"}).status_code, 200)

    def test_new_record_returns_limited_fields(self):
        u = User.objects.create_user(username="usuario", password="demo12345")
        u.user_permissions.set(Permission.objects.filter(content_type__app_label="citizen_registry", codename__in=["add_citizen","view_citizen"]))
        self.client.force_login(u)
        response = self.client.post(reverse("citizen_registry:create"), {"rut": "12.345.678-5", "full_name": "Vecina", "address": "Domicilio", "rsh_folio":"PRIVADO"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 201)
        d = self.client.get(reverse("citizen_registry:lookup"), {"rut": "12.345.678-5"}).json()
        self.assertTrue(d["found"])
        self.assertNotIn("rsh_folio", str(d))


class CitizenListTutorialContextTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(username="ciudadanos", password="demo12345")
        permission = Permission.objects.get(
            content_type__app_label="citizen_registry",
            codename="view_citizen",
        )
        user.user_permissions.add(permission)
        self.client.force_login(user)
        self.url = reverse("citizen_registry:list")

    def test_tutorial_is_absent_without_registration_context(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "data-sgr-autohelp")
        self.assertNotContains(response, "registration_validation_help.css")
        self.assertNotContains(response, "registration_validation_help.js")
        self.assertNotContains(response, "sgr_module_guides.css")
        self.assertNotContains(response, "data-sgr-guide-rail")
        self.assertContains(response, f'href="{self.url}"')

    def test_tutorial_is_available_with_registration_context(self):
        response = self.client.get(
            self.url,
            {"sgr_context": "registration_validation"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-sgr-autohelp="citizen_registry:list"')
        self.assertContains(response, "registration_validation_help.css")
        self.assertContains(response, "registration_validation_help.js")
        self.assertContains(response, "sgr_module_guides.css")
        self.assertContains(response, "Iniciar tutorial")
        self.assertContains(response, "Mostrar guía lateral")
        self.assertContains(response, 'data-sgr-guide-rail')
        self.assertNotContains(response, "Para registrar una persona")
        self.assertNotContains(response, "opciones para modificar, desactivar o reactivar")
        self.assertContains(
            response,
            f'href="{self.url}?sgr_context=registration_validation"',
        )

    def test_tutorial_context_survives_search_and_pagination(self):
        Citizen.objects.bulk_create(
            [
                Citizen(
                    rut=f"RVTUTOR{index:02}",
                    full_name=f"Ciudadano de prueba {index:02}",
                    address="Dirección de prueba",
                )
                for index in range(16)
            ]
        )

        response = self.client.get(
            self.url,
            {
                "sgr_context": "registration_validation",
                "state": "all",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'name="sgr_context" value="registration_validation"',
        )
        self.assertRegex(
            response.content.decode(),
            r'href="[^"]*sgr_context=registration_validation[^"]*page=2"',
        )
