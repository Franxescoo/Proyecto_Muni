import re
from decimal import Decimal, ROUND_HALF_UP
from datetime import timedelta

from django.contrib.auth import get_user_model
import os
from django.db.models import F, Max, OuterRef, Subquery
from django.utils import timezone

from accounts.models import UserProfile
from institutional_mail.models import InstitutionalMessage

from .models import Commitment, CommitmentAlert, Indicator
from .monitor_policy import get_monitoring_settings
from planning_measurements.measurement_rules import evaluate_formula, FormulaError
from planning_measurements.working_days import calculate_computable_days
from registration_validation.models import Activity, Evidence, Validation


_THRESHOLD_PATTERN = re.compile(
    r"(?P<label>[A-Za-zÁÉÍÓÚáéíóúñÑ]+)\s*[:>=]+\s*"
    r"(?P<value>\d+(?:[.,]\d+)?)"
)



def _thresholds(period):
    values = {}

    for match in _THRESHOLD_PATTERN.finditer(period.thresholds or ""):
        label = match.group("label").lower()
        values[label] = Decimal(
            match.group("value").replace(",", ".")
        )

    green = values.get(
        "verde", values.get("green", Decimal("100"))
    )

    yellow = values.get(
        "amarillo", values.get("yellow", Decimal("60"))
    )

    return green, yellow




def _traffic_light(compliance, period, expected_progress=None):
    today = timezone.localdate()
    if (
        period.start_date > today
        or calculate_computable_days(
            period.start_date,
            period.end_date,
        ) <= 0
    ):
        return "Red"

    green, yellow = _thresholds(period)
    if expected_progress is None:
        green_limit = green
        yellow_limit = yellow
    else:
        green_limit = expected_progress * green / Decimal("100")
        yellow_limit = expected_progress * yellow / Decimal("100")

    if compliance >= green_limit:
        return "Green"

    if compliance >= yellow_limit:
        return "Yellow"

    return "Red"




def _expected_progress(period, on_date=None):
    on_date = on_date or timezone.localdate()

    if on_date < period.start_date:
        return Decimal("0.00")

    total_days = calculate_computable_days(
        period.start_date,
        period.end_date
    )

    if total_days <= 0:
        return Decimal("0.00")

    elapsed_days = calculate_computable_days(
        period.start_date,
        min(on_date, period.end_date)
    )

    return (
        Decimal(elapsed_days)
        / Decimal(total_days)
        * Decimal("100")
    ).quantize(Decimal("0.01"), ROUND_HALF_UP)



def _compliance_cap(period):
    values = {}
    for source in (period.parameters_version, period.thresholds):
        for match in _THRESHOLD_PATTERN.finditer(source or ""):
            values[match.group("label").lower()] = Decimal(
                match.group("value").replace(",", ".")
            )
    return values.get("max", values.get("tope", Decimal("150")))


def _evidence_is_approved(evidence):
    if evidence.deleted_at is not None:
        return False

    validations = list(
        evidence.validations.filter(
            deleted_at__isnull=True
        ).order_by("-date", "-version", "-validation_id")
    )
    if validations:
        latest = validations[0]
        return (
            latest.decision.strip().casefold() == "approved"
            and latest.result.strip().casefold() == "approved"
        )
    return False


def _activity_is_approved(activity):
    return any(
        _evidence_is_approved(evidence)
        for evidence in activity.evidences.all()
    )


def pending_evidence_queryset(queryset):
    """Evidencias sin aprobación vigente, según última validación no archivada.

    El texto legacy review_status puede seguir en Pending tras aprobar.
    No modifica registros ajenos a Monitoreo; usa la misma regla del indicador.
    """
    last_validation = Validation.objects.filter(
        evidence_id=OuterRef("pk"), deleted_at__isnull=True,
    ).order_by("-date", "-version", "-validation_id")
    return queryset.annotate(
        _last_validation_decision=Subquery(last_validation.values("decision")[:1]),
        _last_validation_result=Subquery(last_validation.values("result")[:1]),
        _last_validation_pk=Subquery(last_validation.values("pk")[:1]),
    ).exclude(
        _last_validation_decision__iexact="approved",
        _last_validation_result__iexact="approved",
    )


