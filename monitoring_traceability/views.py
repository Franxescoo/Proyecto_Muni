from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.db.models import Prefetch, Q
from django.shortcuts import render
from django.shortcuts import redirect
from django.utils import timezone

from planning_measurements.models import Goal

from .models import Audit, Commitment, CommitmentComment, Indicator
from .services import synchronize_indicators_for_goals


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


@login_required
@permission_required("monitoring_traceability.view_indicator", raise_exception=True)
def indicator_list(request):
    goals = Goal.objects.filter(
        deleted_at__isnull=True,
        period__deleted_at__isnull=True,
    ).select_related("employee", "period")
    if not request.user.is_superuser:
        allowed_ids = allowed_delegation_ids(request.user, "monitoring_traceability.view_indicator")
        goals = goals.filter(employee__delegation_id__in=allowed_ids) if allowed_ids else goals.none()

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
