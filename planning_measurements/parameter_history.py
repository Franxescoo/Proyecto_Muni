"""Registro append-only de revisiones de parámetros y metas por período.

Captura el estado conocido en cada evento. Para datos anteriores a la
instalación no se puede reconstruir la configuración histórica real.
"""
from decimal import Decimal
import re

from django.db import transaction
from django.db.models import Max

from .models import Goal, Period, PeriodParameterSnapshot

_CAP_PATTERN = re.compile(r"(?:tope|max)\s*:\s*(\d+(?:[.,]\d+)?)", re.I)
_VERSION_PATTERN = re.compile(
    r"^(?:[A-Za-z0-9_-]*v)?\d+(?:\.\d+)*$",
    re.I,
)
_VERSION_PARTS_PATTERN = re.compile(
    r"^(.*?)(v)?(\d+(?:\.\d+)*)$",
    re.I,
)


def compliance_cap_value(thresholds):
    found = _CAP_PATTERN.search(thresholds or "")
    return str(Decimal(found.group(1).replace(",", "."))) if found else "150"


def next_parameters_version(value):
    """Incrementa el último componente numérico de una versión válida."""
    current = str(value or "").strip()
    if not _VERSION_PATTERN.fullmatch(current):
        return current
    match = _VERSION_PARTS_PATTERN.fullmatch(current)
    if not match:
        return current
    prefix, marker, components = match.groups()
    numbers = components.split(".")
    numbers[-1] = str(int(numbers[-1]) + 1)
    return f"{prefix}{marker or ''}{'.'.join(numbers)}"


def parameters_version_is_valid(value):
    return bool(_VERSION_PATTERN.fullmatch(str(value or "").strip()))


def advance_period_parameters_version(period):
    """Incrementa la versión funcional dentro de la transacción llamadora."""
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError(
            "La actualización de versión debe ejecutarse dentro de "
            "transaction.atomic()."
        )
    locked = Period.objects.select_for_update().get(pk=period.pk)
    updated = next_parameters_version(locked.parameters_version)
    if updated != locked.parameters_version:
        locked.parameters_version = updated
        locked.save(update_fields=["parameters_version", "updated_at"])
    return locked


def capture_period_parameters(period, *, actor, event):
    """Crea una revisión inmutable dentro de la transacción del llamador."""
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("La captura histórica debe ejecutarse dentro de transaction.atomic().")
    # Serializa por período para evitar revisiones duplicadas bajo concurrencia.
    locked = Period.objects.select_for_update().get(pk=period.pk)
    last = (
        PeriodParameterSnapshot.objects.filter(period=locked)
        .aggregate(last=Max("revision"))["last"] or 0
    )
    goals = list(
        Goal.objects.filter(period=locked, deleted_at__isnull=True)
        .select_related("employee", "position", "measurement_item")
        .order_by("position_id", "employee_id", "goal_id")
    )
    goal_data = []
    positions = {}
    for goal in goals:
        position = goal.position
        if position.pk not in positions:
            positions[position.pk] = {
                "id": position.pk,
                "name": position.position_name,
                "catalog": [
                    {"id": item.pk, "code": item.code, "name": item.name,
                     "is_active": item.is_active, "unit": item.unit,
                     "item_type": item.item_type, "formula": item.formula}
                    for item in position.catalog_items.filter(deleted_at__isnull=True)
                    .order_by("item_id")
                ],
            }
        item = goal.measurement_item
        record = {
            "goal_id": goal.pk,
            "employee_id": goal.employee_id,
            "delegation_id": goal.employee.delegation_id,
            "employee": goal.employee.name,
            "position_id": goal.position_id,
            "position": position.position_name,
            "measurement_item_id": goal.measurement_item_id,
            "item": goal.item,
            "item_code": item.code if item else None,
            "item_type": item.item_type if item else None,
            "formula": item.formula if item else None,
            "objective_value": str(goal.objective_value),
            "weight": str(goal.weight),
            "required_evidence_count": goal.required_evidence_count,
            "unit": goal.unit,
        }
        # Conserva una fotografía del último indicador EXISTENTE, si lo hay.
        # Nunca lo recalcula; el módulo de Monitoreo queda intacto.
        ind = goal.indicators.filter(deleted_at__isnull=True).order_by(
            "-calculation_date", "-indicator_id"
        ).first()
        if ind:
            record["last_indicator"] = {
                "calculation_date": ind.calculation_date.isoformat(),
                "actual_progress": str(ind.actual_progress),
                "compliance": str(ind.compliance),
                "weighted_result": str(ind.weighted_result),
                "traffic_light": ind.traffic_light,
            }
        goal_data.append(record)

    content = {
        "period_id": locked.pk,
        "status": locked.status,
        "start_date": locked.start_date.isoformat(),
        "end_date": locked.end_date.isoformat(),
        "computable_days": locked.computable_days,
        "thresholds": locked.thresholds,
        "compliance_cap": compliance_cap_value(locked.thresholds),
        "parameters_version": locked.parameters_version,
        "positions": sorted(positions.values(), key=lambda obj: obj["id"]),
        "goals": goal_data,
    }
    return PeriodParameterSnapshot.objects.create(
        period=locked, revision=last + 1, event=event,
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        content=content,
    )
