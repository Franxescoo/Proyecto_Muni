"""Consultas en vivo para pantallas históricas Evidencias / Validaciones.

Solo lectura. Conserva scoping institucional mediante las funciones
existentes de views.py, sin duplicar reglas de acceso.
"""
from django.db.models import Prefetch, Q
from .models import AttentionEntry


def consultation_activities(request, scoped_activities):
    """Actividades visibles por permiso del módulo y delegación activa."""
    qs = scoped_activities(request.user, "registration_validation.view_evidence")
    qs = qs.select_related("attention", "activity_type", "goal__period").prefetch_related(
        Prefetch(
            "assigned_attentions",
            queryset=AttentionEntry.objects.filter(deleted_at__isnull=True)
            .select_related("responsible_employee", "delegation")
            .order_by("attention_entry_id"),
        )
    )
    q = request.GET.get("q", "").strip()[:150]
    if q:
        qs = qs.filter(
            Q(action__icontains=q)
            | Q(request_problem__icontains=q)
            | Q(goal__item__icontains=q)
            | Q(author__name__icontains=q)
            | Q(assigned_attentions__requester__icontains=q)
            | Q(assigned_attentions__subject__icontains=q)
            | Q(attention__requester__icontains=q)
        )
    status = request.GET.get("status", "").strip()
    if status in ("Pending", "In progress", "Completed"):
        qs = qs.filter(status=status)
    activity = request.GET.get("activity", "").strip()
    if activity.isdecimal() and len(activity) <= 18:
        qs = qs.filter(pk=int(activity))
    attention = request.GET.get("attention", "").strip()
    if attention.isdecimal() and len(attention) <= 18:
        qs = qs.filter(
            Q(assigned_attentions__pk=int(attention)) | Q(attention_id=int(attention))
        )
    return qs.distinct().order_by("-date", "-activity_id")


def consultation_resolutions(request, scoped_attention_entries):
    """Atenciones cerradas o resueltas, con eventos de seguimiento."""
    qs = scoped_attention_entries(
        request.user, "registration_validation.view_validation"
    ).filter(status__in=("RESOLVED", "CLOSED"))
    qs = qs.select_related(
        "activity", "activity__goal", "activity__goal__period",
        "activity__author", "citizen_request"
    ).prefetch_related(
        "citizen_request__events__actor"
    )
    q = request.GET.get("q", "").strip()[:150]
    if q:
        qs = qs.filter(
            Q(requester__icontains=q)
            | Q(subject__icontains=q)
            | Q(description__icontains=q)
            | Q(responsible_employee__name__icontains=q)
            | Q(delegation__name__icontains=q)
            | Q(activity__action__icontains=q)
            | Q(activity__goal__item__icontains=q)
        )
    status = request.GET.get("status", "").strip().upper()
    if status in ("RESOLVED", "CLOSED"):
        qs = qs.filter(status=status)
    activity = request.GET.get("activity", "").strip()
    if activity.isdecimal() and len(activity) <= 18:
        qs = qs.filter(
            Q(activity_id=int(activity)) | Q(activity__isnull=True, activities__pk=int(activity))
        )
    attention = request.GET.get("attention", "").strip()
    if attention.isdecimal() and len(attention) <= 18:
        qs = qs.filter(pk=int(attention))
    return qs.distinct().order_by("-closed_at", "-registration_date", "-attention_entry_id")


def consultation_is_historical(request):
    # CRUD original por defecto; la consulta nueva se abre mediante ?consulta=1.
    # Los enlaces desde atenciones/actividades con filtros abren la consulta viva.
    params = request.GET
    if params.get("consulta") == "1":
        return False
    if params.get("historico") == "1":
        return True
    if params.get("attention") or params.get("activity"):
        return False
    return True


def enrich_resolution_rows(rows):
    """Etiqueta eventos y recupera el usuario que registró la resolución.

    No inventa el responsable de resolución cuando no existe un evento.
    Trabaja con las relaciones prefetched y no añade escrituras.
    """
    labels = dict(AttentionEntry.STATUS_CHOICES)
    labels["IN_PROGRESS"] = "En gestión"
    for attention in rows:
        attention.sgr_resolution_actor_name = ""
        linked_request = getattr(attention, "citizen_request", None)
        if linked_request is None:
            continue
        events = list(linked_request.events.all())
        for event in events:
            event.sgr_previous_label = labels.get(event.previous_status, event.previous_status)
            event.sgr_new_label = labels.get(event.new_status, event.new_status)
        for event in reversed(events):
            if event.new_status in ("RESOLVED", "CLOSED") and event.actor_id:
                attention.sgr_resolution_actor_name = event.actor.get_username()
                break
