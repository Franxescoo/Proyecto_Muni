import logging
from functools import partial

from asgiref.sync import async_to_sync
from django.db import transaction
from django.db.models.signals import m2m_changed, post_delete, post_save

logger = logging.getLogger(__name__)


def connect_live_signals():
    from accounts.models import UserProfile
    from citizen_registry.models import Citizen
    from citizen_requests.models import CitizenRequest
    from institutional_mail.models import InstitutionalMessage
    from monitoring_traceability.models import Commitment, Indicator
    from monitoring_traceability.models import CommitmentComment
    from organization.models import (
        Delegation,
        Employee,
        OrganizationRole,
        PositionFunction,
    )
    from planning_measurements.models import Goal, MeasurementItem, Period
    from registration_validation.models import (
        Activity,
        ActivityType,
        AttentionEntry,
        AttentionType,
        Evidence,
        EvidenceFile,
        Service,
        SubAttention,
        Validation,
    )
    from municipal_events.models import (
        Beneficiary,
        Campaign,
        Enrollment,
        EventEdition,
        EventParticipation,
        GiftDelivery,
        MunicipalEvent,
    )

    models = (
        Delegation,
        Employee,
        OrganizationRole,
        PositionFunction,
        UserProfile,
        Citizen,
        CitizenRequest,
        InstitutionalMessage,
        Goal,
        MeasurementItem,
        Period,
        Activity,
        ActivityType,
        AttentionEntry,
        AttentionType,
        Evidence,
        EvidenceFile,
        Service,
        SubAttention,
        Validation,
        Commitment,
        CommitmentComment,
        Indicator,
        MunicipalEvent,
        EventEdition,
        Campaign,
        Beneficiary,
        Enrollment,
        GiftDelivery,
        EventParticipation,
    )

    for model in models:
        dispatch_uid = f"websocket.live.{model._meta.label_lower}"
        post_save.connect(
            _publish_data_changed,
            sender=model,
            dispatch_uid=f"{dispatch_uid}.save",
            weak=False,
        )
        post_delete.connect(
            _publish_data_changed,
            sender=model,
            dispatch_uid=f"{dispatch_uid}.delete",
            weak=False,
        )
        for field in model._meta.many_to_many:
            m2m_dispatch_uid = (
                f"{dispatch_uid}.m2m.{field.name}"
            )
            m2m_changed.connect(
                partial(_publish_m2m_changed, model=model),
                sender=field.remote_field.through,
                dispatch_uid=m2m_dispatch_uid,
                weak=False,
            )


def _publish_data_changed(sender, **kwargs):
    _schedule_publish(sender)


def _publish_m2m_changed(sender, model, action, **kwargs):
    if action in {"post_add", "post_remove", "post_clear"}:
        _schedule_publish(model)


def _schedule_publish(model):
    payload = {
        "type": "data_changed",
        "model": model._meta.label_lower,
    }

    def publish():
        try:
            from channels.layers import get_channel_layer

            layer = get_channel_layer()
            async_to_sync(layer.group_send)(
                "sgr_updates",
                {"type": "data_changed", "payload": payload},
            )
        except Exception:
            logger.exception(
                "No se pudo publicar el cambio de datos para %s",
                model._meta.label_lower,
            )

    try:
        transaction.on_commit(publish)
    except Exception:
        logger.exception(
            "No se pudo registrar la publicación del cambio para %s",
            model._meta.label_lower,
        )
