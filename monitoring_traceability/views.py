from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from decimal import Decimal, InvalidOperation

from websocket.live import suppress_indicator_reload

from django.db import transaction
from django.db.models import Prefetch, Q, Count, F
from django.shortcuts import render
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from organization.models import Delegation, Employee
from planning_measurements.models import Goal, Period
from planning_measurements.working_days import calculate_computable_days
from registration_validation.models import Activity, Evidence

from .forms import CommitmentForm, CommitmentReassignmentForm, MonitoringSettingsForm
from .models import (
    Audit,
    Commitment,
    CommitmentAlert,
    CommitmentComment,
    CommitmentReassignment,
    CommitmentStatusHistory,
    Indicator,
    MonitoringSettings, MonitoringSettingsRevision, MonitoringAlertReview,
)
from .services import (
    monitoring_alerts,
    synchronize_commitment_alerts,
    synchronize_indicators_for_goals,
    pending_evidence_queryset,
    valid_activity_queryset,
    activity_missing_workdays,
    inactivity_threshold_days,
)
from organization.exports import workbook_response
from .monitor_policy import get_monitoring_settings, settings_snapshot


from accounts.permissions import allowed_delegation_ids


def _scoped_queryset(queryset, user, relation, permission):
    queryset = queryset.filter(deleted_at__isnull=True)
    if user.is_superuser:
        return queryset
    ids = allowed_delegation_ids(user, permission)
    if not ids:
        return queryset.none()
    return queryset.filter(**{f"{relation}__delegation_id__in": ids})


def _query(value):
    return value.strip() if value else ""


def _employee_scope(request, permission):
    employees = Employee.objects.filter(
        deleted_at__isnull=True,
    ).select_related(
        "delegation",
        "position",
        "user_profile__user",
    )
    if request.user.is_superuser:
        return employees
    ids = allowed_delegation_ids(request.user, permission)
    return employees.filter(delegation_id__in=ids) if ids else employees.none()


def _activity_scope(request):
    employees = _employee_scope(
        request, "monitoring_traceability.view_commitment"
    )
    return Activity.objects.filter(
        deleted_at__isnull=True,
        author_id__in=employees.values("pk"),
    ).select_related("goal", "attention")


def _period_from_request(request):
    period_id = _query(request.GET.get("period"))
    if not period_id.isdigit():
        return None
    return Period.objects.filter(
        pk=period_id,
        deleted_at__isnull=True,
    ).first()


def _filter_effective_traffic_light(indicators, color):
    """Filtra por estado visible, no solo por semáforo técnico."""
    color = (color or "").casefold()
    missing = Q(approved_evidences__lt=F("goal__required_evidence_count"))
    if color in {"pending", "pendiente"}:
        return indicators.filter(missing)
    if color in {"green", "yellow", "red", "verde", "amarillo", "rojo"}:
        return indicators.exclude(missing).filter(traffic_light__iexact=color)
    return indicators


