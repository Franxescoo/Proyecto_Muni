"""Presentación legible de revisiones de reglas operativas de Monitoreo.

La información de auditoría permanece intacta en los JSONField del modelo.
Este filtro solo convierte las diferencias a texto para la plantilla.
"""

from decimal import Decimal, InvalidOperation

from django import template
from django.contrib.auth import get_user_model

register = template.Library()


_FIELDS = (
    ("low_compliance_threshold", "Umbral de cumplimiento bajo", "percent"),
    ("inactivity_workdays", "Días hábiles sin actividad", "workdays"),
    ("due_soon_days", "Aviso antes del vencimiento", "days"),
    ("positive_adjustment_max", "Máximo de bonificación", "points"),
    ("negative_adjustment_max", "Máximo de penalización", "points"),
    ("recipient_user_ids", "Destinatarios adicionales", "users"),
)


def _decimal(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _normalized(value, kind):
    if kind in ("percent", "points", "days", "workdays"):
        normalized = _decimal(value)
        return normalized if normalized is not None else str(value)
    if kind == "users":
        if not isinstance(value, (list, tuple, set)):
            return ()
        return tuple(sorted({str(identifier) for identifier in value}))
    return value


def _human_number(value):
    number = _decimal(value)
    if number is None:
        return str(value) if value is not None else "—"
    number_text = format(number.normalize(), "f")
    return number_text.replace(".", ",")


def _format_users(value, usernames):
    if not value:
        return "Ninguno"
    labels = [usernames.get(str(identifier), f"Usuario #{identifier}") for identifier in value]
    return ", ".join(sorted(labels, key=str.casefold))


def _display(value, kind, usernames):
    if kind == "users":
        return _format_users(value, usernames)
    number = _human_number(value)
    if kind == "percent":
        return f"{number} %"
    if kind == "points":
        return f"{number} puntos"
    if kind == "workdays":
        return f"{number} día hábil" if _decimal(value) == 1 else f"{number} días hábiles"
    if kind == "days":
        return f"{number} día" if _decimal(value) == 1 else f"{number} días"
    return number


@register.filter(name="monitoring_settings_changes")
def monitoring_settings_changes(before, after):
    """Retorna filas {label,before,after} de los valores que realmente cambiaron."""
    if not isinstance(before, dict) or not isinstance(after, dict):
        return []

    changes = []
    for key, label, kind in _FIELDS:
        old = before.get(key)
        new = after.get(key)
        if _normalized(old, kind) != _normalized(new, kind):
            changes.append((label, old, new, kind))

    # Consultar los nombres solo cuando hubo un cambio en los destinatarios.
    user_ids = set()
    for _, old, new, kind in changes:
        if kind == "users":
            user_ids.update(old or [])
            user_ids.update(new or [])

    usernames = {}
    if user_ids:
        for user in get_user_model()._default_manager.filter(pk__in=user_ids):
            usernames[str(user.pk)] = user.get_username()

    return [
        {
            "label": label,
            "before": _display(old, kind, usernames),
            "after": _display(new, kind, usernames),
        }
        for label, old, new, kind in changes
    ]
