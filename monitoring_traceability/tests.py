from django.test import TestCase
from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, RequestFactory

from accounts.models import UserProfile
from organization.models import Delegation, Employee, PositionFunction
from planning_measurements.models import Goal, Period

from .admin import CommitmentAdmin, IndicatorAdmin
from .models import Commitment, Indicator


class TraceabilityModelsTest(TestCase):
	def setUp(self):
		self.north = Delegation.objects.create(
			name="North Delegation",
			status="Active",
			scope="North",
		)
		self.south = Delegation.objects.create(
			name="South Delegation",
			status="Active",
			scope="South",
		)
		position = PositionFunction.objects.create(
			position_name="Coordinator",
			measurable_items="Results",
			services="Planning",
			weightings="100",
			validity_start=date(2026, 1, 1),
			validity_end=date(2026, 12, 31),
		)
		self.north_employee = Employee.objects.create(
			delegation=self.north,
			position=position,
			name="North Employee",
			roles="Coordinator",
			status="Active",
		)
		self.south_employee = Employee.objects.create(
			delegation=self.south,
			position=position,
			name="South Employee",
			roles="Coordinator",
			status="Active",
		)
		period = Period.objects.create(
			start_date=date(2026, 1, 1),
			end_date=date(2026, 12, 31),
			computable_days=250,
			thresholds="Green >= 90",
			parameters_version="1.0",
		)
		self.north_goal = Goal.objects.create(
			period=period,
			employee=self.north_employee,
			position=position,
			item="North goal",
			objective_value=100,
			unit="percent",
			weight=50,
		)
		self.south_goal = Goal.objects.create(
			period=period,
			employee=self.south_employee,
			position=position,
			item="South goal",
			objective_value=100,
			unit="percent",
			weight=50,
		)
		Indicator.objects.create(
			goal=self.north_goal,
			employee=self.north_employee,
			expected_value=100,
			actual_progress=90,
			green_progress=90,
			difference=0,
			compliance=90,
			weighting=50,
			traffic_light="Green",
			calculation_date=date(2026, 6, 30),
		)
		Indicator.objects.create(
			goal=self.south_goal,
			employee=self.south_employee,
			expected_value=100,
			actual_progress=70,
			green_progress=90,
			difference=-20,
			compliance=70,
			weighting=50,
			traffic_light="Yellow",
			calculation_date=date(2026, 6, 30),
		)

	def test_indicator_rejects_employee_different_from_goal(self):
		indicator = Indicator(
			goal=self.north_goal,
			employee=self.south_employee,
			expected_value=100,
			actual_progress=90,
			green_progress=90,
			difference=0,
			compliance=90,
			weighting=50,
			traffic_light="Green",
			calculation_date=date(2026, 6, 30),
		)
		with self.assertRaises(ValidationError):
			indicator.full_clean()

	def test_commitment_rejects_responsible_from_other_delegation(self):
		commitment = Commitment(
			delegation=self.north,
			responsible=self.south_employee,
			requester="Requester",
			territory="North",
			commitment_date=date(2026, 7, 1),
		)
		with self.assertRaises(ValidationError):
			commitment.full_clean()

	def test_indicator_admin_scopes_by_profile_delegation(self):
		user = get_user_model().objects.create_user(
			username="north_operator",
			password="test-password",
			is_staff=True,
		)
		UserProfile.objects.create(
			user=user,
			delegation=self.north,
			employee_code="NORTH-001",
		)
		request = RequestFactory().get("/admin/")
		request.user = user
		model_admin = IndicatorAdmin(Indicator, None)

		queryset = model_admin.get_queryset(request)

		self.assertEqual(queryset.count(), 1)
		self.assertEqual(queryset.first().employee_id, self.north_employee.employee_id)

	def test_commitment_admin_without_profile_sees_nothing(self):
		user = get_user_model().objects.create_user(
			username="without_profile",
			password="test-password",
			is_staff=True,
		)
		request = RequestFactory().get("/admin/")
		request.user = user
		model_admin = CommitmentAdmin(Commitment, None)

		self.assertEqual(model_admin.get_queryset(request).count(), 0)
