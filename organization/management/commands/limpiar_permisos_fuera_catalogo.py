from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from organization.permission_labels import catalog_permission_queryset


class Command(BaseCommand):
    help = (
        "Muestra o elimina permisos de un grupo que no pertenecen "
        "al catálogo configurable."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--rol",
            default="DEMO SGR - Administrador",
            help="Nombre exacto del grupo que se revisará.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Elimina los permisos fuera del catálogo.",
        )

    def handle(self, *args, **options):
        try:
            group = Group.objects.get(name=options["rol"])
        except Group.DoesNotExist as exc:
            raise CommandError(
                f"No existe el grupo '{options['rol']}'."
            ) from exc
        except Group.MultipleObjectsReturned as exc:
            raise CommandError(
                f"Hay más de un grupo llamado '{options['rol']}'."
            ) from exc

        catalog_ids = set(
            catalog_permission_queryset(
                Permission.objects.all()
            ).values_list("pk", flat=True)
        )
        assigned = group.permissions.select_related("content_type")
        outside = [
            permission
            for permission in assigned
            if permission.pk not in catalog_ids
        ]

        self.stdout.write(f"ROL: {group.name}")
        self.stdout.write(f"CATALOGO: {len(catalog_ids)}")
        self.stdout.write(f"ASIGNADOS: {assigned.count()}")
        self.stdout.write(f"FUERA_DEL_CATALOGO: {len(outside)}")
        for permission in outside:
            self.stdout.write(
                f" - {permission.content_type.app_label}."
                f"{permission.content_type.model}."
                f"{permission.codename}"
            )

        if not options["apply"]:
            self.stdout.write(
                self.style.WARNING(
                    "Simulación: no se modificó ningún permiso. "
                    "Usa --apply para ejecutar la limpieza."
                )
            )
            return

        with transaction.atomic():
            group.permissions.remove(*(permission.pk for permission in outside))

        self.stdout.write(
            self.style.SUCCESS(
                f"Se eliminaron {len(outside)} permisos fuera del catálogo."
            )
        )
