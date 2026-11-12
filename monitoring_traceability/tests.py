from django.test import TestCase
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core import management
from django.core.exceptions import ValidationError
from django.test import TestCase, RequestFactory
from django.utils import timezone

from accounts.models import UserProfile
from organization.models import Delegation, Employee, PositionFunction
from planning_measurements.models import Goal, MeasurementItem, Period
from registration_validation.models import Activity, Evidence, Validation

from .admin import AuditAdmin, CommitmentAdmin, IndicatorAdmin
from .models import Audit, Commitment, CommitmentComment, Indicator
from .services import (
	_expected_progress,
	_traffic_light,
	monitoring_alerts,
	recalculate_indicator_for_goal,
)
from .forms import CommitmentForm


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

	def test_commitment_form_exposes_existing_activities_by_delegation(self):
		activity = Activity.objects.create(
			goal=self.north_goal,
			author=self.north_employee,
			date=date(2026, 6, 20),
			request_problem="Request",
			action="Action",
			contact="Contact",
			phone="555",
		)
		form = CommitmentForm(
			employees=Employee.objects.filter(pk=self.north_employee.pk),
			delegations=Delegation.objects.filter(pk=self.north.pk),
			activities=Activity.objects.filter(pk=activity.pk),
		)

		rendered = str(form["activity"])

		self.assertIn(f'value="{activity.pk}"', rendered)
		self.assertIn(
			f'data-delegation-id="{self.north.pk}"',
			rendered,
		)

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
		self.assertEqual(indicator.compliance, 1)
		self.assertEqual(indicator.weighted_result, 0.5)
		self.assertEqual(indicator.traffic_light, "Red")

	def test_traffic_light_uses_configured_compliance_thresholds(self):
		self.north_goal.period.thresholds = (
			"Verde: 90, Amarillo: 60, Rojo: 30"
		)
		self.north_goal.period.save(update_fields=["thresholds"])

		self.assertEqual(
			_traffic_light(Decimal("90"), self.north_goal.period),
			"Green",
		)
		self.assertEqual(
			_traffic_light(Decimal("75"), self.north_goal.period),
			"Yellow",
		)
		self.assertEqual(
			_traffic_light(Decimal("59.99"), self.north_goal.period),
			"Red",
		)

	def test_expected_progress_uses_local_date_and_computable_days(self):
		period = self.north_goal.period

		with patch(
			"monitoring_traceability.services.timezone.localdate",
			return_value=date(2026, 1, 2),
		):
			progress = _expected_progress(period)

		self.assertEqual(progress, Decimal("0.40"))

	def test_contradictory_validation_does_not_approve_evidence(self):
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
			code="EVID-CONTRADICTORY-001",
			activity=activity,
			author=self.north_employee,
			file_link="evidence/contradictory",
			date="2026-06-21T10:00:00Z",
			review_status="Pending",
		)
		Validation.objects.create(
			evidence=evidence,
			verifier=self.north_employee,
			decision="Approved",
			date="2026-06-22T10:00:00Z",
			result="Rejected",
		)

		indicator = recalculate_indicator_for_goal(self.north_goal)

		self.assertEqual(indicator.approved_activities, 0)
		self.assertEqual(indicator.approved_evidences, 0)

	def test_percentage_measurement_uses_approved_activities_once(self):
		item = MeasurementItem.objects.create(
			code="PCT-TRACE-001",
			name="Actividades aprobadas",
			item_type=MeasurementItem.ItemType.PERCENTAGE,
			unit="%",
			formula="(actividades aprobadas / actividades registradas) * 100",
		)
		self.north_goal.measurement_item = item
		self.north_goal.save(update_fields=["measurement_item"])

		for number, approved in ((1, True), (2, False)):
			activity = Activity.objects.create(
				goal=self.north_goal,
				author=self.north_employee,
				date=date(2026, 6, number + 20),
				request_problem="Request",
				action="Action",
				contact="Contact",
				phone="555",
			)
			evidence = Evidence.objects.create(
				code=f"EVID-PCT-{number:03d}",
				activity=activity,
				author=self.north_employee,
				file_link=f"evidence/pct-{number}",
				date="2026-06-21T10:00:00Z",
				review_status="Pending",
			)
			Validation.objects.create(
				evidence=evidence,
				verifier=self.north_employee,
				decision="Approved" if approved else "Rejected",
				date="2026-06-22T10:00:00Z",
				result="Approved" if approved else "Rejected",
			)

		indicator = recalculate_indicator_for_goal(self.north_goal)

		self.assertEqual(indicator.actual_progress, Decimal("50.00"))
		self.assertEqual(indicator.compliance, Decimal("50.00"))

	def test_future_period_has_no_progress_or_approved_activities(self):
		period = Period.objects.create(
			start_date=date(2099, 1, 1),
			end_date=date(2099, 12, 31),
			computable_days=261,
			thresholds="Verde: 90, Amarillo: 60, Rojo: 30",
			parameters_version="1.0",
		)
		goal = Goal.objects.create(
			period=period,
			employee=self.north_employee,
			position=self.north_employee.position,
			item="Future goal",
			objective_value=10,
			unit="unidades",
			weight=50,
		)

		indicator = recalculate_indicator_for_goal(goal)

		self.assertEqual(indicator.actual_progress, 0)
		self.assertEqual(indicator.expected_progress, 0)
		self.assertEqual(indicator.traffic_light, "Red")

	def test_period_without_computable_days_is_red(self):
		period = Period.objects.create(
			start_date=date(2026, 1, 3),
			end_date=date(2026, 1, 4),
			computable_days=1,
			thresholds="Verde: 90, Amarillo: 60, Rojo: 30",
			parameters_version="1.0",
		)
		goal = Goal.objects.create(
			period=period,
			employee=self.north_employee,
			position=self.north_employee.position,
			item="Weekend goal",
			objective_value=1,
			unit="unidades",
			weight=50,
		)

		indicator = recalculate_indicator_for_goal(goal)

		self.assertEqual(indicator.expected_progress, 0)
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
		self.assertEqual(indicator.actual_progress, 1)
		self.assertEqual(indicator.compliance, 1)

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

		self.assertEqual(indicator.approved_evidences, 6)
		self.assertEqual(indicator.actual_progress, 1)
		self.assertEqual(indicator.compliance, 1)

	def test_indicator_uses_goal_evidence_requirement(self):
		self.north_goal.required_evidence_count = 10
		self.north_goal.save(update_fields=["required_evidence_count"])

		indicator = recalculate_indicator_for_goal(self.north_goal)

		self.assertEqual(indicator.expected_value, 100)
		self.assertEqual(indicator.compliance, 0)

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

	def test_activity_control_separates_login_and_activity_inactivity(self):
		user = get_user_model().objects.create_user(
			username="activity_admin",
			password="test-password",
			is_superuser=True,
		)
		UserProfile.objects.create(
			user=user,
			employee_code="ACTIVITY-001",
			employee=self.north_employee,
			delegation=self.north,
		)
		Activity.objects.create(
			goal=self.north_goal,
			author=self.north_employee,
			date=date(2026, 6, 20),
			request_problem="Request",
			action="Action",
			contact="Contact",
			phone="555",
		)

		self.client.force_login(user)
		user.last_login = timezone.make_aware(datetime(2026, 6, 1, 10, 0))
		user.save(update_fields=["last_login"])
		with patch(
			"monitoring_traceability.views.timezone.localdate",
			return_value=date(2026, 6, 30),
		):
			response = self.client.get("/monitoring/actividad/")

		self.assertEqual(response.status_code, 200)
		row = response.context["rows"][0]
		self.assertEqual(row["days_without_login"], 29)
		self.assertEqual(row["days_without_activity"], 10)

	def test_comment_can_be_created_without_employee_link(self):
		user = get_user_model().objects.create_user(
			username="comment_user",
			password="test-password",
		)
		UserProfile.objects.create(
			user=user,
			employee_code="COMMENT-001",
			delegation=self.north,
		)
		commitment = Commitment.objects.create(
			delegation=self.north,
			responsible=self.north_employee,
			requester="Requester",
			territory="North",
			commitment_date=date(2026, 7, 1),
		)

		user.user_permissions.add(*Permission.objects.filter(
			content_type__app_label="monitoring_traceability",
			codename__in=["view_commitment", "add_commitmentcomment"],
		))
		self.client.force_login(user)
		response = self.client.post(
			"/monitoring/compromisos/",
			{
				"commitment_id": commitment.pk,
				"comment": "Comentario publicado.",
			},
		)

		self.assertEqual(response.status_code, 302)
		comment = CommitmentComment.objects.get(
			commitment=commitment,
		)
		self.assertEqual(comment.created_by, user)
		self.assertIsNone(comment.author)

	def test_comment_can_only_be_deleted_by_creator(self):
		creator = get_user_model().objects.create_user(
			username="comment_creator",
			password="test-password",
		)
		UserProfile.objects.create(
			user=creator,
			employee_code="COMMENT-002",
			employee=self.north_employee,
			delegation=self.north,
		)
		other_user = get_user_model().objects.create_user(
			username="other_comment_user",
			password="test-password",
		)
		UserProfile.objects.create(
			user=other_user,
			employee_code="COMMENT-003",
			delegation=self.north,
		)
		commitment = Commitment.objects.create(
			delegation=self.north,
			responsible=self.north_employee,
			requester="Requester",
			territory="North",
			commitment_date=date(2026, 7, 1),
		)
		comment = CommitmentComment.objects.create(
			commitment=commitment,
			created_by=creator,
			text="Comentario para eliminar.",
		)
		self.assertTrue(
			Audit.objects.filter(
				entity="CommitmentComment",
				object_identifier=str(comment.pk),
				user=self.north_employee,
				event="Created CommitmentComment",
			).exists()
		)

		comment_permissions = Permission.objects.filter(
			content_type__app_label="monitoring_traceability",
			codename__in=["view_commitment", "delete_commitmentcomment"],
		)
		creator.user_permissions.add(*comment_permissions)
		other_user.user_permissions.add(*comment_permissions)
		self.client.force_login(other_user)
		self.client.post(
			"/monitoring/compromisos/",
			{
				"action": "delete",
				"commitment_id": commitment.pk,
				"comment_id": comment.pk,
			},
		)
		comment.refresh_from_db()
		self.assertIsNone(comment.deleted_at)

		self.client.force_login(creator)
		response = self.client.post(
			"/monitoring/compromisos/",
			{
				"action": "delete",
				"commitment_id": commitment.pk,
				"comment_id": comment.pk,
			},
		)

		self.assertEqual(response.status_code, 302)
		comment.refresh_from_db()
		self.assertIsNotNone(comment.deleted_at)

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
		validation = Validation.objects.create(
			evidence=evidence,
			verifier=self.north_employee,
			decision="Rejected",
			date="2026-06-22T10:00:00Z",
			result="Rejected",
			version=2,
		)

		indicator = recalculate_indicator_for_goal(self.north_goal)

		self.assertEqual(indicator.approved_activities, 0)

		validation.decision = "Approved"
		validation.result = "Approved"
		validation.save(update_fields=["decision", "result"])

		indicator.refresh_from_db()
		self.assertEqual(indicator.approved_activities, 1)

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

	def test_audit_events_are_immutable(self):
		audit = Audit.objects.create(
			user=self.north_employee,
			event="CREATE",
			entity="Goal",
			object_identifier="1",
			new_value={"item": "Meta"},
		)

		audit.event = "UPDATE"
		with self.assertRaises(ValidationError):
			audit.save()
		with self.assertRaises(ValidationError):
			audit.delete()

	def test_monitoring_alerts_counts_operational_risks(self):
		commitment = Commitment.objects.create(
			delegation=self.north,
			responsible=self.north_employee,
			origin="Origen",
			requester="Solicitante",
			territory="Territorio",
			commitment_date=date(2020, 1, 1),
			status="Pending",
		)
		commitment.refresh_from_db()

		alerts = monitoring_alerts(employees=[self.north_employee])

		self.assertGreaterEqual(alerts["overdue_commitments"], 1)

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
