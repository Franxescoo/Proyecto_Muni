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
