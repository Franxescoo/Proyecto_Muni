from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.shortcuts import render
from django.shortcuts import redirect

from planning_measurements.models import Goal

from .models import Audit, Commitment, CommitmentComment, Indicator
from .services import synchronize_indicators_for_goals


def _delegation_id(user):
    profile = getattr(user, "profile", None)
    return profile.delegation_id if profile else None


def _scoped_queryset(queryset, user, relation):
    queryset = queryset.filter(deleted_at__isnull=True)
    if user.is_superuser:
        return queryset

    delegation_id = _delegation_id(user)
    if delegation_id is None:
        return queryset.none()
    return queryset.filter(**{f"{relation}__delegation_id": delegation_id})


def _query(value):
    return value.strip() if value else ""


@login_required
def indicator_list(request):
    goals = Goal.objects.filter(
        deleted_at__isnull=True,
        period__deleted_at__isnull=True,
    ).select_related("employee", "period")
    if not request.user.is_superuser:
        delegation_id = _delegation_id(request.user)
        if delegation_id is None:
            goals = goals.none()
        else:
            goals = goals.filter(employee__delegation_id=delegation_id)

    synchronize_indicators_for_goals(goals)

    indicators = _scoped_queryset(
        Indicator.objects.select_related("goal", "employee", "goal__period"),
        request.user,
        "employee",
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
        },
    )


@login_required
def commitment_list(request):
    commitments = _scoped_queryset(
        Commitment.objects.select_related(
            "delegation",
            "responsible",
        ).prefetch_related("comments__author"),
        request.user,
        "responsible",
    )

    if request.method == "POST":
        commitment_id = request.POST.get("commitment_id")
        text = _query(request.POST.get("comment"))
        profile = getattr(request.user, "profile", None)
        commitment = commitments.filter(
            pk=commitment_id
        ).first()
        if commitment is None:
            messages.error(request, "No tienes acceso a ese compromiso.")
        elif not text:
            messages.error(request, "El comentario no puede estar vacío.")
        elif not profile or not profile.employee_id:
            messages.error(
                request,
                "Tu usuario no tiene un funcionario asociado para comentar.",
            )
        else:
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
def audit_list(request):
    audits = _scoped_queryset(
        Audit.objects.select_related("user"),
        request.user,
        "user",
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
