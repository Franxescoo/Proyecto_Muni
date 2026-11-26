"""Reglas del cliente para actividad computable en metas SGR.

No se eliminan ni alteran actividades que no ponderan: estas pueden seguir
apareciendo en el historial y en el registro, pero no aumentan indicadores.
No agrega campos ni requiere migración.
"""

import re
import unicodedata

from django.core.exceptions import ValidationError

DAILY_ACTIVITY_LIMIT = 7


def _normalized(value):
    value = unicodedata.normalize("NFKD", str(value or "").casefold())
    value = "".join(c for c in value if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value).split())


def _rut_key(value):
    return re.sub(r"[^0-9k]", "", str(value or "").casefold())


def _person_from_activity(activity):
    """Contacto del usuario, priorizando los datos vinculados a la atención.

    Los campos contact/phone se aceptan como respaldo de datos históricos.
    """
    attention = getattr(activity, "attention", None)
    if attention is None and activity.pk:
        attention = activity.assigned_attentions.filter(
            deleted_at__isnull=True
        ).order_by("pk").first()
    citizen = getattr(attention, "citizen", None) if attention else None
    request = getattr(attention, "citizen_request", None) if attention else None
    request_citizen = getattr(request, "citizen", None) if request else None

    name = (
        getattr(citizen, "full_name", None)
        or getattr(request_citizen, "full_name", None)
        or getattr(attention, "requester", None)
        or getattr(request, "requester_name", None)
        or getattr(activity, "contact", "")
    )
    phone = (
        getattr(citizen, "phone", None)
        or getattr(request_citizen, "phone", None)
        or getattr(attention, "requester_phone", None)
        or getattr(request, "requester_phone", None)
        or getattr(activity, "phone", "")
    )
    rut = (
        getattr(citizen, "rut", None)
        or getattr(request_citizen, "rut", None)
        or ""
    )
    return str(name or "").strip(), str(phone or "").strip(), rut


def _delegate_reference_instant(activity, at_time=None):
    """Instante de referencia para roles históricos, según fecha de gestión.

    Cuando la gestión se registró el mismo día en que se realizó, se conoce
    su instante de registro. Para gestiones ingresadas después, solo se
    dispone de la fecha y se utiliza el inicio del día, sin inventar una hora.
    """
    from datetime import date, datetime, time
    from django.conf import settings
    from django.utils import timezone

    if at_time is None:
        activity_date = getattr(activity, "date", None)
        created_at = getattr(activity, "created_at", None)
        if activity_date is None:
            at_time = created_at or timezone.now()
        elif created_at is not None:
            recorded_date = (
                timezone.localtime(created_at).date()
                if timezone.is_aware(created_at)
                else created_at.date()
            )
            at_time = created_at if recorded_date == activity_date else activity_date
        else:
            at_time = activity_date

    if isinstance(at_time, date) and not isinstance(at_time, datetime):
        at_time = datetime.combine(at_time, time.min)
    if settings.USE_TZ and timezone.is_naive(at_time):
        at_time = timezone.make_aware(at_time, timezone.get_current_timezone())
    return at_time


def _municipal_delegate(activity, at_time=None):
    """Responsable municipal vigente en la fecha/instante de la gestión.

    El historial deja inmune el avance ante cambios posteriores de responsable.
    Si aún no existe historial (datos anteriores al registro de cambios),
    se conserva el comportamiento preexistente por compatibilidad.
    """
    author = getattr(activity, "author", None)
    delegation = getattr(author, "delegation", None) if author else None
    if delegation is None:
        return None

    reference = _delegate_reference_instant(activity, at_time)
    history = delegation.responsibility_history
    # Si hubo un cambio antes de la gestión, ese cambio define al responsable.
    previous_change = (
        history.filter(changed_at__lte=reference)
        .select_related("new_responsible")
        .order_by("-changed_at", "-pk")
        .first()
    )
    if previous_change is not None:
        return previous_change.new_responsible

    # Si la gestión es anterior al PRIMER cambio registrado, el responsable
    # válido entonces era el responsable anterior a ese primer cambio.
    first_later_change = (
        history.filter(changed_at__gt=reference)
        .select_related("previous_responsible")
        .order_by("changed_at", "pk")
        .first()
    )
    if first_later_change is not None:
        return first_later_change.previous_responsible

    # Compatibilidad: delegaciones existentes sin historial auditable.
    return getattr(delegation, "responsible", None)


