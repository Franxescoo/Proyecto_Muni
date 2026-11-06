"""Reglas de ponderación de metas por cargo y funcionario (RN-001)."""

from collections import defaultdict
from decimal import Decimal

from .models import Goal
from .measurement_rules import canonical_percentage_formula


class InvalidPeriodWeights(ValueError):
    """La configuración de ponderadores no está lista para cerrar."""


def validate_period_weights(period):
    """Valida la configuración de las metas activas antes de cerrar.

    - Los ítems de cada cargo suman 100 % una sola vez, aunque estén
      asignados a varios funcionarios.
    - Un ítem tiene el mismo ponderador para todo funcionario del cargo.
    - Cada funcionario **con metas en el período** tiene los ítems
      usados por las metas de su cargo en ese período y suma 100 %.
    - Los ítems nuevos del catálogo que aún no tienen meta en el
      período no son obligatorios para cerrarlo.

    Los funcionarios sin ninguna meta en el período no se incluyen:
    incorporarlos exigiría definir formalmente quién participa en él.
    """
    goals = list(
        Goal.objects.filter(period=period, deleted_at__isnull=True)
        .select_related("position", "employee")
        .order_by("position_id", "employee_id", "item", "pk")
    )

    if not goals:
        raise InvalidPeriodWeights(
            "No puedes cerrar un período sin metas configuradas."
        )

    by_position = defaultdict(dict)
    by_employee = defaultdict(dict)
    positions = {}
    employees = {}
    item_labels = {}

    for goal in goals:
        item = ("catalog", goal.measurement_item_id) if goal.measurement_item_id else ("text", goal.item.strip().casefold())
        position_id = goal.position_id
        employee_key = (position_id, goal.employee_id)
        positions[position_id] = goal.position
        employees[employee_key] = goal.employee
        item_labels[(position_id, item)] = goal.item.strip()

        saved = by_position[position_id].get(item)
        if saved is not None and saved != goal.weight:
            raise InvalidPeriodWeights(
                f"El cargo {goal.position} tiene ponderadores "
                f"diferentes para el mismo ítem «{goal.item}»."
            )
        by_position[position_id][item] = goal.weight

        if item in by_employee[employee_key]:
            raise InvalidPeriodWeights(
                f"El funcionario {goal.employee} tiene el ítem "
                f"«{goal.item}» duplicado en el período."
            )
        by_employee[employee_key][item] = goal.weight

    # Verifica que las metas con referencia al catálogo utilicen ítems
    # activos y asociados al cargo. No exige metas para ítems adicionales
    # del catálogo: la configuración a cerrar es la de Goal en el período.
    # Los registros antiguos solo de texto mantienen la regla heredada.
    goals_by_position = defaultdict(list)
    for goal in goals:
        goals_by_position[goal.position_id].append(goal)

    for position_id, position_goals in goals_by_position.items():
        catalog = {
            item.pk: item for item in position_goals[0].position.catalog_items.filter(
                deleted_at__isnull=True, is_active=True
            )
        }
        # Si el cargo NO tiene catálogo o todas sus metas son anteriores
        # a la introducción de measurement_item, se aplica la regla heredada.
        if not catalog or not any(g.measurement_item_id for g in position_goals):
            continue
        used = {g.measurement_item_id for g in position_goals}
        if None in used:
            raise InvalidPeriodWeights(
                f"El cargo {positions[position_id]} tiene metas sin ítem "
                "del catálogo. Revisa las metas antes del cierre."
            )
        outside = used.difference(catalog)
        if outside:
            raise InvalidPeriodWeights(
                f"El cargo {positions[position_id]} contiene ítems inactivos "
                "o que no pertenecen a su catálogo vigente."
            )
        for g in position_goals:
            if g.measurement_item.item_type == "percentage" and not canonical_percentage_formula(
                g.measurement_item.formula
            ):
                raise InvalidPeriodWeights(
                    f"El ítem porcentual «{g.item}» no tiene una fórmula "
                    "compatible con el cálculo del SGR. Revisa el catálogo."
                )
    for position_id, items in by_position.items():
        total = sum(items.values(), Decimal("0"))
        if total != Decimal("100"):
            raise InvalidPeriodWeights(
                f"Los ponderadores del cargo {positions[position_id]} "
                f"suman {total} %, pero deben sumar "
                "exactamente 100 % antes del cierre."
            )

    for employee_key, items in by_employee.items():
        position_id, _ = employee_key
        expected = by_position[position_id]
        missing = set(expected).difference(items)
        if missing:
            names = ", ".join(
                f"«{item_labels[(position_id, item)]}»"
                for item in sorted(missing, key=str)
            )
            raise InvalidPeriodWeights(
                f"El funcionario {employees[employee_key]} del cargo "
                f"{positions[position_id]} tiene metas incompletas: "
                f"le falta {names}. Así no se puede cerrar el período."
            )

        total = sum(items.values(), Decimal("0"))
        if total != Decimal("100"):
            raise InvalidPeriodWeights(
                f"Los ponderadores del funcionario "
                f"{employees[employee_key]} suman {total} %, "
                "pero deben sumar exactamente 100 % antes del cierre."
            )
