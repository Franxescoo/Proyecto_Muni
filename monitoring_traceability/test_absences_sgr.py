from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.contrib.auth import get_user_model
from .absence_rules import effective_goal_values
from .absence_views import current_delegate_delegation


class AbsenceCalculationTests(SimpleTestCase):
    def setUp(self):
        self.goal = SimpleNamespace(
            objective_value=Decimal('30'), required_evidence_count=5,
            period=SimpleNamespace(start_date=date(2026, 11, 2), end_date=date(2026, 11, 13)),
            employee=SimpleNamespace(pk=4), measurement_item=SimpleNamespace(item_type='quantity'),
        )

    @patch('monitoring_traceability.absence_rules._available_dates', return_value=(10, 2, {date(2026, 11, 5), date(2026, 11, 6)}))
    def test_quantitative_goal_adjusted_without_mutation(self, ignored):
        original = self.goal.objective_value
        effective, required, progress, absent = effective_goal_values(self.goal, date(2026, 11, 13))
        self.assertEqual(effective, Decimal('24.00'))
        self.assertEqual(required, 4)
        self.assertEqual(progress, Decimal('100.00'))
        self.assertEqual(absent, 2)
        self.assertEqual(self.goal.objective_value, original)

    @patch('monitoring_traceability.absence_rules._available_dates', return_value=(10, 2, {date(2026, 11, 5), date(2026, 11, 6)}))
    def test_percentage_goal_keeps_percentage_target(self, ignored):
        self.goal.measurement_item.item_type = 'percentage'
        effective, required, _, _ = effective_goal_values(self.goal, date(2026, 11, 13))
        self.assertEqual(effective, Decimal('30'))
        self.assertEqual(required, 4)

    @patch('monitoring_traceability.absence_rules._available_dates', return_value=(10, 0, set()))
    def test_no_absence_keeps_all_targets(self, ignored):
        effective, required, _, absent = effective_goal_values(self.goal, date(2026, 11, 13))
        self.assertEqual(effective, Decimal('30'))
        self.assertEqual(required, 5)
        self.assertEqual(absent, 0)


class AbsenceAccessTests(TestCase):
    def test_no_profile_cannot_register_absence(self):
        user = get_user_model().objects.create_user(username='ausencia-sin-perfil', password='prueba123')
        self.assertIsNone(current_delegate_delegation(user))

    def test_anonymous_is_denied(self):
        from django.contrib.auth.models import AnonymousUser
        self.assertIsNone(current_delegate_delegation(AnonymousUser()))
