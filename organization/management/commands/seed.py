from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import UserProfile
from monitoring_traceability.models import Audit, Commitment, Indicator
from organization.models import Delegation, Employee, PositionFunction
from planning_measurements.models import Goal, Period
from registration_validation.models import Activity, Evidence


class Command(BaseCommand):

    help = "Creates initial test data for the organization"

    def handle(self, *args, **kwargs):

        # Delegations
        delegation_center, _ = Delegation.objects.get_or_create(
            name="Central Delegation",
            defaults={
                "status": "Active",
                "scope": "Administrative",
            },
        )

        delegation_north, _ = Delegation.objects.get_or_create(
            name="Northern Delegation",
            defaults={
                "status": "Active",
                "scope": "Administrative",
            },
        )

        delegation_south, _ = Delegation.objects.get_or_create(
            name="Southern Delegation",
            defaults={
                "status": "Active",
                "scope": "Administrative",
            },
        )

        # Positions and functions
        coordinator_position, _ = PositionFunction.objects.get_or_create(
            position_name="Coordinator",
            defaults={
                "measurable_items": "Coordination and monitoring",
                "services": "Administrative management",
                "weightings": "100%",
                "validity_start": date(2026, 1, 1),
                "validity_end": date(2026, 12, 31),
            },
        )

        administrative_position, _ = PositionFunction.objects.get_or_create(
            position_name="Administrative Assistant",
            defaults={
                "measurable_items": "Customer service and registration",
                "services": "Administrative support",
                "weightings": "100%",
                "validity_start": date(2026, 1, 1),
                "validity_end": date(2026, 12, 31),
            },
        )

        technical_position, _ = PositionFunction.objects.get_or_create(
            position_name="Technician",
            defaults={
                "measurable_items": "Support and maintenance",
                "services": "Technical support",
                "weightings": "100%",
                "validity_start": date(2026, 1, 1),
                "validity_end": date(2026, 12, 31),
            },
        )

        # Employees
        employees = [
            (
                "John Perez",
                delegation_center,
                coordinator_position,
            ),
            (
                "Maria Gonzalez",
                delegation_center,
                administrative_position,
            ),
            (
                "Peter Soto",
                delegation_north,
                technical_position,
            ),
            (
                "Diego Munoz",
                delegation_south,
                coordinator_position,
            ),
        ]

        for name, delegation, position in employees:
            Employee.objects.get_or_create(
                name=name,
                defaults={
                    "delegation": delegation,
                    "position": position,
                    "roles": "User",
                    "status": "Active",
                },
            )

        # Limited user
        User = get_user_model()

        group, _ = Group.objects.get_or_create(
            name="Limited User"
        )

        permissions = Permission.objects.filter(
            codename__in=[
                "view_delegation",
                "view_positionfunction",
                "view_employee",
                "view_period",
                "view_goal",
                "view_activity",
                "view_evidence",
                "view_validation",
                "view_indicator",
                "view_commitment",
                "view_audit",
                "change_goal",
                "add_goal",
            ]
        )

        group.permissions.set(permissions)

        user, created = User.objects.get_or_create(
            username="evaluator"
        )

        if created:
            user.set_password("User123")
            user.save()

        user.groups.add(group)
        user.is_staff = True
        user.save()

        UserProfile.objects.get_or_create(
            user=user,
            defaults={
                "employee_code": "EVAL-001",
                "delegation": delegation_north,
            },
        )

        # Period
        period, _ = Period.objects.get_or_create(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 6, 30),
            defaults={
                "computable_days": 120,
                "status": "Active",
                "thresholds": "Low: 60, Medium: 80, High: 100",
                "parameters_version": "v1.0",
            },
        )

        # Goals
        goals = [
            (
                "Reports delivered",
                40,
                "units",
                50,
            ),
            (
                "Response time",
                24,
                "hours",
                30,
            ),
            (
                "Citizen satisfaction",
                85,
                "percent",
                20,
            ),
        ]

        for employee in Employee.objects.all():
            for item, value, unit, weight in goals:
                Goal.objects.get_or_create(
                    period=period,
                    employee=employee,
                    item=item,
                    defaults={
                        "position": employee.position,
                        "objective_value": value,
                        "unit": unit,
                        "weight": weight,
                    },
                )

        # Employees and goals used by operational data
        north_employee = Employee.objects.get(
            name="Peter Soto"
        )

        south_employee = Employee.objects.get(
            name="Diego Munoz"
        )

        north_goal = Goal.objects.get(
            period=period,
            employee=north_employee,
            item="Reports delivered",
        )

        south_goal = Goal.objects.get(
            period=period,
            employee=south_employee,
            item="Reports delivered",
        )

        # Activities
        north_activity, _ = Activity.objects.get_or_create(
            goal=north_goal,
            author=north_employee,
            date=date(2026, 6, 30),
            request_problem="Community request",
            defaults={
                "action": "Community follow-up",
                "contact": "Northern office",
                "phone": "+56 9 1111 1111",
                "status": "Completed",
            },
        )

        south_activity, _ = Activity.objects.get_or_create(
            goal=south_goal,
            author=south_employee,
            date=date(2026, 6, 30),
            request_problem="Administrative request",
            defaults={
                "action": "Administrative follow-up",
                "contact": "Southern office",
                "phone": "+56 9 2222 2222",
                "status": "In progress",
            },
        )

        # Evidences
        Evidence.objects.get_or_create(
            code="EVID-NORTH-001",
            defaults={
                "activity": north_activity,
                "author": north_employee,
                "file_link": "evidence/north-001",
                "date": timezone.now(),
                "metadata": {
                    "source": "seed",
                },
                "review_status": "Pending",
            },
        )

        Evidence.objects.get_or_create(
            code="EVID-SOUTH-001",
            defaults={
                "activity": south_activity,
                "author": south_employee,
                "file_link": "evidence/south-001",
                "date": timezone.now(),
                "metadata": {
                    "source": "seed",
                },
                "review_status": "Pending",
            },
        )

        # Indicators
        Indicator.objects.get_or_create(
            goal=north_goal,
            employee=north_employee,
            calculation_date=date(2026, 6, 30),
            defaults={
                "expected_value": 100,
                "actual_progress": 92,
                "green_progress": 90,
                "difference": 2,
                "compliance": 92,
                "weighting": 50,
                "traffic_light": "Green",
            },
        )

        Indicator.objects.get_or_create(
            goal=south_goal,
            employee=south_employee,
            calculation_date=date(2026, 6, 30),
            defaults={
                "expected_value": 100,
                "actual_progress": 72,
                "green_progress": 90,
                "difference": -18,
                "compliance": 72,
                "weighting": 50,
                "traffic_light": "Yellow",
            },
        )

        # Commitments
        north_commitment, _ = Commitment.objects.update_or_create(
            delegation=delegation_north,
            responsible=north_employee,
            territory="Northern territory",
            commitment_date=date(2026, 7, 15),
            defaults={
                "activity": north_activity,
                "origin": "Community activity",
                "requester": "Northern office",
                "support": "Coordination and follow-up",
                "status": "Pending",
                "observation": "Scheduled for the next review.",
            },
        )

        south_commitment, _ = Commitment.objects.update_or_create(
            delegation=delegation_south,
            responsible=south_employee,
            territory="Southern territory",
            commitment_date=date(2026, 8, 15),
            defaults={
                "activity": south_activity,
                "origin": "Administrative activity",
                "requester": "Southern office",
                "support": "Technical support",
                "status": "In progress",
                "observation": "Evidence pending.",
            },
        )

        # Audit
        Audit.objects.get_or_create(
            user=north_employee,
            event="CREATE",
            entity="Commitment",
            object_identifier=str(
                north_commitment.commitment_id
            ),
            defaults={
                "previous_value": None,
                "new_value": {
                    "status": "Pending",
                },
            },
        )

        Audit.objects.get_or_create(
            user=south_employee,
            event="UPDATE",
            entity="Commitment",
            object_identifier=str(
                south_commitment.commitment_id
            ),
            defaults={
                "previous_value": {
                    "status": "Pending",
                },
                "new_value": {
                    "status": "In progress",
                },
            },
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Seed executed successfully."
            )
        )