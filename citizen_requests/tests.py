from datetime import date
import smtplib
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core import mail
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db import IntegrityError
from django.db import transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import UserProfile
from organization.models import (
    Delegation,
    Employee,
    OrganizationRole,
    PositionFunction,
)
from registration_validation.models import AttentionEntry, AttentionType, SubAttention

from .models import CitizenRequest, RequestEvent
from .views import _public_portal_url


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

    def test_anonymous_can_access_public_portal(self):
        response = self.client.get(
            reverse("citizen_requests:public_portal"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Portal Ciudadano")
        self.assertContains(response, "Ingresar solicitud")
        self.assertContains(response, "Consultar solicitud")

    def test_root_shows_public_portal_to_anonymous_visitors(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Portal Ciudadano")
        self.assertContains(response, "Iniciar sesión")
        self.assertContains(response, reverse("login"))
        self.assertNotContains(response, 'data-bs-target="#chatInstitucionalModal"')
        self.assertNotContains(response, 'data-bs-target="#solicitudesModal"')

    def test_public_portal_header_links_to_existing_login(self):
        response = self.client.get(
            reverse("citizen_requests:public_portal"),
        )

        self.assertContains(response, 'href="/accounts/login/"')
        self.assertContains(response, "Logo Municipalidad de La Serena")

    def test_public_tracking_query_returns_only_safe_request_data(self):
        citizen_request = CitizenRequest.objects.create(
            requester_name="Nombre privado",
            requester_email="privado@example.com",
            requester_phone="+56 9 9999 9999",
            address="Dirección privada",
            subject="Asunto visible",
            description="Descripción privada",
            origin="CITIZEN",
            delegation=None,
        )

        response = self.client.post(
            reverse("citizen_requests:public_portal"),
            {
                "tracking_form": "1",
                "tracking_code": str(citizen_request.tracking_code),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Asunto visible")
        self.assertContains(response, "Solicitud recibida")
        self.assertNotContains(response, "Nombre privado")
        self.assertNotContains(response, "privado@example.com")
        self.assertNotContains(response, "+56 9 9999 9999")
        self.assertNotContains(response, "Descripción privada")
        self.assertNotContains(response, f">{citizen_request.pk}<")
        self.assertEqual(CitizenRequest.objects.count(), 1)

    def test_public_tracking_query_rejects_invalid_and_unknown_codes(self):
        invalid_response = self.client.post(
            reverse("citizen_requests:public_portal"),
            {"tracking_form": "1", "tracking_code": "no-es-uuid"},
        )
        self.assertContains(
            invalid_response,
            "Revisa el código de seguimiento ingresado.",
        )

        unknown_response = self.client.post(
            reverse("citizen_requests:public_portal"),
            {
                "tracking_form": "1",
                "tracking_code": "00000000-0000-0000-0000-000000000001",
            },
        )
        self.assertContains(
            unknown_response,
            "No encontramos una solicitud con ese código",
        )

    def test_public_tracking_query_shows_derived_and_management_stages(self):
        citizen_request = CitizenRequest.objects.create(
            requester_name="Vecino",
            requester_email="vecino@example.com",
            address="Calle 1",
            subject="Derivada",
            description="Descripción",
            origin="CITIZEN",
            delegation=self.delegation,
        )
        response = self.client.post(
            reverse("citizen_requests:public_portal"),
            {
                "tracking_form": "1",
                "tracking_code": str(citizen_request.tracking_code),
            },
        )
        self.assertContains(response, "Derivada para revisión")

        attention_type = AttentionType.objects.create(
            code="PUBLIC-AT",
            name="Atención pública",
        )
        sub_attention = SubAttention.objects.create(
            code="PUBLIC-SUB",
            name="Seguimiento",
            attention_type=attention_type,
        )
        attention = AttentionEntry.objects.create(
            requester="Vecino",
            attention_type=attention_type,
            sub_attention=sub_attention,
            description="Atención interna",
            delegation=self.delegation,
        )
        citizen_request.attention_entry = attention
        citizen_request.save(update_fields=("attention_entry", "updated_at"))

        response = self.client.post(
            reverse("citizen_requests:public_portal"),
            {
                "tracking_form": "1",
                "tracking_code": str(citizen_request.tracking_code),
            },
        )
        self.assertContains(response, "En gestión")
        self.assertNotContains(response, "Cerrada")

    def test_public_tracking_query_does_not_claim_closed_without_closed_request(self):
        citizen_request = CitizenRequest.objects.create(
            requester_name="Vecino",
            requester_email="vecino@example.com",
            address="Calle 1",
            subject="En gestión",
            description="Descripción",
            origin="CITIZEN",
            delegation=self.delegation,
        )

        response = self.client.post(
            reverse("citizen_requests:public_portal"),
            {
                "tracking_form": "1",
                "tracking_code": str(citizen_request.tracking_code),
            },
        )

        self.assertContains(response, "Derivada para revisión")
        self.assertNotContains(response, ">Cerrada<")

    def test_html_registration_redirects_to_confirmation_without_duplicates(self):
        response = self.client.post(
            self.url,
            {**self.data, "portal_form": "1"},
        )

        request = CitizenRequest.objects.get()
        confirmation_url = reverse(
            "citizen_requests:public_request_confirmation",
            kwargs={"tracking_code": request.tracking_code},
        )
        self.assertRedirects(response, confirmation_url)
        self.assertContains(
            self.client.get(confirmation_url),
            str(request.tracking_code),
        )
        self.assertEqual(CitizenRequest.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

        self.client.get(confirmation_url)
        self.assertEqual(CitizenRequest.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_anonymous_cannot_access_request_inbox(self):
        response = self.client.get(
            reverse("citizen_requests:request_inbox"),
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

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

    @override_settings(
        DEBUG=True,
        PUBLIC_PORTAL_URL="http://127.0.0.1:8000/portal/",
    )
    def test_confirmation_email_contains_tracking_code(self):
        response = self.client.post(self.url, self.data)

        request = CitizenRequest.objects.get()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].to,
            ["vecino@example.com"],
        )
        self.assertIn(str(request.tracking_code), mail.outbox[0].body)
        self.assertIn("http://127.0.0.1:8000/portal/", mail.outbox[0].body)
        self.assertTrue(response.json()["email_sent"])

    @override_settings(
        PUBLIC_PORTAL_URL="https://sgr.municipio.cl/portal/",
    )
    def test_initial_email_uses_configured_public_portal_url(self):
        self.client.post(self.url, self.data)

        self.assertIn(
            "https://sgr.municipio.cl/portal/",
            mail.outbox[0].body,
        )

    @override_settings(
        DEBUG=False,
        PUBLIC_PORTAL_URL="https://sgr.municipio.cl/portal/",
    )
    def test_public_portal_url_accepts_configured_production_url(self):
        self.assertEqual(
            _public_portal_url(),
            "https://sgr.municipio.cl/portal/",
        )

    @override_settings(
        DEBUG=False,
        PUBLIC_PORTAL_URL="http://127.0.0.1:8000/portal/",
    )
    def test_public_portal_url_rejects_internal_production_url(self):
        self.assertIsNone(_public_portal_url())

    @override_settings(DEBUG=False, PUBLIC_PORTAL_URL="")
    def test_missing_public_portal_url_is_safe_in_production(self):
        self.assertIsNone(_public_portal_url())
        self.client.post(self.url, self.data)

        self.assertEqual(len(mail.outbox), 1)
        self.assertNotIn("localhost", mail.outbox[0].body)
        self.assertNotIn("127.0.0.1", mail.outbox[0].body)

    @override_settings(
        DEBUG=False,
        PUBLIC_PORTAL_URL="ftp://sgr.municipio.cl/portal/",
    )
    def test_malformed_public_portal_url_is_rejected(self):
        self.assertIsNone(_public_portal_url())

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
        cls.position = PositionFunction.objects.create(
            position_name="Operador",
            measurable_items="Atenciones",
            services="Ventanilla",
            weightings="100",
            validity_start=date(2026, 1, 1),
            validity_end=date(2027, 12, 31),
        )
        cls.employee = Employee.objects.create(
            name="Funcionario Norte",
            delegation=cls.north,
            position=cls.position,
            roles="Atención",
            status="Active",
        )
        cls.profile.employee = cls.employee
        cls.profile.save(update_fields=("employee",))
        cls.attention_type = AttentionType.objects.create(
            code="PASO6-AT",
            name="Orientación",
        )
        cls.sub_attention = SubAttention.objects.create(
            code="PASO6-SUB",
            name="Consulta",
            attention_type=cls.attention_type,
        )
        cls.group = Group.objects.create(name="Ingreso de atenciones")
        cls.role = OrganizationRole.objects.create(
            group=cls.group,
            delegation=cls.north,
        )
        cls.role.application_delegations.add(cls.north, cls.south)
        cls.group.permissions.set(
            Permission.objects.filter(
                content_type__app_label="registration_validation",
                codename__in=(
                    "add_attentionentry",
                    "view_attentionentry",
                ),
            )
        )
        cls.group.permissions.add(
            Permission.objects.get(
                content_type__app_label="citizen_requests",
                codename="derivar_solicitud",
            )
        )
        cls.user.groups.add(cls.group)

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

    def attention_url(self, request):
        return (
            f"{reverse('registration:attention_entry_create')}"
            f"?citizen_request={request.pk}"
        )

    def link_attention(self, citizen_request):
        attention = AttentionEntry.objects.create(
            requester=citizen_request.requester_name,
            requester_email=citizen_request.requester_email,
            requester_phone=citizen_request.requester_phone,
            address=citizen_request.address,
            subject=citizen_request.subject,
            description=citizen_request.description,
            delegation=citizen_request.delegation,
            attention_type=self.attention_type,
            sub_attention=self.sub_attention,
        )
        citizen_request.attention_entry = attention
        citizen_request.save(update_fields=("attention_entry", "updated_at"))
        return attention

    @patch("citizen_requests.signals.send_attention_notification")
    def test_first_attention_link_schedules_notification_after_commit(
        self,
        notification_mock,
    ):
        citizen_request = self.make_request("aviso-atencion", self.north)

        with self.captureOnCommitCallbacks(execute=True):
            attention = self.link_attention(citizen_request)

        notification_mock.assert_called_once_with(
            citizen_request.pk,
            citizen_request.requester_name,
            citizen_request.requester_email,
            str(citizen_request.tracking_code),
        )
        self.assertEqual(citizen_request.attention_entry_id, attention.pk)

    @patch("citizen_requests.signals.send_attention_notification")
    def test_repeated_attention_save_does_not_notify_again(
        self,
        notification_mock,
    ):
        citizen_request = self.make_request("atencion-repetida", self.north)

        with self.captureOnCommitCallbacks(execute=True):
            self.link_attention(citizen_request)
        notification_mock.reset_mock()

        with self.captureOnCommitCallbacks(execute=True):
            citizen_request.save(
                update_fields=("attention_entry", "updated_at"),
            )

        notification_mock.assert_not_called()

    @patch("citizen_requests.signals.send_attention_notification")
    def test_request_without_attention_does_not_notify(
        self,
        notification_mock,
    ):
        citizen_request = self.make_request("sin-atencion", self.north)
        citizen_request.save(update_fields=("updated_at",))
        notification_mock.assert_not_called()

    @patch("citizen_requests.signals.send_attention_notification")
    def test_rolled_back_attention_link_does_not_notify(
        self,
        notification_mock,
    ):
        citizen_request = self.make_request("rollback-atencion", self.north)

        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                self.link_attention(citizen_request)
                raise RuntimeError("rollback de prueba")

        notification_mock.assert_not_called()
        citizen_request.refresh_from_db()
        self.assertIsNone(citizen_request.attention_entry_id)

    @override_settings(PUBLIC_PORTAL_URL="https://sgr.municipio.cl/portal/")
    @patch("citizen_requests.notifications.send_mail")
    def test_attention_notification_has_recipient_code_and_public_url(
        self,
        send_mail_mock,
    ):
        citizen_request = self.make_request("correo-atencion", self.north)
        with self.captureOnCommitCallbacks(execute=True):
            self.link_attention(citizen_request)

        send_mail_mock.assert_called_once()
        kwargs = send_mail_mock.call_args.kwargs
        self.assertEqual(
            kwargs["recipient_list"],
            [citizen_request.requester_email],
        )
        self.assertIn(str(citizen_request.tracking_code), kwargs["message"])
        self.assertIn(
            "https://sgr.municipio.cl/portal/",
            kwargs["message"],
        )
        self.assertIn("Estado actual: En gestión.", kwargs["message"])

    @patch("citizen_requests.notifications.send_mail")
    def test_attention_smtp_failure_preserves_link(
        self,
        send_mail_mock,
    ):
        send_mail_mock.side_effect = smtplib.SMTPException("SMTP caído")
        citizen_request = self.make_request("fallo-atencion", self.north)

        with self.captureOnCommitCallbacks(execute=True):
            self.link_attention(citizen_request)

        citizen_request.refresh_from_db()
        self.assertIsNotNone(citizen_request.attention_entry_id)
        self.assertEqual(citizen_request.events.count(), 0)

    def test_create_attention_from_derived_request_copies_citizen_data(self):
        citizen_request = self.make_request("crear", self.north)

        response = self.client.post(
            self.attention_url(citizen_request),
            {
                "requester": citizen_request.requester_name,
                "attention_type": self.attention_type.pk,
                "sub_attention": self.sub_attention.pk,
                "description": citizen_request.description,
                "delegation": self.north.pk,
                "responsible_employee": self.employee.pk,
            },
        )

        self.assertEqual(response.status_code, 302)
        citizen_request.refresh_from_db()
        attention = citizen_request.attention_entry
        self.assertIsNotNone(attention)
        self.assertEqual(attention.requester_email, citizen_request.requester_email)
        self.assertEqual(attention.requester_phone, citizen_request.requester_phone)
        self.assertEqual(attention.subject, citizen_request.subject)
        self.assertEqual(attention.address, citizen_request.address)
        self.assertEqual(attention.origin, "CITIZEN")
        self.assertEqual(attention.delegation_id, self.north.pk)
        self.assertEqual(attention.registered_by_id, self.user.pk)
        self.assertEqual(citizen_request.events.count(), 1)
        self.assertEqual(
            self.client.get(
                self.detail_url.replace("/0/", f"/{citizen_request.pk}/")
            ).json()["request"]["events"][0]["type"],
            "Atención creada",
        )

    def test_create_attention_accepts_linked_employee_from_original_modal(self):
        citizen_request = self.make_request("funcionario-vinculado", self.north)

        response = self.client.post(
            self.attention_url(citizen_request),
            {
                "requester": citizen_request.requester_name,
                "attention_type": self.attention_type.pk,
                "sub_attention": self.sub_attention.pk,
                "description": citizen_request.description,
                "delegation": self.north.pk,
                "responsible_employee": self.employee.pk,
            },
        )

        self.assertEqual(response.status_code, 302)
        citizen_request.refresh_from_db()
        self.assertEqual(
            citizen_request.attention_entry.responsible_employee_id,
            self.employee.pk,
        )

    def test_create_attention_opens_original_registration_modal_with_prefill(self):
        citizen_request = self.make_request("modal", self.north)

        response = self.client.get(self.attention_url(citizen_request))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="attentionEntryModal"')
        self.assertContains(response, citizen_request.requester_name)
        self.assertContains(response, citizen_request.description)
        self.assertContains(response, citizen_request.requester_email)
        self.assertContains(response, citizen_request.subject)
        self.assertContains(
            response,
            f'name="citizen_request" value="{citizen_request.pk}"',
        )

    def test_create_attention_requires_permission_and_active_delegation(self):
        citizen_request = self.make_request("sin-permiso", self.north)
        self.group.permissions.remove(
            Permission.objects.get(
                content_type__app_label="registration_validation",
                codename="add_attentionentry",
            )
        )
        response = self.client.get(self.attention_url(citizen_request))
        self.assertEqual(response.status_code, 403)

        self.group.permissions.add(
            Permission.objects.get(
                content_type__app_label="registration_validation",
                codename="add_attentionentry",
            )
        )
        south_request = self.make_request("otra-delegacion", self.south)
        response = self.client.get(self.attention_url(south_request))
        self.assertEqual(response.status_code, 403)

    def test_pending_request_cannot_create_attention(self):
        citizen_request = self.make_request("pendiente")

        response = self.client.get(self.attention_url(citizen_request))

        self.assertEqual(response.status_code, 404)
        self.assertEqual(AttentionEntry.objects.count(), 0)

    def test_linked_attention_cannot_be_created_twice_and_can_be_viewed(self):
        citizen_request = self.make_request("duplicada", self.north)
        data = {
            "requester": citizen_request.requester_name,
            "attention_type": self.attention_type.pk,
            "sub_attention": self.sub_attention.pk,
            "description": citizen_request.description,
            "delegation": self.north.pk,
            "responsible_employee": self.employee.pk,
        }
        self.assertEqual(
            self.client.post(self.attention_url(citizen_request), data).status_code,
            302,
        )
        self.assertEqual(
            self.client.post(self.attention_url(citizen_request), data).status_code,
            403,
        )
        citizen_request.refresh_from_db()
        self.assertEqual(AttentionEntry.objects.count(), 1)
        self.assertEqual(citizen_request.events.count(), 1)
        view_url = reverse(
            "citizen_requests:view_attention_from_request",
            args=[citizen_request.pk],
        )
        response = self.client.get(view_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, citizen_request.subject)

    def test_view_attention_json_contains_read_only_details_and_codes(self):
        citizen_request = self.make_request("detalle", self.north)
        attention = AttentionEntry.objects.create(
            requester=citizen_request.requester_name,
            requester_email=citizen_request.requester_email,
            requester_phone=citizen_request.requester_phone,
            address=citizen_request.address,
            subject=citizen_request.subject,
            attention_type=self.attention_type,
            sub_attention=self.sub_attention,
            description=citizen_request.description,
            delegation=self.north,
            responsible_employee=self.employee,
        )
        citizen_request.attention_entry = attention
        citizen_request.save(update_fields=("attention_entry",))

        response = self.client.get(
            reverse(
                "citizen_requests:view_attention_from_request",
                args=[citizen_request.pk],
            )
            + "?format=json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()["attention"]
        self.assertEqual(data["tracking_code"], str(attention.tracking_code))
        self.assertEqual(
            data["request_tracking_code"],
            str(citizen_request.tracking_code),
        )
        self.assertEqual(data["requester_email"], citizen_request.requester_email)
        self.assertEqual(data["status"], attention.get_status_display())

    def test_creating_attention_does_not_change_citizen_request_data(self):
        citizen_request = self.make_request("inmutable", self.north)
        original = {
            "email": citizen_request.requester_email,
            "phone": citizen_request.requester_phone,
            "address": citizen_request.address,
            "subject": citizen_request.subject,
            "description": citizen_request.description,
        }

        response = self.client.post(
            self.attention_url(citizen_request),
            {
                "requester": "Otro nombre enviado",
                "requester_email": "otro@example.com",
                "requester_phone": "000",
                "address": "Otra dirección",
                "subject": "Otro asunto",
                "attention_type": self.attention_type.pk,
                "sub_attention": self.sub_attention.pk,
                "description": "Otra descripción",
                "delegation": self.north.pk,
                "responsible_employee": self.employee.pk,
            },
        )

        self.assertEqual(response.status_code, 302)
        citizen_request.refresh_from_db()
        self.assertEqual(citizen_request.requester_email, original["email"])
        self.assertEqual(citizen_request.requester_phone, original["phone"])
        self.assertEqual(citizen_request.address, original["address"])
        self.assertEqual(citizen_request.subject, original["subject"])
        self.assertEqual(citizen_request.description, original["description"])

    def test_inbox_exposes_create_and_view_attention_actions(self):
        available = self.make_request("disponible", self.north)
        linked = self.make_request("vinculada", self.north)
        linked.attention_entry = AttentionEntry.objects.create(
            requester=linked.requester_name,
            attention_type=self.attention_type,
            sub_attention=self.sub_attention,
            description=linked.description,
            delegation=self.north,
        )
        linked.save(update_fields=("attention_entry",))

        items = self.client.get(self.url).json()["delegated"]["items"]
        by_id = {item["id"]: item for item in items}
        self.assertTrue(by_id[available.pk]["can_create_attention"])
        self.assertTrue(by_id[linked.pk]["can_view_attention"])
        self.assertEqual(
            by_id[linked.pk]["attention_entry_id"],
            linked.attention_entry_id,
        )
        self.assertNotEqual(linked.pk, linked.attention_entry_id)
        self.assertEqual(
            reverse(
                "registration:attention_entry_detail",
                args=[by_id[linked.pk]["attention_entry_id"]],
            ),
            reverse(
                "registration:attention_entry_detail",
                args=[linked.attention_entry_id],
            ),
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
        self.assertEqual(payload["pending_count"], 1)

    def test_pending_count_endpoint_is_restricted_and_counts_only_unassigned(self):
        pending = self.make_request("conteo-pendiente")
        self.make_request("conteo-derivada", self.north)

        response = self.client.get(
            reverse("citizen_requests:pending_request_count"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"pending_count": 1})
        self.assertEqual(
            CitizenRequest.objects.get(pk=pending.pk).delegation_id,
            None,
        )

        self.client.logout()
        response = self.client.get(
            reverse("citizen_requests:pending_request_count"),
        )
        self.assertEqual(response.status_code, 302)

    def test_pending_count_updates_after_derivation(self):
        pending = self.make_request("conteo-derivacion")
        count_url = reverse("citizen_requests:pending_request_count")
        assign_url = reverse(
            "citizen_requests:assign_request",
            args=[pending.pk],
        )

        self.assertEqual(
            self.client.get(count_url).json()["pending_count"],
            1,
        )
        response = self.client.post(
            assign_url,
            {"delegation": self.north.pk, "reason": "Derivada."},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.client.get(count_url).json()["pending_count"],
            0,
        )

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
            {
                "delegation": self.north.pk,
                "reason": "Corresponde a Norte.",
            },
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

    @override_settings(
        PUBLIC_PORTAL_URL="http://127.0.0.1:8000/portal/",
    )
    @patch("citizen_requests.views.send_mail")
    def test_first_derivation_sends_tracking_notification_after_commit(
        self,
        send_mail_mock,
    ):
        pending = self.make_request("aviso-derivacion")
        endpoint = reverse(
            "citizen_requests:assign_request",
            args=[pending.pk],
        )

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                endpoint,
                {
                    "delegation": self.north.pk,
                    "reason": "Corresponde a Norte.",
                },
            )

        self.assertEqual(response.status_code, 200)
        send_mail_mock.assert_called_once()
        kwargs = send_mail_mock.call_args.kwargs
        self.assertIn("Actualización de su solicitud", kwargs["subject"])
        self.assertIn(str(pending.tracking_code), kwargs["message"])
        self.assertIn(
            "http://127.0.0.1:8000/portal/",
            kwargs["message"],
        )
        self.assertEqual(kwargs["recipient_list"], [pending.requester_email])
        self.assertEqual(pending.events.count(), 1)

    @override_settings(
        PUBLIC_PORTAL_URL="https://sgr.municipio.cl/portal/",
    )
    @patch("citizen_requests.views.send_mail")
    def test_derivation_email_uses_configured_public_portal_url(
        self,
        send_mail_mock,
    ):
        pending = self.make_request("aviso-url-publica")

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse(
                    "citizen_requests:assign_request",
                    args=[pending.pk],
                ),
                {
                    "delegation": self.north.pk,
                    "reason": "Derivación válida.",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "https://sgr.municipio.cl/portal/",
            send_mail_mock.call_args.kwargs["message"],
        )

    @patch("citizen_requests.views.send_mail")
    def test_derivation_email_failure_keeps_derivation_and_event(
        self,
        send_mail_mock,
    ):
        send_mail_mock.side_effect = smtplib.SMTPException("SMTP caído")
        pending = self.make_request("aviso-fallido")

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse(
                    "citizen_requests:assign_request",
                    args=[pending.pk],
                ),
                {
                    "delegation": self.north.pk,
                    "reason": "Derivación válida.",
                },
            )

        self.assertEqual(response.status_code, 200)
        pending.refresh_from_db()
        self.assertEqual(pending.delegation_id, self.north.pk)
        self.assertEqual(pending.events.count(), 1)
        send_mail_mock.assert_called_once()

    @patch("citizen_requests.views.send_mail")
    def test_repeated_derivation_does_not_send_duplicate_notification(
        self,
        send_mail_mock,
    ):
        pending = self.make_request("aviso-duplicado")
        endpoint = reverse(
            "citizen_requests:assign_request",
            args=[pending.pk],
        )
        payload = {
            "delegation": self.north.pk,
            "reason": "Primera derivación.",
        }

        with self.captureOnCommitCallbacks(execute=True):
            first_response = self.client.post(endpoint, payload)
        second_response = self.client.post(endpoint, payload)

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 404)
        send_mail_mock.assert_called_once()
        self.assertEqual(pending.events.count(), 1)

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
    def test_derivation_works_when_debug_is_false(self):
        pending = self.make_request("produccion")

        response = self.client.post(
            reverse("citizen_requests:assign_request", args=[pending.pk]),
            {"delegation": self.north.pk, "reason": "Motivo."},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            CitizenRequest.objects.get(pk=pending.pk).delegation_id,
            self.north.pk,
        )

    @override_settings(DEBUG=False)
    def test_pending_requests_are_visible_when_authorized_and_debug_is_false(self):
        pending = self.make_request("pendiente-produccion")

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        pending_ids = {
            item["id"] for item in response.json()["pending"]["items"]
        }
        self.assertIn(pending.pk, pending_ids)

    def test_user_without_derivation_permission_cannot_see_pending_requests(self):
        self.user.groups.remove(self.group)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["pending"]["items"], [])
        self.assertEqual(response.json()["pending_count"], 0)

    def test_user_without_derivation_permission_cannot_derive(self):
        self.user.groups.remove(self.group)
        pending = self.make_request("sin-permiso")
        response = self.client.post(
            reverse("citizen_requests:assign_request", args=[pending.pk]),
            {"delegation": self.north.pk, "reason": "Motivo"},
        )
        self.assertEqual(response.status_code, 403)
        pending.refresh_from_db()
        self.assertIsNone(pending.delegation_id)
