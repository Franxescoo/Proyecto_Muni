"""Alertas de Monitoreo exclusivamente del funcionario que inició sesión.

Este resumen es de solo lectura. No genera ni resuelve alertas, no modifica
compromisos, y utiliza las mismas reglas operativas que el Resumen Ejecutivo.
"""
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from accounts.permissions import allowed_delegation_ids
from monitoring_traceability.models import Commitment
from monitoring_traceability.monitor_policy import get_monitoring_settings
from monitoring_traceability.services import monitoring_alerts
from organization.models import Employee


def _can_consult_own(user, permission, delegation_id):
    """El permiso y la delegación activa deben autorizar a esta persona."""
    if not user.has_perm(permission):
        return False
    allowed_ids = allowed_delegation_ids(user, permission)
    return allowed_ids is None or delegation_id in allowed_ids


def personal_monitoring_alerts(user):
    """Devuelve solo alertas cuya responsabilidad corresponde al empleado vinculado.

    No se usa el filtro por delegación como sustituto de la identidad: dos
    funcionarios de una misma delegación tienen paneles distintos.
    """
    profile = getattr(user, "profile", None)
    if (
        not user.is_authenticated or not user.is_active
        or profile is None or profile.deleted_at is not None
        or not profile.employee_id
    ):
        return []

    employee = Employee.objects.filter(
        pk=profile.employee_id,
        deleted_at__isnull=True,
        status__iexact="Active",
        delegation__deleted_at__isnull=True,
        delegation__status__iexact="Active",
    ).first()
    if employee is None:
        return []

    view_commitment = _can_consult_own(
        user, "monitoring_traceability.view_commitment", employee.delegation_id
    )
    view_indicator = _can_consult_own(
        user, "monitoring_traceability.view_indicator", employee.delegation_id
    )
    view_evidence = _can_consult_own(
        user, "registration_validation.view_evidence", employee.delegation_id
    )
    if not any((view_commitment, view_indicator, view_evidence)):
        return []

    rule = get_monitoring_settings()
    today = timezone.localdate()
    alerts = []

    def add_alert(title, count, detail, href, severity):
        if count:
            alerts.append({
                "title": title,
                "count": count,
                "detail": detail,
                "href": reverse(href),
                "severity": severity,
            })

    if view_commitment:
        # Mis compromisos: nunca todos los compromisos de mi delegación.
        commitments = Commitment.objects.filter(
            responsible_id=employee.pk,
            deleted_at__isnull=True,
        ).exclude(status__in=(
            "Completed", "Completado", "Realizado", "Validated", "Validado",
            "Cancelled", "Cancelado",
        ))
        overdue = commitments.filter(commitment_date__lt=today)
        overdue_count = overdue.count()
        if overdue_count:
            first = overdue.order_by("commitment_date", "pk").first()
            add_alert(
                "Compromisos vencidos", overdue_count,
                f"{first.origin} · plazo {first.commitment_date:%d/%m/%Y}",
                "monitoring:commitment_list", "danger",
            )
        upcoming = commitments.filter(
            commitment_date__gte=today,
            commitment_date__lte=today + timedelta(days=rule.due_soon_days),
        )
        upcoming_count = upcoming.count()
        if upcoming_count:
            first = upcoming.order_by("commitment_date", "pk").first()
            add_alert(
                "Compromisos próximos a vencer", upcoming_count,
                f"{first.origin} · plazo {first.commitment_date:%d/%m/%Y}",
                "monitoring:commitment_list", "warning",
            )

    if view_evidence:
        # Son solo las evidencias de las actividades firmadas por el empleado.
        from registration_validation.models import Evidence
        from monitoring_traceability.services import pending_evidence_queryset

        evidences = pending_evidence_queryset(Evidence.objects.filter(
            deleted_at__isnull=True,
            activity__deleted_at__isnull=True,
            activity__author_id=employee.pk,
        ))
        evidence_count = evidences.count()
        if evidence_count:
            first = evidences.order_by("-date", "-pk").first()
            add_alert(
                "Evidencias sin aprobar", evidence_count,
                f"Revisar evidencia {first.code}",
                "registration:evidence_list", "warning",
            )

    if view_indicator:
        # Esta función ya aplica el umbral de cumplimiento, inactividad en
        # días hábiles y las reglas de Monitoreo, con UN solo empleado.
        status = monitoring_alerts(
            employees=[employee], minimum_compliance=rule.low_compliance_threshold
        )
        low_count = status["low_performance"]
        if low_count:
            add_alert(
                "Indicadores bajo el umbral", low_count,
                f"Cumplimiento inferior al {rule.low_compliance_threshold:g}%",
                "monitoring:indicator_list", "warning",
            )
        if status["inactive_employees"]:
            own = status["inactive_details"][0]
            add_alert(
                "Sin registros recientes", 1,
                f"{own['missing_days']} días hábiles sin actividades válidas",
                "monitoring:activity_control", "warning",
            )

    return alerts
