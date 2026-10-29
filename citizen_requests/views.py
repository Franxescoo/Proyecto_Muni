import logging
import re
import smtplib

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import CharField, Q
from django.db.models.functions import Cast
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from organization.models import Delegation

from .forms import CitizenRequestForm
from .models import CitizenRequest, RequestEvent


logger = logging.getLogger(__name__)

REQUESTS_PAGE_SIZE = 10


def _active_delegations():
    return Delegation.objects.filter(
        deleted_at__isnull=True,
        status__in=("Active", "Activo"),
    ).order_by("name", "delegation_id")


def _active_delegation_id(request):
    return getattr(request.user, "sgr_active_delegation_id", None)


def _temporary_operations_enabled():
    return settings.DEBUG


def _request_queryset_for_user(request):
    """Return only pending requests and the current authorized delegation."""
    active_delegation_id = _active_delegation_id(request)
    pending = Q(delegation__isnull=True) if settings.DEBUG else Q(pk__in=[])
    if active_delegation_id is None:
        return CitizenRequest.objects.filter(pending)
    return CitizenRequest.objects.filter(
        pending | Q(delegation_id=active_delegation_id)
    )


def _serialize_request(citizen_request):
    return {
        "id": citizen_request.pk,
        "tracking_code": str(citizen_request.tracking_code),
        "subject": citizen_request.subject,
        "created_at": citizen_request.created_at.isoformat(),
        "status": citizen_request.get_status_display(),
        "status_code": citizen_request.status,
        "address": citizen_request.address,
        "delegation": (
            citizen_request.delegation.name
            if citizen_request.delegation_id
            else "Sin derivar"
        ),
        "has_attention": citizen_request.attention_entry_id is not None,
    }


def _serialize_event(event):
    observation = event.observation or ""
    event_type = "Movimiento"
    previous_delegation = None
    new_delegation = None
    status_labels = dict(CitizenRequest.STATUS_CHOICES)

    derivation_match = re.match(
        r"^(Derivación|Cambio de derivación):\s*(.*?)\s*->\s*(.*?)\s*"
        r"\(ID\s+(\d+)(?:\s*->\s*(\d+))?\)\.\s*Motivo:\s*(.*)$",
        observation,
        flags=re.IGNORECASE,
    )
    if derivation_match:
        event_type = derivation_match.group(1)
        previous_delegation = derivation_match.group(2).strip()
        new_delegation = derivation_match.group(3).strip()
        reason = derivation_match.group(6).strip()
    else:
        reason = observation

    return {
        "type": event_type,
        "created_at": event.created_at.isoformat(),
        "actor": (
            event.actor.get_username()
            if event.actor_id
            else "Ciudadano"
        ),
        "previous_delegation": previous_delegation,
        "new_delegation": new_delegation,
        "reason": reason,
        "observation": observation,
        "previous_status": status_labels.get(
            event.previous_status,
            event.previous_status,
        ),
        "new_status": status_labels.get(
            event.new_status,
            event.new_status,
        ),
    }


def _filtered_requests(queryset, request):
    search = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    if search:
        queryset = queryset.annotate(
            tracking_code_text=Cast(
                "tracking_code",
                output_field=CharField(),
            )
        )
        queryset = queryset.filter(
            Q(subject__icontains=search)
            | Q(
                tracking_code_text__icontains=search,
            )
        )
    if status:
        queryset = queryset.filter(status=status)
    return queryset.order_by("-created_at", "-pk")


def _page_data(queryset, page_number):
    page = Paginator(queryset, REQUESTS_PAGE_SIZE).get_page(page_number)
    return {
        "items": [_serialize_request(item) for item in page.object_list],
        "page": page.number,
        "pages": page.paginator.num_pages,
        "total": page.paginator.count,
        "has_next": page.has_next(),
        "has_previous": page.has_previous(),
    }