def _goal_formula_values(goal, activities, approved_activity_ids, approved_evidences, today):
    """Valores del mismo funcionario/ítem/período: sin sumar duplicados.

    Las solicitudes se vinculan a la meta a través de las atenciones de sus
    actividades. Las solicitudes sin esa relación no se atribuyen a un ítem.
    """
    from citizen_requests.models import CitizenRequest

    attention_ids = {
        activity.attention_id for activity in activities if activity.attention_id
    }
    # RF-014/RN-009: una atención resuelta no otorga avance del ítem si
    # ninguna actividad asociada a esa meta tiene evidencia aprobada.
    # Una atención con varias actividades válidas se contabiliza una vez.
    approved_attention_ids = {
        activity.attention_id for activity in activities
        if activity.pk in approved_activity_ids and activity.attention_id
    }
    from registration_validation.models import AttentionEntry
    attentions = AttentionEntry.objects.filter(
        pk__in=attention_ids, deleted_at__isnull=True,
    )
    approved_attentions = attentions.filter(pk__in=approved_attention_ids)
    completed_attentions = approved_attentions.filter(
        status__in=["RESOLVED", "CLOSED"],
    ).count()
    requests = CitizenRequest.objects.filter(
        attention_entry_id__in=attentions.values_list("pk", flat=True),
    ).distinct()
    commitments = Commitment.objects.filter(
        activity_id__in=[activity.pk for activity in activities],
        deleted_at__isnull=True,
    )
    # Un compromiso cuenta como máximo una vez, aunque tenga varias
    # actualizaciones de estado o evidencias vinculadas a su actividad.
    return {
        "actividades_registradas": len(activities),
        "actividades_aprobadas": len(approved_activity_ids),
        "evidencias_aprobadas": approved_evidences,
        "atenciones_registradas": attentions.count(),
        "atenciones_completadas": completed_attentions,
        "solicitudes_registradas": requests.count(),
        "solicitudes_resueltas": requests.filter(
            status="CLOSED", attention_entry_id__in=approved_attention_ids,
        ).count(),
        "compromisos_registrados": commitments.count(),
        "compromisos_realizados": commitments.filter(
            status__in=["Completed", "Validated"],
        ).count(),
        "compromisos_validados": commitments.filter(status="Validated").count(),
        "compromisos_vencidos": commitments.filter(
            commitment_date__lt=today,
        ).exclude(status__in=["Completed", "Validated", "Cancelled"]).count(),
        "dias_computables": calculate_computable_days(
            goal.period.start_date, goal.period.end_date,
        ),
        "dias_transcurridos": calculate_computable_days(
            goal.period.start_date, min(today, goal.period.end_date),
        ) if today >= goal.period.start_date else 0,
        "meta_objetivo": goal.objective_value,
    }