@login_required
@permission_required("monitoring_traceability.view_indicator", raise_exception=True)
def indicator_list(request):
    employees = _employee_scope(
        request,
        "monitoring_traceability.view_indicator",
    )
    goals = Goal.objects.filter(
        deleted_at__isnull=True,
        period__deleted_at__isnull=True,
    ).select_related(
        "employee",
        "period",
        "position",
        "measurement_item",
    ).filter(employee_id__in=employees.values("pk"))

    delegation_id = _query(request.GET.get("delegation"))
    position_id = _query(request.GET.get("position"))
    period = _period_from_request(request)
    if delegation_id.isdigit():
        goals = goals.filter(employee__delegation_id=delegation_id)
        employees = employees.filter(delegation_id=delegation_id)
    if position_id.isdigit():
        goals = goals.filter(position_id=position_id)
        employees = employees.filter(position_id=position_id)
    if period is not None:
        goals = goals.filter(period=period)

    with suppress_indicator_reload():
        synchronize_indicators_for_goals(goals)

    indicators = _scoped_queryset(
        Indicator.objects.select_related("goal", "employee", "goal__period"),
        request.user,
        "employee", "monitoring_traceability.view_indicator",
    ).filter(
        goal__deleted_at__isnull=True,
        goal__period__deleted_at__isnull=True,
    )

    search = _query(request.GET.get("q"))
    traffic_light = _query(request.GET.get("traffic_light"))
    if search:
        indicators = indicators.filter(
            Q(goal__item__icontains=search)
            | Q(employee__name__icontains=search)
        )
    if traffic_light:
        indicators = _filter_effective_traffic_light(indicators, traffic_light)
    if delegation_id.isdigit():
        indicators = indicators.filter(employee__delegation_id=delegation_id)
    if position_id.isdigit():
        indicators = indicators.filter(goal__position_id=position_id)
    if period is not None:
        indicators = indicators.filter(goal__period=period)

    if request.method == "POST":
        if not request.user.has_perm("monitoring_traceability.change_indicator"):
            raise PermissionDenied("No puedes ajustar indicadores.")
        indicator = indicators.filter(pk=request.POST.get("indicator_id")).first()
        if indicator is None:
            messages.error(request, "El indicador no está disponible.")
        elif indicator.goal.period.status.casefold() == "closed":
            messages.error(request, "No se pueden ajustar indicadores de períodos cerrados.")
        else:
            try:
                adjustment = Decimal(request.POST.get("adjustment", "0"))
            except (InvalidOperation, TypeError, ValueError):
                adjustment = None
            reason = _query(request.POST.get("reason"))
            category = _query(request.POST.get("adjustment_type"))
            rule = get_monitoring_settings()
            lower_limit = -rule.negative_adjustment_max
            upper_limit = rule.positive_adjustment_max
            if adjustment is not None and adjustment.is_finite() and not category:
                category = "bonificacion" if adjustment > 0 else "penalizacion" if adjustment < 0 else "rectificacion"
            if (
                adjustment is None or not adjustment.is_finite()
                or adjustment < lower_limit or adjustment > upper_limit
            ):
                messages.error(request, f"El ajuste debe estar entre {lower_limit} y {upper_limit}.")
            elif category not in {"bonificacion", "penalizacion", "rectificacion"}:
                messages.error(request, "Selecciona un tipo de ajuste válido.")
            elif (category == "bonificacion" and adjustment < 0) or (category == "penalizacion" and adjustment > 0):
                messages.error(request, "El signo del ajuste no corresponde a su tipo.")
            elif adjustment != indicator.adjustment and not reason:
                messages.error(request, "Indica el motivo del ajuste para conservar su trazabilidad.")
            elif adjustment != indicator.adjustment:
                previous = str(indicator.adjustment)
                with transaction.atomic():
                    indicator.adjustment = adjustment
                    indicator.save(update_fields=["adjustment", "updated_at"])
                    profile = getattr(request.user, "profile", None)
                    actor_employee = getattr(profile, "employee", None)
                    if actor_employee is None:
                        raise PermissionDenied("El usuario debe estar vinculado a un empleado para auditar el ajuste.")
                    Audit.objects.create(
                        user=actor_employee,
                        event="Adjusted Indicator",
                        entity="Indicator",
                        object_identifier=str(indicator.pk),
                        previous_value={"adjustment": previous},
                        new_value={
                            "adjustment": str(adjustment),
                            "reason": reason,
                            "tipo": category,
                            "editado_por": request.user.get_username(),
                        },
                    )
                    synchronize_indicators_for_goals(
                        Goal.objects.filter(pk=indicator.goal_id)
                    )
                messages.success(request, "Ajuste aplicado y registrado en el historial.")
            else:
                messages.info(request, "El indicador no presentó cambios.")
        return redirect(request.get_full_path())

    total = indicators.count()
    compliant = indicators.filter(
        traffic_light__iregex=r"^(green|verde)$",
        approved_evidences__gte=F("goal__required_evidence_count"),
    ).count()
    attention = indicators.filter(
        Q(traffic_light__iregex=r"^(red|rojo)$")
        | Q(approved_evidences__lt=F("goal__required_evidence_count"))
    ).count()

    return render(
        request,
        "monitoringfronen/indic.html",
        {
            "indicators": indicators,
            "total_indicators": total,
            "compliant_indicators": compliant,
            "attention_indicators": attention,
            "selected_period": period,
            "delegations": employees.order_by("delegation__name").values(
                "delegation_id", "delegation__name"
            ).distinct(),
            "positions": employees.order_by("position__position_name").values(
                "position_id", "position__position_name"
            ).distinct(),
            "periods": Period.objects.filter(
                deleted_at__isnull=True,
            ).order_by("-start_date"),
        },
    )


@login_required
@permission_required("monitoring_traceability.view_indicator", raise_exception=True)
def indicator_export(request):
    employees = _employee_scope(request, "monitoring_traceability.view_indicator")
    indicators = Indicator.objects.filter(
        deleted_at__isnull=True,
        goal__deleted_at__isnull=True,
        goal__period__deleted_at__isnull=True,
        employee_id__in=employees.values("pk"),
    ).select_related("goal", "employee", "goal__period")
    search = _query(request.GET.get("q"))
    traffic_light = _query(request.GET.get("traffic_light"))
    period = _period_from_request(request)
    if search:
        indicators = indicators.filter(
            Q(goal__item__icontains=search)
            | Q(employee__name__icontains=search)
        )
    if traffic_light:
        indicators = _filter_effective_traffic_light(indicators, traffic_light)
    if period is not None:
        indicators = indicators.filter(goal__period=period)
    delegation_id = _query(request.GET.get("delegation"))
    position_id = _query(request.GET.get("position"))
    if delegation_id.isdigit():
        indicators = indicators.filter(employee__delegation_id=delegation_id)
    if position_id.isdigit():
        indicators = indicators.filter(goal__position_id=position_id)
    metadata = (
        f"Filtros: delegación={delegation_id or 'todas'}; cargo={position_id or 'todos'}; "
        f"q={search or '-'}; semáforo={traffic_light or 'todos'}; "
        f"período={period or 'todos'}; "
        f"generado={timezone.localtime():%Y-%m-%d %H:%M}"
    )
    return workbook_response(
        "indicadores_monitoreo.xlsx",
        ["Meta", "Funcionario", "Avance esperado", "Avance real",
         "Cumplimiento calculado", "Ajuste", "Resultado ponderado",
         "Evidencias requeridas", "Evidencias aprobadas", "Acreditación",
         "Estado visible", "Semáforo técnico", "Fecha cálculo", "Metadatos"],
        [
            (
                indicator.goal.item,
                indicator.employee.name,
                indicator.expected_progress,
                indicator.actual_progress,
                indicator.compliance,
                indicator.adjustment,
                indicator.weighted_result,
                indicator.goal.required_evidence_count,
                indicator.approved_evidences,
                indicator.accreditation_label,
                indicator.effective_traffic_light,
                indicator.traffic_light,
                indicator.calculation_date,
                metadata,
            )
            for indicator in indicators.order_by("employee__name", "goal__item")
        ],
    )