@require_POST
def register_public_request(request):
    """
    Recibe el POST del formulario del mismo sitio protegido por CSRF.

    La interfaz debe incluir {% csrf_token %} en un formulario Django o
    enviar el token en la cabecera X-CSRFToken al hacer una petición AJAX.
    """
    form = CitizenRequestForm(request.POST)
    if not form.is_valid():
        return JsonResponse(
            {
                "result": "error",
                "message": "Revisa los datos ingresados.",
                "errors": form.errors.get_json_data(),
            },
            status=400,
        )

    citizen_request = form.save(commit=False)
    citizen_request.origin = "CITIZEN"
    citizen_request.status = "NEW"
    citizen_request.delegation = None
    citizen_request.assigned_to = None
    citizen_request.attention_entry = None
    citizen_request.save()

    tracking_code = str(citizen_request.tracking_code)
    email_sent = True
    try:
        send_mail(
            subject="Solicitud recibida - código de seguimiento",
            message=(
                f"Hola {citizen_request.requester_name},\n\n"
                "Hemos recibido tu solicitud correctamente.\n"
                f"Tu código de seguimiento es: {tracking_code}\n\n"
                "Conserva este código para consultar posteriormente "
                "el estado de tu solicitud.\n"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[citizen_request.requester_email],
            fail_silently=False,
        )
    except (OSError, smtplib.SMTPException):
        email_sent = False
        logger.exception(
            "No se pudo enviar el correo de confirmación de CitizenRequest %s.",
            citizen_request.pk,
        )

    if email_sent:
        message = "Solicitud registrada correctamente."
    else:
        message = (
            "La solicitud fue registrada, pero no se pudo enviar "
            "el correo de confirmación."
        )

    return JsonResponse(
        {
            "result": "success",
            "message": message,
            "tracking_code": tracking_code,
            "email_sent": email_sent,
        },
        status=201,
    )


@login_required
def request_inbox(request):
    queryset = _request_queryset_for_user(request).select_related(
        "delegation",
    )
    pending = _filtered_requests(
        queryset.filter(delegation__isnull=True),
        request,
    )
    delegated = _filtered_requests(
        queryset.filter(delegation__isnull=False),
        request,
    )
    return JsonResponse(
        {
            "pending": _page_data(
                pending,
                request.GET.get("pending_page", 1),
            ),
            "delegated": _page_data(
                delegated,
                request.GET.get("delegated_page", 1),
            ),
            "active_delegation": getattr(
                getattr(request, "sgr_active_delegation", None),
                "name",
                None,
            ),
            "active_delegations": [
                {"id": delegation.pk, "name": delegation.name}
                for delegation in _active_delegations()
            ],
            "temporary_pending_visibility": settings.DEBUG,
        }
    )


@login_required
@require_POST
def assign_request(request, request_id):
    if not _temporary_operations_enabled():
        return JsonResponse(
            {"result": "error", "message": "Funcionalidad no disponible."},
            status=403,
        )

    delegation_id = request.POST.get("delegation", "").strip()
    reason = request.POST.get("reason", "").strip()
    if not delegation_id:
        return JsonResponse(
            {"result": "error", "message": "Selecciona una delegación."},
            status=400,
        )
    if not reason:
        return JsonResponse(
            {"result": "error", "message": "El motivo es obligatorio."},
            status=400,
        )

    delegation = get_object_or_404(_active_delegations(), pk=delegation_id)
    with transaction.atomic():
        citizen_request = get_object_or_404(
            CitizenRequest.objects.select_for_update(),
            pk=request_id,
            delegation__isnull=True,
        )
        previous_label = "Sin derivar"
        citizen_request.delegation = delegation
        citizen_request.save(update_fields=("delegation", "updated_at"))
        RequestEvent.objects.create(
            request=citizen_request,
            actor=request.user,
            observation=(
                f"Derivación: {previous_label} -> {delegation.name} "
                f"(ID {delegation.pk}). Motivo: {reason}"
            ),
            previous_status=citizen_request.status,
            new_status=citizen_request.status,
        )

    return JsonResponse({"result": "success", "message": "Solicitud derivada."})


@login_required
@require_POST
def change_request_delegation(request, request_id):
    if not _temporary_operations_enabled():
        return JsonResponse(
            {"result": "error", "message": "Funcionalidad no disponible."},
            status=403,
        )

    delegation_id = request.POST.get("delegation", "").strip()
    reason = request.POST.get("reason", "").strip()
    if not delegation_id:
        return JsonResponse(
            {"result": "error", "message": "Selecciona una delegación."},
            status=400,
        )
    if not reason:
        return JsonResponse(
            {"result": "error", "message": "El motivo es obligatorio."},
            status=400,
        )

    destination = get_object_or_404(_active_delegations(), pk=delegation_id)
    with transaction.atomic():
        citizen_request = get_object_or_404(
            _request_queryset_for_user(request).select_for_update(),
            pk=request_id,
            delegation__isnull=False,
        )
        if citizen_request.attention_entry_id:
            return JsonResponse(
                {
                    "result": "error",
                    "message": (
                        "No se puede cambiar la derivación porque "
                        "la solicitud ya tiene una atención vinculada."
                    ),
                },
                status=409,
            )
        if citizen_request.delegation_id == destination.pk:
            return JsonResponse(
                {
                    "result": "error",
                    "message": "La nueva delegación debe ser diferente.",
                },
                status=400,
            )
        previous = citizen_request.delegation
        citizen_request.delegation = destination
        citizen_request.save(update_fields=("delegation", "updated_at"))
        RequestEvent.objects.create(
            request=citizen_request,
            actor=request.user,
            observation=(
                f"Cambio de derivación: {previous.name} -> {destination.name} "
                f"(ID {previous.pk} -> {destination.pk}). Motivo: {reason}"
            ),
            previous_status=citizen_request.status,
            new_status=citizen_request.status,
        )

    return JsonResponse(
        {"result": "success", "message": "Derivación actualizada."}
    )


@login_required
def request_detail(request, request_id):
    citizen_request = get_object_or_404(
        _request_queryset_for_user(request).select_related(
            "delegation",
            "attention_entry",
        ),
        pk=request_id,
    )
    events = (
        citizen_request.events.select_related("actor")
        .order_by("created_at", "pk")
    )
    data = _serialize_request(citizen_request)
    data.update(
        {
            "requester_name": citizen_request.requester_name,
            "requester_email": citizen_request.requester_email,
            "requester_phone": citizen_request.requester_phone,
            "description": citizen_request.description,
            "attention_entry_id": citizen_request.attention_entry_id,
            "events": [_serialize_event(event) for event in events],
        }
    )
    return JsonResponse({"request": data})

# Create your views here.
