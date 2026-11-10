"""Regresiones para la ficha de solicitante y navegación pública."""
import re
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from .history import SESSION_VERIFIED
from .models import CitizenRequest

@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class PublicCitizenDetailsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.url = reverse("citizen_requests:public_request_history")
        self.mine = CitizenRequest.objects.create(
            origin="CITIZEN", requester_name="Persona Autorizada",
            requester_email="autorizado@example.com", requester_phone="+56911111111",
            address="Dirección de prueba A", subject="Solicitud A", description="Prueba")
        self.mine2 = CitizenRequest.objects.create(
            origin="CITIZEN", requester_name="Otra referencia del mismo correo",
            requester_email="autorizado@example.com", requester_phone="+56933333333",
            address="Dirección de prueba B", subject="Solicitud B", description="Prueba")
        self.other = CitizenRequest.objects.create(
            origin="CITIZEN", requester_name="DATOS PRIVADOS AJENOS",
            requester_email="ajeno@example.com", address="Dirección secreta", subject="Solicitud ajena",
            description="Prueba")
        self.internal = CitizenRequest.objects.create(
            origin="INTERNAL", requester_name="DATOS PRIVADOS INTERNOS",
            requester_email="autorizado@example.com", address="Dirección interna",
            subject="Interna", description="Prueba")

    def _verify(self):
        self.client.post(self.url,{"action":"send","email":"autorizado@example.com"})
        code=re.search(r"\b\d{6}\b",mail.outbox[-1].body).group(0)
        self.client.post(self.url,{"action":"verify","code":code})
        self.assertIn(SESSION_VERIFIED,self.client.session)

    def test_no_personal_data_without_verified_email(self):
        response=self.client.get(self.url+"?solicitud="+str(self.mine.tracking_code))
        self.assertNotContains(response,"Persona Autorizada")
        self.assertNotContains(response,"Dirección de prueba A")
        self.assertNotContains(response,"DATOS PRIVADOS AJENOS")

    def test_selecting_request_updates_only_left_card(self):
        self._verify()
        response=self.client.get(self.url+"?solicitud="+str(self.mine.tracking_code))
        self.assertContains(response,"Persona Autorizada")
        self.assertContains(response,"Dirección de prueba A")
        self.assertContains(response,"Solicitud B")
        response=self.client.get(self.url+"?solicitud="+str(self.mine2.tracking_code))
        self.assertContains(response,"Otra referencia del mismo correo")
        self.assertContains(response,"Dirección de prueba B")

    def test_other_email_and_internal_details_are_never_exposed(self):
        self._verify()
        response=self.client.get(self.url+"?solicitud="+str(self.other.tracking_code))
        self.assertNotContains(response,"DATOS PRIVADOS AJENOS")
        self.assertNotContains(response,"Dirección secreta")
        response=self.client.get(self.url+"?solicitud="+str(self.internal.tracking_code))
        self.assertNotContains(response,"DATOS PRIVADOS INTERNOS")
        self.assertNotContains(response,"Dirección interna")

    def test_public_pages_exclude_staff_sidebar(self):
        for route in ("public_portal","public_request_form","public_request_history"):
            response=self.client.get(reverse("citizen_requests:"+route))
            self.assertNotContains(response,'<aside class="global-sidebar"')
        self._verify()
        self.assertNotContains(self.client.get(self.url),'<aside class="global-sidebar"')

    def test_no_edit_delete_controls_and_logout_clears_personal_data(self):
        self._verify()
        response=self.client.get(self.url)
        self.assertContains(response,"Información de solo lectura")
        self.assertNotContains(response,"Eliminar solicitud")
        self.client.post(self.url,{"action":"logout"})
        self.assertNotContains(self.client.get(self.url),"Dirección de prueba B")
