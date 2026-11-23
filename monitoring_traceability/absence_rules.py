"""Regla RN de ausencias informadas: objetivos efectivos sin tocar Planificación.

El ajuste es proporcional a días computables (lunes-viernes sin feriados Chile).
Se aplica solo a metas vigentes; periodos cerrados conservan el indicador.
"""
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP, ROUND_CEILING

import holidays

from planning_measurements.working_days import calculate_computable_days


def _available_dates(period, employee):
    """Devuelve total de días computables y días perdidos sin duplicados."""
    from .models import EmployeeAbsence
    start, end = period.start_date, period.end_date
    total = calculate_computable_days(start, end)
    if not total:
        return 0, 0, set()
    absences = EmployeeAbsence.objects.filter(
        employee_id=employee.pk, cancelled_at__isnull=True,
        start_date__lte=end, end_date__gte=start,
    ).only('start_date', 'end_date')
    lost = set()
    chilean_holidays = holidays.country_holidays(
        'CL', years=range(start.year, end.year + 1),
    )
    for absence in absences:
        day = max(start, absence.start_date)
        stop = min(end, absence.end_date)
        while day <= stop:
            if day.weekday() < 5 and day not in chilean_holidays:
                lost.add(day)
            day += timedelta(days=1)
    return total, len(lost), lost


def effective_goal_values(goal, on_date=None):
    """(objetivo efectivo, evidencias exigidas, avance esperado, días ausentes).

    No altera el objetivo original. Metas porcentuales mantienen su objetivo
    porcentual: la ausencia modifica solamente su ritmo esperado y acreditación.
    """
    from django.utils import timezone
    from .services import _expected_progress

    today = on_date or timezone.localdate()
    period = goal.period
    total, lost_count, lost = _available_dates(period, goal.employee)
    original = Decimal(goal.objective_value)
    required = int(goal.required_evidence_count or 0)
    if not total or not lost_count:
        return original, required, _expected_progress(period, today), 0

    available = max(total - lost_count, 0)
    # Un período completamente ausente no se declara automáticamente cumplido.
    # Mantener un mínimo de 1 unidad en metas cuantitativas evita dividir por 0.
    item = goal.measurement_item
    is_percentage = bool(item and item.item_type == 'percentage')
    ratio = Decimal(available) / Decimal(total)
    effective_target = (
        original if is_percentage else
        max(Decimal('1.00'), (original * ratio).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
    )
    effective_required = (
        max(1, int((Decimal(required) * ratio).to_integral_value(rounding=ROUND_CEILING)))
        if required else 0
    )
    if today < period.start_date:
        expected = Decimal('0.00')
    elif not available:
        expected = Decimal('0.00')
    else:
        end = min(today, period.end_date)
        elapsed = calculate_computable_days(period.start_date, end) if end >= period.start_date else 0
        elapsed_lost = sum(1 for date in lost if date <= end)
        worked = max(elapsed - elapsed_lost, 0)
        expected = (Decimal(worked) / Decimal(available) * Decimal('100')).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP,
        )
    return effective_target, effective_required, expected, lost_count


def absence_intersects_closed_goal(employee_id, start, end):
    from planning_measurements.models import Goal
    return Goal.objects.filter(
        employee_id=employee_id, deleted_at__isnull=True,
        period__deleted_at__isnull=True, period__status__iexact='Closed',
        period__start_date__lte=end, period__end_date__gte=start,
    ).exists()
