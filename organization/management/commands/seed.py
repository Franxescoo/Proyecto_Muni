from datetime import date

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from planning_measurements.models import Period, Goal
from accounts.models import UserProfile

from organization.models import Delegation, PositionFunction, Employee


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
            ("John Perez", delegation_center, coordinator_position),
            ("Maria Gonzalez", delegation_center, administrative_position),
            ("Peter Soto", delegation_north, technical_position),
            ("Diego Munoz", delegation_south, coordinator_position),
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
            defaults={"employee_code": "EVAL-001", "delegation": delegation_north},
        )

        self.stdout.write(
            self.style.SUCCESS("Seed executed successfully.")
        )

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

        goals = [
            ("Reports delivered", 40, "units", 50),
            ("Response time", 24, "hours", 30),
            ("Citizen satisfaction", 85, "percent", 20),
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