"""Regresión: Tubo de seguimiento y navegación a Atención (sin JSON)."""
from django.contrib.auth.models import Permission
from django.test import RequestFactory, TestCase
from django.urls import reverse

from .test_request_actions import CitizenRequestActionModelTests
from .tubo_views import tubo_seguimiento
from .views import request_action_list, view_attention_from_request


class TubosEnlacesSGRTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        CitizenRequestActionModelTests.setUpTestData.__func__(cls)

    make_request = CitizenRequestActionModelTests.make_request
    make_action = CitizenRequestActionModelTests.make_action
    make_attention = CitizenRequestActionModelTests.make_attention

    def setUp(self):
        self.factory = RequestFactory()
        self.user.refresh_from_db()
        self.user.sgr_active_delegation_id = self.north.pk

    def _get_tubo(self):
        req = self.factory.get(reverse("citizen_requests:tubo_seguimiento"))
        req.user = self.user
        return tubo_seguimiento(req)

    def _allow_attention(self):
        perm = Permission.objects.get(
            content_type__app_label="registration_validation", codename="view_attentionentry"
        )
        self.user.user_permissions.add(perm)
        for name in ("_perm_cache", "_user_perm_cache", "_group_perm_cache"):
            self.user.__dict__.pop(name, None)

    def test_tubo_with_attention_links_to_html_page_instead_of_json(self):
        self._allow_attention()
        att = self.make_attention(self.north)
        req = self.make_request(delegation=self.north, attention=att)
        self.make_action(req)
        response = self._get_tubo()
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        target = reverse("citizen_requests:view_attention_from_request", args=[req.pk])
        old = reverse("citizen_requests:request_detail", args=[req.pk])
        self.assertIn(f'href="{target}"', html)
        self.assertNotIn(f'href="{old}"', html)
        self.assertIn("Ver atención", html)

        details = self.factory.get(target)
        details.user = self.user
        output = view_attention_from_request(details, req.pk)
        self.assertEqual(output.status_code, 200)
        self.assertIn("text/html", output["Content-Type"])
        self.assertIn(b"Atenci", output.content)

    def test_tubo_without_attention_does_not_link_to_json_or_missing_page(self):
        req = self.make_request(delegation=self.north)
        self.make_action(req)
        response = self._get_tubo()
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertIn("Sin atención", html)
        self.assertNotIn(
            f'href="{reverse("citizen_requests:request_detail", args=[req.pk])}"', html
        )
        self.assertNotIn(
            f'href="{reverse("citizen_requests:view_attention_from_request", args=[req.pk])}"', html
        )

    def test_tubo_attention_without_permission_shows_no_link(self):
        att = self.make_attention(self.north)
        req = self.make_request(delegation=self.north, attention=att)
        self.make_action(req)
        response = self._get_tubo()
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Atenci", response.content)
        self.assertNotIn(
            f'href="{reverse("citizen_requests:view_attention_from_request", args=[req.pk])}"'.encode(),
            response.content,
        )

    def test_gestiones_back_button_no_longer_opens_json(self):
        self._allow_attention()
        att = self.make_attention(self.north)
        req = self.make_request(delegation=self.north, attention=att)
        self.make_action(req)
        path = reverse("citizen_requests:request_action_list", args=[req.pk])
        http = self.factory.get(path)
        http.user = self.user
        response = request_action_list(http, req.pk)
        self.assertEqual(response.status_code, 200)
        target = reverse("citizen_requests:view_attention_from_request", args=[req.pk])
        self.assertIn(f'href="{target}"'.encode(), response.content)
        self.assertNotIn(
            f'href="{reverse("citizen_requests:request_detail", args=[req.pk])}"'.encode(),
            response.content,
        )
