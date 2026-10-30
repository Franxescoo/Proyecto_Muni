from django.db.models.signals import post_save, pre_save
from django.db import transaction
from django.dispatch import receiver

from .models import CitizenRequest
from .notifications import send_attention_notification


@receiver(pre_save, sender=CitizenRequest)
def remember_attention_link_transition(
    sender,
    instance,
    update_fields=None,
    **kwargs,
):
    if not instance.pk or (
        update_fields is not None
        and "attention_entry" not in update_fields
    ):
        instance._attention_linked_from_empty = False
        return

    previous_attention_id = (
        sender.objects
        .filter(pk=instance.pk)
        .values_list("attention_entry_id", flat=True)
        .first()
    )
    instance._attention_linked_from_empty = (
        previous_attention_id is None
        and instance.attention_entry_id is not None
        and instance.origin == "CITIZEN"
        and bool(instance.requester_email)
    )


@receiver(post_save, sender=CitizenRequest)
def notify_new_attention_link(
    sender,
    instance,
    **kwargs,
):
    if not getattr(instance, "_attention_linked_from_empty", False):
        return

    transaction.on_commit(
        lambda request_id=instance.pk,
        requester_name=instance.requester_name,
        requester_email=instance.requester_email,
        tracking_code=str(instance.tracking_code): send_attention_notification(
            request_id,
            requester_name,
            requester_email,
            tracking_code,
        )
    )
