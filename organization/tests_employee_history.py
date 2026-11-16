"""Auditoría de empleado/cuenta integrados sin superusuario."""
from datetime import date
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse
from accounts.models import UserProfile
from organization.employee_history import employee_snapshot, record_employee_change
from organization.models import Delegation, Employee, EmployeeHistory, PositionFunction, OrganizationRole


class IndividualEmployeeHistoryTests(TestCase):
    def setUp(self):
        self.delegation = Delegation.objects.create(name="Centro", status="Active", scope="Urbano")
        self.other = Delegation.objects.create(name="Sur", status="Active", scope="Rural")
        position = PositionFunction.objects.create(
            position_name="Territorial", measurable_items="Atenciones", services="Servicio",
            weightings="100%", validity_start=date(2026,1,1), validity_end=date(2027,1,1),
        )
        self.employee = Employee.objects.create(name="Ana", delegation=self.delegation,
            position=position, roles="Funciones", status="Active")
        self.user = get_user_model().objects.create_user(username="revisor_hist", password="test-only-password")
        self.profile = UserProfile.objects.create(user=self.user, employee=self.employee,
            employee_code="HIST-01", delegation=self.delegation)
        self.profile.authorized_delegations.add(self.delegation)
        group = Group.objects.create(name="Consultor historial")
        OrganizationRole.objects.create(group=group, delegation=self.delegation, description="Consulta")
        group.permissions.add(Permission.objects.get(content_type__app_label="organization", codename="view_employee"))
        self.user.groups.add(group)

    def test_audit_is_one_timeline_for_employee_and_linked_account(self):
        before = employee_snapshot(self.employee)
        self.employee.name = "Ana María"
        self.employee.save(update_fields=["name","updated_at"])
        event = record_employee_change(self.employee, self.user, "Modificación", before)
        self.assertEqual(event.employee, self.employee)
        self.assertIn("Nombre", [x["label"] for x in event.changes])
        self.profile.user.email = "ana@example.test"
        self.profile.user.save(update_fields=["email"])
        event2 = record_employee_change(self.employee, self.user, "Cambio de cuenta", event.new_value)
        self.assertEqual(EmployeeHistory.objects.filter(employee=self.employee).count(), 2)
        self.assertIn("Correo", [x["label"] for x in event2.changes])

    def test_history_modal_requires_eligible_delegation(self):
        self.client.force_login(self.user)
        url = reverse("organization:employee_list")
        response = self.client.get(url, {"history":self.employee.pk})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Historial de Ana")
        foreign = Employee.objects.create(name="Otro", delegation=self.other,
            position=self.employee.position, roles="Funciones", status="Active")
        response = self.client.get(url, {"history":foreign.pk})
        self.assertEqual(response.status_code,404)

    def test_history_is_append_only(self):
        event = record_employee_change(self.employee, self.user, "Creación", {})
        event.event = "Alterado"
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError): event.save()
        with self.assertRaises(ValidationError): event.delete()
