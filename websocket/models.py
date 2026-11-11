"""Mensajería persistente y cursor de lectura por funcionario y delegación."""

import uuid

from django.conf import settings
from django.db import models


class ChatMessage(models.Model):
    delegation = models.ForeignKey(
        "organization.Delegation", on_delete=models.PROTECT,
        related_name="institutional_chat_messages",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="institutional_chat_messages",
    )
    message = models.CharField(max_length=300)
    client_id = models.UUIDField(default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["sender", "client_id"], name="chat_sender_client_unique"
            ),
        ]
        indexes = [models.Index(fields=["delegation", "id"], name="chat_delegation_msg_idx")]


class ChatReadState(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="institutional_chat_read_states",
    )
    delegation = models.ForeignKey(
        "organization.Delegation", on_delete=models.CASCADE,
        related_name="institutional_chat_read_states",
    )
    last_read_id = models.PositiveBigIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "delegation"], name="chat_read_user_delegation_unique"
            ),
        ]
