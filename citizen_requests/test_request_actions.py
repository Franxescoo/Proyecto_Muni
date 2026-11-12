from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from organization.models import Delegation, Employee, PositionFunction
from registration_validation.models import (
    Activity,
    AttentionEntry,
    AttentionType,
    Evidence,
    SubAttention,
    Validation as EvidenceValidation,
)

from .models import CitizenRequest, CitizenRequestAction, RequestEvent


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
