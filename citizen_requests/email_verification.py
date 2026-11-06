"""Confirmación de destinatario de seguimiento tras corrección de RUT."""
import logging
import smtplib
import uuid
from django.conf import settings
from django.core import signing
from django.core.mail import send_mail
from django.db import transaction
from django.urls import reverse
from .notifications import public_portal_url
from .tracking import tracking_stages

logger = logging.getLogger(__name__)
SALT = "citizen_requests.corrected_identity_email.v1"
MAX_AGE = 24 * 3600


def reset_followup_email(citizen_request, citizen):
    """En transacción bloqueada; invalida el correo anterior y enlaces antiguos."""
    citizen_request.followup_email_paused = True
    citizen_request.verified_followup_email = ""
    citizen_request.pending_followup_email = (citizen.email or "").strip().lower()
    citizen_request.followup_verification_nonce = uuid.uuid4()


def verification_token(citizen_request):
    return signing.dumps({
        "request": citizen_request.pk,
        "citizen": citizen_request.citizen_id,
        "email": citizen_request.pending_followup_email,
        "nonce": str(citizen_request.followup_verification_nonce),
    }, salt=SALT, compress=True)


def matches_current_verification(citizen_request, data):
    return bool(
        citizen_request.followup_email_paused
        and citizen_request.citizen_id == data.get("citizen")
        and citizen_request.pk == data.get("request")
        and str(citizen_request.followup_verification_nonce) == data.get("nonce")
        and citizen_request.pending_followup_email
        and citizen_request.pending_followup_email == data.get("email")
        and citizen_request.citizen is not None
        and citizen_request.citizen.is_active
        and (citizen_request.citizen.email or "").lower() == data.get("email")
    )


def send_verification_email(request_id, token, to_email):
    """Mensaje sin código de seguimiento ni información del caso."""
    portal = public_portal_url()
    if not portal:
        logger.error("No se envió verificación: URL pública no válida.")
        return
    # El sitio base del portal incluye /portal/. La URL pública verificada es
    # el mismo host usado para la ruta /portal/verificar-correo/...
    from urllib.parse import urlsplit
    parsed = urlsplit(portal)
    link = f"{parsed.scheme}://{parsed.netloc}" + reverse(
        "citizen_requests:verify_followup_email", kwargs={"token": token}
    )
    try:
        send_mail(
            subject="Verifica tu correo para seguimiento municipal — SGR",
            message=(
                "Se solicitó asociar una gestión municipal a tu registro de ciudadano.\n\n"
                "Para autorizar el envío de futuras notificaciones a este correo, "
                "abre el enlace y confirma la dirección:\n"
                f"{link}\n\n"
                "El enlace vence en 24 horas y solo puede utilizarse una vez.\n"
                "Si no reconoces esta gestión, ignora este mensaje. "
                "No contiene información privada ni el código del caso."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to_email],
            fail_silently=False,
        )
    except (OSError, smtplib.SMTPException):
        logger.exception("No pudo enviarse la verificación de solicitud %s", request_id)


def schedule_verification(citizen_request):
    """El correo solo se envía si la transacción se confirma."""
    email = citizen_request.pending_followup_email
    if not email:
        return
    token = verification_token(citizen_request)
    transaction.on_commit(lambda rid=citizen_request.pk, tok=token, dest=email: send_verification_email(rid,tok,dest))


def notify_after_verification(citizen_request):
    from .notifications import send_request_state_notification
    from .views import _public_tracking_data
    label = _public_tracking_data(citizen_request)["status"]
    stages = tuple(s["label"] for s in tracking_stages(citizen_request))
    rid, name, email, code = citizen_request.pk, citizen_request.citizen.full_name, citizen_request.followup_recipient, str(citizen_request.tracking_code)
    transaction.on_commit(lambda: send_request_state_notification(rid,name,email,code,label,stages=stages))
