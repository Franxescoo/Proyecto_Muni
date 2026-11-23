"""Regla de semanas cerradas; no modifica registros históricos."""
from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone


def start_of_week(day):
    if hasattr(day, "tzinfo"):
        if timezone.is_aware(day):
            day = timezone.localtime(day)
        else:
            day = timezone.make_aware(day, timezone.get_current_timezone())
        day = day.date()
    return day - timedelta(days=day.weekday())


def assert_week_open(delegation_id, performed_at):
    """Validar fecha en servidor incluso si se omite el formulario HTML."""
    if not delegation_id or not performed_at:
        return
    from .weekly_models import CitizenRequestActionWeek

    if CitizenRequestActionWeek.objects.filter(
        delegation_id=delegation_id,
        week_start=start_of_week(performed_at),
        is_closed=True,
    ).exists():
        raise ValidationError(
            "La semana correspondiente está cerrada para esta delegación. "
            "No se pueden registrar ni modificar gestiones de esa semana."
        )


def manage_week(*, delegation_id, monday, action, actor, reason=""):
    """Cierre/reapertura auditable y serializada por delegación."""
    from organization.models import Delegation
    from .weekly_models import CitizenRequestActionWeek, CitizenRequestActionWeekEvent

    if not isinstance(monday, date) or hasattr(monday, "hour") or monday.weekday() != 0:
        raise ValidationError("Selecciona un lunes válido como inicio de semana.")
    if action not in ("close", "reopen"):
        raise ValidationError("La operación solicitada no es válida.")
    reason = (reason or "").strip()
    if action == "reopen" and len(reason) < 5:
        raise ValidationError("Indica un motivo de reapertura de al menos 5 caracteres.")
    if len(reason) > 500:
        raise ValidationError("El motivo no puede superar los 500 caracteres.")

    with transaction.atomic():
        # La creación de gestiones adquiere el MISMO bloqueo para evitar carreras.
        Delegation.objects.select_for_update().get(pk=delegation_id)
        week = (
            CitizenRequestActionWeek.objects.select_for_update()
            .filter(delegation_id=delegation_id, week_start=monday)
            .first()
        )
        if action == "close":
            if monday + timedelta(days=6) >= timezone.localdate():
                raise ValidationError("Solo se pueden cerrar semanas que ya terminaron.")
            if week and week.is_closed:
                raise ValidationError("Esta semana ya está cerrada.")
            if week is None:
                week = CitizenRequestActionWeek(
                    delegation_id=delegation_id, week_start=monday
                )
            week.is_closed = True
            week.closed_at = timezone.now()
            week.closed_by = actor
            week.save()
            kind = CitizenRequestActionWeekEvent.CLOSE
        else:
            if week is None or not week.is_closed:
                raise ValidationError("La semana no está cerrada.")
            week.is_closed = False
            week.closed_at = None
            week.closed_by = None
            week.save(update_fields=["is_closed", "closed_at", "closed_by"])
            kind = CitizenRequestActionWeekEvent.REOPEN

        CitizenRequestActionWeekEvent.objects.create(
            week=week, action=kind, actor=actor, reason=reason if kind == "REOPEN" else ""
        )
        return week
