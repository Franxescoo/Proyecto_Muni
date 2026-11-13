"""Auditar y sincronizar roles heredados de cargos, sin superusuario."""
from django.core.management.base import BaseCommand
from django.core.exceptions import ValidationError
from django.db import transaction
from accounts.models import UserProfile
from accounts.services import position_groups, sync_user_groups, validate_employee_role_scope


class Command(BaseCommand):
    help = "Compara los roles actuales con los heredados del cargo; --apply sincroniza."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Aplicar los cambios después de revisar el reporte")

    def handle(self, *args, **options):
        profiles = (UserProfile.objects.filter(deleted_at__isnull=True, employee__isnull=False)
                    .select_related("employee__position", "user", "delegation")
                    .order_by("user__username"))
        changed = 0
        rejected = 0
        for profile in profiles:
            user = profile.user
            current = set(user.groups.values_list("pk", flat=True))
            expected = set(position_groups(profile.employee).values_list("pk", flat=True))
            direct = user.user_permissions.exists()
            if current == expected and not direct:
                continue
            changed += 1
            old_names = list(user.groups.values_list("name", flat=True))
            new_names = list(position_groups(profile.employee).values_list("name", flat=True))
            self.stdout.write(f"{user.username} | {profile.employee.name} | {old_names} -> {new_names} | directos={direct}")
            delegations = list(profile.authorized_delegations.all())
            if not delegations and profile.delegation_id:
                delegations = [profile.delegation]
            try:
                validate_employee_role_scope(profile.employee, delegations)
            except ValidationError as exc:
                rejected += 1
                self.stderr.write(self.style.ERROR(f"  BLOQUEADO: {exc}"))
                continue
            if options["apply"]:
                with transaction.atomic():
                    sync_user_groups(user)
        self.stdout.write(f"Diferencias: {changed}; incompatibles: {rejected}; modo: {'APLICADO' if options['apply'] else 'SOLO LECTURA'}")
        if rejected:
            self.stderr.write(self.style.WARNING("Revisa las delegaciones autorizadas de cada cuenta antes de aplicar cambios."))
