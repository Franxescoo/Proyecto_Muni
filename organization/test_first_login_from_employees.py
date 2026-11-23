"""Pruebas específicas del flujo que crea usuarios desde Organización > Empleados."""
from datetime import date
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase

from organization.models import Delegation, Employee, OrganizationRole, PositionFunction
from organization.forms import EmployeeForm
from organization.views import _sync_employee_account


class EmployeePasswordFirstLoginTests(TestCase):
    def setUp(self):
        self.delegation = Delegation.objects.create(
            code='PRIMER-INGRESO', name='Delegación de prueba',
            address='Dirección de prueba', commune='La Serena',
            status='Active', scope='Comunal',
        )
        self.position = PositionFunction.objects.create(
            position_name='Cargo temporal', measurable_items='', services='',
            weightings='', validity_start=date(2026, 1, 1),
            validity_end=date(2027, 1, 1),
        )
        self.role = Group.objects.create(name='Rol de prueba de primer ingreso')
        OrganizationRole.objects.create(group=self.role, delegation=self.delegation)
        self.position.role_groups.add(self.role)
        self.employee = Employee.objects.create(
            delegation=self.delegation, position=self.position,
            name='Persona de prueba', roles='Atender solicitudes', status='Active',
        )

    def form(self, password, *, username='cuenta_desde_empleados'):
        return SimpleNamespace(cleaned_data={
            'username': username, 'password1': password,
            'email': 'empleados-primer-ingreso@example.invalid',
            'employee_code': 'EMP-FIRST-LOGIN-001',
            'authorized_delegations': [self.delegation],
        })

    def test_new_employee_account_requires_password_change_and_keeps_roles(self):
        _sync_employee_account(self.employee, self.form('Temporal#DesdeEmpleados2026'))
        user = get_user_model().objects.get(username='cuenta_desde_empleados')
        self.assertTrue(user.check_password('Temporal#DesdeEmpleados2026'))
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.is_staff)
        self.assertEqual(user.profile.employee_id, self.employee.pk)
        self.assertTrue(user.profile.must_change_password)
        self.assertQuerySetEqual(user.groups.all(), [self.role], transform=lambda value: value)

    def test_edit_without_new_password_does_not_force_a_new_change(self):
        _sync_employee_account(self.employee, self.form('Temporal#DesdeEmpleados2026'))
        user = get_user_model().objects.get(username='cuenta_desde_empleados')
        profile = user.profile
        profile.must_change_password = False
        profile.save(update_fields=['must_change_password'])
        _sync_employee_account(self.employee, self.form(''))
        profile.refresh_from_db()
        self.assertFalse(profile.must_change_password)
        user.refresh_from_db()
        self.assertTrue(user.check_password('Temporal#DesdeEmpleados2026'))

    def test_new_password_from_employees_is_temporary_for_existing_account(self):
        _sync_employee_account(self.employee, self.form('Temporal#DesdeEmpleados2026'))
        profile = self.employee.user_profile
        profile.must_change_password = False
        profile.save(update_fields=['must_change_password'])
        _sync_employee_account(self.employee, self.form('OtraTemporal#DesdeEmpleados2026'))
        profile.refresh_from_db()
        self.assertTrue(profile.must_change_password)
        self.assertTrue(profile.user.check_password('OtraTemporal#DesdeEmpleados2026'))

    def test_employee_form_labels_temporary_password(self):
        form = EmployeeForm()
        self.assertIn('temporal', form.fields['password1'].label.lower())
        self.assertIn('temporal', form.fields['password2'].label.lower())
