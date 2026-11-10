"""Pruebas de privacidad del historial público; no requieren superusuario."""
import re
from unittest.mock import patch

from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from .history import (
    SESSION_PENDING, SESSION_VERIFIED, CODE_EXPIRY_SECONDS,
)
from .models import CitizenRequest


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class PublicRequestHistoryTests(TestCase):
    def setUp(self):
        cache.clear()
        self.url = reverse("citizen_requests:public_request_history")
        self.mine = CitizenRequest.objects.create(
            origin="CITIZEN", requester_name="Vecina",
            requester_email="vecina@example.com", address="Calle 1",
            subject="Luminaria", description="Farol apagado",
        )
        self.other = CitizenRequest.objects.create(
            origin="CITIZEN", requester_name="Otro",
            requester_email="otro@example.com", address="Calle 2",
            subject="Arboles", description="Poda",
        )
        self.internal = CitizenRequest.objects.create(
            origin="INTERNAL", requester_name="Interna",
            requester_email="vecina@example.com", address="Calle 3",
            subject="Nota interna", description="No pública",
        )

    def _send_and_read(self, email="VECINA@EXAMPLE.COM"):
        response = self.client.post(self.url, {"action": "send", "email": email})
        self.assertRedirects(response, self.url)
        self.assertEqual(len(mail.outbox), 1)
        return re.search(r"\b\d{6}\b", mail.outbox[0].body).group(0)

    def test_history_is_private_until_email_code_is_verified(self):
        response = self.client.get(self.url)
        self.assertNotContains(response, "Luminaria")
        self.assertNotContains(response, str(self.mine.tracking_code))
        code = self._send_and_read()
        response = self.client.get(self.url)
        self.assertNotContains(response, "Luminaria")
        self.assertContains(response, "Verifica tu correo")
        response = self.client.post(self.url, {"action": "verify", "code": code})
        self.assertRedirects(response, self.url)
        response = self.client.get(self.url)
        self.assertContains(response, "Luminaria")
        self.assertContains(response, str(self.mine.tracking_code))
        self.assertNotContains(response, "Arboles")
        self.assertNotContains(response, "Nota interna")
        self.assertEqual(response["Cache-Control"].split(",")[0], "max-age=0")

    def test_invalid_code_does_not_reveal_history(self):
        code = self._send_and_read()
        wrong = "000000" if code != "000000" else "000001"
        for _ in range(5):
            response = self.client.post(self.url, {"action": "verify", "code": wrong})
            self.assertNotContains(response, "Luminaria")
        self.assertNotIn(SESSION_PENDING, self.client.session)
        self.assertNotIn(SESSION_VERIFIED, self.client.session)

    def test_code_expires(self):
        code = self._send_and_read()
        issued = self.client.session[SESSION_PENDING]["issued_at"]
        with patch("citizen_requests.history.time.time", return_value=issued + CODE_EXPIRY_SECONDS + 1):
            response = self.client.post(self.url, {"action": "verify", "code": code})
        self.assertNotContains(response, "Luminaria")

    def test_same_email_case_insensitive_and_logout(self):
        code = self._send_and_read()
        self.client.post(self.url, {"action": "verify", "code": code})
        self.assertContains(self.client.get(self.url), "Luminaria")
        self.client.post(self.url, {"action": "logout"})
        self.assertNotContains(self.client.get(self.url), "Luminaria")

    def test_verified_access_expires_after_thirty_minutes(self):
        code = self._send_and_read()
        self.client.post(self.url, {"action": "verify", "code": code})
        issued = self.client.session[SESSION_VERIFIED]["verified_at"]
        with patch("citizen_requests.history.time.time", return_value=issued + 1801):
            response = self.client.get(self.url)
        self.assertNotContains(response, "Luminaria")

    def test_second_code_invalidates_first(self):
        first = self._send_and_read()
        mail.outbox.clear()
        second = self._send_and_read()
        wrong = first if first != second else "x" * 6
        response = self.client.post(self.url, {"action": "verify", "code": wrong})
        if first != second:
            self.assertContains(response, "Código incorrecto")
        self.assertNotContains(response, "Luminaria")
        response = self.client.post(self.url, {"action": "verify", "code": second})
        self.assertRedirects(response, self.url)
        self.assertContains(self.client.get(self.url), "Luminaria")

    def test_nonexistent_email_gets_same_verification_flow(self):
        self._send_and_read("no-existe@example.com")
        self.assertIn(SESSION_PENDING, self.client.session)
        self.assertContains(self.client.get(self.url), "Verifica tu correo")

    def test_rate_limit_per_email(self):
        for _ in range(3):
            response = self.client.post(self.url, {"action": "send", "email": "vecina@example.com"})
            self.assertRedirects(response, self.url)
        response = self.client.post(self.url, {"action": "send", "email": "vecina@example.com"})
        self.assertContains(response, "Demasiados intentos", status_code=200)
        self.assertEqual(len(mail.outbox), 3)

    def test_public_portal_links_to_history(self):
        response = self.client.get(reverse("citizen_requests:public_portal"))
        self.assertContains(response, self.url)