@login_required
@permission_required("monitoring_traceability.view_indicator", raise_exception=True)
def executive_dashboard(request):
    employees = _employee_scope(
        request,
        "monitoring_traceability.view_indicator",
    )
    period = _period_from_request(request)
    delegation_id = _query(request.GET.get("delegation"))
    position_id = _query(request.GET.get("position"))

    if delegation_id.isdigit():
        employees = employees.filter(delegation_id=delegation_id)
    # El cargo del indicador es el cargo histórico asignado a la meta.
    # No limitar primero por el cargo actual del funcionario.

    goals = Goal.objects.filter(
        deleted_at__isnull=True,
        period__deleted_at__isnull=True,
        employee_id__in=employees.values("pk"),
    ).select_related("employee", "period", "position")
    if period is not None:
        goals = goals.filter(period=period)
    if position_id.isdigit():
        goals = goals.filter(position_id=position_id)
        employees = employees.filter(pk__in=goals.values("employee_id"))
    with suppress_indicator_reload():
        synchronize_indicators_for_goals(goals)

    indicators = Indicator.objects.filter(
        deleted_at__isnull=True,
        goal__deleted_at__isnull=True,
        goal__period__deleted_at__isnull=True,
        employee_id__in=employees.values("pk"),
    ).select_related("employee", "goal", "goal__period", "goal__position")
    if period is not None:
        indicators = indicators.filter(goal__period=period)
    if position_id.isdigit():
        indicators = indicators.filter(goal__position_id=position_id)

    rows = {}
    for indicator in indicators:
        row = rows.setdefault(
            indicator.employee_id,
            {
                "employee": indicator.employee,
                "goals": 0,
                "weighting": Decimal("0"),
                "weighted_result": Decimal("0"),
                "approved_evidences": 0,
                "compliance": Decimal("0"),
                "green": 0,
                "yellow": 0,
                "red": 0,
                "pending": 0,
            },
        )
        row["goals"] += 1
        row["weighting"] += indicator.weighting
        row["weighted_result"] += indicator.weighted_result
        row["approved_evidences"] += indicator.approved_evidences
        row["compliance"] += indicator.compliance
        color = indicator.effective_traffic_light.casefold()
        if color in {"pending", "pendiente"}:
            row["pending"] += 1
        elif color in {"green", "verde"}:
            row["green"] += 1
        elif color in {"yellow", "amarillo"}:
            row["yellow"] += 1
        else:
            row["red"] += 1

    for row in rows.values():
        row["compliance"] = (
            row["compliance"] / row["goals"]
        ).quantize(Decimal("0.01"))

    # RF-031: agrupar por el cargo de la META y período, no por cargo actual.
    positions_summary = {}
    for indicator in indicators:
        goal = indicator.goal
        key = (goal.position_id, goal.period_id)
        summary = positions_summary.setdefault(key, {
            "position": goal.position,
            "period": goal.period,
            "employees": set(), "goals": 0,
            "weighting": Decimal("0"), "weighted_result": Decimal("0"),
            "compliance": Decimal("0"), "approved_evidences": 0,
            "latest_calculation": None,
        })
        summary["employees"].add(indicator.employee_id)
        summary["goals"] += 1
        summary["weighting"] += indicator.weighting
        summary["weighted_result"] += indicator.weighted_result
        summary["compliance"] += indicator.compliance
        summary["approved_evidences"] += indicator.approved_evidences
        if (summary["latest_calculation"] is None
                or indicator.calculation_date > summary["latest_calculation"]):
            summary["latest_calculation"] = indicator.calculation_date
    for summary in positions_summary.values():
        summary["employee_count"] = len(summary["employees"])
        summary["compliance"] = (
            summary["compliance"] / summary["goals"]
        ).quantize(Decimal("0.01"))
    ordered_position_summaries = sorted(
        positions_summary.values(),
        key=lambda x: (str(x["position"]), x["period"].start_date),
    )

    employees = employees.order_by("name")
    monitoring_rule = get_monitoring_settings()
    alerts = monitoring_alerts(
        employees=employees,
        period=period,
        minimum_compliance=monitoring_rule.low_compliance_threshold,
    )
    commitment_scope = Commitment.objects.filter(
        deleted_at__isnull=True,
        responsible_id__in=employees.values("pk"),
    )
    if period is not None:
        commitment_scope = commitment_scope.filter(
            commitment_date__gte=period.start_date,
            commitment_date__lte=period.end_date,
        )
    synchronize_commitment_alerts(commitment_scope)
    # Mostrar solo las alertas de compromisos que pertenecen al ámbito
    # y período seleccionados. No modifica la generación de las alertas.
    commitment_alerts = CommitmentAlert.objects.filter(
        commitment__in=commitment_scope,
        resolved_at__isnull=True,
    ).select_related(
        "commitment", "commitment__responsible", "commitment__delegation"
    ).order_by("due_at", "pk")[:25]
    commitment_alerts = list(commitment_alerts)

    # Desgloses de lectura: mismos criterios de los contadores ya existentes.
    # No revelar detalles de evidencias a cuentas sin permiso de consulta.
    evidence_employee_ids = (
        _employee_scope(request, "registration_validation.view_evidence")
        .filter(pk__in=employees.values("pk"))
        .values("pk")
        if request.user.has_perm("registration_validation.view_evidence")
        else []
    )
    pending_evidence_details = Evidence.objects.filter(
        deleted_at__isnull=True,
        activity__deleted_at__isnull=True,
        activity__author_id__in=evidence_employee_ids,
    )
    if period is not None:
        pending_evidence_details = pending_evidence_details.filter(
            activity__date__gte=period.start_date,
            activity__date__lte=period.end_date,
        )
    pending_evidence_details = pending_evidence_queryset(
        pending_evidence_details
    ).select_related(
        "activity__author__delegation", "activity__goal"
    ).order_by("-date", "-pk")[:20]
    pending_evidence_details = list(pending_evidence_details)

    low_performance_scope = Indicator.objects.filter(
        deleted_at__isnull=True,
        employee_id__in=employees.values("pk"),
        compliance__lt=monitoring_rule.low_compliance_threshold,
    )
    if period is not None:
        low_performance_scope = low_performance_scope.filter(goal__period=period)
    low_performance_details = low_performance_scope.select_related(
        "employee__delegation", "goal"
    ).order_by("compliance", "pk")[:20]
    low_performance_details = list(low_performance_details)

    # Las alertas derivadas reciben una clave estable. Revisar no las elimina.
    alert_keys = {}
    for alert in commitment_alerts:
        alert.monitor_key = f"compromiso:{alert.pk}"
        alert_keys[alert.monitor_key] = "commitment"
    for evidence in pending_evidence_details:
        evidence.monitor_key = f"evidencia:{evidence.pk}:v{evidence._last_validation_pk or 0}"
        alert_keys[evidence.monitor_key] = "evidence"
    for record in alerts["inactive_details"]:
        record["monitor_key"] = (
            f"inactividad:{record['employee'].pk}:"
            f"{record['last_activity'] or 'sin-registro'}:{record['threshold']}"
        )
        alert_keys[record["monitor_key"]] = "inactivity"
    for indicator in low_performance_details:
        indicator.monitor_key = f"bajo:{indicator.pk}:{indicator.compliance}:{monitoring_rule.low_compliance_threshold}"
        alert_keys[indicator.monitor_key] = "low"
    if request.method == "POST":
        key = _query(request.POST.get("alert_key"))
        alert_kind = alert_keys.get(key)
        may_review = (
            request.user.has_perm("monitoring_traceability.change_commitment")
            if alert_kind == "commitment"
            else request.user.has_perm("monitoring_traceability.change_indicator")
        )
        if not alert_kind or not may_review or (
            alert_kind == "evidence" and not request.user.has_perm("registration_validation.view_evidence")
        ):
            raise PermissionDenied("La alerta no está disponible o falta autorización.")
        with transaction.atomic():
            _, created = MonitoringAlertReview.objects.get_or_create(
                alert_key=key,
                defaults={"reviewed_by": request.user, "comment": _query(request.POST.get("comment"))[:250]},
            )
        messages.success(request, "Alerta marcada como revisada." if created else "La alerta ya estaba revisada.")
        return redirect(request.get_full_path())
    seen = set(MonitoringAlertReview.objects.filter(
        alert_key__in=alert_keys,
    ).values_list("alert_key", flat=True))
    for alert in commitment_alerts:
        alert.monitor_reviewed = alert.monitor_key in seen
    for evidence in pending_evidence_details:
        evidence.monitor_reviewed = evidence.monitor_key in seen
    for record in alerts["inactive_details"]:
        record["monitor_reviewed"] = record["monitor_key"] in seen
    for indicator in low_performance_details:
        indicator.monitor_reviewed = indicator.monitor_key in seen

    return render(
        request,
        "monitoringfronen/dashboard.html",
        {
            "rows": list(rows.values()),
            "positions_summary": ordered_position_summaries,
            "monitoring_rule": monitoring_rule,
            "alerts": alerts,
            "commitment_alerts": commitment_alerts,
            "pending_evidence_details": pending_evidence_details,
            "low_performance_details": low_performance_details,
            "selected_period": period,
            "delegations": employees.order_by("delegation__name").values(
                "delegation_id", "delegation__name"
            ).distinct(),
            "positions": employees.order_by("position__position_name").values(
                "position_id", "position__position_name"
            ).distinct(),
            "periods": Period.objects.filter(
                deleted_at__isnull=True,
            ).order_by("-start_date"),
        },
    )


