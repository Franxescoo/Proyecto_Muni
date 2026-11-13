from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from decimal import Decimal, InvalidOperation

from django.db.models import Prefetch, Q
from django.shortcuts import render
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from organization.models import Delegation, Employee
from planning_measurements.models import Goal, Period
from planning_measurements.working_days import calculate_computable_days
from registration_validation.models import Activity

from .forms import CommitmentForm, CommitmentReassignmentForm
from .models import (
    Audit,
    Commitment,
    CommitmentAlert,
    CommitmentComment,
    CommitmentReassignment,
    CommitmentStatusHistory,
    Indicator,
)
from .services import (
    monitoring_alerts,
    synchronize_commitment_alerts,
    synchronize_indicators_for_goals,
)
from organization.exports import workbook_response


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

    if request.method == "POST":
        if not request.user.has_perm("monitoring_traceability.change_indicator"):
            raise PermissionDenied("No puedes ajustar indicadores.")
        indicator = indicators.filter(pk=request.POST.get("indicator_id")).first()
        if indicator is None:
            messages.error(request, "El indicador no está disponible.")
        else:
            try:
                adjustment = Decimal(request.POST.get("adjustment", "0"))
            except InvalidOperation:
                adjustment = None
            if adjustment is None or adjustment < Decimal("-100") or adjustment > Decimal("100"):
                messages.error(request, "El ajuste debe estar entre -100 y 100.")
            else:
                indicator.adjustment = adjustment
                indicator.save(update_fields=["adjustment", "updated_at"])
                synchronize_indicators_for_goals(
                    Goal.objects.filter(pk=indicator.goal_id)
                )
                messages.success(request, "Ajuste aplicado al indicador.")
        return redirect(request.get_full_path())

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
        indicators = indicators.filter(traffic_light__iexact=traffic_light)
    if period is not None:
        indicators = indicators.filter(goal__period=period)
    metadata = (
        f"Filtros: q={search or '-'}; semáforo={traffic_light or 'todos'}; "
        f"período={period or 'todos'}"
    )
    return workbook_response(
        "indicadores_monitoreo.xlsx",
        ["Meta", "Funcionario", "Avance esperado", "Avance real",
         "Cumplimiento", "Ajuste", "Resultado ponderado", "Semáforo",
         "Fecha cálculo", "Metadatos"],
        [
            (
                indicator.goal.item,
                indicator.employee.name,
                indicator.expected_progress,
                indicator.actual_progress,
                indicator.compliance,
                indicator.adjustment,
                indicator.weighted_result,
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
    commitment_alerts = CommitmentAlert.objects.filter(
        commitment__responsible_id__in=employees.values("pk"),
        commitment__deleted_at__isnull=True,
        resolved_at__isnull=True,
    ).select_related("commitment", "commitment__responsible")
    return render(
        request,
        "monitoringfronen/dashboard.html",
        {
            "rows": list(rows.values()),
            "alerts": alerts,
            "commitment_alerts": commitment_alerts,
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
        employees = employees.filter(position_id=position_id)
    indicators = Indicator.objects.filter(
        deleted_at__isnull=True,
        goal__deleted_at__isnull=True,
        employee_id__in=employees.values("pk"),
    ).select_related("employee", "goal", "goal__period")
    if period is not None:
        indicators = indicators.filter(goal__period=period)
    metadata = (
        f"Filtros: delegación={delegation_id or 'todas'}; "
        f"cargo={position_id or 'todos'}; período={period or 'todos'}"
    )
    return workbook_response(
        "resumen_monitoreo.xlsx",
        ["Funcionario", "Meta", "Cumplimiento", "Ponderación",
         "Resultado ponderado", "Semáforo", "Metadatos"],
        [
            (
                indicator.employee.name,
                indicator.goal.item,
                indicator.compliance,
                indicator.weighting,
                indicator.weighted_result,
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
            "days_without_login": (
                max((today - timezone.localtime(last_login).date()).days, 0)
                if last_login else None
            ),
            "days_without_activity": (
                max((today - last_activity.date).days, 0)
                if last_activity else None
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
@permission_required("monitoring_traceability.add_commitment", raise_exception=True)
def commitment_create(request):
    return redirect(
        f"{reverse('monitoring:commitment_list')}?open_modal=create"
    )


@login_required
@permission_required("monitoring_traceability.change_commitment", raise_exception=True)
def commitment_edit(request, commitment_id):
    return redirect(
        f"{reverse('monitoring:commitment_list')}?open_modal=edit"
        f"&commitment_id={commitment_id}"
    )


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

    return {
        "commitments": commitments,
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
        "open_modal": modal in {"create", "edit"},
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
        Commitment.objects.select_related("delegation", "responsible"),
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
            | Q(responsible__name__icontains=search)
        )
    if status:
        commitments = commitments.filter(
            Q(activity__status__iexact=status)
            | Q(activity__isnull=True, status__iexact=status)
        )
    metadata = f"Filtros: q={search or '-'}; estado={status or 'todos'}"
    return workbook_response(
        "compromisos_monitoreo.xlsx",
        ["ID", "Delegación", "Responsable", "Meta", "Solicitante",
         "Territorio", "Fecha límite", "Estado", "Metadatos"],
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
            "activity",
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
        modal_commitment = commitments.filter(
            pk=request.GET.get("commitment_id")
        ).first()
        if modal_commitment is None:
            raise PermissionDenied("No tienes acceso a ese compromiso.")
        modal_form = CommitmentForm(
            instance=modal_commitment,
            employees=employees,
            delegations=delegations,
            activities=activities,
        )
        modal_title = "Editar compromiso"
    elif modal == "create":
        modal_form = CommitmentForm(
            employees=employees,
            delegations=delegations,
            activities=activities,
        )
        modal_title = "Nuevo compromiso"
    elif modal == "reassign":
        reassignment_commitment = commitments.filter(
            pk=request.GET.get("commitment_id")
        ).first()
        if reassignment_commitment is None:
            raise PermissionDenied("No tienes acceso a ese compromiso.")
        reassignment_form = CommitmentReassignmentForm(
            employees=employees.filter(
                delegation_id=reassignment_commitment.responsible.delegation_id
            ).exclude(
                pk=reassignment_commitment.responsible_id
            )
        )

    if request.method == "POST":
        action = request.POST.get("action", "add")
        if action in {"create_commitment", "edit_commitment"}:
            commitment_id = request.POST.get("commitment_id")
            instance = None
            if action == "edit_commitment":
                instance = commitments.filter(pk=commitment_id).first()
                if instance is None:
                    raise PermissionDenied("No tienes acceso a ese compromiso.")
            form = CommitmentForm(
                request.POST,
                instance=instance,
                employees=employees,
                delegations=delegations,
                activities=activities,
            )
            if form.is_valid():
                commitment = form.save(commit=False)
                commitment._audit_actor_user = request.user
                commitment.save()
                messages.success(
                    request,
                    "Compromiso actualizado correctamente."
                    if instance
                    else "Compromiso creado correctamente.",
                )
                return redirect("monitoring:commitment_list")
            commitments = commitments.filter(
                pk=commitment_id
            ) if instance else commitments
            return render(
                request,
                "monitoringfronen/compro.html",
                _commitment_list_context(
                    request,
                    commitments,
                    form=form,
                    modal="edit" if instance else "create",
                    modal_commitment=instance,
                    modal_title=(
                        "Editar compromiso" if instance
                        else "Nuevo compromiso"
                    ),
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
            valid_statuses = {value for value, _ in Commitment.Status.choices}
            if new_status not in valid_statuses:
                messages.error(request, "Estado de compromiso no válido.")
            else:
                commitment.status = new_status
                commitment._audit_actor_user = request.user
                commitment._status_observation = _query(
                    request.POST.get("observation")
                )
                commitment.save(update_fields=["status", "updated_at"])
                messages.success(request, "Estado actualizado.")
        elif action == "reassign":
            if not request.user.has_perm("monitoring_traceability.change_commitment"):
                raise PermissionDenied("No puedes reasignar compromisos.")
            employees = _employee_scope(
                request, "monitoring_traceability.view_commitment"
            ).filter(
                delegation_id=commitment.responsible.delegation_id
            ).exclude(
                pk=commitment.responsible_id
            )
            reassignment_form = CommitmentReassignmentForm(
                request.POST, employees=employees
            )
            if reassignment_form.is_valid():
                previous = commitment.responsible
                new_responsible = reassignment_form.cleaned_data["responsible"]
                commitment.responsible = new_responsible
                commitment._audit_actor_user = request.user
                commitment.save(update_fields=["responsible", "updated_at"])
                CommitmentReassignment.objects.create(
                    commitment=commitment,
                    previous_responsible=previous,
                    new_responsible=new_responsible,
                    reason=reassignment_form.cleaned_data["reason"],
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
