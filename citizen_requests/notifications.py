import ipaddress
import logging
import smtplib
from urllib.parse import urlsplit

from django.conf import settings
from django.core.mail import send_mail


logger = logging.getLogger(__name__)
LOCAL_PUBLIC_PORTAL_URL = "http://127.0.0.1:8000/portal/"


def public_portal_url():
    configured_url = getattr(settings, "PUBLIC_PORTAL_URL", "").strip()
    if not configured_url:
        if settings.DEBUG:
            configured_url = LOCAL_PUBLIC_PORTAL_URL
        else:
            logger.error(
                "PUBLIC_PORTAL_URL no está configurada en producción."
            )
            return None

    try:
        parsed = urlsplit(configured_url)
        hostname = parsed.hostname
        if (
            parsed.scheme.lower() not in {"http", "https"}
            or not hostname
            or parsed.username
            or parsed.password
            or parsed.fragment
            or not parsed.path.rstrip("/").endswith("/portal")
        ):
            raise ValueError("URL pública inválida")

        if not settings.DEBUG:
            normalized_hostname = hostname.lower().rstrip(".")
            if normalized_hostname in {
                "localhost",
                "localhost.localdomain",
            } or normalized_hostname.endswith(".local"):
                raise ValueError("host local no permitido")

            try:
                address = ipaddress.ip_address(normalized_hostname)
            except ValueError:
                address = None
            if address and (
                address.is_loopback
                or address.is_private
                or address.is_link_local
                or address.is_unspecified
                or address.is_reserved
            ):
                raise ValueError("host privado no permitido")

        parsed.port
    except (TypeError, ValueError):
        logger.error("PUBLIC_PORTAL_URL tiene un formato o destino inválido.")
        return None

    return configured_url.rstrip("/") + "/"


def portal_link_text():
    configured_url = public_portal_url()
    if configured_url is None:
        return (
            "Puedes consultar el estado de tu solicitud ingresando al "
            "Portal Ciudadano desde el sitio oficial de la Municipalidad."
        )
    return f"Portal Ciudadano: {configured_url}"


def send_attention_notification(
    request_id,
    requester_name,
    requester_email,
    tracking_code,
):
    try:
        send_mail(
            subject=(
                "Atención registrada para su solicitud — "
                "SGR Municipalidad de La Serena"
            ),
            message=(
                f"Estimado/a {requester_name}:\n\n"
                "Le informamos que se registró una atención para gestionar "
                "su solicitud.\n\n"
                "Estado actual: En gestión.\n"
                f"Código de seguimiento: {tracking_code}\n\n"
                f"{portal_link_text()}\n\n"
                "Conserve su código de seguimiento para futuras consultas."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[requester_email],
            fail_silently=False,
        )
    except (OSError, smtplib.SMTPException):
        logger.exception(
            "No se pudo enviar el aviso de atención para CitizenRequest %s.",
            request_id,
        )