@login_required
@permission_required("monitoring_traceability.view_indicator", raise_exception=True)
def dashboard_export(request):
    employees = _employee_scope(request, "monitoring_traceability.view_indicator")
    period = _period_from_request(request)
    delegation_id = _query(request.GET.get("delegation"))
    position_id = _query(request.GET.get("position"))
    if delegation_id.isdigit():
        employees = employees.filter(delegation_id=delegation_id)
    if position_id.isdigit():
        employees = employees.filter(pk__in=Goal.objects.filter(
            deleted_at__isnull=True, position_id=position_id,
            employee_id__in=employees.values("pk"),
        ).values("employee_id"))
    indicators = Indicator.objects.filter(
        deleted_at__isnull=True,
        goal__deleted_at__isnull=True,
        employee_id__in=employees.values("pk"),
    ).select_related("employee", "goal", "goal__period")
    if period is not None:
        indicators = indicators.filter(goal__period=period)
    if position_id.isdigit():
        indicators = indicators.filter(goal__position_id=position_id)
    metadata = (
        f"Filtros: delegación={delegation_id or 'todas'}; "
        f"cargo={position_id or 'todos'}; período={period or 'todos'}; "
        f"generado={timezone.localtime():%Y-%m-%d %H:%M}"
    )
    return workbook_response(
        "resumen_monitoreo.xlsx",
        ["Funcionario", "Delegación", "Cargo de la meta", "Período", "Meta", "Cumplimiento calculado", "Ponderación",
         "Resultado ponderado", "Acreditación", "Estado visible",
         "Semáforo técnico", "Metadatos"],
        [
            (
                indicator.employee.name,
                str(indicator.employee.delegation),
                str(indicator.goal.position),
                str(indicator.goal.period),
                indicator.goal.item,
                indicator.compliance,
                indicator.weighting,
                indicator.weighted_result,
                indicator.accreditation_label,
                indicator.effective_traffic_light,
                indicator.traffic_light,
                metadata,
            )
            for indicator in indicators.order_by("employee__name", "goal__item")
        ],
    )


