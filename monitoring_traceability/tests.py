from django.test import TestCase
from datetime import date

from django.contrib.auth import get_user_model
from django.core import management
from django.core.exceptions import ValidationError
from django.test import TestCase, RequestFactory

from accounts.models import UserProfile
from organization.models import Delegation, Employee, PositionFunction
from planning_measurements.models import Goal, Period
from registration_validation.models import Activity, Evidence, Validation

from .admin import AuditAdmin, CommitmentAdmin, IndicatorAdmin
from .models import Audit, Commitment, CommitmentComment, Indicator
from .services import recalculate_indicator_for_goal


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

	def test_indicator_recalculates_from_approved_evidence(self):
		activity = Activity.objects.create(
			goal=self.north_goal,
			author=self.north_employee,
			date=date(2026, 6, 20),
			request_problem="Request",
			action="Action",
			contact="Contact",
			phone="555",
		)
		evidence = Evidence.objects.create(
			code="EVID-TEST-001",
			activity=activity,
			author=self.north_employee,
			file_link="evidence/test",
			date="2026-06-21T10:00:00Z",
			review_status="Pending",
		)

		indicator = Indicator.objects.get(goal=self.north_goal)
		self.assertEqual(indicator.actual_progress, 0)

		Validation.objects.create(
			evidence=evidence,
			verifier=self.north_employee,
			decision="Approved",
			date="2026-06-22T10:00:00Z",
			result="Approved",
		)

		indicator.refresh_from_db()
		self.assertEqual(indicator.actual_progress, 1)
		self.assertEqual(indicator.compliance, 0)
		self.assertEqual(indicator.weighted_result, 0)
		self.assertEqual(indicator.traffic_light, "Red")

	def test_multiple_evidences_on_one_activity_count_once(self):
		activity = Activity.objects.create(
			goal=self.north_goal,
			author=self.north_employee,
			date=date(2026, 6, 20),
			request_problem="Request",
			action="Action",
			contact="Contact",
			phone="555",
		)
		for code in ("EVID-ONE-001", "EVID-ONE-002"):
			evidence = Evidence.objects.create(
				code=code,
				activity=activity,
				author=self.north_employee,
				file_link=f"evidence/{code}",
				date="2026-06-21T10:00:00Z",
				review_status="Pending",
			)
			Validation.objects.create(
				evidence=evidence,
				verifier=self.north_employee,
				decision="Approved",
				date="2026-06-22T10:00:00Z",
				result="Approved",
			)

		indicator = recalculate_indicator_for_goal(self.north_goal)

		self.assertEqual(indicator.approved_activities, 1)
		self.assertEqual(indicator.approved_evidences, 2)
		self.assertEqual(indicator.actual_progress, 2)
		self.assertEqual(indicator.compliance, 0)

		for number in range(3, 7):
			evidence = Evidence.objects.create(
				code=f"EVID-ONE-00{number}",
				activity=activity,
				author=self.north_employee,
				file_link=f"evidence/EVID-ONE-00{number}",
				date="2026-06-21T10:00:00Z",
				review_status="Pending",
			)
			Validation.objects.create(
				evidence=evidence,
				verifier=self.north_employee,
				decision="Approved",
				date="2026-06-22T10:00:00Z",
				result="Approved",
			)

		indicator = recalculate_indicator_for_goal(self.north_goal)

		self.assertEqual(indicator.approved_evidences, 5)
		self.assertEqual(indicator.actual_progress, 5)
		self.assertEqual(indicator.compliance, 100)

	def test_commitment_comments_preserve_author_and_text(self):
		commitment = Commitment.objects.create(
			delegation=self.north,
			responsible=self.north_employee,
			requester="Requester",
			territory="North",
			commitment_date=date(2026, 7, 1),
		)

		comment = CommitmentComment.objects.create(
			commitment=commitment,
			author=self.north_employee,
			text="Seguimiento realizado.",
		)

		self.assertEqual(comment.author, self.north_employee)
		self.assertEqual(comment.text, "Seguimiento realizado.")

	def test_latest_rejected_validation_removes_activity_from_advance(self):
		activity = Activity.objects.create(
			goal=self.north_goal,
			author=self.north_employee,
			date=date(2026, 6, 20),
			request_problem="Request",
			action="Action",
			contact="Contact",
			phone="555",
		)
		evidence = Evidence.objects.create(
			code="EVID-LATEST-001",
			activity=activity,
			author=self.north_employee,
			file_link="evidence/latest",
			date="2026-06-21T10:00:00Z",
			review_status="Pending",
		)
		Validation.objects.create(
			evidence=evidence,
			verifier=self.north_employee,
			decision="Approved",
			date="2026-06-21T10:00:00Z",
			result="Approved",
		)
		Validation.objects.create(
			evidence=evidence,
			verifier=self.north_employee,
			decision="Rejected",
			date="2026-06-22T10:00:00Z",
			result="Rejected",
			version=2,
		)

		indicator = recalculate_indicator_for_goal(self.north_goal)

		self.assertEqual(indicator.approved_activities, 0)

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

	def test_evaluator_can_view_monitoring_but_cannot_change_it(self):
		management.call_command("seed")
		evaluator = get_user_model().objects.get(username="evaluator")

		self.assertTrue(
			evaluator.has_perm("monitoring_traceability.view_indicator")
		)
		self.assertFalse(
			evaluator.has_perm("monitoring_traceability.change_indicator")
		)

		request = RequestFactory().get("/admin/")
		request.user = evaluator
		model_admin = AuditAdmin(Audit, None)

		self.assertFalse(model_admin.has_change_permission(request))
