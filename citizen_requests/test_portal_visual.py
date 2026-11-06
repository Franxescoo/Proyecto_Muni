"""Comprueba el acceso visible al portal desde el login y la landing ampliada."""
from django.test import TestCase
from django.urls import reverse

class PortalLandingVisualTests(TestCase):
    def test_landing_uses_expanded_layout(self):
        response = self.client.get(reverse("citizen_requests:public_portal"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="public-portal portal-landing"')
        self.assertContains(response, 'css/portal_publico_moderno.css')
        self.assertContains(response, reverse("citizen_requests:public_request_history"))

    def test_login_offers_return_to_citizen_portal(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Volver al Portal Ciudadano")
        self.assertContains(response, reverse("citizen_requests:public_portal"))
