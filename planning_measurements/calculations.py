
"""Reglas de ponderación de metas por cargo y período (RN-001)."""

from collections import defaultdict
from decimal import Decimal

from .models import Goal


class InvalidPeriodWeights(ValueError):
    """La configuración de ponderadores no está lista para cerrar."""


def validate_period_weights(period):
    """
    Valida una configuración completa antes de cerrar un período.

    Cada (cargo, ítem) se cuenta una vez, incluso si varios
    funcionarios del mismo cargo comparten el ítem.
    Sus ponderadores deben coincidir.

    No cambia el modelo ni introduce excepciones
    a la regla del 100 %.
    """

    goals = (
        Goal.objects.filter(
            period=period,
            deleted_at__isnull=True
        )
        .select_related("position")
        .order_by("position_id", "item", "pk")
    )

    by_position = defaultdict(dict)

    for goal in goals:
        item = goal.item.strip().casefold()

        saved = by_position[goal.position_id].get(item)

        if saved is not None and saved != goal.weight:
            raise InvalidPeriodWeights(
                f"El cargo {goal.position} tiene ponderadores "
                f"diferentes para el mismo ítem «{goal.item}»."
            )

        by_position[goal.position_id][item] = goal.weight

    if not by_position:
        raise InvalidPeriodWeights(
            "No puedes cerrar un período sin metas configuradas."
        )

    for position_id, items in by_position.items():

        total = sum(
            items.values(),
            Decimal("0")
        )

        if total != Decimal("100"):

            position = next(
                goal.position
                for goal in goals
                if goal.position_id == position_id
            )

            raise InvalidPeriodWeights(
                f"Los ponderadores del cargo {position} "
                f"suman {total} %, pero deben sumar "
                "exactamente 100 % antes del cierre."
            )
