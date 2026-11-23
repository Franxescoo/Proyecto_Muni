"""Pruebas del Tubo transversal sin nuevas tablas ni superusuario."""
from django.urls import reverse
from django.test import TestCase

from .test_request_actions import CitizenRequestActionModelTests
from .models import CitizenRequestAction


class TuboSeguimientoSGRTests(TestCase):
    """Reutiliza los datos de prueba existentes, sin repetir sus pruebas."""

    @classmethod
    def setUpTestData(cls):
        CitizenRequestActionModelTests.setUpTestData.__func__(cls)

    make_request = CitizenRequestActionModelTests.make_request
    make_action = CitizenRequestActionModelTests.make_action

    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)
        # Reproduce la selección del delegado/delegación global.
        self.user.sgr_active_delegation_id = self.north.pk
        # El middleware puede resetear el atributo al resolver la solicitud;
        # la prueba usa patch sobre el helper de selección para aislar esta vista.

    def _get(self, query=None, delegation=None, user=None):
        from unittest.mock import patch
        from . import tubo_views
        if user is not None:
            self.client.force_login(user)
        delegation = delegation if delegation is not None else self.north
        with patch.object(tubo_views, "_selected_delegation", return_value=delegation):
            return self.client.get(reverse("citizen_requests:tubo_seguimiento"), query or {})

    def test_tubo_uses_existing_actions_without_duplication(self):
        req = self.make_request(delegation=self.north, subject="Reparación luminaria")
        action = self.make_action(req)
        before = CitizenRequestAction.objects.count()
        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reparación luminaria")
        self.assertContains(response, "Gestiones")
        self.assertEqual(CitizenRequestAction.objects.count(), before)
        self.assertEqual(response.context["page_obj"].paginator.count, 1)

    def test_filters_by_requester_name_and_subject(self):
        req = self.make_request(delegation=self.north, subject="Podar árbol")
        self.make_action(req)
        yes = self._get({"q": "solicitante de prueba"})
        no = self._get({"q": "no-existe"})
        self.assertEqual(yes.context["page_obj"].paginator.count, 1)
        self.assertEqual(no.context["page_obj"].paginator.count, 0)

    def test_other_delegation_not_visible(self):
        req = self.make_request(delegation=self.south, subject="Privado Sur")
        self.make_action(req, responsible=self.south_employee, delegation=self.south)
        response = self._get()
        self.assertNotContains(response, "Privado Sur")
        self.assertEqual(response.context["page_obj"].paginator.count, 0)

    def test_different_delegation_selector(self):
        req = self.make_request(delegation=self.north, subject="Privado Norte")
        self.make_action(req)
        response = self._get(delegation=self.south)
        self.assertNotContains(response, "Privado Norte")

    def test_user_without_permission_is_denied(self):
        self.client.force_login(self.other_user)
        response = self._get(user=self.other_user)
        self.assertEqual(response.status_code, 403)

    def test_date_filter_invalid_is_handled(self):
        req = self.make_request(delegation=self.north)
        self.make_action(req)
        response = self._get({"from": "no-fecha"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "fecha válida")
