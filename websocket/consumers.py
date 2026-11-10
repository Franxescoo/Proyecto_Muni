"""Socket de solo lectura por delegación activa. Los envíos usan POST/CSRF."""

from asgiref.sync import async_to_sync
from channels.generic.websocket import JsonWebsocketConsumer

from .access import chat_delegation_id


class ChatConsumer(JsonWebsocketConsumer):
    def connect(self):
        user = self.scope.get("user")
        session = self.scope.get("session")
        if user is None or session is None:
            self.close()
            return
        selected = session.get("sgr_active_delegation")
        delegation_id = chat_delegation_id(user, selected)
        if delegation_id is None:
            self.close()
            return
        # 3. Crear nombre del grupo
        self.delegation_id = delegation_id
        self.group_name = f"chat_delegation_{delegation_id}"
        async_to_sync(self.channel_layer.group_add)(self.group_name, self.channel_name)
        self.accept()

    def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            async_to_sync(self.channel_layer.group_discard)(self.group_name, self.channel_name)

    def receive_json(self, content, **kwargs):
        # No se acepta envío por WebSocket para impedir saltarse CSRF y validación.
        self.send_json({"type": "error", "message": "Usa el formulario para enviar"})

    def chat_event(self, event):
        # Revocación de delegación: dejar de recibir eventos en la misma conexión.
        if chat_delegation_id(self.scope["user"], self.delegation_id) is None:
            self.close(code=4403)
            return
        self.send_json(event["payload"])


class UpdatesConsumer(JsonWebsocketConsumer):
    group_name = "sgr_updates"

    def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            self.close()
            return
        async_to_sync(self.channel_layer.group_add)(
            self.group_name, self.channel_name
        )
        self.accept()

    def disconnect(self, close_code):
        async_to_sync(self.channel_layer.group_discard)(
            self.group_name, self.channel_name
        )

    def receive_json(self, content, **kwargs):
        return

    def data_changed(self, event):
        self.send_json(event["payload"])
