from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from accounts.delegation_audit import delegation_transition_inventory


class Command(BaseCommand):
    help = "Compara alcances territoriales actuales y propuestos sin modificar datos."

    def handle(self, *args, **options):
        rows = delegation_transition_inventory(get_user_model())
        if not rows:
            self.stdout.write(
                "No se detectaron diferencias entre el alcance actual y el modelo propuesto."
            )
            return

        self.stdout.write(
            "usuario | permiso | alcance actual | alcance propuesto | "
            "ganancias | pérdidas | roles con alcance"
        )
        for row in rows:
            role_scopes = "; ".join(
                f'{scope["role"]}: {scope["delegations"]}'
                for scope in row["role_scopes"]
            ) or "sin alcance de rol"
            self.stdout.write(
                f'{row["username"]} | {row["permission"]} | '
                f'{row["current_delegations"]} | {row["proposed_delegations"]} | '
                f'{row["would_gain"]} | {row["would_lose"]} | {role_scopes}'
            )
