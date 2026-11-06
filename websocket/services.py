"""Serialización, no leídos y publicación en tiempo real del chat."""

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .models import ChatMessage, ChatReadState

logger = logging.getLogger(__name__)


def serialize_message(message):
    return {
        "id": message.pk,
        "client_id": str(message.client_id),
        "user_id": message.sender_id,
        "username": message.sender.get_username(),
        "message": message.message,
        "created_at": message.created_at.isoformat(),
    }


def unread_count(user, delegation_id):
    last_read = ChatReadState.objects.filter(
        user=user, delegation_id=delegation_id,
    ).values_list("last_read_id", flat=True).first() or 0
    return ChatMessage.objects.filter(
        delegation_id=delegation_id, id__gt=last_read,
    ).exclude(sender=user).count()


def publish_chat_message(message):
    """Publicación best-effort: la BD es la fuente de verdad (fallback HTTP)."""
    layer = get_channel_layer()
    if layer is None:
        return
    try:
        async_to_sync(layer.group_send)(
            f"chat_delegation_{message.delegation_id}",
            {"type": "chat_event", "payload": {
                "type": "chat_message", **serialize_message(message),
            }},
        )
    except Exception:
        logger.exception("No fue posible publicar el mensaje %s por WebSocket", message.pk)
