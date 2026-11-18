from datetime import date, timedelta
from io import BytesIO
from tempfile import TemporaryDirectory
import uuid
import zipfile

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils.datastructures import MultiValueDict
from django.utils import timezone
from unittest.mock import Mock, patch

from accounts.models import UserProfile
from organization.models import Delegation, Employee, PositionFunction
from registration_validation.models import (
    Activity,
    AttentionEntry,
    AttentionType,
    Evidence,
    SubAttention,
    Validation as EvidenceValidation,
)

from .forms import CitizenRequestActionForm
from .models import (
    CitizenRequest,
    CitizenRequestAction,
    CitizenRequestActionAttachment,
    RequestEvent,
)
from .storage import MAX_ACTION_ATTACHMENT_SIZE, PrivateActionStorage


class CitizenRequestActionModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.north = Delegation.objects.create(
            code="CRA-NORTH",
            name="Delegación Norte",
            status="Active",
            scope="Urbana",
        )
        cls.south = Delegation.objects.create(
            code="CRA-SOUTH",
            name="Delegación Sur",
            status="Active",
            scope="Rural",
        )
        cls.position = PositionFunction.objects.create(
            position_name="Funcionario de gestiones",
            measurable_items="Atenciones",
            services="Ventanilla",
            weightings="100",
            validity_start=date(2026, 1, 1),
            validity_end=date(2027, 12, 31),
        )
        cls.north_employee = Employee.objects.create(
            name="Funcionario Norte",
            rut="CRA-EMP-001",
            delegation=cls.north,
            position=cls.position,
            roles="Gestiones",
            status="Active",
        )
        cls.other_north_employee = Employee.objects.create(
            name="Segundo funcionario Norte",
            rut="CRA-EMP-002",
            delegation=cls.north,
            position=cls.position,
            roles="Gestiones",
            status="Active",
        )
        cls.south_employee = Employee.objects.create(
            name="Funcionario Sur",
            rut="CRA-EMP-003",
            delegation=cls.south,
            position=cls.position,
            roles="Gestiones",
            status="Active",
        )
        cls.user = get_user_model().objects.create_user(
            username="request-action-user",
            password="test-password",
        )
        cls.other_user = get_user_model().objects.create_user(
            username="request-action-other",
            password="test-password",
        )
        cls.profile = UserProfile.objects.create(
            user=cls.user,
            employee_code="CRA-USER-001",
            delegation=cls.north,
        )
        cls.profile.authorized_delegations.add(cls.north)
        action_permissions = Permission.objects.filter(
            content_type__app_label="citizen_requests",
            codename__in=(
                "add_citizenrequestaction",
                "change_citizenrequestaction",
                "view_citizenrequestaction",
            ),
        )
        cls.user.user_permissions.add(*action_permissions)
        cls.attention_type = AttentionType.objects.create(
            code="CRA-ATT",
            name="Atención de prueba",
        )
        cls.sub_attention = SubAttention.objects.create(
            code="CRA-SUB",
            name="Subatención de prueba",
            attention_type=cls.attention_type,
        )

    def make_request(self, *, delegation=None, attention=None, subject="Solicitud"):
        request = CitizenRequest.objects.create(
            origin="INTERNAL",
            requester_name="Solicitante de prueba",
            requester_email="",
            address="Dirección de prueba",
            subject=subject,
            description="Descripción de prueba",
            delegation=delegation,
            attention_entry=attention,
        )
        return request

    def make_attention(self, delegation):
        return AttentionEntry.objects.create(
            origin="INTERNAL",
            requester="Solicitante de prueba",
            attention_type=self.attention_type,
            sub_attention=self.sub_attention,
            description="Atención de prueba",
            delegation=delegation,
        )

    def make_action(self, request, **overrides):
        values = {
            "request": request,
            "responsible": self.north_employee,
            "delegation": self.north,
            "registered_by": self.user,
            "action_type": "INSPECTION",
            "performed_at": timezone.now(),
            "description": "Se inspeccionó el lugar.",
        }
        values.update(overrides)
        return CitizenRequestAction.objects.create(**values)

    def action_form_data(self, responsible=None, **overrides):
        values = {
            "responsible": (responsible or self.north_employee).pk,
            "action_type": "INSPECTION",
            "performed_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
            "description": "Se inspeccionó el lugar.",
            "outcome": "Se requiere una reparación.",
        }
        values.update(overrides)
        return values

    def use_private_test_storage(self):
        temporary_directory = TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        file_field = CitizenRequestActionAttachment._meta.get_field("file")
        original_storage = file_field.storage
        file_field.storage = PrivateActionStorage(
            location=temporary_directory.name,
            file_permissions_mode=0o600,
            directory_permissions_mode=0o700,
        )
        self.addCleanup(setattr, file_field, "storage", original_storage)

    def uploaded_pdf(self, name="informe.pdf", content=b"%PDF-1.4\nprueba"):
        return SimpleUploadedFile(
            name,
            content,
            content_type="application/octet-stream",
        )

    def test_creates_action_without_requiring_attention_entry(self):
        request = self.make_request(delegation=self.north)

        action = self.make_action(request)

        self.assertEqual(action.request_id, request.pk)
        self.assertEqual(action.responsible_id, self.north_employee.pk)
        self.assertEqual(action.delegation_id, self.north.pk)
        self.assertEqual(action.registered_by_id, self.user.pk)
        self.assertEqual(request.actions.get(), action)

    def test_multiple_actions_keep_their_own_responsible_employee(self):
        request = self.make_request(delegation=self.north)

        first = self.make_action(request)
        second = self.make_action(
            request,
            responsible=self.other_north_employee,
            action_type="COORDINATION",
            description="Se coordinó la reparación.",
        )

        self.assertEqual(request.actions.count(), 2)
        self.assertEqual(first.responsible_id, self.north_employee.pk)
        self.assertEqual(second.responsible_id, self.other_north_employee.pk)

    def test_rejects_request_without_assigned_delegation(self):
        request = self.make_request()

        with self.assertRaises(ValidationError) as caught:
            self.make_action(request)

        self.assertIn("request", caught.exception.message_dict)

    def test_rejects_responsible_from_another_delegation(self):
        request = self.make_request(delegation=self.north)

        with self.assertRaises(ValidationError) as caught:
            self.make_action(request, responsible=self.south_employee)

        self.assertIn("responsible", caught.exception.message_dict)

    def test_rejects_delegation_different_from_request_delegation(self):
        request = self.make_request(delegation=self.north)

        with self.assertRaises(ValidationError) as caught:
            self.make_action(request, delegation=self.south)

        self.assertIn("delegation", caught.exception.message_dict)

    def test_rejects_delegation_mismatch_with_linked_attention(self):
        attention = self.make_attention(self.south)
        request = self.make_request(delegation=self.north, attention=attention)

        with self.assertRaises(ValidationError) as caught:
            self.make_action(request)

        self.assertIn("request", caught.exception.message_dict)

    def test_historical_delegation_survives_employee_delegation_change(self):
        request = self.make_request(delegation=self.north)
        action = self.make_action(request)

        self.north_employee.delegation = self.south
        self.north_employee.save(update_fields=("delegation", "updated_at"))
        action.outcome = "La inspección quedó registrada."
        action.save(update_fields=("outcome", "updated_at"))

        action.refresh_from_db()
        self.assertEqual(action.delegation_id, self.north.pk)
        self.assertEqual(action.responsible_id, self.north_employee.pk)

    def test_existing_action_cannot_move_to_another_request(self):
        request = self.make_request(delegation=self.north)
        other_request = self.make_request(
            delegation=self.north,
            subject="Otra solicitud",
        )
        action = self.make_action(request)
        action.request = other_request

        with self.assertRaises(ValidationError) as caught:
            action.save()

        self.assertIn("request", caught.exception.message_dict)
        action.refresh_from_db()
        self.assertEqual(action.request_id, request.pk)

    def test_historical_delegation_and_registrant_cannot_be_changed(self):
        request = self.make_request(delegation=self.north)
        action = self.make_action(request)

        action.delegation = self.south
        with self.assertRaises(ValidationError) as caught:
            action.save()
        self.assertIn("delegation", caught.exception.message_dict)

        action.refresh_from_db()
        action.registered_by = self.other_user
        with self.assertRaises(ValidationError) as caught:
            action.save()
        self.assertIn("registered_by", caught.exception.message_dict)

    def test_update_fields_preserves_immutable_historical_relations(self):
        request = self.make_request(delegation=self.north)
        other_request = self.make_request(
            delegation=self.north,
            subject="Otra solicitud",
        )
        action = self.make_action(request)
        action.request = other_request
        action.delegation = self.south
        action.registered_by = self.other_user
        action.description = "Descripción actualizada."

        action.save(update_fields=("description", "updated_at"))

        action.refresh_from_db()
        self.assertEqual(action.request_id, request.pk)
        self.assertEqual(action.delegation_id, self.north.pk)
        self.assertEqual(action.registered_by_id, self.user.pk)
        self.assertEqual(action.description, "Descripción actualizada.")

    def test_new_actions_do_not_create_or_modify_indicator_records(self):
        request = self.make_request(delegation=self.north)
        before = (
            Activity.objects.count(),
            Evidence.objects.count(),
            EvidenceValidation.objects.count(),
        )

        self.make_action(request)

        after = (
            Activity.objects.count(),
            Evidence.objects.count(),
            EvidenceValidation.objects.count(),
        )
        self.assertEqual(after, before)

    def test_request_events_and_action_relations_coexist(self):
        request = self.make_request(delegation=self.north)
        event = RequestEvent.objects.create(
            request=request,
            actor=self.user,
            observation="Solicitud derivada.",
            previous_status="NEW",
            new_status="NEW",
        )

        action = self.make_action(request)

        self.assertEqual(request.events.get(), event)
        self.assertEqual(request.actions.get(), action)

    def test_model_does_not_define_delete_permission(self):
        self.assertEqual(
            set(CitizenRequestAction._meta.default_permissions),
            {"add", "change", "view"},
        )

    def test_form_creates_action_and_assigns_protected_fields(self):
        request = self.make_request(delegation=self.north)
        form = CitizenRequestActionForm(
            data=self.action_form_data(),
            citizen_request=request,
            user=self.user,
        )

        self.assertTrue(form.is_valid(), form.errors)
        action = form.save()

        self.assertEqual(action.request_id, request.pk)
        self.assertEqual(action.delegation_id, self.north.pk)
        self.assertEqual(action.registered_by_id, self.user.pk)
        self.assertEqual(action.responsible_id, self.north_employee.pk)
        self.assertNotIn("request", form.fields)
        self.assertNotIn("delegation", form.fields)
        self.assertNotIn("registered_by", form.fields)

    def test_form_edits_action_without_changing_original_relations(self):
        request = self.make_request(delegation=self.north)
        action = self.make_action(request)
        self.north_employee.delegation = self.south
        self.north_employee.save(update_fields=("delegation", "updated_at"))
        form = CitizenRequestActionForm(
            data=self.action_form_data(
                responsible=self.north_employee,
                action_type="VERIFICATION",
                description="Se verificó la reparación.",
            ),
            instance=action,
            citizen_request=request,
            user=self.user,
        )

        self.assertTrue(form.is_valid(), form.errors)
        updated = form.save()

        self.assertEqual(updated.request_id, request.pk)
        self.assertEqual(updated.delegation_id, self.north.pk)
        self.assertEqual(updated.registered_by_id, self.user.pk)
        self.assertEqual(updated.responsible_id, self.north_employee.pk)
        self.assertEqual(updated.action_type, "VERIFICATION")

    def test_responsible_selector_is_limited_to_authorized_delegation(self):
        request = self.make_request(delegation=self.north)
        form = CitizenRequestActionForm(
            citizen_request=request,
            user=self.user,
        )

        responsible_ids = set(
            form.fields["responsible"].queryset.values_list("pk", flat=True)
        )
        self.assertEqual(
            responsible_ids,
            {self.north_employee.pk, self.other_north_employee.pk},
        )

    def test_form_rejects_responsible_from_another_delegation(self):
        request = self.make_request(delegation=self.north)
        form = CitizenRequestActionForm(
            data=self.action_form_data(responsible=self.south_employee),
            citizen_request=request,
            user=self.user,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("responsible", form.errors)

    def test_form_ignores_posted_protected_fields(self):
        request = self.make_request(delegation=self.north)
        forged_request = self.make_request(
            delegation=self.south,
            subject="Solicitud manipulada",
        )
        form_data = self.action_form_data()
        form_data.update(
            {
                "request": forged_request.pk,
                "delegation": self.south.pk,
                "registered_by": self.other_user.pk,
            }
        )
        form = CitizenRequestActionForm(
            data=form_data,
            citizen_request=request,
            user=self.user,
        )

        self.assertTrue(form.is_valid(), form.errors)
        action = form.save()

        self.assertEqual(action.request_id, request.pk)
        self.assertEqual(action.delegation_id, self.north.pk)
        self.assertEqual(action.registered_by_id, self.user.pk)

    def test_form_rejects_request_without_delegation(self):
        request = self.make_request()
        form = CitizenRequestActionForm(
            data=self.action_form_data(),
            citizen_request=request,
            user=self.user,
        )

        self.assertFalse(form.is_valid())
        self.assertTrue(form.non_field_errors())

    def test_form_rejects_request_with_inconsistent_attention(self):
        attention = self.make_attention(self.south)
        request = self.make_request(delegation=self.north, attention=attention)
        form = CitizenRequestActionForm(
            data=self.action_form_data(),
            citizen_request=request,
            user=self.user,
        )

        self.assertFalse(form.is_valid())
        self.assertTrue(form.non_field_errors())

    def test_form_rejects_edit_for_different_authorized_request(self):
        request = self.make_request(delegation=self.north)
        other_request = self.make_request(
            delegation=self.north,
            subject="Otra solicitud",
        )
        action = self.make_action(request)
        form = CitizenRequestActionForm(
            data=self.action_form_data(),
            instance=action,
            citizen_request=other_request,
            user=self.user,
        )

        self.assertFalse(form.is_valid())
        self.assertTrue(form.non_field_errors())

    def test_authorized_user_can_list_actions_for_request(self):
        citizen_request = self.make_request(delegation=self.north)
        first = self.make_action(citizen_request)
        second = self.make_action(
            citizen_request,
            action_type="COORDINATION",
            description="Se coordinó la reparación.",
        )
        self.client.force_login(self.user)

        response = self.client.get(
            reverse(
                "citizen_requests:request_action_list",
                args=(citizen_request.pk,),
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(response.context["actions"]),
            [first, second],
        )
        self.assertContains(response, "Se inspeccionó el lugar.")
        self.assertContains(response, "Se coordinó la reparación.")

    def test_request_detail_merges_events_and_actions_in_chronological_order(self):
        citizen_request = self.make_request(delegation=self.north)
        base_time = timezone.now() - timedelta(hours=2)
        earlier_event = RequestEvent.objects.create(
            request=citizen_request,
            actor=self.user,
            observation="Derivación administrativa.",
            previous_status="NEW",
            new_status="NEW",
        )
        tied_event = RequestEvent.objects.create(
            request=citizen_request,
            actor=self.user,
            observation="Cambio administrativo con empate.",
            previous_status="NEW",
            new_status="NEW",
        )
        RequestEvent.objects.filter(pk=earlier_event.pk).update(
            created_at=base_time
        )
        RequestEvent.objects.filter(pk=tied_event.pk).update(
            created_at=base_time + timedelta(minutes=5)
        )
        first_action = self.make_action(
            citizen_request,
            performed_at=base_time + timedelta(minutes=2),
            outcome="Se requiere una reparación.",
        )
        tied_action = self.make_action(
            citizen_request,
            action_type="VERIFICATION",
            performed_at=base_time + timedelta(minutes=5),
            description="Verificación posterior al evento empatado.",
        )
        self.client.force_login(self.user)

        response = self.client.get(
            reverse(
                "citizen_requests:request_detail",
                args=(citizen_request.pk,),
            )
        )

        self.assertEqual(response.status_code, 200)
        timeline = response.json()["request"]["timeline"]
        self.assertEqual(
            [(item["kind"], item["occurred_at"]) for item in timeline],
            [
                ("event", base_time.isoformat()),
                ("action", first_action.performed_at.isoformat()),
                ("event", (base_time + timedelta(minutes=5)).isoformat()),
                ("action", tied_action.performed_at.isoformat()),
            ],
        )
        self.assertEqual(
            timeline[1]["responsible"],
            self.north_employee.name,
        )
        self.assertEqual(timeline[1]["action_type"], "Inspección")
        self.assertEqual(
            timeline[1]["outcome"],
            "Se requiere una reparación.",
        )
        self.assertEqual(
            timeline[3]["description"],
            "Verificación posterior al evento empatado.",
        )
        self.assertEqual(
            [event["observation"] for event in response.json()["request"]["events"]],
            [
                "Derivación administrativa.",
                "Cambio administrativo con empate.",
            ],
        )

    def test_request_detail_timeline_includes_protected_action_attachments(self):
        self.use_private_test_storage()
        citizen_request = self.make_request(delegation=self.north)
        action = self.make_action(citizen_request)
        attachment = CitizenRequestActionAttachment(
            action=action,
            file=self.uploaded_pdf("timeline.pdf"),
            original_name="timeline.pdf",
            uploaded_by=self.user,
        )
        attachment.save()
        self.client.force_login(self.user)

        response = self.client.get(
            reverse(
                "citizen_requests:request_detail",
                args=(citizen_request.pk,),
            )
        )

        self.assertEqual(response.status_code, 200)
        action_item = response.json()["request"]["timeline"][0]
        self.assertEqual(action_item["attachments"][0]["name"], "timeline.pdf")
        self.assertEqual(
            action_item["attachments"][0]["url"],
            reverse(
                "citizen_requests:download_request_action_attachment",
                args=(citizen_request.pk, action.pk, attachment.pk),
            ),
        )
        self.assertEqual(action_item["attachments"][0]["type"], "PDF")
        self.assertEqual(
            action_item["attachments"][0]["size"],
            len(b"%PDF-1.4\nprueba"),
        )
        self.assertNotIn(attachment.file.name, response.content.decode())

    def test_request_detail_timeline_excludes_actions_from_other_requests(self):
        citizen_request = self.make_request(delegation=self.north)
        other_request = self.make_request(
            delegation=self.north,
            subject="Solicitud ajena",
        )
        self.make_action(
            other_request,
            description="Esta gestión no corresponde a la solicitud consultada.",
        )
        self.client.force_login(self.user)

        response = self.client.get(
            reverse(
                "citizen_requests:request_detail",
                args=(citizen_request.pk,),
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["request"]["timeline"], [])
        self.assertNotContains(
            response,
            "Esta gestión no corresponde a la solicitud consultada.",
        )

    def test_request_detail_timeline_does_not_disclose_actions_without_view_permission(self):
        citizen_request = self.make_request(delegation=self.north)
        self.make_action(
            citizen_request,
            description="Observación interna restringida.",
        )
        UserProfile.objects.create(
            user=self.other_user,
            employee_code="CRA-OTHER-004",
            delegation=self.north,
        ).authorized_delegations.add(self.north)
        self.client.force_login(self.other_user)

        response = self.client.get(
            reverse(
                "citizen_requests:request_detail",
                args=(citizen_request.pk,),
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["request"]["can_view_actions"])
        self.assertEqual(response.json()["request"]["timeline"], [])
        self.assertNotContains(response, "Observación interna restringida.")

    def test_public_history_does_not_disclose_internal_action_notes(self):
        citizen_request = CitizenRequest.objects.create(
            origin="CITIZEN",
            requester_name="Solicitante público",
            requester_email="timeline-public@example.com",
            address="Dirección",
            subject="Solicitud pública",
            description="Descripción pública",
            delegation=self.north,
        )
        self.make_action(
            citizen_request,
            description="Nota interna que no debe ser pública.",
            outcome="Resultado reservado.",
        )
        session = self.client.session
        session["citizen_history_verified_v1"] = {
            "email": "timeline-public@example.com",
            "verified_at": int(timezone.now().timestamp()),
        }
        session.save()

        response = self.client.get(
            reverse("citizen_requests:public_request_history"),
            {"solicitud": str(citizen_request.tracking_code)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Nota interna que no debe ser pública.")
        self.assertNotContains(response, "Resultado reservado.")

    def test_user_without_view_permission_cannot_list_actions(self):
        citizen_request = self.make_request(delegation=self.north)
        self.client.force_login(self.other_user)

        response = self.client.get(
            reverse(
                "citizen_requests:request_action_list",
                args=(citizen_request.pk,),
            )
        )

        self.assertEqual(response.status_code, 403)

    def test_authorized_user_can_create_action_without_changing_protected_fields(self):
        citizen_request = self.make_request(delegation=self.north)
        forged_request = self.make_request(
            delegation=self.south,
            subject="Solicitud manipulada",
        )
        data = self.action_form_data()
        data.update(
            {
                "request": forged_request.pk,
                "delegation": self.south.pk,
                "registered_by": self.other_user.pk,
            }
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse(
                "citizen_requests:create_request_action",
                args=(citizen_request.pk,),
            ),
            data,
        )

        self.assertEqual(response.status_code, 302)
        action = CitizenRequestAction.objects.get(request=citizen_request)
        self.assertEqual(action.delegation_id, self.north.pk)
        self.assertEqual(action.registered_by_id, self.user.pk)
        self.assertEqual(action.request_id, citizen_request.pk)
        self.assertFalse(citizen_request.events.exists())

    def test_user_without_add_permission_cannot_create_action(self):
        citizen_request = self.make_request(delegation=self.north)
        self.client.force_login(self.other_user)

        response = self.client.post(
            reverse(
                "citizen_requests:create_request_action",
                args=(citizen_request.pk,),
            ),
            self.action_form_data(),
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(CitizenRequestAction.objects.filter(request=citizen_request).exists())

    def test_authorized_user_can_edit_action_and_keep_historical_relations(self):
        citizen_request = self.make_request(delegation=self.north)
        action = self.make_action(citizen_request)
        self.client.force_login(self.user)

        response = self.client.post(
            reverse(
                "citizen_requests:edit_request_action",
                args=(citizen_request.pk, action.pk),
            ),
            self.action_form_data(
                action_type="VERIFICATION",
                description="Se verificó la reparación.",
            ),
        )

        self.assertEqual(response.status_code, 302)
        action.refresh_from_db()
        self.assertEqual(action.action_type, "VERIFICATION")
        self.assertEqual(action.request_id, citizen_request.pk)
        self.assertEqual(action.delegation_id, self.north.pk)
        self.assertEqual(action.registered_by_id, self.user.pk)

    def test_user_without_change_permission_cannot_edit_action(self):
        citizen_request = self.make_request(delegation=self.north)
        action = self.make_action(citizen_request)
        UserProfile.objects.create(
            user=self.other_user,
            employee_code="CRA-OTHER-001",
            delegation=self.north,
        )
        self.other_user.profile.authorized_delegations.add(self.north)
        self.client.force_login(self.other_user)

        response = self.client.get(
            reverse(
                "citizen_requests:edit_request_action",
                args=(citizen_request.pk, action.pk),
            )
        )

        self.assertEqual(response.status_code, 403)

    def test_action_urls_reject_requests_from_another_delegation(self):
        citizen_request = self.make_request(delegation=self.south)
        action = self.make_action(
            self.make_request(delegation=self.north),
        )
        self.client.force_login(self.user)

        list_response = self.client.get(
            reverse(
                "citizen_requests:request_action_list",
                args=(citizen_request.pk,),
            )
        )
        create_response = self.client.get(
            reverse(
                "citizen_requests:create_request_action",
                args=(citizen_request.pk,),
            )
        )
        edit_response = self.client.get(
            reverse(
                "citizen_requests:edit_request_action",
                args=(citizen_request.pk, action.pk),
            )
        )

        self.assertEqual(list_response.status_code, 403)
        self.assertEqual(create_response.status_code, 403)
        self.assertEqual(edit_response.status_code, 403)

    def test_edit_rejects_action_id_from_another_request(self):
        citizen_request = self.make_request(delegation=self.north)
        other_request = self.make_request(
            delegation=self.north,
            subject="Otra solicitud",
        )
        action = self.make_action(other_request)
        self.client.force_login(self.user)

        response = self.client.get(
            reverse(
                "citizen_requests:edit_request_action",
                args=(citizen_request.pk, action.pk),
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_historical_action_is_read_only_after_request_delegation_changes(self):
        citizen_request = self.make_request(delegation=self.north)
        action = self.make_action(citizen_request)
        self.profile.authorized_delegations.add(self.south)
        citizen_request.delegation = self.south
        citizen_request.save(update_fields=("delegation", "updated_at"))
        self.client.force_login(self.user)
        session = self.client.session
        session["sgr_active_delegation"] = self.south.pk
        session.save()

        response = self.client.get(
            reverse(
                "citizen_requests:request_action_list",
                args=(citizen_request.pk,),
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["actions"]), [action])
        self.assertFalse(response.context["actions"][0].can_edit)

    def test_action_views_do_not_create_activity_evidence_or_validation(self):
        citizen_request = self.make_request(delegation=self.north)
        before = (
            Activity.objects.count(),
            Evidence.objects.count(),
            EvidenceValidation.objects.count(),
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse(
                "citizen_requests:create_request_action",
                args=(citizen_request.pk,),
            ),
            self.action_form_data(),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            (
                Activity.objects.count(),
                Evidence.objects.count(),
                EvidenceValidation.objects.count(),
            ),
            before,
        )

    def test_create_action_with_multiple_private_attachments(self):
        self.use_private_test_storage()
        citizen_request = self.make_request(delegation=self.north)
        self.client.force_login(self.user)
        data = self.action_form_data()
        data["attachments"] = [
            self.uploaded_pdf("informe inicial.pdf"),
            self.uploaded_pdf("informe final.pdf"),
        ]

        response = self.client.post(
            reverse(
                "citizen_requests:create_request_action",
                args=(citizen_request.pk,),
            ),
            data,
        )

        self.assertEqual(response.status_code, 302)
        action = CitizenRequestAction.objects.get(request=citizen_request)
        attachments = list(action.attachments.order_by("original_name"))
        self.assertEqual(len(attachments), 2)
        self.assertEqual(
            [attachment.original_name for attachment in attachments],
            ["informe_final.pdf", "informe_inicial.pdf"],
        )
        for attachment in attachments:
            self.assertNotIn(attachment.original_name, attachment.file.name)
            stored_stem = attachment.file.name.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            self.assertEqual(len(uuid.UUID(hex=stored_stem).hex), 32)
            with self.assertRaises(ValueError):
                attachment.file.url

    def test_create_action_without_attachments(self):
        citizen_request = self.make_request(delegation=self.north)
        self.client.force_login(self.user)

        response = self.client.post(
            reverse(
                "citizen_requests:create_request_action",
                args=(citizen_request.pk,),
            ),
            self.action_form_data(),
        )

        self.assertEqual(response.status_code, 302)
        action = CitizenRequestAction.objects.get(request=citizen_request)
        self.assertFalse(action.attachments.exists())
        self.assertFalse(citizen_request.events.exists())

    def test_attachment_validation_accepts_allowed_content_signatures(self):
        docx_content = BytesIO()
        with zipfile.ZipFile(docx_content, "w") as archive:
            archive.writestr("word/document.xml", "<document/>")
        valid_uploads = (
            ("valid.pdf", b"%PDF-1.4\ncontent"),
            ("valid.jpg", b"\xff\xd8\xffcontent"),
            ("valid.jpeg", b"\xff\xd8\xffcontent"),
            ("valid.png", b"\x89PNG\r\n\x1a\ncontent"),
            ("valid.doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1content"),
            ("valid.docx", docx_content.getvalue()),
        )

        for filename, content in valid_uploads:
            with self.subTest(filename=filename):
                form = CitizenRequestActionForm(
                    data=self.action_form_data(),
                    files=MultiValueDict(
                        {"attachments": [self.uploaded_pdf(filename, content)]}
                    ),
                    citizen_request=self.make_request(delegation=self.north),
                    user=self.user,
                )

                self.assertTrue(form.is_valid(), form.errors)

    def test_rejects_attachment_with_content_mismatched_to_extension(self):
        form = CitizenRequestActionForm(
            data=self.action_form_data(),
            files=MultiValueDict(
                {
                    "attachments": [
                        self.uploaded_pdf(
                            "looks-like-a-pdf.pdf",
                            b"\x89PNG\r\n\x1a\nnot a PDF",
                        )
                    ]
                }
            ),
            citizen_request=self.make_request(delegation=self.north),
            user=self.user,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("no coincide", str(form.errors["attachments"]))

    def test_edit_action_adds_attachments_without_removing_existing_ones(self):
        self.use_private_test_storage()
        citizen_request = self.make_request(delegation=self.north)
        self.client.force_login(self.user)
        create_data = self.action_form_data()
        create_data["attachments"] = [self.uploaded_pdf("anterior.pdf")]
        create_response = self.client.post(
            reverse(
                "citizen_requests:create_request_action",
                args=(citizen_request.pk,),
            ),
            create_data,
        )
        self.assertEqual(create_response.status_code, 302)
        action = CitizenRequestAction.objects.get(request=citizen_request)

        edit_data = self.action_form_data(description="Descripción editada.")
        edit_data["attachments"] = [self.uploaded_pdf("nuevo.pdf")]
        edit_response = self.client.post(
            reverse(
                "citizen_requests:edit_request_action",
                args=(citizen_request.pk, action.pk),
            ),
            edit_data,
        )

        self.assertEqual(edit_response.status_code, 302)
        self.assertEqual(
            set(action.attachments.values_list("original_name", flat=True)),
            {"anterior.pdf", "nuevo.pdf"},
        )

    def test_rejects_disallowed_attachment_extension(self):
        citizen_request = self.make_request(delegation=self.north)
        form = CitizenRequestActionForm(
            data=self.action_form_data(),
            files=MultiValueDict(
                {"attachments": [self.uploaded_pdf("programa.exe")]}
            ),
            citizen_request=citizen_request,
            user=self.user,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("attachments", form.errors)

    def test_rejects_attachment_exceeding_individual_size_limit(self):
        citizen_request = self.make_request(delegation=self.north)
        oversized_pdf = self.uploaded_pdf(
            content=b"%PDF-1.4\n" + b"x" * (MAX_ACTION_ATTACHMENT_SIZE + 1)
        )
        form = CitizenRequestActionForm(
            data=self.action_form_data(),
            files=MultiValueDict({"attachments": [oversized_pdf]}),
            citizen_request=citizen_request,
            user=self.user,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("50 MB", str(form.errors["attachments"]))

    def test_rejects_more_than_five_attachments(self):
        citizen_request = self.make_request(delegation=self.north)
        uploads = [
            self.uploaded_pdf(f"archivo-{index}.pdf")
            for index in range(6)
        ]
        form = CitizenRequestActionForm(
            data=self.action_form_data(),
            files=MultiValueDict({"attachments": uploads}),
            citizen_request=citizen_request,
            user=self.user,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("cinco", str(form.errors["attachments"]))

    def test_edit_rejects_attachment_count_above_five_including_existing_files(self):
        self.use_private_test_storage()
        citizen_request = self.make_request(delegation=self.north)
        self.client.force_login(self.user)
        create_data = self.action_form_data()
        create_data["attachments"] = [
            self.uploaded_pdf(f"archivo-{index}.pdf")
            for index in range(5)
        ]
        self.client.post(
            reverse(
                "citizen_requests:create_request_action",
                args=(citizen_request.pk,),
            ),
            create_data,
        )
        action = CitizenRequestAction.objects.get(request=citizen_request)
        edit_data = self.action_form_data()
        edit_data["attachments"] = [self.uploaded_pdf("sexto.pdf")]

        response = self.client.post(
            reverse(
                "citizen_requests:edit_request_action",
                args=(citizen_request.pk, action.pk),
            ),
            edit_data,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(action.attachments.count(), 5)

    def test_rejects_total_attachment_size_over_fifty_megabytes(self):
        citizen_request = self.make_request(delegation=self.north)
        action = self.make_action(citizen_request)
        existing = Mock()
        existing.file.size = MAX_ACTION_ATTACHMENT_SIZE - 1
        attachment_queryset = Mock()
        attachment_queryset.count.return_value = 1
        attachment_queryset.only.return_value = [existing]
        with patch(
            "citizen_requests.forms.CitizenRequestActionAttachment.objects.filter",
            return_value=attachment_queryset,
        ):
            form = CitizenRequestActionForm(
                data=self.action_form_data(),
                files=MultiValueDict(
                    {"attachments": [self.uploaded_pdf(content=b"%PDF-1.4\nx")]}
                ),
                instance=action,
                citizen_request=citizen_request,
                user=self.user,
            )

            self.assertFalse(form.is_valid())

        self.assertIn("50 MB", str(form.errors["attachments"]))

    def test_download_attachment_requires_permission_and_serves_private_file(self):
        self.use_private_test_storage()
        citizen_request = self.make_request(delegation=self.north)
        self.client.force_login(self.user)
        data = self.action_form_data()
        data["attachments"] = [self.uploaded_pdf("descarga segura.pdf")]
        self.client.post(
            reverse(
                "citizen_requests:create_request_action",
                args=(citizen_request.pk,),
            ),
            data,
        )
        attachment = CitizenRequestActionAttachment.objects.get(
            action__request=citizen_request,
        )

        response = self.client.get(
            reverse(
                "citizen_requests:download_request_action_attachment",
                args=(
                    citizen_request.pk,
                    attachment.action_id,
                    attachment.pk,
                ),
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertNotIn(attachment.file.name, response["Content-Disposition"])
        self.assertEqual(b"".join(response.streaming_content), b"%PDF-1.4\nprueba")
        response.close()

    def test_download_attachment_rejects_anonymous_user(self):
        citizen_request = self.make_request(delegation=self.north)

        response = self.client.get(
            reverse(
                "citizen_requests:download_request_action_attachment",
                args=(citizen_request.pk, 1, 1),
            )
        )

        self.assertEqual(response.status_code, 302)

    def test_download_attachment_rejects_user_without_view_permission(self):
        UserProfile.objects.create(
            user=self.other_user,
            employee_code="CRA-OTHER-002",
            delegation=self.north,
        ).authorized_delegations.add(self.north)
        citizen_request = self.make_request(delegation=self.north)
        self.client.force_login(self.other_user)

        response = self.client.get(
            reverse(
                "citizen_requests:download_request_action_attachment",
                args=(citizen_request.pk, 1, 1),
            )
        )

        self.assertEqual(response.status_code, 403)

    def test_download_attachment_rejects_another_delegation(self):
        UserProfile.objects.create(
            user=self.other_user,
            employee_code="CRA-OTHER-003",
            delegation=self.south,
        ).authorized_delegations.add(self.south)
        self.other_user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="citizen_requests",
                codename="view_citizenrequestaction",
            )
        )
        citizen_request = self.make_request(delegation=self.north)
        self.client.force_login(self.other_user)

        response = self.client.get(
            reverse(
                "citizen_requests:download_request_action_attachment",
                args=(citizen_request.pk, 1, 1),
            )
        )

        self.assertEqual(response.status_code, 403)

    def test_download_attachment_rejects_attachment_from_another_request(self):
        self.use_private_test_storage()
        citizen_request = self.make_request(delegation=self.north)
        other_request = self.make_request(
            delegation=self.north,
            subject="Otra solicitud",
        )
        action = self.make_action(other_request)
        attachment = CitizenRequestActionAttachment(
            action=action,
            file=self.uploaded_pdf(),
            original_name="privado.pdf",
            uploaded_by=self.user,
        )
        attachment.save()
        self.client.force_login(self.user)

        response = self.client.get(
            reverse(
                "citizen_requests:download_request_action_attachment",
                args=(citizen_request.pk, action.pk, attachment.pk),
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_list_shows_protected_download_link_without_physical_path(self):
        self.use_private_test_storage()
        citizen_request = self.make_request(delegation=self.north)
        action = self.make_action(citizen_request)
        attachment = CitizenRequestActionAttachment(
            action=action,
            file=self.uploaded_pdf("visible.pdf"),
            original_name="visible.pdf",
            uploaded_by=self.user,
        )
        attachment.save()
        self.client.force_login(self.user)

        response = self.client.get(
            reverse(
                "citizen_requests:request_action_list",
                args=(citizen_request.pk,),
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "visible.pdf")
        self.assertContains(
            response,
            reverse(
                "citizen_requests:download_request_action_attachment",
                args=(citizen_request.pk, action.pk, attachment.pk),
            ),
        )
        self.assertNotContains(response, attachment.file.name)

    def test_storage_failure_rolls_back_action_and_cleans_partial_file(self):
        self.use_private_test_storage()
        citizen_request = self.make_request(delegation=self.north)
        self.client.force_login(self.user)
        data = self.action_form_data()
        data["attachments"] = [self.uploaded_pdf()]
        original_save = PrivateActionStorage.save

        def save_then_fail(storage, name, content, max_length=None):
            original_save(storage, name, content, max_length)
            raise OSError("Fallo simulado de almacenamiento")

        with patch.object(PrivateActionStorage, "save", save_then_fail):
            response = self.client.post(
                reverse(
                    "citizen_requests:create_request_action",
                    args=(citizen_request.pk,),
                ),
                data,
            )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            CitizenRequestAction.objects.filter(request=citizen_request).exists()
        )
        storage = CitizenRequestActionAttachment._meta.get_field("file").storage
        _, files = storage.listdir("citizen_request_actions")
        self.assertEqual(files, [])

    def test_attachments_do_not_create_activity_evidence_or_validation(self):
        self.use_private_test_storage()
        citizen_request = self.make_request(delegation=self.north)
        before = (
            Activity.objects.count(),
            Evidence.objects.count(),
            EvidenceValidation.objects.count(),
        )
        self.client.force_login(self.user)
        data = self.action_form_data()
        data["attachments"] = [self.uploaded_pdf()]

        response = self.client.post(
            reverse(
                "citizen_requests:create_request_action",
                args=(citizen_request.pk,),
            ),
            data,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            (
                Activity.objects.count(),
                Evidence.objects.count(),
                EvidenceValidation.objects.count(),
            ),
            before,
        )