@login_required
@permission_required("monitoring_traceability.view_indicator", raise_exception=True)
def activity_control(request):
    employees = _employee_scope(
        request,
        "monitoring_traceability.view_indicator",
    )
    period = _period_from_request(request)
    delegation_id = _query(request.GET.get("delegation"))
    position_id = _query(request.GET.get("position"))
    if delegation_id.isdigit():
        employees = employees.filter(delegation_id=delegation_id)
    if position_id.isdigit():
        employees = employees.filter(position_id=position_id)

    today = timezone.localdate()
    as_of = min(today, period.end_date) if period is not None else today
    rows = []
    for employee in employees.order_by("name"):
        activities = valid_activity_queryset(
            [employee.pk], period=period, on_date=as_of,
        )
        total = activities.count()
        last_activity = activities.order_by("-date", "-activity_id").first()
        earliest_activity = activities.order_by("date", "activity_id").first()

        if period is not None:
            denominator = (
                calculate_computable_days(period.start_date, as_of)
                if as_of >= period.start_date else 0
            )
        elif earliest_activity is not None:
            denominator = calculate_computable_days(earliest_activity.date, as_of)
        else:
            denominator = 0

        user = getattr(getattr(employee, "user_profile", None), "user", None)
        last_login = user.last_login if user else None
        days_without_activity = (
            activity_missing_workdays(
                employee, last_activity.date if last_activity else None, as_of, period,
            ) if period is None or today >= period.start_date else None
        )
        rows.append({
            "employee": employee,
            "last_login": last_login,
            "days_without_login": (
                max((today - timezone.localtime(last_login).date()).days, 0)
                if last_login else None
            ),
            "days_without_activity": days_without_activity,
            "records": total,
            "last_activity": last_activity.date if last_activity else None,
            "daily_average": (
                Decimal(total) / Decimal(denominator)
                if denominator > 0 else Decimal("0")
            ).quantize(Decimal("0.01")),
        })

    return render(
        request,
        "monitoringfronen/activity.html",
        {
            "rows": rows,
            "selected_period": period,
            "inactivity_threshold": inactivity_threshold_days(),
            "delegations": employees.order_by("delegation__name").values(
                "delegation_id", "delegation__name"
            ).distinct(),
            "positions": employees.order_by("position__position_name").values(
                "position_id", "position__position_name"
            ).distinct(),
            "periods": Period.objects.filter(
                deleted_at__isnull=True,
            ).order_by("-start_date"),
        },
    )


@login_required
@permission_required("monitoring_traceability.add_commitment", raise_exception=True)
def commitment_create(request):
    return redirect(
        f"{reverse('monitoring:commitment_list')}?open_modal=create"
    )


@login_required
def commitment_edit(request, commitment_id):
    # SGR_COMPROMISOS_RESTRICCIONES_20261117: compatibilidad URL, edición prohibida.
    raise PermissionDenied(
        "No está permitido modificar compromisos. Usa Actualizar estado o Reasignar responsable."
    )


def _responsible_unavailable(employee):
    """El estado real del empleado debe justificar una ausencia anticipada."""
    return bool(
        employee is not None
        and (
            employee.deleted_at is not None
            or (employee.status or "").strip().casefold() in {
                "inactive", "inactivo", "on leave", "on_leave", "con licencia", "licencia",
            }
        )
    )


def _commitment_can_be_reassigned(commitment):
    """Por vencimiento, o anticipadamente por empleado inactivo/con licencia."""
    current = Commitment.LEGACY_STATUS_MAP.get(commitment.status, commitment.status)
    return (
        commitment.deleted_at is None
        and current in {Commitment.Status.PENDING, Commitment.Status.IN_PROGRESS}
        and (
            commitment.is_overdue
            or _responsible_unavailable(commitment.responsible)
        )
    )


# SGR_REASIGNACION_ESTADO_FUNCIONARIO_20261117


def _commitment_list_context(
    request,
    commitments,
    *,
    form=None,
    modal="",
    modal_commitment=None,
    modal_title="",
    activities=None,
    reassignment_form=None,
    reassignment_commitment=None,
):
    synchronize_commitment_alerts(commitments)
    for commitment in commitments:
        commitment.display_status = (
            "Vencido" if commitment.is_overdue else commitment.effective_status
        )
        commitment.status = commitment.effective_status
        commitment.open_alerts = commitment.alerts.filter(
            resolved_at__isnull=True
        )
        commitment.transition_options = commitment.available_transitions()
        commitment.can_be_reassigned = _commitment_can_be_reassigned(commitment)

    # RF-021: los mismos filtros que el listado se aplican al resumen colectivo.
    summary_rows = list(commitments.values(
        "responsible_id", "responsible__name",
    ).annotate(
        total=Count("pk"),
        realized=Count("pk", filter=Q(status__in=[
            "Completed", "Validated", "Completado", "Validado", "Realizado",
        ])),
        pending=Count("pk", filter=Q(status__in=[
            "Pending", "Pendiente", "In progress", "En progreso",
        ])),
    ).order_by("responsible__name"))
    for row in summary_rows:
        row["pct_realized"] = round(row["realized"] * 100 / row["total"], 2) if row["total"] else 0
        row["pct_pending"] = round(row["pending"] * 100 / row["total"], 2) if row["total"] else 0

    return {
        "commitments": commitments,
        "commitment_summary": summary_rows,
        "total_commitments": commitments.count(),
        "pending_commitments": commitments.filter(
            status__in=["Pending", "Pendiente", "In progress", "En progreso"]
        ).exclude(commitment_date__lt=timezone.localdate()).count(),
        "completed_commitments": commitments.filter(
            status__in=["Completed", "Completado", "Realizado", "Validated", "Validado"]
        ).count(),
        "overdue_commitments": sum(
            commitment.is_overdue for commitment in commitments
        ),
        "status_choices": Commitment.Status.choices,
        "reassignment_employees": _employee_scope(
            request, "monitoring_traceability.view_commitment"
        ).order_by("name"),
        "open_modal": modal == "create",
        "commitment_form": form,
        "modal_commitment": modal_commitment,
        "modal_title": modal_title,
        "modal_action": request.path,
        "reassignment_form": reassignment_form,
        "reassignment_commitment": reassignment_commitment,
        "reassignment_open": reassignment_commitment is not None,
        "activities": activities or _activity_scope(request),
    }


