"""Provisionamiento explícito y único de un administrador SIN superusuario."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from accounts.models import UserProfile
from organization.models import Delegation, OrganizationRole


class Command(BaseCommand):
    help = "Crear un rol administrativo para una cuenta existente sin activar is_superuser."

    def add_arguments(self, parser):
        parser.add_argument("--usuario", required=True, help="Cuenta existente que recibirá el rol")
        parser.add_argument("--confirmar", action="store_true", help="Confirmar la asignación")
        parser.add_argument("--rol", default="Administración institucional")

    @transaction.atomic
    def handle(self, *args, **options):
        if not options["confirmar"]:
            raise CommandError("Por seguridad, repite con --confirmar tras revisar usuario y alcance.")
        account = get_user_model().objects.filter(
            username=options["usuario"], is_active=True, is_superuser=False
        ).first()
        if not account:
            raise CommandError("La cuenta debe existir, estar activa y NO ser superusuario.")
        profile = UserProfile.objects.filter(
            user=account, deleted_at__isnull=True
        ).first()
        if not profile:
            raise CommandError("La cuenta debe tener un perfil activo.")
        scopes = list(Delegation.objects.filter(
            pk__in=profile.authorized_delegations.values_list("pk", flat=True),
            deleted_at__isnull=True,
        ))
        if not scopes and profile.delegation_id:
            scopes = list(Delegation.objects.filter(
                pk=profile.delegation_id, deleted_at__isnull=True
            ))
        if not scopes:
            raise CommandError("La cuenta no tiene delegaciones autorizadas.")
        if Group.objects.filter(name=options["rol"]).exists():
            raise CommandError("Ya existe un rol con ese nombre. Elige otro con --rol.")
        # El permiso de períodos cerrados solo se concede individualmente.
        permissions = Permission.objects.filter(
            content_type__app_label__in=[
                "organization", "accounts", "planning_measurements",
                "registration_validation", "monitoring_traceability",
            ]
        ).exclude(
            codename="delete_closed_period",
            content_type__app_label="planning_measurements",
        ).exclude(
            content_type__app_label="organization",
            content_type__model="delegationresponsibilitylog",
        )
        group = Group.objects.create(name=options["rol"])
        group.permissions.set(permissions)
        role = OrganizationRole.objects.create(
            group=group, delegation=scopes[0],
            description="Administración del sistema sin privilegios de superusuario.",
        )
        role.application_delegations.set(scopes)
        account.groups.add(group)
        self.stdout.write(self.style.SUCCESS(
            f"Rol '{group.name}' asignado a {account.username} "
            f"para {len(scopes)} delegación(es). is_superuser permanece False."
        ))
