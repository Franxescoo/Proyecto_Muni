import re
from decimal import Decimal, ROUND_HALF_UP
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from accounts.models import UserProfile
from institutional_mail.models import InstitutionalMessage

from .models import Commitment, CommitmentAlert, Indicator
from planning_measurements.measurement_rules import canonical_percentage_formula
from planning_measurements.working_days import calculate_computable_days
from registration_validation.models import Activity, Evidence


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


def recalculate_indicator_for_goal(goal, create_if_missing=True):
    today = timezone.localdate()
    activities = (
        goal.activities.filter(
            deleted_at__isnull=True,
            date__gte=goal.period.start_date,
            date__lte=min(today, goal.period.end_date),
        )
        .prefetch_related("evidences__validations")
    )
    approved_activities = sum(
        _activity_is_approved(activity)
        for activity in activities
    )
    raw_approved_evidences = sum(
        1
        for activity in activities
        for evidence in activity.evidences.all()
        if _evidence_is_approved(evidence)
    )

    expected = Decimal(goal.objective_value)
    actual = Decimal(approved_activities)


    # Fórmula porcentual: actividades aprobadas / registradas.
    item = goal.measurement_item

    if item and item.item_type == "percentage":
        if canonical_percentage_formula(item.formula):
            total_actividades = len(activities)

            if total_actividades > 0:
                actual = (
                    Decimal(approved_activities)
                    / Decimal(total_actividades)
                    * Decimal("100")
                ).quantize(
                    Decimal("0.01"),
                    ROUND_HALF_UP,
                )
            else:
                actual = Decimal("0.00")


    if expected <= 0:
        raise ValueError(
            "El valor objetivo de la meta debe ser mayor que cero."
        )

    cap = _compliance_cap(goal.period)

    compliance = (
        actual / expected * Decimal("100")
    )

    compliance = min(compliance, cap).quantize(
        Decimal("0.01"), ROUND_HALF_UP
    )

    expected_progress = _expected_progress(goal.period)

    existing_indicator = (
        Indicator.objects.filter(
            goal=goal,
            deleted_at__isnull=True,
        )
        .order_by("-calculation_date", "-indicator_id")
        .first()
    )
    adjustment = (
        Decimal(existing_indicator.adjustment)
        if existing_indicator is not None
        else Decimal("0")
    )
    adjusted_compliance = max(
        Decimal("0"),
        min(compliance + adjustment, cap),
    )
    weighted_result = (
        goal.weight * adjusted_compliance / Decimal("100")
    ).quantize(Decimal("0.01"), ROUND_HALF_UP)

    difference = (actual - expected).quantize(
        Decimal("0.01"), ROUND_HALF_UP
    )



    indicator = existing_indicator
    if indicator is None and create_if_missing:
        indicator = Indicator(
            goal=goal,
            employee=goal.employee,
            calculation_date=today,
        )
    if indicator is None:
        return None

    indicator.employee = goal.employee
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
    indicator.traffic_light = _traffic_light(
        compliance,
        goal.period,
        expected_progress,
    )
    indicator.save(
        update_fields=[
            "employee",
            "expected_value",
            "actual_progress",
            "green_progress",
            "expected_progress",
            "difference",
            "compliance",
            "weighting",
            "weighted_result",
            "approved_activities",
            "approved_evidences",
            "traffic_light",
            "updated_at",
        ]
        if indicator.pk
        else None
    )
    return indicator


def synchronize_commitment_alerts(commitments):
    """Keep one open alert per current commitment deadline condition."""
    today = timezone.localdate()
    for commitment in commitments:
        if commitment.is_completed:
            CommitmentAlert.objects.filter(
                commitment=commitment,
                resolved_at__isnull=True,
            ).update(resolved_at=timezone.now(), updated_at=timezone.now())
            continue
        alert_type = (
            "overdue"
            if commitment.commitment_date < today
            else "due_soon"
            if commitment.commitment_date <= today + timedelta(days=7)
            else None
        )
        if alert_type is None:
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
        CommitmentAlert.objects.get_or_create(
            commitment=commitment,
            alert_type=alert_type,
            resolved_at=None,
            defaults={
                "message": message,
                "due_at": commitment.commitment_date,
            },
        )
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


def monitoring_alerts(*, employees, period=None, minimum_compliance=Decimal("80")):
    """Return operational alerts using only active monitoring records."""
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

    pending_evidences = Evidence.objects.filter(
        deleted_at__isnull=True,
        activity__in=Activity.objects.filter(**activity_filter),
    ).exclude(
        review_status__iexact="Approved",
    ).count()

    overdue_commitments = Commitment.objects.filter(
        deleted_at__isnull=True,
        responsible_id__in=employee_ids,
        commitment_date__lt=timezone.localdate(),
    ).exclude(
        status__in=("Completed", "Completado", "Realizado"),
    ).count()

    low_performance = Indicator.objects.filter(
        deleted_at__isnull=True,
        employee_id__in=employee_ids,
        compliance__lt=minimum_compliance,
    ).count()

    return {
        "pending_evidences": pending_evidences,
        "overdue_commitments": overdue_commitments,
        "low_performance": low_performance,
    }
