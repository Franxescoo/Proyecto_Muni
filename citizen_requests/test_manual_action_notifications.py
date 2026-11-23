"""Pruebas de la notificación opcional al modificar una gestión.

Solo buzón en memoria; no hace conexiones SMTP.
"""
from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

import citizen_requests.test_action_notifications as fixtures
from citizen_requests.models import CitizenRequestAction


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="sgr-test@example.org",
    PUBLIC_PORTAL_URL="http://127.0.0.1:8000/portal/",
)
class OptionalManualActionNotificationTests(TestCase):
    setUpTestData = classmethod(fixtures.ActionNotificationsTests.setUpTestData.__func__)
    make_request = fixtures.ActionNotificationsTests.make_request
    make_attention = fixtures.ActionNotificationsTests.make_attention
    action_form_data = fixtures.ActionNotificationsTests.action_form_data
    _request = fixtures.ActionNotificationsTests._request
    _create = fixtures.ActionNotificationsTests._create

    def setUp(self):
        self.client.force_login(self.user)
        mail.outbox.clear()

    def edit_data(self, action, **overrides):
        values = self.action_form_data(
            responsible=action.responsible,
            action_type=action.action_type,
            performed_at=timezone.localtime(action.performed_at).strftime("%Y-%m-%dT%H:%M"),
            description=action.description,
            outcome=action.outcome,
            executor_type=action.executor_type,
            executor_name=action.executor_name,
            executor_contact=action.executor_contact,
            expected_execution_date=(
                action.expected_execution_date.isoformat()
                if action.expected_execution_date else ""
            ),
        )
        values.update(overrides)
        return values

    def edit(self, req, action, **overrides):
        data = self.edit_data(action, **overrides)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(
                reverse("citizen_requests:edit_request_action", args=(req.pk, action.pk)),
                data,
            )

    def test_checkbox_only_in_edit_not_create(self):
        req = self._request()
        _, action = self._create(req)
        edit_response = self.client.get(
            reverse("citizen_requests:edit_request_action", args=(req.pk, action.pk))
        )
        self.assertEqual(edit_response.status_code, 200)
        self.assertContains(edit_response, 'name="notify_citizen"')
        self.assertContains(edit_response, 'Notificar al ciudadano sobre esta modificación')
        self.assertNotContains(edit_response, 'name="notify_citizen" checked')
        create_response = self.client.get(
            reverse("citizen_requests:create_request_action", args=(req.pk,))
        )
        self.assertEqual(create_response.status_code, 200)
        self.assertNotContains(create_response, 'name="notify_citizen"')

    def test_unchecked_date_change_does_not_notify(self):
        req = self._request()
        _, action = self._create(req)
        mail.outbox.clear()
        response = self.edit(req, action, expected_execution_date="2026-12-05")
        self.assertEqual(response.status_code, 302)
        action.refresh_from_db()
        self.assertEqual(action.expected_execution_date.isoformat(), "2026-12-05")
        self.assertEqual(len(mail.outbox), 0)

    def test_checked_date_change_sends_one_safe_email(self):
        req = self._request()
        _, action = self._create(req)
        mail.outbox.clear()
        response = self.edit(
            req, action,
            expected_execution_date="2026-12-05",
            description="OBSERVACIÓN INTERNA RESERVADA",
            outcome="RESULTADO PRIVADO",
            executor_contact="privado-nuevo@example.org",
            notify_citizen="on",
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertIn("Actualización de gestión operativa", message.subject)
        self.assertIn("05/12/2026", message.body)
        self.assertIn("fecha prevista de intervención", message.body)
        self.assertEqual(message.to, ["vecina@example.org"])
        self.assertIn(str(req.tracking_code), message.body)
        self.assertNotIn("OBSERVACIÓN INTERNA RESERVADA", message.body)
        self.assertNotIn("RESULTADO PRIVADO", message.body)
        self.assertNotIn("privado-nuevo@example.org", message.body)
        req.refresh_from_db()
        self.assertEqual(req.status, "NEW")

    def test_checked_without_actual_change_does_not_notify(self):
        req = self._request()
        _, action = self._create(req)
        mail.outbox.clear()
        response = self.edit(req, action, notify_citizen="on")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

    def test_executor_change_with_checkbox_still_sends_one_automatic_email(self):
        req = self._request()
        _, action = self._create(req)
        mail.outbox.clear()
        response = self.edit(
            req, action,
            executor_name="Nueva empresa luminarias",
            expected_execution_date="2026-12-05",
            notify_citizen="on",
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Cambio de ejecutor", mail.outbox[0].subject)
        self.assertIn("05/12/2026", mail.outbox[0].body)
        self.assertNotIn("Actualización de gestión operativa", mail.outbox[0].subject)

    def test_checked_internal_executor_change_uses_generic_notice(self):
        req = self._request()
        _, action = self._create(req)
        mail.outbox.clear()
        response = self.edit(
            req, action,
            executor_type="MUNICIPAL",
            executor_name="Cuadrilla municipal",
            notify_citizen="on",
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Actualización de gestión operativa", mail.outbox[0].subject)
        self.assertNotIn("Ejecutor: Cuadrilla municipal", mail.outbox[0].body)

    def test_unverified_email_prevents_manual_notice(self):
        req = self._request(paused=True)
        _, action = self._create(req)
        mail.outbox.clear()
        response = self.edit(
            req, action, expected_execution_date="2026-12-05", notify_citizen="on",
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

    def test_invalid_form_does_not_send_even_when_checked(self):
        req = self._request()
        _, action = self._create(req)
        mail.outbox.clear()
        response = self.edit(
            req, action, responsible="", expected_execution_date="2026-12-05",
            notify_citizen="on",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(mail.outbox), 0)
        action.refresh_from_db()
        self.assertEqual(action.expected_execution_date.isoformat(), "2026-11-25")

    def test_smtp_error_never_reverts_saved_edit(self):
        req = self._request()
        _, action = self._create(req)
        mail.outbox.clear()
        with patch("citizen_requests.action_notifications.send_mail", side_effect=OSError("SMTP offline")):
            with self.assertLogs("citizen_requests.action_notifications", level="ERROR"):
                response = self.edit(
                    req, action,
                    expected_execution_date="2026-12-05",
                    notify_citizen="on",
                )
        self.assertEqual(response.status_code, 302)
        action.refresh_from_db()
        self.assertEqual(action.expected_execution_date.isoformat(), "2026-12-05")
        self.assertEqual(len(mail.outbox), 0)

    def test_checked_without_recipient_never_sends(self):
        req = self._request(recipient="")
        _, action = self._create(req)
        response = self.edit(
            req, action,
            expected_execution_date="2026-12-05",
            notify_citizen="on",
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

    def test_forged_checkbox_in_create_has_no_manual_effect(self):
        req = self._request()
        data = self.action_form_data(
            executor_type="MUNICIPAL", executor_name="Equipo municipal",
            notify_citizen="on",
        )
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("citizen_requests:create_request_action", args=(req.pk,)), data
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)
        self.assertTrue(CitizenRequestAction.objects.filter(request=req).exists())
