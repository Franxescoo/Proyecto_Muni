from datetime import date

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission

from organization.models import Delegacion, CargoFuncion, Funcionario


class Command(BaseCommand):

    help = "Creates initial test data for the organization"

    def handle(self, *args, **kwargs):

        # Delegations
        delegation_center, _ = Delegacion.objects.get_or_create(
            name="Central Delegation",
            defaults={
                "status": "Active",
                "scope": "Administrative",
            },
        )

        delegation_north, _ = Delegacion.objects.get_or_create(
            name="Northern Delegation",
            defaults={
                "status": "Active",
                "scope": "Administrative",
            },
        )

        delegation_south, _ = Delegacion.objects.get_or_create(
            name="Southern Delegation",
            defaults={
                "status": "Active",
                "scope": "Administrative",
            },
        )

        # Positions and functions
        coordinator_position, _ = CargoFuncion.objects.get_or_create(
            position_name="Coordinator",
            defaults={
                "measurable_items": "Coordination and monitoring",
                "services": "Administrative management",
                "weightings": "100%",
                "validity_start": date(2026, 1, 1),
                "validity_end": date(2026, 12, 31),
            },
        )

        administrative_position, _ = CargoFuncion.objects.get_or_create(
            position_name="Administrative Assistant",
            defaults={
                "measurable_items": "Customer service and registration",
                "services": "Administrative support",
                "weightings": "100%",
                "validity_start": date(2026, 1, 1),
                "validity_end": date(2026, 12, 31),
            },
        )

        technical_position, _ = CargoFuncion.objects.get_or_create(
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
            ("Camila Rojas", delegation_north, administrative_position),
            ("Diego Munoz", delegation_south, coordinator_position),
            ("Valentina Silva", delegation_south, technical_position),
        ]

        for name, delegation, position in employees:
            Funcionario.objects.get_or_create(
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
                "view_delegacion",
                "view_cargofuncion",
                "view_funcionario",
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

        self.stdout.write(
            self.style.SUCCESS("Seed executed successfully.")
        )