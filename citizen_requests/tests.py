from django.core.exceptions import ValidationError
from django.core import mail
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import UserProfile
from organization.models import Delegation
from registration_validation.models import AttentionEntry, AttentionType, SubAttention

from .models import CitizenRequest, RequestEvent


class CitizenRequestModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.delegation = Delegation.objects.create(
            code="CR-1",
            name="Delegación solicitudes",
            status="Active",
            scope="Urbana",
            commune="La Serena",
        )
        cls.attention_type = AttentionType.objects.create(
            code="CR-AT",
            name="Solicitud ciudadana",
        )
        cls.sub_attention = SubAttention.objects.create(
            code="CR-SUB",
            name="Orientación",
            attention_type=cls.attention_type,
        )

    def build_request(self, **kwargs):
        values = {
            "delegation": self.delegation,
            "requester_name": "Vecino",
            "requester_email": "",
            "requester_phone": "",
            "address": "Dirección 1",
            "subject": "Consulta",
            "description": "Descripción de la solicitud",
        }
        values.update(kwargs)
        return CitizenRequest(**values)

    def build_attention(self):
        return AttentionEntry.objects.create(
            requester="Vecino",
            attention_type=self.attention_type,
            sub_attention=self.sub_attention,
            description="Atención formal",
            delegation=self.delegation,
        )

    def test_citizen_without_email_is_invalid(self):
        request = self.build_request(origin="CITIZEN")

        with self.assertRaises(ValidationError) as context:
            request.full_clean()

        self.assertIn("requester_email", context.exception.message_dict)

    def test_citizen_with_invalid_email_is_invalid(self):
        request = self.build_request(
            origin="CITIZEN",
            requester_email="correo-invalido",
        )

        with self.assertRaises(ValidationError) as context:
            request.full_clean()

        self.assertIn("requester_email", context.exception.message_dict)

    def test_citizen_with_valid_email_is_allowed_and_trimmed(self):
        request = self.build_request(
            origin="CITIZEN",
            requester_email="  vecino@example.com  ",
        )

        request.full_clean()
        request.save()

        self.assertEqual(request.requester_email, "vecino@example.com")

    def test_direct_save_rejects_invalid_citizen_email(self):
        request = self.build_request(
            origin="CITIZEN",
            requester_email="correo-invalido",
        )

        with self.assertRaises(ValidationError):
            request.save()

        self.assertEqual(CitizenRequest.objects.count(), 0)

    def test_internal_request_without_email_is_allowed(self):
        request = self.build_request(origin="INTERNAL")

        request.full_clean()
        request.save()

        self.assertEqual(request.requester_email, "")

    def test_internal_request_can_keep_its_delegation(self):
        request = self.build_request(
            origin="INTERNAL",
            requester_email="",
            delegation=self.delegation,
        )

        request.full_clean()
        request.save()

        self.assertEqual(request.delegation_id, self.delegation.pk)

    def test_creation_does_not_create_attention_entry(self):
        request = self.build_request(
            origin="CITIZEN",
            requester_email="vecino@example.com",
        )

        request.save()

        self.assertIsNone(request.attention_entry_id)
        self.assertEqual(AttentionEntry.objects.count(), 0)

    def test_tracking_codes_are_unique(self):
        first = self.build_request(
            origin="CITIZEN",
            requester_email="first@example.com",
        )
        second = self.build_request(
            origin="CITIZEN",
            requester_email="second@example.com",
        )

        first.save()
        second.save()

        self.assertIsNotNone(first.tracking_code)
        self.assertIsNotNone(second.tracking_code)
        self.assertNotEqual(first.tracking_code, second.tracking_code)

    def test_request_can_be_linked_to_existing_attention(self):
        attention = self.build_attention()
        request = self.build_request(
            origin="CITIZEN",
            requester_email="vecino@example.com",
            attention_entry=attention,
        )

        request.save()

        self.assertEqual(request.attention_entry_id, attention.pk)
        self.assertEqual(attention.citizen_request.pk, request.pk)

    def test_attention_cannot_be_linked_to_two_requests(self):
        attention = self.build_attention()
        first = self.build_request(
            origin="CITIZEN",
            requester_email="first@example.com",
            attention_entry=attention,
        )
        second = self.build_request(
            origin="CITIZEN",
            requester_email="second@example.com",
            attention_entry=attention,
        )

        first.save()

        with self.assertRaises(IntegrityError):
            second.save()

    def test_public_event_can_have_no_actor(self):
        request = self.build_request(origin="INTERNAL")
        request.save()

        event = RequestEvent.objects.create(
            request=request,
            actor=None,
            observation="Solicitud recibida desde el portal.",
            previous_status="",
            new_status="NEW",
        )

        self.assertIsNone(event.actor_id)


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class PublicCitizenRequestViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.delegation = Delegation.objects.create(
            code="PUBLIC-1",
            name="Delegación pública",
            status="Active",
            scope="Urbana",
            commune="La Serena",
        )
        cls.disabled_delegation = Delegation.objects.create(
            code="PUBLIC-2",
            name="Delegación deshabilitada",
            status="Inactive",
            scope="Urbana",
            commune="La Serena",
        )

    def setUp(self):
        self.url = reverse("citizen_requests:register_public_request")
        self.data = {
            "requester_name": "Vecino Portal",
            "requester_email": "vecino@example.com",
            "requester_phone": "+56 9 1234 5678",
            "address": "Calle 1",
            "subject": "Consulta",
            "description": "Descripción desde el portal.",
        }

    def test_public_request_can_be_created_without_login(self):
        response = self.client.post(self.url, self.data)

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        request = CitizenRequest.objects.get()

        self.assertEqual(payload["result"], "success")
        self.assertEqual(payload["tracking_code"], str(request.tracking_code))
        self.assertEqual(request.origin, "CITIZEN")
        self.assertEqual(request.status, "NEW")
        self.assertIsNone(request.delegation_id)
        self.assertIsNone(request.assigned_to_id)
        self.assertIsNone(request.attention_entry_id)
        self.assertFalse(request._state.adding)
        self.assertEqual(AttentionEntry.objects.count(), 0)

    def test_only_post_is_allowed(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 405)

    def test_empty_email_is_rejected(self):
        data = {**self.data, "requester_email": "   "}

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, 400)
        self.assertIn("requester_email", response.json()["errors"])
        self.assertEqual(CitizenRequest.objects.count(), 0)

    def test_invalid_email_is_rejected(self):
        data = {**self.data, "requester_email": "no-es-correo"}

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, 400)
        self.assertIn("requester_email", response.json()["errors"])
        self.assertEqual(CitizenRequest.objects.count(), 0)

    def test_required_fields_are_rejected_when_empty(self):
        data = {field: "" for field in self.data}
        data["delegation"] = ""

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, 400)
        errors = response.json()["errors"]
        for field in (
            "requester_name",
            "requester_email",
            "address",
            "subject",
            "description",
        ):
            self.assertIn(field, errors)

    def test_public_form_does_not_expose_delegation(self):
        from .forms import CitizenRequestForm

        self.assertNotIn("delegation", CitizenRequestForm().fields)

    def test_public_delegation_is_ignored(self):
        data = {
            **self.data,
            "delegation": self.delegation.pk,
            "origin": "INTERNAL",
            "status": "CLOSED",
            "assigned_to": "999999",
            "attention_entry": "999999",
            "tracking_code": "00000000-0000-0000-0000-000000000001",
        }

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, 201)
        request = CitizenRequest.objects.get()
        self.assertEqual(request.origin, "CITIZEN")
        self.assertEqual(request.status, "NEW")
        self.assertIsNone(request.delegation_id)
        self.assertIsNone(request.assigned_to_id)
        self.assertIsNone(request.attention_entry_id)

    def test_confirmation_email_contains_tracking_code(self):
        response = self.client.post(self.url, self.data)

        request = CitizenRequest.objects.get()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].to,
            ["vecino@example.com"],
        )
        self.assertIn(str(request.tracking_code), mail.outbox[0].body)
        self.assertTrue(response.json()["email_sent"])

    def test_invalid_form_does_not_send_email(self):
        response = self.client.post(
            self.url,
            {**self.data, "requester_email": "invalido"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(EMAIL_BACKEND="citizen_requests.tests.FailingEmailBackend")
    def test_request_is_kept_when_email_sending_fails(self):
        response = self.client.post(self.url, self.data)

        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.json()["email_sent"])
        self.assertTrue(
            CitizenRequest.objects.filter(
                requester_email="vecino@example.com",
            ).exists()
        )

    def test_csrf_protects_anonymous_post(self):
        client = Client(enforce_csrf_checks=True)

        response = client.post(self.url, self.data)

        self.assertEqual(response.status_code, 403)


class FailingEmailBackend:
    def send_messages(self, email_messages):
        raise OSError("SMTP unavailable")


@override_settings(DEBUG=True)
class RequestInboxTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.north = Delegation.objects.create(
            code="INBOX-N",
            name="Norte",
            status="Active",
            scope="Urbana",
            commune="La Serena",
        )
        cls.south = Delegation.objects.create(
            code="INBOX-S",
            name="Sur",
            status="Active",
            scope="Rural",
            commune="La Serena",
        )
        cls.other = Delegation.objects.create(
            code="INBOX-O",
            name="Otra",
            status="Active",
            scope="Rural",
            commune="La Serena",
        )
        cls.user = get_user_model().objects.create_user(
            username="bandeja-user",
            password="test-password-123",
        )
        cls.profile = UserProfile.objects.create(
            user=cls.user,
            employee_code="INBOX-USER",
            delegation=cls.north,
        )
        cls.profile.authorized_delegations.add(cls.north, cls.south)

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("citizen_requests:request_inbox")
        self.detail_url = reverse(
            "citizen_requests:request_detail",
            args=[0],
        )

    def make_request(self, suffix, delegation=None, status="NEW"):
        return CitizenRequest.objects.create(
            requester_name=f"Vecino {suffix}",
            requester_email=f"vecino{suffix}@example.com",
            address=f"Dirección {suffix}",
            subject=f"Asunto {suffix}",
            description=f"Descripción {suffix}",
            delegation=delegation,
            status=status,
        )

    def test_anonymous_user_is_denied(self):
        self.client.logout()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)

    def test_authenticated_user_sees_pending_and_active_delegation(self):
        pending = self.make_request("pendiente")
        north = self.make_request("norte", self.north)
        south = self.make_request("sur", self.south)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        pending_ids = {item["id"] for item in payload["pending"]["items"]}
        delegated_ids = {item["id"] for item in payload["delegated"]["items"]}
        self.assertIn(pending.pk, pending_ids)
        self.assertIn(north.pk, delegated_ids)
        self.assertNotIn(south.pk, delegated_ids)

    def test_changing_active_delegation_changes_results(self):
        north = self.make_request("norte-cambio", self.north)
        south = self.make_request("sur-cambio", self.south)

        self.client.post(
            reverse("accounts:change_active_delegation"),
            {"delegation": self.south.pk, "next": self.url},
        )
        response = self.client.get(self.url)

        delegated_ids = {
            item["id"] for item in response.json()["delegated"]["items"]
        }
        self.assertIn(south.pk, delegated_ids)
        self.assertNotIn(north.pk, delegated_ids)

    def test_detail_cannot_access_other_delegation(self):
        south = self.make_request("sur-detalle", self.south)

        response = self.client.get(
            self.detail_url.replace("/0/", f"/{south.pk}/")
        )

        self.assertEqual(response.status_code, 404)

    def test_detail_can_access_pending_request(self):
        pending = self.make_request("pend-detalle")

        response = self.client.get(
            self.detail_url.replace("/0/", f"/{pending.pk}/")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["request"]["tracking_code"],
            str(pending.tracking_code),
        )

    def test_detail_includes_request_events_in_chronological_order(self):
        request = self.make_request("historial", self.north)
        first = RequestEvent.objects.create(
            request=request,
            actor=self.user,
            observation=(
                "Derivación: Sin derivar -> Norte "
                f"(ID {self.north.pk}). Motivo: Primera derivación."
            ),
            previous_status="NEW",
            new_status="NEW",
        )
        second = RequestEvent.objects.create(
            request=request,
            actor=self.user,
            observation=(
                "Cambio de derivación: Norte -> Sur "
                f"(ID {self.north.pk} -> {self.south.pk}). "
                "Motivo: Corrección."
            ),
            previous_status="NEW",
            new_status="NEW",
        )

        response = self.client.get(
            self.detail_url.replace("/0/", f"/{request.pk}/")
        )

        events = response.json()["request"]["events"]
        self.assertEqual([event["type"] for event in events], [
            "Derivación",
            "Cambio de derivación",
        ])
        self.assertEqual(events[0]["actor"], self.user.get_username())
        self.assertEqual(events[0]["new_delegation"], "Norte")
        self.assertEqual(events[0]["reason"], "Primera derivación.")
        self.assertLess(events[0]["created_at"], events[1]["created_at"])

    def test_detail_does_not_include_events_from_other_request(self):
        request = self.make_request("historial-propio", self.north)
        other = self.make_request("historial-ajeno", self.north)
        RequestEvent.objects.create(
            request=other,
            actor=self.user,
            observation="Evento ajeno",
            previous_status="NEW",
            new_status="NEW",
        )

        response = self.client.get(
            self.detail_url.replace("/0/", f"/{request.pk}/")
        )

        self.assertEqual(response.json()["request"]["events"], [])

    def test_detail_without_events_returns_empty_history(self):
        request = self.make_request("sin-historial")

        response = self.client.get(
            self.detail_url.replace("/0/", f"/{request.pk}/")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["request"]["events"], [])

    def test_filters_and_pagination_apply_to_authorized_queryset(self):
        for index in range(12):
            self.make_request(f"pagina-{index}")
        self.make_request("busqueda", status="CLOSED")

        response = self.client.get(
            self.url,
            {"q": "busqueda", "status": "CLOSED"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()["pending"]
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["status_code"], "CLOSED")

        response = self.client.get(self.url)

        self.assertTrue(response.json()["pending"]["has_next"])

    def test_assign_pending_request_records_event_and_removes_pending(self):
        pending = self.make_request("derivar")

        response = self.client.post(
            reverse(
                "citizen_requests:assign_request",
                args=[pending.pk],
            ),
            {"delegation": self.north.pk, "reason": "Corresponde a Norte."},
        )

        self.assertEqual(response.status_code, 200)
        pending.refresh_from_db()
        self.assertEqual(pending.delegation_id, self.north.pk)
        self.assertEqual(pending.events.count(), 1)
        self.assertIn("Corresponde a Norte.", pending.events.get().observation)
        inbox = self.client.get(self.url).json()
        self.assertFalse(inbox["pending"]["items"])
        self.assertEqual(inbox["delegated"]["items"][0]["id"], pending.pk)
        self.assertIsNone(pending.attention_entry_id)

    def test_assign_rejects_inactive_delegation(self):
        inactive = Delegation.objects.create(
            code="INBOX-I",
            name="Inactiva",
            status="Inactive",
            scope="Urbana",
            commune="La Serena",
        )
        pending = self.make_request("inactiva")

        response = self.client.post(
            reverse("citizen_requests:assign_request", args=[pending.pk]),
            {"delegation": inactive.pk, "reason": "Motivo"},
        )

        self.assertEqual(response.status_code, 404)
        pending.refresh_from_db()
        self.assertIsNone(pending.delegation_id)

    def test_assign_requires_reason(self):
        pending = self.make_request("sin-motivo")

        response = self.client.post(
            reverse("citizen_requests:assign_request", args=[pending.pk]),
            {"delegation": self.north.pk, "reason": " "},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIsNone(
            CitizenRequest.objects.get(pk=pending.pk).delegation_id
        )

    def test_duplicate_assign_is_rejected(self):
        pending = self.make_request("duplicada")
        endpoint = reverse("citizen_requests:assign_request", args=[pending.pk])
        payload = {"delegation": self.north.pk, "reason": "Primera derivación."}

        self.assertEqual(self.client.post(endpoint, payload).status_code, 200)
        self.assertEqual(self.client.post(endpoint, payload).status_code, 404)
        self.assertEqual(pending.events.count(), 1)

    def test_change_delegation_records_event(self):
        assigned = self.make_request("cambiar", self.north)

        response = self.client.post(
            reverse(
                "citizen_requests:change_request_delegation",
                args=[assigned.pk],
            ),
            {"delegation": self.south.pk, "reason": "Corresponde a Sur."},
        )

        self.assertEqual(response.status_code, 200)
        assigned.refresh_from_db()
        self.assertEqual(assigned.delegation_id, self.south.pk)
        self.assertIn("Cambio de derivación", assigned.events.get().observation)

    def test_change_delegation_rejects_same_destination(self):
        assigned = self.make_request("misma", self.north)

        response = self.client.post(
            reverse(
                "citizen_requests:change_request_delegation",
                args=[assigned.pk],
            ),
            {"delegation": self.north.pk, "reason": "Motivo."},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            CitizenRequest.objects.get(pk=assigned.pk).delegation_id,
            self.north.pk,
        )

    def test_change_delegation_blocks_linked_attention(self):
        attention_type = AttentionType.objects.create(
            code="INBOX-AT",
            name="Atención bandeja",
        )
        sub_attention = SubAttention.objects.create(
            code="INBOX-SUB",
            name="Subatención bandeja",
            attention_type=attention_type,
        )
        attention = AttentionEntry.objects.create(
            requester="Vecino",
            attention_type=attention_type,
            sub_attention=sub_attention,
            description="Atención",
            delegation=self.north,
        )
        assigned = self.make_request(
            "con-atencion",
            self.north,
        )
        assigned.attention_entry = attention
        assigned.save(update_fields=("attention_entry",))

        response = self.client.post(
            reverse(
                "citizen_requests:change_request_delegation",
                args=[assigned.pk],
            ),
            {"delegation": self.south.pk, "reason": "Motivo."},
        )

        self.assertEqual(response.status_code, 409)
        assigned.refresh_from_db()
        self.assertEqual(assigned.delegation_id, self.north.pk)
        self.assertEqual(assigned.events.count(), 0)

    def test_operations_require_authentication_and_csrf(self):
        pending = self.make_request("seguridad")
        endpoint = reverse("citizen_requests:assign_request", args=[pending.pk])
        self.client.logout()
        self.assertEqual(
            self.client.post(
                endpoint,
                {"delegation": self.north.pk, "reason": "Motivo."},
            ).status_code,
            302,
        )

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        response = csrf_client.post(
            endpoint,
            {"delegation": self.north.pk, "reason": "Motivo."},
        )
        self.assertEqual(response.status_code, 403)

    @override_settings(DEBUG=False)
    def test_temporary_operations_are_blocked_when_debug_is_false(self):
        pending = self.make_request("produccion")

        response = self.client.post(
            reverse("citizen_requests:assign_request", args=[pending.pk]),
            {"delegation": self.north.pk, "reason": "Motivo."},
        )

        self.assertEqual(response.status_code, 403)
        self.assertIsNone(
            CitizenRequest.objects.get(pk=pending.pk).delegation_id
        )

    @override_settings(DEBUG=False)
    def test_pending_requests_are_hidden_when_debug_is_false(self):
        pending = self.make_request("pendiente-produccion")

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        pending_ids = {
            item["id"] for item in response.json()["pending"]["items"]
        }
        self.assertNotIn(pending.pk, pending_ids)
