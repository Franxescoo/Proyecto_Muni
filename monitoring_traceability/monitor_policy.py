"""Reglas operativas de Monitoreo; sin dependencias de Registro/Planificación.

La ausencia de una fila implica los valores académicos predeterminados.
"""
from decimal import Decimal

from .models import MonitoringSettings


def get_monitoring_settings():
    return MonitoringSettings.objects.filter(key="global").first() or MonitoringSettings(key="global")


def settings_snapshot(rule):
    return {
        "low_compliance_threshold": str(rule.low_compliance_threshold),
        "inactivity_workdays": rule.inactivity_workdays,
        "due_soon_days": rule.due_soon_days,
        "positive_adjustment_max": str(rule.positive_adjustment_max),
        "negative_adjustment_max": str(rule.negative_adjustment_max),
        "recipient_user_ids": (
            sorted(rule.recipient_users.values_list("pk", flat=True))
            if rule.pk else []
        ),
    }
