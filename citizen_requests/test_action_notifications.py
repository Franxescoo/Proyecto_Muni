"""Pruebas de correos de Gestiones operativas; nunca se conecta a SMTP real.

Ejecutar: python manage.py test citizen_requests.test_action_notifications -v 2
"""
from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from citizen_requests.models import CitizenRequest, CitizenRequestAction
from citizen_requests.test_request_actions import CitizenRequestActionModelTests


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="sgr-test@example.org",
    PUBLIC_PORTAL_URL="http://127.0.0.1:8000/portal/",
)
class ActionNotificationsTests(TestCase):
    setUpTestData = classmethod(CitizenRequestActionModelTests.setUpTestData.__func__)
    make_request = CitizenRequestActionModelTests.make_request
    make_attention = CitizenRequestActionModelTests.make_attention
    action_form_data = CitizenRequestActionModelTests.action_form_data

    def setUp(self):
        self.client.force_login(self.user)
        mail.outbox.clear()

    def _request(self, *, recipient="vecina@example.org", paused=False):
        attention = self.make_attention(self.north)
        req = self.make_request(delegation=self.north, attention=attention)
        CitizenRequest.objects.filter(pk=req.pk).update(
            requester_name="Vecina de prueba",
            requester_email=recipient,
            followup_email_paused=paused,
        )
        return CitizenRequest.objects.get(pk=req.pk)

    def _create(self, req, **overrides):
        data = self.action_form_data(
            executor_type="COMPANY",
            executor_name="CGE",
            executor_contact="contacto-privado@example.org",
            expected_execution_date="2026-11-25",
            **overrides,
        )
        url = reverse("citizen_requests:create_request_action", args=(req.pk,))
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(url, data)
        return response, CitizenRequestAction.objects.filter(request=req).last()

    def _progress(self, req, action, old, new, note="Cambio registrado"):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(
                reverse(
                    "citizen_requests:update_request_action_progress",
                    args=(req.pk, action.pk),
                ),
                {"expected_status": old, "new_status": new, "note": note},
            )

    def test_creation_notifies_once_without_exposing_private_details(self):
        req = self._request()
        response, action = self._create(req)
        self.assertEqual(response.status_code, 302)
        self.assertIsNotNone(action)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["vecina@example.org"])
        self.assertIn("Asignación de ejecutor", message.subject)
        self.assertIn("CGE", message.body)
        self.assertIn(str(req.tracking_code), message.body)
        self.assertNotIn("contacto-privado@example.org", message.body)
        self.assertNotIn("Se inspeccionó el lugar", message.body)
        req.refresh_from_db()
        self.assertEqual(req.status, "NEW")
        self.assertEqual(action.execution_status, "PENDING")
        self.assertEqual(action.progress_events.count(), 1)

    def test_no_email_for_municipal_executor(self):
        req = self._request()
        data = self.action_form_data(
            executor_type="MUNICIPAL", executor_name="Unidad municipal",
        )
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("citizen_requests:create_request_action", args=(req.pk,)), data,
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

    def test_no_email_without_recipient_or_during_reverification(self):
        req_without_email = self._request(recipient="")
        response, _ = self._create(req_without_email)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)
        req_paused = self._request(paused=True)
        response, _ = self._create(req_paused)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

    def test_uses_verified_email_not_old_requester_email(self):
        req = self._request(recipient="anterior@example.org")
        CitizenRequest.objects.filter(pk=req.pk).update(
            verified_followup_email="actual@example.org",
        )
        response, _ = self._create(req)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["actual@example.org"])

    def test_progress_only_significant_states_and_reopening(self):
        req = self._request()
        response, action = self._create(req)
        self.assertEqual(response.status_code, 302)
        mail.outbox.clear()

        response = self._progress(req, action, "PENDING", "COORDINATED")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

        response = self._progress(req, action, "COORDINATED", "IN_PROGRESS")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Inicio de ejecución", mail.outbox[0].subject)

        response = self._progress(req, action, "IN_PROGRESS", "FINISHED")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn("Finalización de gestión", mail.outbox[1].subject)

        response = self._progress(req, action, "FINISHED", "PENDING", note="Trabajo incompleto")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 3)
        self.assertIn("Reapertura de gestión", mail.outbox[2].subject)
        self.assertNotIn("Trabajo incompleto", mail.outbox[2].body)

        action.refresh_from_db()
        self.assertEqual(action.execution_status, "PENDING")
        self.assertEqual(action.progress_events.count(), 5)
        req.refresh_from_db()
        self.assertEqual(req.status, "NEW")

    def test_duplicate_or_invalid_transition_does_not_notify(self):
        req = self._request()
        _, action = self._create(req)
        mail.outbox.clear()
        response = self._progress(req, action, "COORDINATED", "IN_PROGRESS")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)
        action.refresh_from_db()
        self.assertEqual(action.execution_status, "PENDING")

    def test_edit_only_notifies_if_executor_identity_changed(self):
        req = self._request()
        _, action = self._create(req)
        mail.outbox.clear()
        url = reverse("citizen_requests:edit_request_action", args=(req.pk, action.pk))

        only_contact = self.action_form_data(
            executor_type="COMPANY", executor_name="CGE",
            executor_contact="nuevo-telefono@example.org",
            expected_execution_date="2026-11-25",
        )
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(url, only_contact)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

        new_name = self.action_form_data(
            executor_type="COMPANY", executor_name="Contratista de luminarias",
            executor_contact="nuevo-telefono@example.org",
            expected_execution_date="2026-11-25",
        )
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(url, new_name)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Cambio de ejecutor", mail.outbox[0].subject)
        self.assertIn("Contratista de luminarias", mail.outbox[0].body)

    def test_attachment_failure_rolls_back_and_never_notifies(self):
        req = self._request()
        data = self.action_form_data(
            executor_type="COMPANY", executor_name="CGE",
        )
        with patch("citizen_requests.views._save_action_attachments", side_effect=OSError("archivo fallido")):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    reverse("citizen_requests:create_request_action", args=(req.pk,)),
                    data,
                )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(CitizenRequestAction.objects.filter(request=req).count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_smtp_failure_does_not_undo_action(self):
        req = self._request()
        with patch("citizen_requests.action_notifications.send_mail", side_effect=OSError("SMTP no disponible")):
            with self.assertLogs("citizen_requests.action_notifications", level="ERROR"):
                response, action = self._create(req)
        self.assertEqual(response.status_code, 302)
        self.assertIsNotNone(action)
        self.assertEqual(len(mail.outbox), 0)

    def test_no_email_when_closed_attention_rejects_new_action(self):
        req = self._request()
        attention = req.attention_entry
        attention.status = "CLOSED"
        attention.save(update_fields=["status"])
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("citizen_requests:create_request_action", args=(req.pk,)),
                self.action_form_data(executor_type="COMPANY", executor_name="CGE"),
            )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(CitizenRequestAction.objects.filter(request=req).exists())
        self.assertEqual(len(mail.outbox), 0)
