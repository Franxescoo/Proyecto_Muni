from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render

from .models import Audit, Commitment, Indicator


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
    indicators = _scoped_queryset(
        Indicator.objects.select_related("goal", "employee"),
        request.user,
        "employee",
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
        ),
        request.user,
        "responsible",
    )

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

    total = commitments.count()
    pending = commitments.filter(status__iexact="Pending").count()
    completed = commitments.filter(
        status__iexact="Completed"
    ).count()

    return render(
        request,
        "monitoringfronen/compro.html",
        {
            "commitments": commitments,
            "total_commitments": total,
            "pending_commitments": pending,
            "completed_commitments": completed,
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
