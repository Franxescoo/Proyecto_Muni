from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from decimal import Decimal

from django.db.models import Prefetch, Q
from django.shortcuts import render
from django.shortcuts import redirect
from django.utils import timezone

from organization.models import Employee
from planning_measurements.models import Goal, Period
from planning_measurements.working_days import calculate_computable_days
from registration_validation.models import Activity

from .models import Audit, Commitment, CommitmentComment, Indicator
from .services import monitoring_alerts, synchronize_indicators_for_goals


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


def _period_from_request(request):
    period_id = _query(request.GET.get("period"))
    if not period_id.isdigit():
        return None
    return Period.objects.filter(
        pk=period_id,
        deleted_at__isnull=True,
    ).first()


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
        indicators = indicators.filter(traffic_light__iexact=traffic_light)
    if delegation_id.isdigit():
        indicators = indicators.filter(employee__delegation_id=delegation_id)
    if position_id.isdigit():
        indicators = indicators.filter(goal__position_id=position_id)
    if period is not None:
        indicators = indicators.filter(goal__period=period)

    total = indicators.count()
    compliant = indicators.filter(
        traffic_light__iregex=r"^(green|verde)$"
    ).count()
    attention = indicators.filter(
        traffic_light__iregex=r"^(red|rojo)$"
    ).count()

    return render(
        request,
        "monitoringfronen/indic.html",
        {
            "indicators": indicators,
            "total_indicators": total,
            "compliant_indicators": compliant,
            "attention_indicators": attention,
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
    if position_id.isdigit():
        employees = employees.filter(position_id=position_id)

    goals = Goal.objects.filter(
        deleted_at__isnull=True,
        period__deleted_at__isnull=True,
        employee_id__in=employees.values("pk"),
    ).select_related("employee", "period", "position")
    if period is not None:
        goals = goals.filter(period=period)
    synchronize_indicators_for_goals(goals)

    indicators = Indicator.objects.filter(
        deleted_at__isnull=True,
        goal__deleted_at__isnull=True,
        employee_id__in=employees.values("pk"),
    ).select_related("employee", "goal", "goal__period")
    if period is not None:
        indicators = indicators.filter(goal__period=period)

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
            },
        )
        row["goals"] += 1
        row["weighting"] += indicator.weighting
        row["weighted_result"] += indicator.weighted_result
        row["approved_evidences"] += indicator.approved_evidences
        row["compliance"] += indicator.compliance
        color = indicator.traffic_light.casefold()
        if color in {"green", "verde"}:
            row["green"] += 1
        elif color in {"yellow", "amarillo"}:
            row["yellow"] += 1
        else:
            row["red"] += 1

    for row in rows.values():
        row["compliance"] = (
            row["compliance"] / row["goals"]
        ).quantize(Decimal("0.01"))

    employees = employees.order_by("name")
    alerts = monitoring_alerts(
        employees=employees,
        period=period,
    )
    return render(
        request,
        "monitoringfronen/dashboard.html",
        {
            "rows": list(rows.values()),
            "alerts": alerts,
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
    rows = []
    for employee in employees.order_by("name"):
        activities = Activity.objects.filter(
            deleted_at__isnull=True,
            author=employee,
        )
        if period is not None:
            activities = activities.filter(
                date__gte=period.start_date,
                date__lte=period.end_date,
            )
            denominator = calculate_computable_days(
                period.start_date,
                min(today, period.end_date),
            ) if today >= period.start_date else 0
        else:
            denominator = 1
        total = activities.count()
        last_activity = activities.order_by("-date", "-activity_id").first()
        user = getattr(getattr(employee, "user_profile", None), "user", None)
        last_login = user.last_login if user else None
        rows.append({
            "employee": employee,
            "last_login": last_login,
            "days_without_activity": (
                (today - timezone.localtime(last_login).date()).days
                if last_login else None
            ),
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
@permission_required("monitoring_traceability.view_commitment", raise_exception=True)
def commitment_list(request):
    commitments = _scoped_queryset(
        Commitment.objects.select_related(
            "delegation",
            "responsible",
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
        ),
        request.user,
        "responsible", "monitoring_traceability.view_commitment",
    )

    if request.method == "POST":
        action = request.POST.get("action", "add")
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
            | Q(observation__icontains=search)
            | Q(responsible__name__icontains=search)
        )
    if status:
        commitments = commitments.filter(status__iexact=status)

    for commitment in commitments:
        commitment.display_status = (
            "Vencido" if commitment.is_overdue else commitment.status
        )

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
        {
            "commitments": commitments,
            "total_commitments": total,
            "pending_commitments": pending,
            "completed_commitments": completed,
            "overdue_commitments": overdue,
        },
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
