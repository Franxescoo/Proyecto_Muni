from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from accounts.permission_audit import direct_permission_inventory


class Command(BaseCommand):
    help = "Informa permisos directos y si están cubiertos por roles; no modifica datos."

    def handle(self, *args, **options):
        rows = direct_permission_inventory(get_user_model())
        if not rows:
            self.stdout.write("No se encontraron permisos directos en usuarios no superusuarios.")
            return

        self.stdout.write(
            "usuario | permisos directos | roles | cobertura | requiere revisión"
        )
        for row in rows:
            covered = "cubierto por rol" if row["covered_by_role"] else "no cubierto"
            review = "no" if row["covered_by_role"] else "sí"
            roles = ", ".join(row["roles"]) or "sin roles"
            self.stdout.write(
                f'{row["username"]} | {row["direct_permission"]} | '
                f"{roles} | {covered} | {review}"
            )
