"""Comprobaciones visuales y de navegación del portal institucional."""
from django.template.loader import get_template
from django.test import TestCase
from django.urls import reverse


class PortalInstitutionalAppearanceTests(TestCase):
    def test_landing_shows_original_municipal_footer(self):
        response = self.client.get(reverse('citizen_requests:public_portal'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Transparencia Activa')
        self.assertContains(response, 'Plataforma Ley del Lobby')
        self.assertContains(response, 'Ilustre Municipalidad de La Serena')
        self.assertContains(response, 'consultarSolicitudModal')

    def test_request_form_is_full_width_and_has_footer(self):
        response = self.client.get(reverse('citizen_requests:public_request_form'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'portal-request-page')
        self.assertContains(response, 'Identifica tu registro de ciudadano')
        self.assertContains(response, 'Transparencia Activa')

    def test_history_is_full_width_and_has_footer(self):
        response = self.client.get(reverse('citizen_requests:public_request_history'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'portal-history-page')
        self.assertContains(response, 'Plataforma Ley del Lobby')

    def test_confirmation_template_uses_matching_design(self):
        template = get_template('citizen_requests/confirmation.html')
        self.assertIsNotNone(template)
        source = template.template.source
        self.assertIn('portal-confirmation-page', source)
        self.assertIn('copy-code', source)