@login_required
@permission_required("monitoring_traceability.view_commitment", raise_exception=True)
def commitment_export(request):
    commitments = _scoped_queryset(
        Commitment.objects.select_related("delegation", "responsible", "activity__goal"),
        request.user,
        "responsible",
        "monitoring_traceability.view_commitment",
    )
    search = _query(request.GET.get("q"))
    status = _query(request.GET.get("status"))
    if search:
        commitments = commitments.filter(
            Q(origin__icontains=search)
            | Q(requester__icontains=search)
            | Q(territory__icontains=search)
            | Q(activity__action__icontains=search)
            | Q(activity__goal__item__icontains=search)
            | Q(responsible__name__icontains=search)
        )
    if status:
        commitments = commitments.filter(status__iexact=status)
    metadata = (
        f"Filtros: q={search or '-'}; estado={status or 'todos'}; "
        f"generado={timezone.localtime():%Y-%m-%d %H:%M}"
    )
    return workbook_response(
        "compromisos_monitoreo.xlsx",
        ["ID", "Delegación", "Responsable", "Origen", "Solicitante",
         "Territorio", "Fecha límite", "Estado", "Actividad", "Meta", "Metadatos"],
        [
            (
                commitment.pk,
                commitment.delegation.name,
                commitment.responsible.name,
                commitment.origin,
                commitment.requester,
                commitment.territory,
                commitment.commitment_date,
                commitment.status,
                (f"#{commitment.activity_id} - {commitment.activity.action}"
                 if commitment.activity_id else "Sin actividad asociada"),
                (commitment.activity.goal.item
                 if commitment.activity_id else "Sin meta asociada"),
                metadata,
            )
            for commitment in commitments.order_by("-commitment_date", "pk")
        ],
    )