def _creator_is_municipal_delegate(activity):
    """Excluir solo si la cuenta que CREO la actividad era el delegado.

    author es el titular de la meta; attention.requester es un ciudadano;
    ninguno identifica necesariamente a la persona que pulsó Crear.
    Si la actividad histórica no conserva creador, no inventar su identidad.
    """
    creator_employee_id = getattr(activity, "created_by_employee_id", None)
    recorded_at = getattr(activity, "created_at", None)
    if creator_employee_id is None or recorded_at is None:
        return False
    delegate = _municipal_delegate(activity, at_time=recorded_at)
    return delegate is not None and delegate.pk == creator_employee_id


def _activity_category(activity):
    """SGR-RESPALDO-FELICITACIONES-20261121: clasificación persistida en Tipos de actividad."""
    kind = getattr(activity, "activity_type", None)
    if kind is not None and bool(getattr(kind, "is_preparatory_coordination", False)):
        return "preparatory"
    if kind is not None and bool(getattr(kind, "is_congratulation", False)):
        return "congratulation"
    return "ordinary"


def _latest_active_validation(evidence):
    # Mismo criterio de orden usado por el servicio de Monitoreo.
    records = [v for v in evidence.validations.all() if v.deleted_at is None]
    return max(records, key=lambda v: (v.date, v.version, v.pk), default=None)


def _has_support_document(evidence):
    if (getattr(evidence, "file_link", "") or "").strip():
        return True
    if bool(getattr(evidence, "file", None)):
        return True
    return any(item.deleted_at is None for item in evidence.files.all())


def _congratulation_with_delegate_support(activity, is_approved):
    """Exige aval con firma de la CUENTA del delegado, no su nombre seleccionado.

    Se conserva el historial si cambia posteriormente el responsable.
    La validación más reciente debe seguir aprobada, con respaldo documental.
    """
    for evidence in activity.evidences.all():
        if not is_approved(evidence) or not _has_support_document(evidence):
            continue
        record = _latest_active_validation(evidence)
        if record is None:
            continue
        if (
            getattr(record, "formal_delegate_endorsement", False)
            and getattr(record, "delegate_endorsed_by_id", None) is not None
            and getattr(record, "delegate_endorsed_at", None) is not None
        ):
            return True
    return False


def activity_qualifies_for_goal(activity, is_evidence_approved):
    """Regla de ponderación. La evidencia se verifica en Monitoreo.

    La aprobación de una felicitación se considera respaldo formal solo cuando
    existe documento y la validación aprobada vigente fue hecha por el
    responsable municipal de la delegación. No basta marcarla en un formulario.
    """
    name, phone, _ = _person_from_activity(activity)
    if not name or not phone:
        return False
    if _creator_is_municipal_delegate(activity):
        return False
    category = _activity_category(activity)
    if category == "preparatory":
        return False
    if category == "congratulation":
        return _congratulation_with_delegate_support(activity, is_evidence_approved)
    return True


def daily_capacity_exceeded(author_id, date, *, activity_pk=None):
    """Cuenta todas las metas del funcionario en la fecha, sin archivadas."""
    if not author_id or date is None:
        return False
    from registration_validation.models import Activity

    if activity_pk is not None:
        before = Activity.objects.filter(pk=activity_pk).values(
            "author_id", "date", "deleted_at"
        ).first()
        if before and (
            before["author_id"] == author_id
            and before["date"] == date
            and before["deleted_at"] is None
        ):
            # Editar los demás datos de un registro activo no consume cupo nuevo.
            return False

    others = Activity.objects.filter(
        author_id=author_id, date=date, deleted_at__isnull=True,
    )
    if activity_pk is not None:
        others = others.exclude(pk=activity_pk)
    return others.count() >= DAILY_ACTIVITY_LIMIT


def validate_daily_activity_limit(activity):
    if activity.deleted_at is not None:
        return
    if daily_capacity_exceeded(
        activity.author_id, activity.date, activity_pk=activity.pk,
    ):
        raise ValidationError({
            "date": (
                "El funcionario ya tiene siete actividades registradas en "
                "esta fecha. No se permite registrar una octava actividad, "
                "aunque corresponda a otra meta."
            )
        })
