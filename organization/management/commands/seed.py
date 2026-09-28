from datetime import date

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission

from organization.models import Delegacion, CargoFuncion, Funcionario


class Command(BaseCommand):
    help = "Crea datos iniciales de prueba para la organización"

    def handle(self, *args, **kwargs):

        # Delegaciones
        delegacion_centro, _ = Delegacion.objects.get_or_create(
            nombre="Delegación Centro",
            defaults={
                "estado": "Activa",
                "ambito": "Administrativo",
            },
        )

        delegacion_norte, _ = Delegacion.objects.get_or_create(
            nombre="Delegación Norte",
            defaults={
                "estado": "Activa",
                "ambito": "Administrativo",
            },
        )

        delegacion_sur, _ = Delegacion.objects.get_or_create(
            nombre="Delegación Sur",
            defaults={
                "estado": "Activa",
                "ambito": "Administrativo",
            },
        )

        # Cargos y funciones
        cargo_coordinador, _ = CargoFuncion.objects.get_or_create(
            nombre_cargo="Coordinador",
            defaults={
                "items_medibles": "Coordinación y seguimiento",
                "servicios": "Gestión administrativa",
                "ponderaciones": "100%",
                "vigencia_inicio": date(2026, 1, 1),
                "vigencia_fin": date(2026, 12, 31),
            },
        )

        cargo_administrativo, _ = CargoFuncion.objects.get_or_create(
            nombre_cargo="Administrativo",
            defaults={
                "items_medibles": "Atención y registro",
                "servicios": "Apoyo administrativo",
                "ponderaciones": "100%",
                "vigencia_inicio": date(2026, 1, 1),
                "vigencia_fin": date(2026, 12, 31),
            },
        )

        cargo_tecnico, _ = CargoFuncion.objects.get_or_create(
            nombre_cargo="Técnico",
            defaults={
                "items_medibles": "Soporte y mantenimiento",
                "servicios": "Soporte técnico",
                "ponderaciones": "100%",
                "vigencia_inicio": date(2026, 1, 1),
                "vigencia_fin": date(2026, 12, 31),
            },
        )

        # Funcionarios
        funcionarios = [
            ("Juan Pérez", delegacion_centro, cargo_coordinador),
            ("María González", delegacion_centro, cargo_administrativo),
            ("Pedro Soto", delegacion_norte, cargo_tecnico),
            ("Camila Rojas", delegacion_norte, cargo_administrativo),
            ("Diego Muñoz", delegacion_sur, cargo_coordinador),
            ("Valentina Silva", delegacion_sur, cargo_tecnico),
        ]

        for nombre, delegacion, cargo in funcionarios:
            Funcionario.objects.get_or_create(
                nombre=nombre,
                defaults={
                    "delegacion": delegacion,
                    "cargo": cargo,
                    "roles": "Usuario",
                    "estado": "Activo",
                },
            )


        # Usuario limitado
        User = get_user_model()

        grupo, _ = Group.objects.get_or_create(
            name="Usuario Limitado"
        )

        permisos = Permission.objects.filter(
            codename__in=[
                "view_delegacion",
                "view_cargofuncion",
                "view_funcionario",
            ]
        )

        grupo.permissions.set(permisos)

        usuario, creado = User.objects.get_or_create(
            username="evaluador"
        )

        if creado:
            usuario.set_password("User123")
            usuario.save()

        usuario.groups.add(grupo)
        usuario.is_staff = True
        usuario.save()
        self.stdout.write(
            self.style.SUCCESS("Seed ejecutada correctamente.")
        )