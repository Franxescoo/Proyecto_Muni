from django.test import TestCase
from django.contrib.auth.models import User, Permission
from django.urls import reverse
from .models import Citizen, CitizenAudit


class CitizenReactivationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="operador_ciudadanos", password="demo-pass")
        self.user.user_permissions.add(Permission.objects.get(content_type__app_label="citizen_registry", codename="change_citizen"))
        self.client.force_login(self.user)
        self.citizen = Citizen.objects.create(rut="12.345.678-5", full_name="Vecina", address="Domicilio", is_active=False)

    def test_reactivate_keeps_pk_and_unique_rut(self):
        r=self.client.post(reverse("citizen_registry:reactivate", args=[self.citizen.pk]))
        self.assertEqual(r.status_code, 200)
        self.citizen.refresh_from_db()
        self.assertTrue(self.citizen.is_active)
        self.assertEqual(Citizen.objects.filter(rut=self.citizen.rut).count(), 1)
        self.assertTrue(CitizenAudit.objects.filter(citizen=self.citizen, action="REACTIVATED").exists())

    def test_cannot_reactivate_without_permission(self):
        other=User.objects.create_user(username="sin_permiso", password="demo-pass")
        self.client.force_login(other)
        self.assertEqual(self.client.post(reverse("citizen_registry:reactivate", args=[self.citizen.pk])).status_code, 403)
