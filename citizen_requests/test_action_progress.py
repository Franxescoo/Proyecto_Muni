"""Pruebas aisladas para ejecutar dentro de citizen_requests/test_action_progress.py.

python manage.py test citizen_requests.test_action_progress -v 2
No sustituye las pruebas preexistentes de la aplicación.
"""
from django.test import TestCase
from django.urls import reverse

from citizen_requests.forms import CitizenRequestActionForm
from citizen_requests.models import CitizenRequestAction, CitizenRequestActionProgress
from citizen_requests.test_request_actions import CitizenRequestActionModelTests
from registration_validation.models import AttentionEntry


class ActionProgressTests(TestCase):
    # Reutiliza únicamente los datos auxiliares de las pruebas ya presentes;
    # NO hereda sus decenas de casos ni los ejecuta de nuevo.
    setUpTestData = classmethod(CitizenRequestActionModelTests.setUpTestData.__func__)
    make_request = CitizenRequestActionModelTests.make_request
    make_attention = CitizenRequestActionModelTests.make_attention
    make_action = CitizenRequestActionModelTests.make_action
    action_form_data = CitizenRequestActionModelTests.action_form_data

    def _form_create(self, citizen_request, executor="CGE"):
        data = self.action_form_data(
            executor_type="COMPANY",
            executor_name=executor,
            executor_contact="contacto@example.org",
            expected_execution_date="2026-11-25",
        )
        form = CitizenRequestActionForm(
            data=data, citizen_request=citizen_request, user=self.user,
        )
        self.assertTrue(form.is_valid(), form.errors.as_json())
        return form.save()

    def _post_status(self, citizen_request, action, old, new, note="Avance documentado"):
        return self.client.post(
            reverse("citizen_requests:update_request_action_progress", args=(citizen_request.pk, action.pk)),
            {"expected_status": old, "new_status": new, "note": note},
        )

    def test_create_external_executor_and_initial_history(self):
        request = self.make_request(delegation=self.north)
        action = self._form_create(request)
        self.assertEqual(action.executor_name, "CGE")
        self.assertEqual(action.execution_status, "PENDING")
        self.assertEqual(action.progress_events.count(), 1)
        record = action.progress_events.get()
        self.assertEqual(record.new_status, "PENDING")
        self.assertEqual(record.recorded_by_id, self.user.pk)
        request.refresh_from_db()
        self.assertEqual(request.status, "NEW")  # No se cierra ni resuelve la solicitud.

    def test_legacy_actions_remain_valid_without_executor(self):
        request = self.make_request(delegation=self.north)
        action = self.make_action(request)
        self.assertEqual(action.execution_status, "")
        self.assertEqual(action.progress_events.count(), 0)

    def test_multiple_actions_track_independently(self):
        request = self.make_request(delegation=self.north)
        one = self._form_create(request, executor="CGE")
        two = self._form_create(request, executor="Equipo municipal")
        self.client.force_login(self.user)
        response = self._post_status(request, one, "PENDING", "COORDINATED")
        self.assertEqual(response.status_code, 302)
        one.refresh_from_db()
        two.refresh_from_db()
        self.assertEqual(one.execution_status, "COORDINATED")
        self.assertEqual(two.execution_status, "PENDING")

    def test_complete_and_reopen_preserves_full_history(self):
        request = self.make_request(delegation=self.north)
        action = self._form_create(request)
        self.client.force_login(self.user)
        for before, after in [
            ("PENDING", "COORDINATED"),
            ("COORDINATED", "IN_PROGRESS"),
            ("IN_PROGRESS", "FINISHED"),
            ("FINISHED", "PENDING"),
        ]:
            response = self._post_status(request, action, before, after, note=f"Paso: {before} -> {after}")
            self.assertEqual(response.status_code, 302)
            action.refresh_from_db()
            self.assertEqual(action.execution_status, after)
        self.assertEqual(action.progress_events.count(), 5)
        self.assertEqual(action.progress_events.last().previous_status, "FINISHED")
        self.assertEqual(action.progress_events.last().new_status, "PENDING")
        request.refresh_from_db()
        self.assertNotEqual(request.status, "CLOSED")

    def test_missing_note_and_stale_status_are_rejected(self):
        request = self.make_request(delegation=self.north)
        action = self._form_create(request)
        self.client.force_login(self.user)
        self._post_status(request, action, "PENDING", "COORDINATED", note="")
        self._post_status(request, action, "COORDINATED", "IN_PROGRESS")
        action.refresh_from_db()
        self.assertEqual(action.execution_status, "PENDING")
        self.assertEqual(action.progress_events.count(), 1)

    def test_update_denied_without_change_permission(self):
        request = self.make_request(delegation=self.north)
        action = self._form_create(request)
        self.client.force_login(self.other_user)
        response = self._post_status(request, action, "PENDING", "COORDINATED")
        self.assertIn(response.status_code, (403, 404))
        action.refresh_from_db()
        self.assertEqual(action.execution_status, "PENDING")

    def test_reopening_blocked_when_attention_closed(self):
        attention = self.make_attention(self.north)
        AttentionEntry.objects.filter(pk=attention.pk).update(status="CLOSED")
        request = self.make_request(delegation=self.north, attention=attention)
        action = self.make_action(
            request, executor_type="COMPANY", executor_name="CGE", execution_status="FINISHED",
        )
        self.client.force_login(self.user)
        response = self._post_status(request, action, "FINISHED", "PENDING", "Reparación incompleta")
        self.assertEqual(response.status_code, 302)
        action.refresh_from_db()
        self.assertEqual(action.execution_status, "FINISHED")
        self.assertEqual(CitizenRequestActionProgress.objects.filter(action=action).count(), 0)

    def test_completed_action_cannot_be_edited_until_reopened(self):
        request = self.make_request(delegation=self.north)
        action = self.make_action(
            request, executor_type="COMPANY", executor_name="CGE", execution_status="FINISHED",
        )
        form = CitizenRequestActionForm(
            data=self.action_form_data(
                executor_type="COMPANY", executor_name="CGE",
            ),
            instance=action, citizen_request=request, user=self.user,
        )
        self.assertFalse(form.is_valid())

    def test_changing_executor_keeps_audit_event(self):
        request = self.make_request(delegation=self.north)
        action = self._form_create(request)
        data = self.action_form_data(
            executor_type="COMPANY",
            executor_name="Empresa de mantenimiento",
            executor_contact="contacto@example.org",
            expected_execution_date="2026-11-26",
        )
        form = CitizenRequestActionForm(
            data=data, instance=action, citizen_request=request, user=self.user,
        )
        self.assertTrue(form.is_valid(), form.errors.as_json())
        form.save()
        action.refresh_from_db()
        self.assertEqual(action.executor_name, "Empresa de mantenimiento")
        self.assertEqual(action.progress_events.count(), 2)
        self.assertIn("Datos del ejecutor modificados", action.progress_events.last().note)

    def test_closed_attention_rejects_new_work_order(self):
        attention = self.make_attention(self.north)
        AttentionEntry.objects.filter(pk=attention.pk).update(status="CLOSED")
        request = self.make_request(delegation=self.north, attention=attention)
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("citizen_requests:create_request_action", args=(request.pk,)),
            self.action_form_data(executor_type="COMPANY", executor_name="CGE"),
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(CitizenRequestAction.objects.filter(request=request).exists())
