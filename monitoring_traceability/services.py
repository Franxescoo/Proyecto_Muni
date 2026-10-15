import re
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from .models import Indicator


MIN_APPROVED_EVIDENCES = 2
MAX_APPROVED_EVIDENCES = 5


_THRESHOLD_PATTERN = re.compile(
    r"(?P<label>[A-Za-zÁÉÍÓÚáéíóúñÑ]+)\s*[:>=]+\s*"
    r"(?P<value>\d+(?:[.,]\d+)?)"
)


def _thresholds(period):
    values = {}
    for match in _THRESHOLD_PATTERN.finditer(period.thresholds or ""):
        label = match.group("label").lower()
        values[label] = Decimal(match.group("value").replace(",", "."))

    if "green" in values or "verde" in values:
        green = values.get("green", values.get("verde"))
        yellow = values.get("yellow", values.get("amarillo", Decimal("60")))
        return green, yellow

    ordered = sorted(values.values(), reverse=True)
    if not ordered:
        return Decimal("90"), Decimal("60")
    green = ordered[0]
    yellow = ordered[1] if len(ordered) > 1 else Decimal("60")
    return green, yellow


def _traffic_light(compliance, period):
    expected = _expected_progress(period)
    if compliance >= expected:
        return "Green"
    if compliance >= expected * Decimal("0.60"):
        return "Yellow"
    return "Red"


def _expected_progress(period, on_date=None):
    on_date = on_date or date.today()
    total_days = period.computable_days or (
        period.end_date - period.start_date
    ).days + 1
    if on_date <= period.start_date:
        return Decimal("0.00")
    elapsed = min(
        max((on_date - period.start_date).days + 1, 0),
        total_days,
    )
    return (
        Decimal(elapsed) / Decimal(total_days) * Decimal("100")
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
        ).order_by("-date", "-version")
    )
    if validations:
        latest = validations[0]
        return (
            latest.decision.casefold() == "approved"
            or latest.result.casefold() == "approved"
        )
    return evidence.review_status.casefold() == "approved"


def _activity_is_approved(activity):
    return any(
        _evidence_is_approved(evidence)
        for evidence in activity.evidences.all()
    )


def recalculate_indicator_for_goal(goal, create_if_missing=True):
    activities = (
        goal.activities.filter(
            deleted_at__isnull=True,
            date__gte=goal.period.start_date,
            date__lte=goal.period.end_date,
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
    approved_evidences = min(
        raw_approved_evidences,
        MAX_APPROVED_EVIDENCES,
    )

    expected = Decimal(goal.objective_value)
    actual = Decimal(min(approved_evidences, MAX_APPROVED_EVIDENCES))
    cap = _compliance_cap(goal.period)
    if approved_evidences < MIN_APPROVED_EVIDENCES:
        compliance = Decimal("0")
    else:
        compliance = (
            Decimal(
                approved_evidences - MIN_APPROVED_EVIDENCES
            )
            / Decimal(MAX_APPROVED_EVIDENCES - MIN_APPROVED_EVIDENCES)
            * Decimal("100")
        )
    compliance = min(compliance, cap).quantize(
        Decimal("0.01"), ROUND_HALF_UP
    )
    expected_progress = _expected_progress(goal.period)
    weighted_result = (
        goal.weight * compliance / Decimal("100")
    ).quantize(Decimal("0.01"), ROUND_HALF_UP)
    difference = (actual - expected).quantize(
        Decimal("0.01"), ROUND_HALF_UP
    )

    indicator = (
        Indicator.objects.filter(
            goal=goal,
            deleted_at__isnull=True,
        )
        .order_by("-calculation_date", "-indicator_id")
        .first()
    )
    if indicator is None and create_if_missing:
        indicator = Indicator(
            goal=goal,
            employee=goal.employee,
            calculation_date=date.today(),
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
    indicator.approved_evidences = approved_evidences
    indicator.traffic_light = _traffic_light(compliance, goal.period)
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


def synchronize_indicators_for_goals(goals):
    """Create or recalculate the derived indicator for each active goal."""
    for goal in goals.select_related("employee", "period"):
        if goal.deleted_at is None and goal.period.deleted_at is None:
            recalculate_indicator_for_goal(goal, create_if_missing=True)
