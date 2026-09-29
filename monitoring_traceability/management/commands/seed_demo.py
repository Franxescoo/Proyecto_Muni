from datetime import date

from django.core.management.base import BaseCommand

from accounts.models import UserProfile
from organization.models import Delegation, Employee, PositionFunction
from planning_measurements.models import Goal, Period

from monitoring_traceability.models import Activity, Audit, Commitment, Evidence, Indicator


class Command(BaseCommand):
    help = "Load reproducible demo data for monitoring and traceability."

    def handle(self, *args, **options):
        north = self.get_delegation("North Delegation", "North")
        south = self.get_delegation("South Delegation", "South")
        position = self.get_position()
        north_employee = self.get_employee(north, position, "North Employee")
        south_employee = self.get_employee(south, position, "South Employee")
        period = self.get_period()
        north_goal = self.get_goal(period, north_employee, position, "North annual goal")
        south_goal = self.get_goal(period, south_employee, position, "South annual goal")
        activity = Activity.objects.get_or_create(name="Community activity")[0]
        evidence = Evidence.objects.get_or_create(name="Administrative evidence")[0]

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
        north_commitment = Commitment.objects.get_or_create(
            delegation=north,
            responsible=north_employee,
            territory="North territory",
            commitment_date=date(2026, 7, 15),
            defaults={
                "activity": activity,
                "evidence": evidence,
                "requester": "North office",
                "support": "Coordination and follow-up",
                "status": "Pending",
                "observation": "Scheduled for the next review.",
            },
        )[0]
        south_commitment = Commitment.objects.get_or_create(
            delegation=south,
            responsible=south_employee,
            territory="South territory",
            commitment_date=date(2026, 8, 15),
            defaults={
                "activity": activity,
                "evidence": evidence,
                "requester": "South office",
                "support": "Technical support",
                "status": "In progress",
                "observation": "Evidence pending.",
            },
        )[0]
        Audit.objects.get_or_create(
            user=north_employee,
            event="CREATE",
            entity="Commitment",
            object_identifier=str(north_commitment.commitment_id),
            defaults={"previous_value": None, "new_value": {"status": "Pending"}},
        )
        Audit.objects.get_or_create(
            user=south_employee,
            event="UPDATE",
            entity="Commitment",
            object_identifier=str(south_commitment.commitment_id),
            defaults={
                "previous_value": {"status": "Pending"},
                "new_value": {"status": "In progress"},
            },
        )
        self.stdout.write(self.style.SUCCESS("Demo data loaded successfully."))

    def get_delegation(self, name, scope):
        return Delegation.objects.get_or_create(
            name=name,
            defaults={"status": "Active", "scope": scope},
        )[0]

    def get_position(self):
        return PositionFunction.objects.get_or_create(
            position_name="Monitoring Coordinator",
            defaults={
                "measurable_items": "Indicators and commitments",
                "services": "Monitoring",
                "weightings": "100",
                "validity_start": date(2026, 1, 1),
                "validity_end": date(2026, 12, 31),
            },
        )[0]

    def get_employee(self, delegation, position, name):
        return Employee.objects.get_or_create(
            name=name,
            defaults={
                "delegation": delegation,
                "position": position,
                "roles": "Monitoring operator",
                "status": "Active",
            },
        )[0]

    def get_period(self):
        return Period.objects.get_or_create(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            defaults={
                "computable_days": 250,
                "status": "Active",
                "thresholds": "Green >= 90",
                "parameters_version": "1.0",
            },
        )[0]

    def get_goal(self, period, employee, position, item):
        return Goal.objects.get_or_create(
            period=period,
            employee=employee,
            position=position,
            item=item,
            defaults={"objective_value": 100, "unit": "percent", "weight": 50},
        )[0]

