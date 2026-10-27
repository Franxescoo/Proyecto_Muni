from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def publish_chat_message(user, delegation_id, message):
    layer = get_channel_layer()

    if layer is None:
        raise RuntimeError("Channel layer no configurado")

    async_to_sync(layer.group_send)(
        f"chat_delegation_{delegation_id}",
        {
            "type": "chat_event",
            "payload": {
                "type": "chat_message",
                "username": user.get_username(),
                "message": message,
            },
        },
    )