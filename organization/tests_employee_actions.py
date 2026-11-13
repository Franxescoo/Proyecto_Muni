"""Acciones por actor en todas las secciones de Organización."""
from datetime import date
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from accounts.models import UserProfile
from organization.employee_history import organization_snapshot, record_organization_action
from organization.models import Delegation, Employee, EmployeeHistory, PositionFunction, OrganizationRole


class ActorHistoryTests(TestCase):
    def setUp(self):
        self.delegation = Delegation.objects.create(name="Centro", status="Active", scope="Urbano")
        self.position = PositionFunction.objects.create(
            position_name="Inspector", measurable_items="Atenciones", services="Recepción",
            weightings="100%", validity_start=date(2026, 1, 1), validity_end=date(2027, 1, 1))
        self.employee = Employee.objects.create(
            name="Roberto", delegation=self.delegation, position=self.position,
            roles="Funcionario", status="Active")
        self.actor = get_user_model().objects.create_user(username="roberto", password="test-only")
        UserProfile.objects.create(user=self.actor, employee=self.employee,
                                   employee_code="ROB-01", delegation=self.delegation)

    def test_every_section_records_under_actor_employee(self):
        group = Group.objects.create(name="Evaluador")
        OrganizationRole.objects.create(group=group, description="Rol de evaluación")
        for section, obj in (("Delegaciones", self.delegation),
                             ("Empleados", self.employee),
                             ("Cargos y Funciones", self.position),
                             ("Roles y Permisos", group)):
            record_organization_action(self.actor, section, "Creó", obj)
        events = list(EmployeeHistory.objects.filter(employee=self.employee, event__startswith="Acción: "))
        self.assertEqual(len(events), 4)
        self.assertTrue(all(event.actor_id == self.actor.pk for event in events))
        self.assertTrue(any("Roles y Permisos" in event.event for event in events))

    def test_edit_records_old_and_new(self):
        before = organization_snapshot(self.delegation)
        self.delegation.name = "Norte"
        self.delegation.save(update_fields=["name", "updated_at"])
        event = record_organization_action(self.actor, "Delegaciones", "Modificó", self.delegation, before)
        self.assertIn("Nombre", [change["label"] for change in event.action_changes])
        self.assertEqual(event.employee, self.employee)

    def test_action_does_not_appear_as_change_received(self):
        record_organization_action(self.actor, "Delegaciones", "Creó", self.delegation)
        self.assertFalse(EmployeeHistory.objects.filter(employee=self.employee)
                         .exclude(event__startswith="Acción: ").exists())

    def test_unlinked_actor_is_not_assigned_to_other_employee(self):
        user = get_user_model().objects.create_user(username="unlinked", password="test-only")
        self.assertIsNone(record_organization_action(user, "Delegaciones", "Creó", self.delegation))
        self.assertEqual(EmployeeHistory.objects.count(), 0)
