"""Regresión de navegación pública: portada, formulario e historial."""
import time

from django.test import TestCase
from django.urls import reverse


class PortalRedesignTests(TestCase):
    def test_homepage_has_three_access_options(self):
        response = self.client.get(reverse("citizen_requests:public_portal"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ingresar solicitud")
        self.assertContains(response, "Consultar solicitud")
        self.assertContains(response, "Mis solicitudes")
        self.assertContains(response, reverse("citizen_requests:public_request_form"))
        self.assertContains(response, reverse("citizen_requests:public_request_history"))
        self.assertContains(response, 'id="consultarSolicitudModal"')

    def test_request_form_is_public_and_starts_with_rut_verification(self):
        response = self.client.get(reverse("citizen_requests:public_request_form"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="action" value="identify"')
        self.assertContains(response, 'name="rut"')
        self.assertContains(response, "Verificar RUT")
        # No exponer campos personales antes de validar el correo.
        self.assertNotContains(response, 'name="requester_email"')
        self.assertNotContains(response, 'name="address"')

    def test_unverified_html_submission_is_forbidden(self):
        response = self.client.post(
            reverse("citizen_requests:register_public_request"),
            {"portal_form": "1", "subject": "", "description": ""},
        )
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, "citizen_requests/request_form.html")
        self.assertContains(response, "verificar tu RUT", status_code=403)

    def test_invalid_html_submission_after_verification_shows_errors(self):
        from citizen_registry.models import Citizen
        from citizen_requests.views import PUBLIC_RUT_VERIFIED

        citizen = Citizen.objects.create(
            rut="111111111", full_name="Vecino de prueba",
            email="vecino@example.com", phone="+56 9 1234 5678",
            address="Calle 123",
        )
        session = self.client.session
        session[PUBLIC_RUT_VERIFIED] = {
            "id": citizen.pk,
            "rut": citizen.rut,
            "email": citizen.email,
            "verified_at": int(time.time()),
        }
        session.save()
        response = self.client.post(
            reverse("citizen_requests:register_public_request"),
            {"portal_form": "1", "subject": "", "description": ""},
        )
        self.assertEqual(response.status_code, 400)
        self.assertTemplateUsed(response, "citizen_requests/request_form.html")
        self.assertContains(response, "Ingresar solicitud", status_code=400)
        self.assertIn("subject", response.context["form"].errors)
        self.assertIn("description", response.context["form"].errors)

    def test_tracking_post_keeps_result_in_modal(self):
        response = self.client.post(
            reverse("citizen_requests:public_portal"),
            {"tracking_form": "1", "tracking_code": "no-es-uuid"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Revisa el código de seguimiento ingresado.")
        self.assertContains(response, 'id="consultarSolicitudModal"')
        self.assertContains(response, "bootstrap.Modal.getOrCreateInstance")

    def test_history_still_has_email_verification_form(self):
        response = self.client.get(reverse("citizen_requests:public_request_history"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="action" value="send"')
        self.assertContains(response, 'name="email"')
