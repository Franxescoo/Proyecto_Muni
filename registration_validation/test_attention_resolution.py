from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db import IntegrityError
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import UserProfile
from monitoring_traceability.models import Audit
from organization.models import (
    Delegation,
    Employee,
    OrganizationRole,
    PositionFunction,
)

from .models import AttentionEntry, AttentionType, SubAttention


class AttentionResolutionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.north = Delegation.objects.create(
            code="RES-N",
            name="Delegación Norte",
            status="Active",
            scope="Urbana",
        )
        cls.south = Delegation.objects.create(
            code="RES-S",
            name="Delegación Sur",
            status="Active",
            scope="Rural",
        )
        cls.position = PositionFunction.objects.create(
            position_name="Operador de atención",
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
        cls.attention_type = AttentionType.objects.create(
            code="RES-AT",
            name="Orientación",
            status=True,
        )
        cls.sub_attention = SubAttention.objects.create(
            code="RES-SUB",
            name="Consulta",
            attention_type=cls.attention_type,
            status=True,
        )

        User = get_user_model()
        cls.user = User.objects.create_user(
            username="resolver-norte",
            password="test-password",
        )
        cls.profile = UserProfile.objects.create(
            user=cls.user,
            employee_code="RES-USER-N",
            employee=cls.employee,
            delegation=cls.north,
        )
        cls.profile.authorized_delegations.add(cls.north, cls.south)

        cls.group = Group.objects.create(name="Resolver atenciones Norte")
        cls.role = OrganizationRole.objects.create(
            group=cls.group,
            delegation=cls.north,
        )
        cls.role.application_delegations.add(cls.north, cls.south)
        cls.change_permission = Permission.objects.get(
            content_type__app_label="registration_validation",
            codename="change_attentionentry",
        )
        cls.view_permission = Permission.objects.get(
            content_type__app_label="registration_validation",
            codename="view_attentionentry",
        )
        cls.group.permissions.add(
            cls.change_permission,
            cls.view_permission,
        )
        cls.user.groups.add(cls.group)

    def setUp(self):
        self.client.force_login(self.user)

    def resolve_url(self, entry):
        return reverse(
            "registration:attention_entry_resolve",
            args=[entry.pk],
        )

    def make_entry(self, status="NEW", delegation=None):
        delegation = delegation or self.north
        employee = (
            self.employee
            if delegation.pk == self.north.pk
            else Employee.objects.create(
                name=f"Funcionario {delegation.pk}",
                delegation=delegation,
                position=self.position,
                roles="Atención",
                status="Active",
            )
        )
        return AttentionEntry.objects.create(
            requester=f"Solicitante {status} {delegation.pk}",
            attention_type=self.attention_type,
            sub_attention=self.sub_attention,
            description="Solicitud de atención",
            delegation=delegation,
            responsible_employee=employee,
            status=status,
        )

    def test_new_pending_and_in_progress_attentions_are_resolved(self):
        for initial_status in ("NEW", "PENDING", "IN_PROGRESS"):
            with self.subTest(initial_status=initial_status):
                entry = self.make_entry(status=initial_status)

                response = self.client.post(self.resolve_url(entry))

                self.assertRedirects(
                    response,
                    reverse("registration:attention_entry_list"),
                    fetch_redirect_response=False,
                )
                entry.refresh_from_db()
                self.assertEqual(entry.status, "RESOLVED")
                audit = Audit.objects.get(
                    entity="AttentionEntry",
                    object_identifier=str(entry.pk),
                    event="Resolución de atención",
                )
                self.assertEqual(audit.user_id, self.employee.pk)
                self.assertEqual(
                    audit.previous_value,
                    {"status": initial_status},
                )
                self.assertEqual(
                    audit.new_value,
                    {
                        "status": "RESOLVED",
                        "resolved_by": self.user.username,
                        "resolved_by_user_id": self.user.pk,
                    },
                )
                self.assertIsNotNone(audit.event_date)

    def test_resolved_closed_and_rejected_attentions_cannot_be_resolved(self):
        for initial_status in ("RESOLVED", "CLOSED", "REJECTED"):
            with self.subTest(initial_status=initial_status):
                entry = self.make_entry(status=initial_status)

                response = self.client.post(self.resolve_url(entry))

                self.assertRedirects(
                    response,
                    reverse("registration:attention_entry_list"),
                    fetch_redirect_response=False,
                )
                entry.refresh_from_db()
                self.assertEqual(entry.status, initial_status)
                self.assertFalse(
                    Audit.objects.filter(
                        entity="AttentionEntry",
                        object_identifier=str(entry.pk),
                        event="Resolución de atención",
                    ).exists()
                )

    def test_user_without_change_permission_is_rejected(self):
        self.group.permissions.remove(self.change_permission)

        response = self.client.post(
            self.resolve_url(self.make_entry())
        )

        self.assertEqual(response.status_code, 403)

    def test_user_without_authorized_role_scope_is_rejected(self):
        User = get_user_model()
        user = User.objects.create_user(
            username="resolver-sin-alcance",
            password="test-password",
        )
        profile = UserProfile.objects.create(
            user=user,
            employee_code="RES-USER-NO-SCOPE",
            delegation=self.north,
        )
        profile.authorized_delegations.add(self.north)
        group = Group.objects.create(name="Resolver fuera de alcance")
        role = OrganizationRole.objects.create(
            group=group,
            delegation=self.south,
        )
        role.application_delegations.add(self.south)
        group.permissions.add(self.change_permission)
        user.groups.add(group)
        self.client.force_login(user)

        response = self.client.post(
            self.resolve_url(self.make_entry())
        )

        self.assertEqual(response.status_code, 403)

    def test_user_without_an_authorized_delegation_is_rejected(self):
        User = get_user_model()
        user = User.objects.create_user(
            username="resolver-sin-delegacion",
            password="test-password",
        )
        UserProfile.objects.create(
            user=user,
            employee_code="RES-USER-NO-DELEGATION",
        )
        group = Group.objects.create(name="Resolver sin delegación")
        role = OrganizationRole.objects.create(
            group=group,
            delegation=self.north,
        )
        role.application_delegations.add(self.north)
        group.permissions.add(self.change_permission)
        user.groups.add(group)
        self.client.force_login(user)

        response = self.client.post(
            self.resolve_url(self.make_entry())
        )

        self.assertEqual(response.status_code, 403)

    def test_attention_in_another_delegation_is_not_resolvable(self):
        entry = self.make_entry(status="NEW", delegation=self.south)

        response = self.client.post(self.resolve_url(entry))

        self.assertEqual(response.status_code, 404)
        entry.refresh_from_db()
        self.assertEqual(entry.status, "NEW")
        self.assertFalse(
            Audit.objects.filter(
                entity="AttentionEntry",
                object_identifier=str(entry.pk),
                event="Resolución de atención",
            ).exists()
        )

    def test_resolution_route_requires_post(self):
        response = self.client.get(
            self.resolve_url(self.make_entry())
        )

        self.assertEqual(response.status_code, 405)

    def test_resolution_form_is_protected_by_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)

        response = client.post(
            self.resolve_url(self.make_entry())
        )

        self.assertEqual(response.status_code, 403)

    def test_audit_failure_rolls_back_attention_status(self):
        entry = self.make_entry(status="IN_PROGRESS")

        with patch(
            "registration_validation.views.Audit.objects.create",
            side_effect=IntegrityError("audit insert failed"),
        ):
            response = self.client.post(self.resolve_url(entry))

        self.assertRedirects(
            response,
            reverse("registration:attention_entry_list"),
            fetch_redirect_response=False,
        )
        entry.refresh_from_db()
        self.assertEqual(entry.status, "IN_PROGRESS")
        self.assertFalse(
            Audit.objects.filter(
                entity="AttentionEntry",
                object_identifier=str(entry.pk),
                event="Resolución de atención",
            ).exists()
        )

    def test_list_only_shows_resolve_button_for_resolvable_statuses(self):
        for status in (
            "NEW",
            "PENDING",
            "IN_PROGRESS",
            "RESOLVED",
            "CLOSED",
            "REJECTED",
        ):
            self.make_entry(status=status)

        response = self.client.get(
            reverse("registration:attention_entry_list")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'class="js-resolve-attention-entry m-0"',
            count=3,
        )
