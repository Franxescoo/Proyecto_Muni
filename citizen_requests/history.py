"""Acceso por correo verificado al historial público de solicitudes vecinales.

No crea cuentas de Django ni modifica los permisos de los funcionarios.
"""
import hashlib
import logging
import secrets
import smtplib
import time
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.cache import cache
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import redirect, render
from django.utils.crypto import constant_time_compare, salted_hmac
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .models import CitizenRequest
from .views import _public_tracking_data


logger = logging.getLogger(__name__)
SESSION_PENDING = "citizen_history_pending_v1"
SESSION_VERIFIED = "citizen_history_verified_v1"
CODE_EXPIRY_SECONDS = 600
VERIFIED_EXPIRY_SECONDS = 1800
MAX_CODE_ATTEMPTS = 5
SEND_WINDOW_SECONDS = 900
SEND_LIMIT_PER_EMAIL = 3
SEND_LIMIT_PER_IP = 10
PAGE_SIZE = 10


def _email_form_value(raw):
    from django import forms

    field = forms.EmailField(max_length=254)
    return field.clean(raw).strip().lower()


def _digest(email, code):
    return salted_hmac(
        "citizen_requests.public_history_code.v1",
        f"{email}|{code}",
    ).hexdigest()


def _limit_key(kind, value):
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"citizen-history-send-v1:{kind}:{digest}"


def _limited(key, limit):
    """Cache-backed throttling; use a shared cache in multi-worker production."""
    if cache.get(key, 0) >= limit:
        return True
    if not cache.add(key, 1, SEND_WINDOW_SECONDS):
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, SEND_WINDOW_SECONDS)
    return False


def _clear_auth(request):
    request.session.pop(SESSION_PENDING, None)
    request.session.pop(SESSION_VERIFIED, None)


def _verified_email(request, now):
    data = request.session.get(SESSION_VERIFIED) or {}
    if not data or now - data.get("verified_at", 0) > VERIFIED_EXPIRY_SECONDS:
        request.session.pop(SESSION_VERIFIED, None)
        return None
    return data.get("email")


@never_cache
@require_http_methods(["GET", "POST"])
def public_request_history(request):
    """No muestra datos hasta demostrar control del buzón mediante un código."""
    now = int(time.time())
    error = None
    notice = None
    email_value = ""

    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "logout":
            _clear_auth(request)
            return redirect("citizen_requests:public_request_history")

        if action == "send":
            # Un nuevo intento nunca hereda el acceso concedido antes.
            _clear_auth(request)
            try:
                email_value = _email_form_value(request.POST.get("email", ""))
            except ValidationError:
                error = "Ingresa un correo electrónico válido."
            else:
                ip = request.META.get("REMOTE_ADDR") or "unknown"
                email_key = _limit_key("email", email_value)
                ip_key = _limit_key("ip", ip)
                if (_limited(email_key, SEND_LIMIT_PER_EMAIL)
                        or _limited(ip_key, SEND_LIMIT_PER_IP)):
                    error = "Demasiados intentos. Intenta nuevamente en 15 minutos."
                else:
                    code = f"{secrets.randbelow(1000000):06d}"
                    try:
                        send_mail(
                            subject="Código de acceso a tus solicitudes — SGR La Serena",
                            message=(
                                "Solicitaste revisar el historial de solicitudes vecinales.\n\n"
                                f"Tu código temporal es: {code}\n\n"
                                "Caduca en 10 minutos. No compartas este código.\n"
                                "Si no solicitaste el acceso, ignora este mensaje."
                            ),
                            from_email=settings.DEFAULT_FROM_EMAIL,
                            recipient_list=[email_value],
                            fail_silently=False,
                        )
                    except (OSError, smtplib.SMTPException):
                        logger.exception("No fue posible enviar el código de historial.")
                        error = "No pudimos enviar el código. Intenta nuevamente más tarde."
                    else:
                        request.session[SESSION_PENDING] = {
                            "email": email_value,
                            "digest": _digest(email_value, code),
                            "issued_at": now,
                            "attempts": 0,
                        }
                        return redirect("citizen_requests:public_request_history")

        elif action == "verify":
            pending = request.session.get(SESSION_PENDING) or {}
            candidate = request.POST.get("code", "").strip()
            expired = (
                not pending
                or now - pending.get("issued_at", 0) > CODE_EXPIRY_SECONDS
            )
            if expired or pending.get("attempts", 0) >= MAX_CODE_ATTEMPTS:
                request.session.pop(SESSION_PENDING, None)
                error = "El código expiró o se agotaron los intentos. Solicita uno nuevo."
            elif not (len(candidate) == 6 and candidate.isascii() and candidate.isdigit()
                      and constant_time_compare(_digest(pending["email"], candidate), pending["digest"])):
                pending["attempts"] += 1
                if pending["attempts"] >= MAX_CODE_ATTEMPTS:
                    request.session.pop(SESSION_PENDING, None)
                    error = "Se agotaron los intentos. Solicita otro código."
                else:
                    request.session[SESSION_PENDING] = pending
                    error = "Código incorrecto. Revísalo e intenta nuevamente."
            else:
                email = pending["email"]
                request.session.cycle_key()
                request.session.pop(SESSION_PENDING, None)
                request.session[SESSION_VERIFIED] = {
                    "email": email,
                    "verified_at": now,
                }
                return redirect("citizen_requests:public_request_history")
        else:
            error = "Operación no válida."

    verified_email = _verified_email(request, now)
    pending = request.session.get(SESSION_PENDING)
    if pending and now - pending.get("issued_at", 0) > CODE_EXPIRY_SECONDS:
        request.session.pop(SESSION_PENDING, None)
        pending = None
        notice = "El código caducó. Solicita uno nuevo."

    items = None
    page = None
    selected_request = None
    if verified_email:
        requests = CitizenRequest.objects.filter(
            Q(followup_email_paused=False, verified_followup_email__iexact=verified_email)
            | Q(followup_email_paused=False, verified_followup_email="", requester_email__iexact=verified_email)
        ).filter(
            Q(origin="CITIZEN") |
            Q(origin="INTERNAL", attention_entry__isnull=False)
        ).select_related("attention_entry").order_by("-created_at", "-pk")
        page = Paginator(requests, PAGE_SIZE).get_page(request.GET.get("page"))
        # La ficha se obtiene SOLAMENTE desde las solicitudes del correo
        # verificado; nunca basta conocer el UUID de seguimiento.
        selected_code = (request.GET.get("solicitud") or "").strip()
        if selected_code:
            try:
                selected_uuid = uuid.UUID(selected_code)
            except (ValueError, AttributeError):
                selected_uuid = None
            if selected_uuid:
                selected_request = requests.filter(tracking_code=selected_uuid).first()
        if selected_request is None:
            selected_request = next(iter(page.object_list), None)
        items = []
        for item in page.object_list:
            public_item = _public_tracking_data(item)
            public_item["is_selected"] = bool(
                selected_request
                and item.pk == selected_request.pk
            )
            items.append(public_item)

    return render(
        request,
        "citizen_requests/history.html",
        {
            "error": error,
            "notice": notice,
            "email_value": email_value,
            "pending": pending,
            "verified_email": verified_email,
            "items": items,
            "page": page,
            "selected_request": selected_request,
        },
    )
