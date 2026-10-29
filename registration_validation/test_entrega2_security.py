"""Autorización real por delegación y atribución de ingresos."""
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from accounts.models import UserProfile
from organization.models import Delegation, Employee, OrganizationRole, PositionFunction
from .models import AttentionEntry, AttentionType, SubAttention


class Entrega2SecurityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.north = Delegation.objects.create(
            code="N1", name="Norte", status="Active", scope="Urbana", commune="La Serena"
        )
        cls.south = Delegation.objects.create(
            code="S1", name="Sur", status="Active", scope="Rural", commune="La Serena"
        )
        cls.position = PositionFunction.objects.create(
            position_name="Operador", measurable_items="Atenciones", services="Ventanilla",
            weightings="100", validity_start=date(2026, 1, 1), validity_end=date(2027, 12, 31),
        )
        cls.employee_north = Employee.objects.create(
            name="Responsable Norte", delegation=cls.north, position=cls.position,
            roles="Atención", status="Active",
        )
        cls.employee_south = Employee.objects.create(
            name="Responsable Sur", delegation=cls.south, position=cls.position,
            roles="Atención", status="Active",
        )
        cls.type = AttentionType.objects.create(code="AT01", name="Social", status=True)
        cls.sub = SubAttention.objects.create(code="SUB01", name="Orientación", attention_type=cls.type, status=True)
        cls.user = get_user_model().objects.create_user(username="norte", password="Seguro2026+Clave")
        cls.profile = UserProfile.objects.create(
            user=cls.user, employee_code="UN01", delegation=cls.north, employee=cls.employee_north,
        )
        cls.profile.authorized_delegations.add(cls.north, cls.south)
        cls.group = Group.objects.create(name="Ingreso Norte")
        cls.role = OrganizationRole.objects.create(group=cls.group, delegation=cls.north)
        cls.role.application_delegations.add(cls.north)
        cls.group.permissions.set(Permission.objects.filter(
            content_type__app_label="registration_validation",
            codename__in=["view_attentionentry", "add_attentionentry", "change_attentionentry", "delete_attentionentry"],
        ))
        cls.user.groups.add(cls.group)
        cls.south_entry = AttentionEntry.objects.create(
            requester="Solicitante Sur", attention_type=cls.type, sub_attention=cls.sub,
            description="Consulta en Sur", delegation=cls.south,
            responsible_employee=cls.employee_south,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def _build_entry(self, **kwargs):
        values = {
            "requester": "Solicitante",
            "attention_type": self.type,
            "sub_attention": self.sub,
            "description": "Consulta",
            "delegation": self.north,
            "responsible_employee": self.employee_north,
        }
        values.update(kwargs)
        return AttentionEntry(**values)

    def test_citizen_without_email_is_invalid(self):
        entry = self._build_entry(origin="CITIZEN")

        with self.assertRaises(ValidationError) as context:
            entry.full_clean()

        self.assertIn("requester_email", context.exception.message_dict)

    def test_citizen_with_invalid_email_is_invalid(self):
        entry = self._build_entry(
            origin="CITIZEN",
            requester_email="correo-invalido",
        )

        with self.assertRaises(ValidationError) as context:
            entry.full_clean()

        self.assertIn("requester_email", context.exception.message_dict)

    def test_citizen_with_valid_email_is_allowed_and_trimmed(self):
        entry = self._build_entry(
            origin="CITIZEN",
            requester_email="  vecino@example.com  ",
        )

        entry.full_clean()
        entry.save()

        self.assertEqual(entry.requester_email, "vecino@example.com")

    def test_internal_without_email_is_allowed(self):
        entry = self._build_entry(origin="INTERNAL")

        entry.full_clean()

    def test_legacy_without_email_is_allowed(self):
        entry = self._build_entry(origin="LEGACY")

        entry.full_clean()

    def test_direct_save_rejects_invalid_citizen_email(self):
        entry = self._build_entry(
            origin="CITIZEN",
            requester_email="correo-invalido",
        )

        with self.assertRaises(ValidationError) as context:
            entry.save()

        self.assertIn("requester_email", context.exception.message_dict)
        self.assertFalse(
            AttentionEntry.objects.filter(requester="Solicitante").exists()
        )

    def test_partial_save_normalizes_citizen_email(self):
        entry = self._build_entry(
            origin="CITIZEN",
            requester_email="vecino@example.com",
        )
        entry.save()
        entry.requester_email = "  vecino@example.com  "
        entry.status = "PENDING"
        entry.save(update_fields=("status",))

        entry.refresh_from_db()
        self.assertEqual(entry.requester_email, "vecino@example.com")
        self.assertEqual(entry.status, "PENDING")

    def test_authorized_context_is_displayed_and_other_delegation_denied(self):
        resp = self.client.get(reverse("registration:attention_entry_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "Solicitante Sur")
        self.assertContains(resp, "Norte")
        response = self.client.get(reverse("registration:attention_entry_update", args=[self.south_entry.pk]))
        self.assertEqual(response.status_code, 404)

    def test_switch_context_not_granted_by_role_does_not_expand_access(self):
        response = self.client.post(reverse("accounts:change_active_delegation"), {
            "delegation": self.south.pk, "next": reverse("registration:attention_entry_list"),
        })
        self.assertEqual(response.status_code, 302)
        resp = self.client.get(reverse("registration:attention_entry_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "Solicitante Sur")
        self.assertEqual(self.client.session["sgr_active_delegation"], self.south.pk)

    def test_forged_active_delegation_id_is_rejected(self):
        other = Delegation.objects.create(code="E1", name="Este", status="Active", scope="Rural")
        res = self.client.post(reverse("accounts:change_active_delegation"), {"delegation": other.pk})
        self.assertEqual(res.status_code, 403)

    def test_create_attention_auto_sets_account_employee_and_delegation(self):
        response = self.client.post(reverse("registration:attention_entry_create"), {
            "requester": "Sol Norte", "attention_type": self.type.pk,
            "sub_attention": self.sub.pk, "description": "Solicita orientación",
            "delegation": self.south.pk,  # forged value is ignored
            "responsible_employee": self.employee_south.pk,  # forged value is ignored
        })
        self.assertEqual(response.status_code, 302)
        attention = AttentionEntry.objects.get(requester="Sol Norte")
        self.assertEqual(attention.registered_by_id, self.user.pk)
        self.assertEqual(attention.responsible_employee_id, self.employee_north.pk)
        self.assertEqual(attention.delegation_id, self.north.pk)

    def test_no_change_permission_rejects_direct_edit(self):
        self.group.permissions.remove(Permission.objects.get(
            content_type__app_label="registration_validation", codename="change_attentionentry"
        ))
        self.user = get_user_model().objects.get(pk=self.user.pk)  # discard cached permissions
        self.client.force_login(self.user)
        record = AttentionEntry.objects.create(
            requester="Sol Norte 2", attention_type=self.type, sub_attention=self.sub,
            description="Consulta", delegation=self.north, responsible_employee=self.employee_north,
        )
        response = self.client.get(reverse("registration:attention_entry_update", args=[record.pk]))
        self.assertEqual(response.status_code, 403)

    def test_no_delete_scope_even_if_account_has_delete_via_outside_role(self):
        second = Group.objects.create(name="Borrado Sur")
        role = OrganizationRole.objects.create(group=second, delegation=self.south)
        role.application_delegations.add(self.south)
        second.permissions.add(Permission.objects.get(
            content_type__app_label="registration_validation", codename="delete_attentionentry"
        ))
        # Remove deletion permission from the north group, leaving view north / delete south.
        self.group.permissions.remove(Permission.objects.get(
            content_type__app_label="registration_validation", codename="delete_attentionentry"
        ))
        self.user.groups.add(second)
        self.user = get_user_model().objects.get(pk=self.user.pk)
        self.client.force_login(self.user)
        rec = AttentionEntry.objects.create(
            requester="Otra atención norte", attention_type=self.type, sub_attention=self.sub,
            description="Consulta", delegation=self.north, responsible_employee=self.employee_north,
        )
        res = self.client.post(reverse("registration:attention_entry_delete", args=[rec.pk]))
        self.assertEqual(res.status_code, 404)
        rec.refresh_from_db()
        self.assertIsNone(rec.deleted_at)

    def test_employee_view_only_cannot_open_edit_and_cannot_view_south(self):
        view_employee = Permission.objects.get(
            content_type__app_label="organization", codename="view_employee"
        )
        self.group.permissions.add(view_employee)
        self.user = get_user_model().objects.get(pk=self.user.pk)
        self.client.force_login(self.user)
        list_response = self.client.get(reverse("organization:employee_list"))
        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, "Responsable Norte")
        self.assertNotContains(list_response, "Responsable Sur")
        detail = self.client.get(reverse("organization:employee_list"), {
            "modal": "view", "id": self.employee_south.pk,
        })
        self.assertEqual(detail.status_code, 404)
        edit = self.client.get(reverse("organization:employee_list"), {
            "modal": "edit", "id": self.employee_north.pk,
        })
        self.assertEqual(edit.status_code, 403)

    def test_monitoring_requires_explicit_view_permission(self):
        for path in ("/monitoring/indicadores/", "/monitoring/compromisos/", "/monitoring/auditoria/"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 403)
