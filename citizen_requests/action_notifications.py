"""Notificaciones al ciudadano sobre hitos relevantes de Gestiones operativas.

No cambia estados, no envía información privada y reutiliza la política de
correos del seguimiento de Solicitudes (incluida la pausa por verificación).
"""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction

from .notifications import portal_link_text


logger = logging.getLogger(__name__)

# Solo hitos relevantes; no correo por cada edición, nota o coordinación.
NOTIFIABLE_EVENTS = frozenset({
    "ASSIGNED", "REASSIGNED", "IN_PROGRESS", "FINISHED", "REOPENED", "UPDATED",
})
EXTERNAL_EXECUTOR_TYPES = frozenset({"TECHNICIAN", "COMPANY"})

# Se describen solo cambios comprensibles y seguros para el ciudadano.
# Deliberadamente NO se envían: descripción, resultado, contacto ni adjuntos.
PUBLIC_CHANGE_LABELS = {
    "action_type": "tipo de gestión",
    "performed_at": "fecha de la actuación",
    "expected_execution_date": "fecha prevista de intervención",
    "executor_type": "tipo de ejecutor",
    "executor_name": "ejecutor asignado",
    "responsible": "funcionario municipal responsable",
}


def queue_action_notification(action_id, event, *, changed_fields=()):
    """Enviar solamente si la transacción de la gestión termina con éxito.

    Llamar dentro de transaction.atomic(). Se consulta el destinatario después
    del commit para respetar correcciones del ciudadano y pausas de correo.
    """
    if event not in NOTIFIABLE_EVENTS:
        return
    public_fields = tuple(
        field for field in changed_fields if field in PUBLIC_CHANGE_LABELS
    )
    transaction.on_commit(
        lambda action_id=action_id, event=event, fields=public_fields: send_action_notification(
            action_id, event, changed_fields=fields,
        ),
    )


def send_action_notification(action_id, event, *, changed_fields=()):
    """Envío seguro: un problema SMTP nunca invalida una gestión guardada."""
    if event not in NOTIFIABLE_EVENTS:
        return False

    try:
        # Import local: evita ciclos con las señales que emplean esta utilidad.
        from .models import CitizenRequestAction

        action = (
            CitizenRequestAction.objects
            .select_related("request")
            .filter(pk=action_id)
            .first()
        )
        if action is None:
            return False
        # Los hitos automáticos corresponden a trabajos externos. La edición
        # expresamente notificada también puede ser de una gestión municipal.
        if event != "UPDATED" and (
            action.executor_type not in EXTERNAL_EXECUTOR_TYPES
            or not (action.executor_name or "").strip()
        ):
            return False

        citizen_request = action.request
        recipient = (citizen_request.followup_recipient or "").strip()
        if not recipient:
            # Solicitud interna sin correo, o correo pausado por reverificación.
            return False

        executor_label = (
            "empresa externa" if action.executor_type == "COMPANY"
            else "técnico externo"
        )
        article = "una" if action.executor_type == "COMPANY" else "un"
        status_texts = {
            "ASSIGNED": (
                "Asignación de ejecutor",
                f"Se asignó {article} {executor_label} para atender una gestión de su solicitud.",
            ),
            "REASSIGNED": (
                "Cambio de ejecutor",
                f"Se actualizó el ejecutor de una gestión: {executor_label}.",
            ),
            "IN_PROGRESS": (
                "Inicio de ejecución",
                "La ejecución del trabajo asociado a esta gestión ha comenzado.",
            ),
            "FINISHED": (
                "Finalización de gestión",
                "El trabajo asociado a esta gestión operativa fue registrado como finalizado.",
            ),
            "REOPENED": (
                "Reapertura de gestión",
                "Una gestión previamente finalizada fue reabierta para continuar su seguimiento.",
            ),
            "UPDATED": (
                "Actualización de gestión operativa",
                "Se registró una modificación de una gestión operativa de su solicitud.",
            ),
        }
        title, summary = status_texts[event]
        change_detail = ""
        if event == "UPDATED" or changed_fields:
            # También sirve para UN solo correo automático cuando el mismo
            # guardado cambia ejecutor y fecha con la casilla marcada.
            # Solo los nombres seguros de campos; nunca contenido libre interno.
            names = [PUBLIC_CHANGE_LABELS[field] for field in changed_fields
                     if field in PUBLIC_CHANGE_LABELS]
            if names:
                change_detail = "Información actualizada: " + ", ".join(names) + ".\n"
            if "expected_execution_date" in changed_fields:
                new_date = action.expected_execution_date
                readable_date = (
                    new_date.strftime("%d/%m/%Y") if new_date
                    else "pendiente de confirmar"
                )
                change_detail += f"Nueva fecha prevista: {readable_date}.\n"
        executor_detail = (
            f"Ejecutor: {action.executor_name}\n"
            if action.executor_type in EXTERNAL_EXECUTOR_TYPES
            and (action.executor_name or "").strip()
            else ""
        )
        requester_name = (citizen_request.requester_name or "vecino/a").strip()
        message = (
            f"Estimado/a {requester_name}:\n\n"
            f"{summary}\n\n"
            f"{change_detail}"
            f"Tipo de gestión: {action.get_action_type_display()}\n"
            f"{executor_detail}"
            f"Código de seguimiento: {citizen_request.tracking_code}\n\n"
            "Esta comunicación informa un avance de la gestión operativa; "
            "no significa que la solicitud o atención haya cambiado de estado.\n\n"
            f"{portal_link_text()}\n\n"
            "Puede consultar el estado general de su solicitud con su código "
            "de seguimiento."
        )
        send_mail(
            subject=f"{title} — SGR Municipalidad de La Serena",
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=False,
        )
        return True
    except Exception:
        # El estado y su auditoría ya fueron guardados. Una falla del correo
        # no debe mostrar al ciudadano un error ni repetir el guardado.
        logger.exception(
            "No se pudo enviar el aviso de gestión operativa %s (%s).",
            action_id, event,
        )
        return False
