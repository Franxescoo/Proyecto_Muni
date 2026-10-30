import logging
import re
import smtplib
import time
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import CharField, Q
from django.db.models.functions import Cast
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.permissions import allowed_delegation_ids
from organization.models import Delegation
from registration_validation.models import AttentionEntry

from .forms import CitizenRequestForm, PublicTrackingCodeForm
from .models import CitizenRequest, RequestEvent
from .notifications import (
    LOCAL_PUBLIC_PORTAL_URL,
    portal_link_text,
    public_portal_url,
)


logger = logging.getLogger(__name__)

REQUESTS_PAGE_SIZE = 10
PUBLIC_CONFIRMATION_SESSION_KEY = "citizen_request_confirmation"
PUBLIC_TRACKING_ATTEMPTS_SESSION_KEY = "citizen_tracking_attempts"
PUBLIC_TRACKING_ATTEMPT_LIMIT = 10
PUBLIC_TRACKING_WINDOW_SECONDS = 60
_public_portal_url = public_portal_url
_portal_link_text = portal_link_text


def _send_derivation_notification(
    request_id,
    requester_name,
    requester_email,
    tracking_code,
    portal_url,
):
    """Envía el aviso sin propagar un fallo del proveedor SMTP."""
    try:
        send_mail(
            subject=(
                "Actualización de su solicitud — "
                "SGR Municipalidad de La Serena"
            ),
            message=(
                f"Estimado/a {requester_name}:\n\n"
                "Le informamos que su solicitud ha sido derivada al área "
                "correspondiente para su revisión.\n\n"
                "Estado actual: Derivada para revisión.\n"
                f"Código de seguimiento: {tracking_code}\n\n"
                f"Puede consultar el avance de su solicitud en el "
                f"{portal_url}\n\n"
                "Conserve su código de seguimiento para futuras consultas."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[requester_email],
            fail_silently=False,
        )
    except (OSError, smtplib.SMTPException):
        logger.exception(
            "No se pudo enviar el aviso de derivación para "
            "CitizenRequest %s.",
            request_id,
        )


def public_portal(request):
    tracking_form = PublicTrackingCodeForm()
    tracking_result = None
    tracking_error = None
    if request.method == "POST" and request.POST.get("tracking_form") == "1":
        tracking_form = PublicTrackingCodeForm(request.POST)
        if not _tracking_attempt_allowed(request):
            tracking_error = (
                "Se alcanzó el límite temporal de consultas. "
                "Intenta nuevamente en un momento."
            )
        elif tracking_form.is_valid():
            citizen_request = (
                CitizenRequest.objects.select_related("attention_entry")
                .filter(
                    tracking_code=tracking_form.cleaned_data["tracking_code"],
                    origin="CITIZEN",
                )
                .first()
            )
            if citizen_request is None:
                tracking_error = (
                    "No encontramos una solicitud con ese código de seguimiento."
                )
            else:
                tracking_result = _public_tracking_data(citizen_request)
        else:
            tracking_error = "Revisa el código de seguimiento ingresado."

    return render(
        request,
        "citizen_requests/portal.html",
        {
            "form": CitizenRequestForm(),
            "tracking_form": tracking_form,
            "tracking_result": tracking_result,
            "tracking_error": tracking_error,
        },
    )


def _tracking_attempt_allowed(request):
    attempts = request.session.get(PUBLIC_TRACKING_ATTEMPTS_SESSION_KEY, [])
    now = int(time.time())
    attempts = [
        timestamp
        for timestamp in attempts
        if now - timestamp < PUBLIC_TRACKING_WINDOW_SECONDS
    ]
    if len(attempts) >= PUBLIC_TRACKING_ATTEMPT_LIMIT:
        request.session[PUBLIC_TRACKING_ATTEMPTS_SESSION_KEY] = attempts
        return False
    attempts.append(now)
    request.session[PUBLIC_TRACKING_ATTEMPTS_SESSION_KEY] = attempts
    return True


def _public_tracking_data(citizen_request):
    stages = [
        {"label": "Solicitud recibida", "complete": True},
    ]
    if citizen_request.delegation_id:
        stages.append({"label": "Derivada para revisión", "complete": True})
    if citizen_request.attention_entry_id:
        stages.append({"label": "En gestión", "complete": True})

    if citizen_request.status == "CLOSED":
        public_status = "Cerrada"
        stages.append({"label": "Cerrada", "complete": True})
    elif citizen_request.attention_entry_id:
        public_status = "En gestión"
    elif citizen_request.delegation_id:
        public_status = "Derivada para revisión"
    else:
        public_status = "Solicitud recibida"

    return {
        "tracking_code": str(citizen_request.tracking_code),
        "created_at": citizen_request.created_at,
        "subject": citizen_request.subject,
        "status": public_status,
        "stages": stages,
    }


def public_request_confirmation(request, tracking_code):
    confirmation = request.session.get(PUBLIC_CONFIRMATION_SESSION_KEY)
    if not confirmation or confirmation["tracking_code"] != str(tracking_code):
        return redirect("citizen_requests:public_portal")
    return render(
        request,
        "citizen_requests/confirmation.html",
        {"confirmation": confirmation},
    )


def _active_delegations():
    return Delegation.objects.filter(
        deleted_at__isnull=True,
        status__in=("Active", "Activo"),
    ).order_by("name", "delegation_id")


def _active_delegation_id(request):
    return getattr(request.user, "sgr_active_delegation_id", None)


DERIVATION_PERMISSION = "citizen_requests.derivar_solicitud"


def _derivation_scope(request):
    if not request.user.has_perm(DERIVATION_PERMISSION):
        return set()
    scope = allowed_delegation_ids(
        request.user,
        DERIVATION_PERMISSION,
        active_only=False,
    )
    return set(scope or ())


def _can_derive(request):
    return bool(
        request.user.has_perm(DERIVATION_PERMISSION)
        and _active_delegation_id(request) is not None
        and _derivation_scope(request)
    )


def _authorized_active_delegations(request):
    scope = _derivation_scope(request)
    if not scope:
        return Delegation.objects.none()
    return _active_delegations().filter(pk__in=scope)


def _request_queryset_for_user(request):
    """Return pending derivation requests and the active assigned delegation."""
    active_delegation_id = _active_delegation_id(request)
    clauses = Q(pk__in=[])
    if _can_derive(request):
        clauses |= Q(delegation__isnull=True)
    if active_delegation_id is not None:
        clauses |= Q(delegation_id=active_delegation_id)
    return CitizenRequest.objects.filter(clauses)


def _attention_delegation_access(request, delegation_id, permission):
    if not request.user.has_perm(permission):
        return False
    active_id = _active_delegation_id(request)
    if not request.user.is_superuser and active_id != delegation_id:
        return False
    allowed_ids = allowed_delegation_ids(request.user, permission)
    return allowed_ids is None or delegation_id in allowed_ids


def _serialize_request(citizen_request, request=None):
    can_derive = bool(
        request
        and _can_derive(request)
        and citizen_request.status != "CLOSED"
    )
    can_change_delegation = bool(
        can_derive
        and citizen_request.delegation_id
        and citizen_request.attention_entry_id is None
        and citizen_request.delegation_id in _derivation_scope(request)
        and _active_delegation_id(request) == citizen_request.delegation_id
    )
    can_create_attention = bool(
        request
        and citizen_request.delegation_id
        and citizen_request.attention_entry_id is None
        and _attention_delegation_access(
            request,
            citizen_request.delegation_id,
            "registration_validation.add_attentionentry",
        )
    )
    can_view_attention = bool(
        request
        and citizen_request.attention_entry_id
        and _attention_delegation_access(
            request,
            citizen_request.delegation_id,
            "registration_validation.view_attentionentry",
        )
    )
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
        "attention_entry_id": citizen_request.attention_entry_id,
        "can_create_attention": can_create_attention,
        "can_view_attention": can_view_attention,
        "can_derive": can_derive and citizen_request.delegation_id is None,
        "can_change_delegation": can_change_delegation,
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
    if observation.startswith("Atención creada desde solicitud."):
        event_type = "Atención creada"
        reason = observation
    elif derivation_match:
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


def _page_data(queryset, page_number, request=None):
    page = Paginator(queryset, REQUESTS_PAGE_SIZE).get_page(page_number)
    return {
        "items": [_serialize_request(item, request) for item in page.object_list],
        "page": page.number,
        "pages": page.paginator.num_pages,
        "total": page.paginator.count,
        "has_next": page.has_next(),
        "has_previous": page.has_previous(),
        }


def register_public_request(request):
    """
    Recibe el POST del formulario del mismo sitio protegido por CSRF.

    La interfaz debe incluir {% csrf_token %} en un formulario Django o
    enviar el token en la cabecera X-CSRFToken al hacer una petición AJAX.
    """
    if request.method != "POST":
        return JsonResponse(
            {"result": "error", "message": "Método no permitido."},
            status=405,
        )

    portal_form = request.POST.get("portal_form") == "1"
    form = CitizenRequestForm(request.POST)
    if not form.is_valid():
        if portal_form:
            return render(
                request,
                "citizen_requests/portal.html",
                {"form": form},
                status=400,
            )
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
                "el estado de tu solicitud.\n\n"
                f"{_portal_link_text()}\n"
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

    if portal_form:
        request.session[PUBLIC_CONFIRMATION_SESSION_KEY] = {
            "tracking_code": tracking_code,
            "email_sent": email_sent,
        }
        request.session.modified = True
        return redirect(
            "citizen_requests:public_request_confirmation",
            tracking_code=tracking_code,
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
    pending_count = queryset.filter(delegation__isnull=True).count()
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
                request,
            ),
            "delegated": _page_data(
                delegated,
                request.GET.get("delegated_page", 1),
                request,
            ),
            "pending_count": pending_count,
            "active_delegation": getattr(
                getattr(request, "sgr_active_delegation", None),
                "name",
                None,
            ),
            "active_delegations": [
                {"id": delegation.pk, "name": delegation.name}
                for delegation in _authorized_active_delegations(request)
            ],
            "can_derive": _can_derive(request),
        }
    )


