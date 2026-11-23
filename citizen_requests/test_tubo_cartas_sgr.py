"""Pruebas de integración del Tubo de cartas (usuarios normales, sin superusuario)."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import RequestFactory, TestCase

from accounts.models import UserProfile
from organization.models import Delegation
from .letter_models import CitizenRequestLetter
from .letter_views import tubo_cartas
from .models import CitizenRequest


class LetterTubeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.north = Delegation.objects.create(
            code="LET-N", name="Delegación prueba norte", status="Active", scope="Urbano"
        )
        cls.south = Delegation.objects.create(
            code="LET-S", name="Delegación prueba sur", status="Active", scope="Rural"
        )
        cls.user = get_user_model().objects.create_user(
            username="letter-test-normal-user", password="test-password"
        )
        p = UserProfile.objects.create(
            user=cls.user, employee_code="LET-N-1", delegation=cls.north
        )
        p.authorized_delegations.add(cls.north)
        perms = Permission.objects.filter(
            content_type__app_label__in=("citizen_requests", "registration_validation"),
            codename__in=(
                "view_citizenrequestaction", "add_citizenrequestaction", "add_attentionentry",
            ),
        )
        cls.user.user_permissions.add(*perms)

    def setUp(self):
        self.factory = RequestFactory()
        self.user.refresh_from_db()
        self.user.sgr_active_delegation_id = self.north.pk

    def _request(self, method="get", data=None):
        req = (self.factory.post if method == "post" else self.factory.get)(
            "/seguimiento/cartas/", data=data or {}
        )
        req.user = self.user
        return req

    def _letter(self, delegation):
        citizen_request = CitizenRequest.objects.create(
            origin="INTERNAL", requester_name="Vecino de prueba", address="Dirección 123",
            subject="Carta de prueba", description="Prueba", delegation=delegation,
        )
        return CitizenRequestLetter.objects.create(
            request=citizen_request, registered_by=self.user,
            kind=CitizenRequestLetter.Kind.CARTA,
        )

    def test_list_returns_200_for_authorized_normal_user(self):
        self._letter(self.north)
        response = tubo_cartas(self._request())
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Vecino de prueba", response.content)

    def test_cross_delegation_letter_not_visible(self):
        self._letter(self.south)
        response = tubo_cartas(self._request())
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"Vecino de prueba", response.content)

    @patch("citizen_requests.letter_views.messages.success")
    def test_create_letter_links_one_request_without_attention(self, _message):
        response = tubo_cartas(self._request("post", {
            "kind": "CARTA",
            "external_folio": "FOL-123",
            "sender_institution": "Organización de prueba",
            "requester_name": "Persona de prueba",
            "requester_phone": "555111",
            "address": "Calle de prueba 123",
            "subject": "Solicitud por carta",
            "description": "Prueba de correspondencia",
            "rut": "",
        }))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(CitizenRequest.objects.count(), 1)
        self.assertEqual(CitizenRequestLetter.objects.count(), 1)
        letter = CitizenRequestLetter.objects.select_related("request").get()
        self.assertEqual(letter.request.origin, "INTERNAL")
        self.assertEqual(letter.request.delegation_id, self.north.pk)
        self.assertIsNone(letter.request.attention_entry_id)
        self.assertEqual(letter.external_folio, "FOL-123")
        self.assertTrue(letter.request.tracking_code)

    def test_without_active_delegation_does_not_show_letters(self):
        self._letter(self.north)
        self.user.sgr_active_delegation_id = None
        response = tubo_cartas(self._request())
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"Vecino de prueba", response.content)