def recalculate_indicator_for_goal(goal, create_if_missing=True):
    """Actualiza métricas de forma reproducible y protege períodos cerrados."""
    today = timezone.localdate()
    existing_indicator = (
        Indicator.objects.filter(goal=goal, deleted_at__isnull=True)
        .order_by("-calculation_date", "-indicator_id").first()
    )
    if existing_indicator is None and not create_if_missing:
        return None
    # RF-038: ninguna señal tardía debe cambiar resultados ya consolidados.
    if goal.period.status.casefold() == "closed" and existing_indicator is not None:
        return existing_indicator

    activities = list(
        goal.activities.filter(
            deleted_at__isnull=True,
            date__gte=goal.period.start_date,
            date__lte=min(today, goal.period.end_date),
        ).select_related("attention").prefetch_related("evidences__validations")
    )
    approved_activity_ids = {
        activity.pk for activity in activities if _activity_is_approved(activity)
    }
    approved_activities = len(approved_activity_ids)
    raw_approved_evidences = sum(
        1 for a in activities for e in a.evidences.all() if _evidence_is_approved(e)
    )
    expected = Decimal(goal.objective_value)
    if expected <= 0:
        raise ValueError("El valor objetivo de la meta debe ser mayor que cero.")

    item = goal.measurement_item
    formula = (item.formula or "").strip() if item else ""
    # Algunos ítems cuantitativos históricos usan formula como texto libre,
    # no como expresión. Mantener su cómputo antiguo hasta que la fórmula
    # se configure explícitamente con variables conocidas.
    if item and item.item_type != "percentage":
        from planning_measurements.measurement_rules import canonical_percentage_formula
        if not canonical_percentage_formula(formula):
            formula = ""
    if item and item.item_type == "percentage" and not formula:
        raise FormulaError("El ítem porcentual no tiene una fórmula definida.")

    if formula:
        values = _goal_formula_values(
            goal, activities, approved_activity_ids, raw_approved_evidences, today,
        )
        actual = evaluate_formula(formula, values).quantize(
            Decimal("0.01"), ROUND_HALF_UP,
        )
    else:
        # Regla histórica de los ítems cuantitativos sin fórmula: una unidad
        # por actividad con al menos una evidencia aprobada.
        actual = Decimal(approved_activities)

    cap = _compliance_cap(goal.period)
    compliance = min(actual / expected * Decimal("100"), cap).quantize(
        Decimal("0.01"), ROUND_HALF_UP,
    )
    expected_progress = _expected_progress(goal.period)
    adjustment = Decimal(existing_indicator.adjustment) if existing_indicator else Decimal("0")
    adjusted_compliance = max(Decimal("0"), min(compliance + adjustment, cap))
    weighted_result = (
        goal.weight * adjusted_compliance / Decimal("100")
    ).quantize(Decimal("0.01"), ROUND_HALF_UP)
    difference = (actual - expected).quantize(Decimal("0.01"), ROUND_HALF_UP)

    indicator = existing_indicator
    if indicator is None and create_if_missing:
        indicator = Indicator(goal=goal, employee=goal.employee, calculation_date=today)
    if indicator is None:
        return None
    indicator.employee = goal.employee
    indicator.calculation_date = today
    indicator.expected_value = expected
    indicator.actual_progress = actual
    indicator.expected_progress = expected_progress
    indicator.green_progress = expected_progress
    indicator.difference = difference
    indicator.compliance = compliance
    indicator.weighting = goal.weight
    indicator.weighted_result = weighted_result
    indicator.approved_activities = approved_activities
    indicator.approved_evidences = raw_approved_evidences
    indicator.traffic_light = _traffic_light(compliance, goal.period, expected_progress)
    indicator.save(update_fields=[
        "employee", "expected_value", "actual_progress", "green_progress",
        "expected_progress", "difference", "compliance", "weighting",
        "weighted_result", "approved_activities", "approved_evidences",
        "traffic_light", "calculation_date", "updated_at",
    ] if indicator.pk else None)
    return indicator


