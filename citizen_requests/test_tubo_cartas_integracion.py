"""Pruebas de integración: un expediente, cero atenciones duplicadas."""
from unittest.mock import patch

from django.test import RequestFactory, TestCase
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from accounts.models import UserProfile
from citizen_registry.models import Citizen
from organization.models import Delegation
from .models import CitizenRequest, RequestEvent
from .letter_models import CitizenRequestLetter
from .letter_views import tubo_cartas, carta_detalle


class CartaIntegracionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.delegation = Delegation.objects.create(
            code="CARTA-INT-01", name="Delegación cartas", status="Active", scope="Urbano"
        )
        cls.other = Delegation.objects.create(
            code="CARTA-INT-02", name="Otra delegación", status="Active", scope="Urbano"
        )
        cls.user = get_user_model().objects.create_user(
            username="test-cartas-integration", password="test-password"
        )
        profile = UserProfile.objects.create(
            user=cls.user, employee_code="CARTA-INT-01", delegation=cls.delegation
        )
        profile.authorized_delegations.add(cls.delegation)
        perms = Permission.objects.filter(
            content_type__app_label__in=("citizen_requests", "registration_validation"),
            codename__in=("view_citizenrequestaction", "add_citizenrequestaction"),
        )
        cls.user.user_permissions.add(*perms)

    def setUp(self):
        self.factory = RequestFactory()
        self.user.refresh_from_db()
        self.user.sgr_active_delegation_id = self.delegation.pk

    def _post(self, data):
        req = self.factory.post("/seguimiento/cartas/", data)
        req.user = self.user
        return req

    def _request(self, delegation=None):
        return CitizenRequest.objects.create(
            requester_name="Vecino", origin="INTERNAL", subject="Problema de alumbrado",
            address="Dirección 123", description="Solicita reparación", delegation=delegation or self.delegation
        )

    @patch("citizen_requests.letter_views.messages.success")
    def test_vincula_carta_a_solicitud_existente_sin_duplicar(self, _message):
        original = self._request()
        response = tubo_cartas(self._post({
            "existing_request_code": str(original.tracking_code),
            "kind": "CARTA", "external_folio": "C-777",
            "sender_institution": "Junta de vecinos",
        }))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(CitizenRequest.objects.count(), 1)
        self.assertEqual(CitizenRequestLetter.objects.count(), 1)
        self.assertEqual(CitizenRequestLetter.objects.get().request_id, original.pk)
        self.assertIsNone(CitizenRequest.objects.get().attention_entry_id)
        self.assertEqual(RequestEvent.objects.filter(request=original).count(), 1)

    @patch("citizen_requests.letter_views.messages.success")
    def test_rechaza_vinculo_duplicado(self, _message):
        original = self._request()
        body = {"existing_request_code": str(original.tracking_code), "kind": "CARTA"}
        self.assertEqual(tubo_cartas(self._post(body)).status_code, 302)
        self.assertEqual(tubo_cartas(self._post(body)).status_code, 200)
        self.assertEqual(CitizenRequest.objects.count(), 1)
        self.assertEqual(CitizenRequestLetter.objects.count(), 1)

    def test_no_permite_vincular_solicitud_de_otra_delegacion(self):
        foreign = self._request(self.other)
        result = tubo_cartas(self._post({
            "existing_request_code": str(foreign.tracking_code), "kind": "CARTA"
        }))
        self.assertEqual(result.status_code, 200)
        self.assertEqual(CitizenRequest.objects.count(), 1)
        self.assertEqual(CitizenRequestLetter.objects.count(), 0)

    @patch("citizen_requests.letter_views.messages.success")
    def test_solicitud_nueva_sin_atencion_duplicada(self, _message):
        response = tubo_cartas(self._post({
            "kind": "CARTA", "requester_name": "Persona nueva",
            "address": "Calle 123", "subject": "Arreglo", "description": "Detalle",
        }))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(CitizenRequest.objects.count(), 1)
        self.assertEqual(CitizenRequestLetter.objects.count(), 1)
        self.assertIsNone(CitizenRequest.objects.get().attention_entry_id)

    @patch("citizen_requests.letter_views.messages.success")
    def test_detalle_es_html_y_accede_al_expediente_original(self, _message):
        original = self._request()
        tubo_cartas(self._post({
            "existing_request_code": str(original.tracking_code), "kind": "CARTA",
        }))
        req = self.factory.get("/seguimiento/cartas/123/")
        req.user = self.user
        response = carta_detalle(req, original.pk)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"gestiones", response.content)
        self.assertIn(str(original.tracking_code).encode(), response.content)

    @patch("citizen_requests.letter_views.messages.success")
    def test_reutiliza_datos_centrales_cuando_existe_rut(self, _message):
        person = Citizen.objects.create(
            rut="12345678-5", full_name="María González", phone="912345678",
            email="maria@example.cl", address="Calle Central 123",
        )
        result = tubo_cartas(self._post({
            "kind": "CARTA", "rut": person.rut,
            "requester_name": "Nombre que no debe reemplazar al registro central",
            "requester_phone": "0000", "requester_email": "inventado@example.cl",
            "address": "Dirección diferente", "subject": "Luminarias",
            "description": "Reparar luminaria del sector",
        }))
        self.assertEqual(result.status_code, 302)
        obj = CitizenRequest.objects.get()
        self.assertEqual(obj.citizen_id, person.pk)
        self.assertEqual(obj.requester_name, person.full_name)
        self.assertEqual(obj.requester_phone, person.phone)
        self.assertEqual(obj.requester_email, person.email)
        self.assertEqual(obj.address, person.address)
        self.assertIsNone(obj.attention_entry_id)

    @patch("citizen_requests.letter_views.messages.success")
    def test_reutiliza_correo_de_carta_sin_rut(self, _message):
        result = tubo_cartas(self._post({
            "kind": "CARTA", "requester_name": "Persona sin RUT",
            "requester_email": "vecino@example.cl", "requester_phone": "900000000",
            "address": "Sector Central 11", "subject": "Luminarias",
            "description": "Reparar dos luminarias",
        }))
        self.assertEqual(result.status_code, 302)
        obj = CitizenRequest.objects.get()
        self.assertEqual(obj.requester_email, "vecino@example.cl")
        self.assertEqual(obj.requester_phone, "900000000")
        self.assertEqual(obj.address, "Sector Central 11")