@login_required
@permission_required("monitoring_traceability.view_commitment", raise_exception=True)
def commitment_list(request):
    commitments = _scoped_queryset(
        Commitment.objects.select_related(
            "delegation",
            "responsible",
            "activity__goal",
        ).prefetch_related(
            Prefetch(
                "comments",
                queryset=CommitmentComment.objects.filter(
                    deleted_at__isnull=True,
                ).select_related(
                    "author",
                    "created_by__profile",
                ),
            ),
            Prefetch(
                "status_history",
                queryset=CommitmentStatusHistory.objects.select_related(
                    "changed_by"
                ),
            ),
            Prefetch(
                "reassignments",
                queryset=CommitmentReassignment.objects.select_related(
                    "previous_responsible",
                    "new_responsible",
                    "changed_by",
                ),
            ),
        ),
        request.user,
        "responsible", "monitoring_traceability.view_commitment",
    )
    employees = _employee_scope(
        request, "monitoring_traceability.view_commitment"
    )
    activities = _activity_scope(request)
    delegations = Delegation.objects.filter(
        deleted_at__isnull=True,
        delegation_id__in=employees.values("delegation_id"),
    )
    modal = _query(request.GET.get("open_modal"))
    modal_commitment = None
    modal_form = None
    modal_title = ""
    reassignment_form = None
    reassignment_commitment = None
    if modal == "edit":
        raise PermissionDenied("Los compromisos no admiten edición general.")
    elif modal == "create":
        if not request.user.has_perm("monitoring_traceability.add_commitment"):
            raise PermissionDenied("No puedes crear compromisos.")
        modal_form = CommitmentForm(
            employees=employees,
            delegations=delegations,
            activities=activities,
        )
        modal_title = "Nuevo compromiso"
    elif modal == "reassign":
        if not request.user.has_perm("monitoring_traceability.change_commitment"):
            raise PermissionDenied("No puedes reasignar compromisos.")
        reassignment_commitment = commitments.filter(
            pk=request.GET.get("commitment_id")
        ).first()
        if reassignment_commitment is None:
            raise PermissionDenied("No tienes acceso a ese compromiso.")
        if not _commitment_can_be_reassigned(reassignment_commitment):
            raise PermissionDenied("Solo se pueden reasignar compromisos no finalizados.")
        reassignment_form = CommitmentReassignmentForm(
            employees=employees.filter(
                delegation_id=reassignment_commitment.delegation_id,
                status__iexact="Active",
            ).exclude(
                pk=reassignment_commitment.responsible_id
            ),
            is_overdue=reassignment_commitment.is_overdue,
            employee_unavailable=_responsible_unavailable(reassignment_commitment.responsible),
        )

    if request.method == "POST":
        action = request.POST.get("action", "add")
        if action == "edit_commitment":
            raise PermissionDenied(
                "No está permitido editar compromisos. Usa Actualizar estado o Reasignar."
            )
        if action == "create_commitment":
            if not request.user.has_perm("monitoring_traceability.add_commitment"):
                raise PermissionDenied("No puedes crear compromisos.")
            form = CommitmentForm(
                request.POST,
                employees=employees,
                delegations=delegations,
                activities=activities,
            )
            if form.is_valid():
                commitment = form.save(commit=False)
                commitment._audit_actor_user = request.user
                with transaction.atomic():
                    if commitment.activity_id:
                        # Evita compromisos duplicados creados al mismo tiempo.
                        Activity.objects.select_for_update().get(pk=commitment.activity_id)
                        if Commitment.objects.filter(
                            activity_id=commitment.activity_id,
                            deleted_at__isnull=True,
                        ).exists():
                            messages.error(
                                request,
                                "La actividad ya tiene un compromiso asociado.",
                            )
                            return redirect("monitoring:commitment_list")
                    commitment.save()
                messages.success(request, "Compromiso creado correctamente.")
                return redirect("monitoring:commitment_list")
            return render(
                request,
                "monitoringfronen/compro.html",
                _commitment_list_context(
                    request,
                    commitments,
                    form=form,
                    modal="create",
                    modal_title="Nuevo compromiso",
                    activities=activities,
                    reassignment_form=reassignment_form,
                    reassignment_commitment=reassignment_commitment,
                ),
            )
        commitment_id = request.POST.get("commitment_id")
        profile = getattr(request.user, "profile", None)
        commitment = commitments.filter(
            pk=commitment_id
        ).first()
        if commitment is None:
            messages.error(request, "No tienes acceso a ese compromiso.")
        elif action == "delete":
            if not request.user.has_perm("monitoring_traceability.delete_commitmentcomment"):
                raise PermissionDenied("No puedes eliminar comentarios.")
            comment = CommitmentComment.objects.filter(
                comment_id=request.POST.get("comment_id"),
                commitment=commitment,
                created_by=request.user,
                deleted_at__isnull=True,
            ).first()
            if comment is None:
                messages.error(
                    request,
                    "No puedes eliminar este comentario.",
                )
            else:
                comment.deleted_at = timezone.now()
                comment.save(update_fields=["deleted_at", "updated_at"])
                messages.success(request, "Comentario eliminado.")
        elif action == "status":
            if not request.user.has_perm("monitoring_traceability.change_commitment"):
                raise PermissionDenied("No puedes cambiar estados.")
            new_status = _query(request.POST.get("status"))
            observation = _query(request.POST.get("observation"))
            if not observation:
                messages.error(request, "Indica una observación para el cambio de estado.")
            else:
                with transaction.atomic():
                    locked = Commitment.objects.select_for_update().get(pk=commitment.pk)
                    expected_status = _query(request.POST.get("expected_status"))
                    if expected_status and locked.status != expected_status:
                        messages.error(request, "El estado fue modificado por otro usuario. Actualiza la pantalla.")
                    elif not locked.can_transition_to(new_status):
                        messages.error(request, "Transición no permitida desde el estado actual.")
                    else:
                        locked.status = new_status
                        locked._audit_actor_user = request.user
                        locked._status_observation = observation
                        locked.save(update_fields=["status", "updated_at"])
                        messages.success(request, "Estado actualizado y registrado en el historial.")
        elif action == "reassign":
            if not request.user.has_perm("monitoring_traceability.change_commitment"):
                raise PermissionDenied("No puedes reasignar compromisos.")
            if not _commitment_can_be_reassigned(commitment):
                raise PermissionDenied("Solo se pueden reasignar compromisos no finalizados.")
            employees = _employee_scope(
                request, "monitoring_traceability.view_commitment"
            ).filter(
                delegation_id=commitment.delegation_id,
                status__iexact="Active",
            ).exclude(
                pk=commitment.responsible_id
            )
            reassignment_form = CommitmentReassignmentForm(
                request.POST,
                employees=employees,
                is_overdue=commitment.is_overdue,
                employee_unavailable=_responsible_unavailable(commitment.responsible),
            )
            if reassignment_form.is_valid():
                with transaction.atomic():
                    locked = Commitment.objects.select_for_update().get(
                        pk=commitment.pk
                    )
                    # Revalidar también la situación del empleado dentro de la transacción.
                    locked.responsible = Employee.objects.select_for_update().get(pk=locked.responsible_id)
                    if not _commitment_can_be_reassigned(locked):
                        raise PermissionDenied("Solo puedes reasignar por vencimiento o por funcionario inactivo/con licencia.")
                    cause = reassignment_form.cleaned_data["cause"]
                    if cause == "overdue" and not locked.is_overdue:
                        raise PermissionDenied("No puedes declarar vencido un compromiso vigente.")
                    if cause == "absence" and not _responsible_unavailable(locked.responsible):
                        raise PermissionDenied("La ausencia requiere que el funcionario esté inactivo o con licencia.")
                    if locked.responsible_id != commitment.responsible_id:
                        raise PermissionDenied("Cambió el responsable. Actualiza el listado.")
                    previous = locked.responsible
                    new_responsible = reassignment_form.cleaned_data["responsible"]
                    if new_responsible.delegation_id != locked.delegation_id:
                        raise PermissionDenied("El nuevo responsable debe ser de la misma delegación.")
                    if new_responsible.deleted_at is not None or new_responsible.status.casefold() != "active":
                        raise PermissionDenied("El nuevo responsable debe estar activo.")
                    locked.responsible = new_responsible
                    locked._audit_actor_user = request.user
                    locked.save(update_fields=["responsible", "updated_at"])
                    CommitmentReassignment.objects.create(
                        commitment=locked,
                        previous_responsible=previous,
                        new_responsible=new_responsible,
                        reason=(
                            f"{dict(CommitmentReassignmentForm.CAUSE_CHOICES)[cause]}: "
                            f"{reassignment_form.cleaned_data['reason']}"
                        ),
                        changed_by=request.user,
                    )
                messages.success(request, "Compromiso reasignado.")
            else:
                messages.error(request, "Revisa los datos de la reasignación.")
                return render(
                    request,
                    "monitoringfronen/compro.html",
                    _commitment_list_context(
                        request,
                        commitments,
                        reassignment_form=reassignment_form,
                        reassignment_commitment=commitment,
                        activities=activities,
                    ),
                )
        elif action == "resolve_alert":
            if not request.user.has_perm("monitoring_traceability.change_commitment"):
                raise PermissionDenied("No puedes resolver alertas.")
            alert = CommitmentAlert.objects.filter(
                pk=request.POST.get("alert_id"),
                commitment=commitment,
                resolved_at__isnull=True,
            ).first()
            if alert:
                alert.resolved_at = timezone.now()
                alert.save(update_fields=["resolved_at", "updated_at"])
                Audit.objects.create(
                    user=(
                        getattr(profile, "employee", None)
                        or commitment.responsible
                    ),
                    event="Resolved CommitmentAlert",
                    entity="CommitmentAlert",
                    object_identifier=str(alert.pk),
                    previous_value={"resolved_at": None},
                    new_value={"resolved_at": alert.resolved_at.isoformat()},
                )
                messages.success(request, "Alerta resuelta.")
            else:
                messages.error(request, "La alerta no está disponible.")
        else:
            if not request.user.has_perm("monitoring_traceability.add_commitmentcomment"):
                raise PermissionDenied("No puedes agregar comentarios.")
            text = _query(request.POST.get("comment"))
            if not text:
                messages.error(request, "El comentario no puede estar vacío.")
                return redirect(request.get_full_path())
            CommitmentComment.objects.create(
                commitment=commitment,
                author=profile.employee if profile else None,
                created_by=request.user,
                text=text,
            )
            messages.success(request, "Comentario agregado.")
        return redirect(request.get_full_path())

    search = _query(request.GET.get("q"))
    status = _query(request.GET.get("status"))
    if search:
        commitments = commitments.filter(
            Q(origin__icontains=search)
            | Q(requester__icontains=search)
            | Q(territory__icontains=search)
            | Q(activity__action__icontains=search)
            | Q(activity__goal__item__icontains=search)
            | Q(observation__icontains=search)
            | Q(responsible__name__icontains=search)
        )
    if status:
        commitments = commitments.filter(status__iexact=status)

    synchronize_commitment_alerts(commitments)
    for commitment in commitments:
        commitment.display_status = (
            "Vencido" if commitment.is_overdue else commitment.effective_status
        )
        commitment.status = commitment.effective_status
        commitment.open_alerts = commitment.alerts.filter(
            resolved_at__isnull=True
        )
        commitment.transition_options = commitment.available_transitions()
        commitment.can_be_reassigned = _commitment_can_be_reassigned(commitment)

    total = commitments.count()
    pending = commitments.filter(
        status__in=["Pending", "Pendiente", "In progress", "En progreso"]
    ).exclude(
        commitment_date__lt=timezone.localdate()
    ).count()
    completed = commitments.filter(
        status__in=["Completed", "Completado", "Realizado"]
    ).count()
    overdue = sum(commitment.is_overdue for commitment in commitments)

    return render(
        request,
        "monitoringfronen/compro.html",
        _commitment_list_context(
            request,
            commitments,
            form=modal_form,
            modal=modal,
            modal_commitment=modal_commitment,
            modal_title=modal_title,
            reassignment_form=reassignment_form,
            reassignment_commitment=reassignment_commitment,
        ),
    )