def synchronize_commitment_alerts(commitments):
    """Keep one open alert per current commitment deadline condition."""
    today = timezone.localdate()
    due_soon_days = get_monitoring_settings().due_soon_days
    for commitment in commitments:
        if commitment.is_completed or commitment.status.casefold() in {
            "cancelled", "cancelado"
        }:
            CommitmentAlert.objects.filter(
                commitment=commitment,
                resolved_at__isnull=True,
            ).update(resolved_at=timezone.now(), updated_at=timezone.now())
            continue
        alert_type = (
            "overdue"
            if commitment.commitment_date < today
            else "due_soon"
            if commitment.commitment_date <= today + timedelta(days=due_soon_days)
            else None
        )
        if alert_type is None:
            # Al reprogramar o terminar un compromiso no debe persistir un
            # aviso cuyo motivo ya no corresponde.
            CommitmentAlert.objects.filter(
                commitment=commitment, resolved_at__isnull=True,
            ).update(resolved_at=timezone.now(), updated_at=timezone.now())
            continue
        message = (
            "Compromiso vencido."
            if alert_type == "overdue"
            else "Compromiso próximo a vencer."
        )
        CommitmentAlert.objects.filter(
            commitment=commitment,
            alert_type="overdue" if alert_type == "due_soon" else "due_soon",
            resolved_at__isnull=True,
        ).update(resolved_at=timezone.now(), updated_at=timezone.now())
        alert, created = CommitmentAlert.objects.get_or_create(
            commitment=commitment,
            alert_type=alert_type,
            resolved_at=None,
            defaults={
                "message": message,
                "due_at": commitment.commitment_date,
            },
        )
        if not created and (
            alert.due_at != commitment.commitment_date or alert.message != message
        ):
            alert.due_at = commitment.commitment_date
            alert.message = message
            alert.save(update_fields=["due_at", "message", "updated_at"])
        if alert_type == "overdue":
            _notify_overdue_commitment(commitment)


def _notify_overdue_commitment(commitment):
    """Notify the responsible employee and delegation administrator once."""
    responsible_user = getattr(
        getattr(commitment.responsible, "user_profile", None),
        "user",
        None,
    )
    delegation_admin = getattr(commitment.delegation, "responsible", None)
    admin_user = getattr(
        getattr(delegation_admin, "user_profile", None),
        "user",
        None,
    )
    admin_users = UserProfile.objects.filter(
        delegation=commitment.delegation,
        user__is_active=True,
    ).values_list("user_id", flat=True)
    recipients = {
        user.pk: user for user in (responsible_user, admin_user) if user
    }
    if admin_users:
        users = get_user_model().objects.filter(pk__in=admin_users)
        recipients.update({user.pk: user for user in users})
    rule = get_monitoring_settings()
    if rule.pk:
        # Los destinatarios configurados no reciben detalles de delegaciones
        # ajenas: conservar la misma autorización de lectura del compromiso.
        from accounts.permissions import allowed_delegation_ids
        for recipient in rule.recipient_users.filter(is_active=True):
            if commitment.delegation_id in allowed_delegation_ids(
                recipient, "monitoring_traceability.view_commitment"
            ):
                recipients[recipient.pk] = recipient
    admin_fallback = next(iter(recipients.values()), None)

    if not recipients:
        return

    sender = (
        commitment.delegation.created_by
        or responsible_user
        or admin_user
        or admin_fallback
    )
    if sender is None:
        return
    subject = f"Compromiso vencido: {commitment.origin}"
    body = (
        f"El compromiso asociado a la meta «{commitment.origin}» "
        f"venció el {commitment.commitment_date:%d/%m/%Y}.\n"
        f"Responsable actual: {commitment.responsible.name}.\n"
        "Revisa el compromiso y gestiona la reasignación pendiente."
    )
    for recipient in recipients.values():
        if InstitutionalMessage.objects.filter(
            sender=sender,
            recipient=recipient,
            subject=subject,
            body=body,
        ).exists():
            continue
        InstitutionalMessage.objects.create(
            sender=sender,
            recipient=recipient,
            subject=subject,
            body=body,
            notice_status=InstitutionalMessage.NoticeStatus.SENT,
        )


def synchronize_indicators_for_goals(goals):
    """Create or recalculate the derived indicator for each active goal."""
    for goal in goals.select_related("employee", "period"):
        if goal.deleted_at is None and goal.period.deleted_at is None:
            recalculate_indicator_for_goal(goal, create_if_missing=True)


