from types import SimpleNamespace
from django.test import SimpleTestCase
from organization.assignment_rules import (
    delegation_available, position_available,
    validate_employee_assignment, validate_delegation_authorizations,
)

class ErrorForm:
    def __init__(self): self.errors = []
    def add_error(self, field, message): self.errors.append((field, message))

class OrganizationStage3RulesTests(SimpleTestCase):
    def delegation(self, pk, status, deleted_at=None):
        return SimpleNamespace(pk=pk, status=status, deleted_at=deleted_at)
    def position(self, pk, deleted_at=None):
        return SimpleNamespace(pk=pk, deleted_at=deleted_at)

    def test_inactive_delegation_rejected_for_new_employee(self):
        form = ErrorForm()
        validate_employee_assignment(form, self.delegation(3,"Inactive"), self.position(2))
        self.assertEqual(form.errors[0][0], "delegation")

    def test_inactive_historical_delegation_remains_editable(self):
        form = ErrorForm()
        previous = SimpleNamespace(delegation_id=3, position_id=2)
        validate_employee_assignment(form, self.delegation(3,"Inactive"), self.position(2), previous)
        self.assertFalse(form.errors)

    def test_archived_position_rejected_for_new_employee(self):
        form = ErrorForm()
        validate_employee_assignment(form, self.delegation(3,"Active"), self.position(2,"archived"))
        self.assertEqual(form.errors[0][0], "position")

    def test_new_account_delegation_cannot_be_inactive(self):
        form = ErrorForm()
        validate_delegation_authorizations(form, [self.delegation(3,"Inactive")])
        self.assertEqual(form.errors[0][0], "authorized_delegations")

    def test_unchanged_historical_account_authorization(self):
        form = ErrorForm()
        validate_delegation_authorizations(form, [self.delegation(3,"Inactive")], [3])
        self.assertFalse(form.errors)

    def test_active_and_archived_statuses(self):
        self.assertTrue(delegation_available(self.delegation(3,"Activo")))
        self.assertFalse(delegation_available(self.delegation(3,"Active","archived")))
        self.assertFalse(position_available(self.position(2,"archived")))

from django.contrib.auth.models import Group
from django.contrib.auth import get_user_model
from django.test import TestCase
from organization.forms import EmployeeForm as IntegratedEmployeeForm
from accounts.forms import AccountCreateForm, AccountEditForm
from accounts.models import UserProfile
from organization.models import Delegation, PositionFunction, Employee, OrganizationRole


class OrganizationStage3IntegrationTests(TestCase):
    """Comprobar selectores reales y preservación de referencias históricas."""

    @classmethod
    def setUpTestData(cls):
        cls.active = Delegation.objects.create(
            code='ST3-A', name='Delegación activa prueba', address='Dirección A',
            commune='La Serena', scope='Urbano', status='Active',
        )
        cls.inactive = Delegation.objects.create(
            code='ST3-I', name='Delegación inactiva prueba', address='Dirección I',
            commune='La Serena', scope='Rural', status='Inactive',
        )
        cls.current_position = PositionFunction.objects.create(
            position_name='Cargo de prueba', measurable_items='Prueba',
            services='Prueba', weightings='100', validity_start='2026-01-01',
            validity_end='2027-12-31',
        )
        cls.employee = Employee.objects.create(
            name='Empleado Histórico', delegation=cls.inactive,
            position=cls.current_position, roles='Funciones prueba', status='Active',
        )

    def test_employee_create_lists_only_active_delegations(self):
        form = IntegratedEmployeeForm()
        self.assertIn(self.active.pk, form.fields['delegation'].queryset.values_list('pk', flat=True))
        self.assertNotIn(self.inactive.pk, form.fields['delegation'].queryset.values_list('pk', flat=True))

    def test_historical_employee_remains_editable_in_form(self):
        form = IntegratedEmployeeForm(instance=self.employee)
        self.assertIn(self.inactive.pk, form.fields['delegation'].queryset.values_list('pk', flat=True))

    def test_account_create_does_not_offer_inactive_delegations(self):
        form = AccountCreateForm()
        self.assertNotIn(self.inactive.pk, form.fields['authorized_delegations'].queryset.values_list('pk', flat=True))
        self.assertIn(self.active.pk, form.fields['authorized_delegations'].queryset.values_list('pk', flat=True))

    def test_account_edit_retains_historical_authorizations(self):
        account = get_user_model().objects.create_user(username='stage3_user', password='test-strong-only')
        profile = UserProfile.objects.create(user=account, employee_code='ST3-USER',
                                            employee=self.employee, delegation=self.inactive)
        profile.authorized_delegations.add(self.inactive)
        form = AccountEditForm(instance=account)
        self.assertIn(self.inactive.pk, form.fields['authorized_delegations'].queryset.values_list('pk', flat=True))

    def test_role_without_delegation_has_safe_string(self):
        group = Group.objects.create(name='ST3 Rol')
        role = OrganizationRole.objects.create(group=group, description='Rol de prueba', delegation=None)
        self.assertEqual(str(role), 'ST3 Rol')

    def test_view_keeps_historical_delegation_inside_actor_scope(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from organization.views import _limit_form_choices
        form = IntegratedEmployeeForm(instance=self.employee)
        actor = SimpleNamespace(is_superuser=False)
        with patch('organization.views._delegation_ids', return_value={self.active.pk, self.inactive.pk}):
            _limit_form_choices(form, actor, 'organization.change_employee', respect_role_scope=False)
        selected = set(form.fields['delegation'].queryset.values_list('pk', flat=True))
        self.assertIn(self.active.pk, selected)
        self.assertIn(self.inactive.pk, selected)

    def test_archived_historical_position_is_selectable_only_on_existing_employee(self):
        from django.utils import timezone
        self.current_position.deleted_at = timezone.now()
        self.current_position.save(update_fields=['deleted_at'])
        create_form = IntegratedEmployeeForm()
        edit_form = IntegratedEmployeeForm(instance=self.employee)
        self.assertNotIn(self.current_position.pk,
                         create_form.fields['position'].queryset.values_list('pk', flat=True))
        self.assertIn(self.current_position.pk,
                      edit_form.fields['position'].queryset.values_list('pk', flat=True))