@login_required
def pending_request_count(request):
    if not _can_derive(request):
        return JsonResponse(
            {"result": "error", "message": "No tienes permiso para consultar pendientes."},
            status=403,
        )
    pending = _request_queryset_for_user(request).filter(
        delegation__isnull=True,
    )
    return JsonResponse({"pending_count": pending.count()})


@login_required
@require_POST
def assign_request(request, request_id):
    if not _can_derive(request):
        return JsonResponse(
            {"result": "error", "message": "No tienes permiso para derivar solicitudes."},
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

    delegation = get_object_or_404(
        _authorized_active_delegations(request),
        pk=delegation_id,
    )
    with transaction.atomic():
        citizen_request = get_object_or_404(
            CitizenRequest.objects.select_for_update(),
            pk=request_id,
            delegation__isnull=True,
        )
        if citizen_request.status == "CLOSED":
            return JsonResponse(
                {"result": "error", "message": "No se puede derivar una solicitud cerrada."},
                status=409,
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
        portal_url = _public_portal_url()
        if citizen_request.origin == "CITIZEN" and citizen_request.requester_email:
            transaction.on_commit(
                lambda request_id=citizen_request.pk,
                requester_name=citizen_request.requester_name,
                requester_email=citizen_request.requester_email,
                tracking_code=str(citizen_request.tracking_code),
                portal_url=(
                    portal_url
                    or (
                        "Portal Ciudadano desde el sitio oficial de la "
                        "Municipalidad."
                    )
                ): _send_derivation_notification(
                    request_id,
                    requester_name,
                    requester_email,
                    tracking_code,
                    portal_url,
                )
            )

    return JsonResponse({"result": "success", "message": "Solicitud derivada."})


@login_required
@require_POST
def change_request_delegation(request, request_id):
    if not _can_derive(request):
        return JsonResponse(
            {"result": "error", "message": "No tienes permiso para derivar solicitudes."},
            status=403,
        )

    allowed_ids = _derivation_scope(request)
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

    destination = get_object_or_404(
        _authorized_active_delegations(request),
        pk=delegation_id,
    )
    with transaction.atomic():
        citizen_request = get_object_or_404(
            _request_queryset_for_user(request).select_for_update(),
            pk=request_id,
            delegation__isnull=False,
        )
        if citizen_request.status == "CLOSED":
            return JsonResponse(
                {"result": "error", "message": "No se puede cambiar una solicitud cerrada."},
                status=409,
            )
        if (
            citizen_request.delegation_id not in allowed_ids
            or _active_delegation_id(request) != citizen_request.delegation_id
        ):
            raise PermissionDenied(
                "No tienes autorización sobre la delegación de origen."
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


def _get_attention_request(request, request_id, permission):
    if not request.user.has_perm(permission):
        raise PermissionDenied(
            "No tienes el permiso requerido para esta atención."
        )
    queryset = CitizenRequest.objects.select_related(
        "delegation",
        "attention_entry",
    )
    citizen_request = get_object_or_404(
        queryset,
        pk=request_id,
        delegation__isnull=False,
    )
    if not _attention_delegation_access(
        request,
        citizen_request.delegation_id,
        permission,
    ):
        raise PermissionDenied(
            "La solicitud no pertenece a tu delegación activa autorizada."
        )
    return citizen_request


@login_required
def create_attention_from_request(request, request_id):
    if request.method != "GET":
        return JsonResponse(
            {"result": "error", "message": "Método no permitido."},
            status=405,
        )

    if not request.user.has_perm(
        "registration_validation.add_attentionentry"
    ):
        raise PermissionDenied(
            "No tienes permiso para ingresar atenciones."
        )

    if request.method == "GET":
        citizen_request = _get_attention_request(
            request,
            request_id,
            "registration_validation.add_attentionentry",
        )
        if citizen_request.attention_entry_id:
            return redirect(
                "citizen_requests:view_attention_from_request",
                request_id=citizen_request.pk,
            )
        target = reverse("registration:attention_entry_create")
        return redirect(
            f"{target}?{urlencode({'citizen_request': citizen_request.pk})}",
        )


@login_required
def view_attention_from_request(request, request_id):
    citizen_request = _get_attention_request(
        request,
        request_id,
        "registration_validation.view_attentionentry",
    )
    if citizen_request.attention_entry_id is None:
        return JsonResponse(
            {"result": "error", "message": "La solicitud no tiene atención."},
            status=404,
        )
    attention_entry = citizen_request.attention_entry
    if (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.GET.get("format") == "json"
    ):
        return JsonResponse(
            {
                "attention": {
                    "id": attention_entry.pk,
                    "tracking_code": (
                        str(attention_entry.tracking_code)
                        if attention_entry.tracking_code
                        else ""
                    ),
                    "request_tracking_code": str(
                        citizen_request.tracking_code
                    ),
                    "requester": attention_entry.requester,
                    "requester_email": attention_entry.requester_email,
                    "requester_phone": attention_entry.requester_phone,
                    "address": attention_entry.address,
                    "subject": attention_entry.subject,
                    "attention_type": attention_entry.attention_type.name,
                    "sub_attention": attention_entry.sub_attention.name,
                    "description": attention_entry.description,
                    "delegation": attention_entry.delegation.name,
                    "responsible_employee": (
                        attention_entry.responsible_employee.name
                        if attention_entry.responsible_employee_id
                        else ""
                    ),
                    "status": attention_entry.get_status_display(),
                    "registration_date": (
                        attention_entry.registration_date.isoformat()
                        if attention_entry.registration_date
                        else ""
                    ),
                    "registered_by": (
                        attention_entry.registered_by.username
                        if attention_entry.registered_by_id
                        else ""
                    ),
                }
            }
        )
    return render(
        request,
        "citizen_requests/attention_detail.html",
        {
            "citizen_request": citizen_request,
            "attention_entry": citizen_request.attention_entry,
        },
    )