@login_required
@permission_required("monitoring_traceability.view_audit", raise_exception=True)
def audit_list(request):
    audits = _scoped_queryset(
        Audit.objects.select_related("user"),
        request.user,
        "user", "monitoring_traceability.view_audit",
    )

    search = _query(request.GET.get("q"))
    date_from = _query(request.GET.get("date_from"))
    if search:
        audits = audits.filter(
            Q(event__icontains=search)
            | Q(entity__icontains=search)
            | Q(object_identifier__icontains=search)
            | Q(user__name__icontains=search)
        )
    if date_from:
        audits = audits.filter(event_date__date__gte=date_from)

    audits = audits.order_by("-event_date", "-audit_id")
    return render(
        request,
        "monitoringfronen/audit.html",
        {
            "audits": audits,
            "total_audits": audits.count(),
            "last_audit_date": audits.first().event_date
            if audits.exists()
            else None,
        },
    )


@login_required
@permission_required("monitoring_traceability.change_monitoringsettings", raise_exception=True)
def monitoring_settings_view(request):
    """Gestión de umbrales y destinatarios, con historial auditable."""
    rule = get_monitoring_settings()
    if request.method == "POST":
        form = MonitoringSettingsForm(request.POST, instance=rule)
        if form.is_valid():
            with transaction.atomic():
                old_rule = MonitoringSettings.objects.select_for_update().filter(key="global").first()
                before = settings_snapshot(old_rule or MonitoringSettings(key="global"))
                if old_rule is not None:
                    # Revalidar sobre la versión bloqueada para evitar sobrescrituras.
                    posted_version = _query(request.POST.get("effective_from"))
                    if posted_version and posted_version != old_rule.effective_from.isoformat():
                        messages.error(request, "Otro usuario cambió las reglas. Actualiza la página.")
                        return redirect("monitoring:monitoring_settings")
                updated = form.save(commit=False)
                updated.key = "global"
                updated.updated_by = request.user
                updated.effective_from = timezone.now()
                updated.full_clean(exclude=["recipient_users"])
                updated.save()
                form.save_m2m()
                after = settings_snapshot(updated)
                MonitoringSettingsRevision.objects.create(
                    changed_by=request.user, previous_value=before, new_value=after,
                )
            messages.success(request, "Reglas guardadas con historial y fecha de vigencia.")
            return redirect("monitoring:monitoring_settings")
    else:
        form = MonitoringSettingsForm(instance=rule)
    return render(request, "monitoringfronen/settings.html", {
        "form": form,
        "effective_from": rule.effective_from.isoformat() if rule.pk else "",
        "revisions": MonitoringSettingsRevision.objects.select_related("changed_by")[:20],
    })