def valid_activity_queryset(employee_ids, *, period=None, on_date=None):
    """Registros válidos para Monitoreo, nunca futuros ni fuera de su meta.

    Se reutiliza en el Resumen Ejecutivo y el Control de Actividad para
    que ambos informen el mismo último registro y cantidad válida.
    No cambia ni elimina actividades de Registro y Validación.
    """
    on_date = on_date or timezone.localdate()
    activities = Activity.objects.filter(
        deleted_at__isnull=True,
        goal__deleted_at__isnull=True,
        goal__period__deleted_at__isnull=True,
        author_id__in=employee_ids,
        date__lte=on_date,
        date__gte=F("goal__period__start_date"),
    )
    # Mantener ambas cotas con nombres de campo distintos en una misma consulta.
    activities = activities.exclude(date__gt=F("goal__period__end_date"))
    if period is not None:
        activities = activities.filter(goal__period=period)
    return activities


def activity_missing_workdays(employee, last_activity, as_of, period=None):
    """Días hábiles sin registros (mismo criterio que las alertas)."""
    if last_activity is not None:
        first_missing = last_activity + timedelta(days=1)
    elif period is not None:
        first_missing = period.start_date
    else:
        first_missing = timezone.localtime(employee.created_at).date()
    return calculate_computable_days(first_missing, as_of) if first_missing <= as_of else 0


def inactivity_threshold_days():
    """Umbral configurable en el propio módulo; sin lectura de env temporal."""
    return get_monitoring_settings().inactivity_workdays


def _inactivity_details(employees, period=None):
    """RF-037: falta de actividad medida en días hábiles y con alcance territorial."""
    today = timezone.localdate()
    if period is not None and (
        today < period.start_date or today > period.end_date
        or period.status.casefold() == "closed"
    ):
        return []
    days_limit = inactivity_threshold_days()
    authorized = [employee for employee in employees if employee.status.casefold() == "active"]
    if not authorized:
        return []
    records = valid_activity_queryset(
        [employee.pk for employee in authorized], period=period, on_date=today,
    )
    latest = dict(
        records.values("author_id").annotate(last=Max("date"))
        .values_list("author_id", "last")
    )
    alerts = []
    for employee in authorized:
        previous = latest.get(employee.pk)
        missing_days = activity_missing_workdays(employee, previous, today, period)
        if missing_days >= days_limit:
            alerts.append({
                "employee": employee,
                "missing_days": missing_days,
                "last_activity": previous,
                "threshold": days_limit,
            })
    return alerts


def monitoring_alerts(*, employees, period=None, minimum_compliance=None):
    """Return operational alerts using only active monitoring records."""
    if minimum_compliance is None:
        minimum_compliance = get_monitoring_settings().low_compliance_threshold
    employee_ids = [employee.pk for employee in employees]
    activity_filter = {
        "deleted_at__isnull": True,
        "author_id__in": employee_ids,
    }
    if period is not None:
        activity_filter.update(
            date__gte=period.start_date,
            date__lte=period.end_date,
        )

    pending_evidences = pending_evidence_queryset(Evidence.objects.filter(
        deleted_at__isnull=True,
        activity__in=Activity.objects.filter(**activity_filter),
    )).count()

    overdue_scope = Commitment.objects.filter(
        deleted_at__isnull=True,
        responsible_id__in=employee_ids,
        commitment_date__lt=timezone.localdate(),
    )
    if period is not None:
        overdue_scope = overdue_scope.filter(
            commitment_date__gte=period.start_date,
            commitment_date__lte=period.end_date,
        )
    overdue_commitments = overdue_scope.exclude(
        status__in=(
            "Completed", "Completado", "Realizado",
            "Validated", "Validado", "Cancelled", "Cancelado",
        ),
    ).count()

    performance_scope = Indicator.objects.filter(
        deleted_at__isnull=True,
        employee_id__in=employee_ids,
        compliance__lt=minimum_compliance,
    )
    if period is not None:
        performance_scope = performance_scope.filter(goal__period=period)
    low_performance = performance_scope.count()

    inactivity = _inactivity_details(employees, period)
    return {
        "pending_evidences": pending_evidences,
        "overdue_commitments": overdue_commitments,
        "low_performance": low_performance,
        "inactive_employees": len(inactivity),
        "inactive_details": inactivity[:20],
    }
