"""Regresiones del chat: ámbito, historial, no leídos e idempotencia."""

import uuid
from unittest.mock import patch

from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from accounts.models import UserProfile
from citizen_registry.models import Citizen
from organization.models import Delegation
from config.asgi import application
from .consumers import UpdatesConsumer
from .models import ChatMessage, ChatReadState


class ChatApiTests(TestCase):
    def setUp(self):
        self.north = Delegation.objects.create(name="Norte", status="Active", scope="Urbano")
        self.south = Delegation.objects.create(name="Sur", status="Active", scope="Urbano")
        User = get_user_model()
        self.alice = User.objects.create_user(username="alice_chat", password="testpass123")
        self.bob = User.objects.create_user(username="bob_chat", password="testpass123")
        self.carol = User.objects.create_user(username="carol_chat", password="testpass123")
        for index, (user, delegation) in enumerate((
            (self.alice, self.north), (self.bob, self.north), (self.carol, self.south),
        )):
            profile = UserProfile.objects.create(
                user=user, employee_code=f"CHAT-{index}", delegation=delegation,
            )
            profile.authorized_delegations.add(delegation)
        self.send_url = reverse("websocket:send")
        self.history_url = reverse("websocket:history")
        self.read_url = reverse("websocket:read")

    def login(self, user):
        self.client.force_login(user)

    @patch("websocket.views.publish_chat_message")
    def test_persistence_and_sender_confirmation(self, publish):
        self.login(self.alice)
        client_id = str(uuid.uuid4())
        response = self.client.post(self.send_url, {"message": "Hola", "client_id": client_id})
        self.assertEqual(response.status_code, 200)
        payload = response.json()["message"]
        self.assertEqual(payload["message"], "Hola")
        self.assertEqual(payload["user_id"], self.alice.pk)
        self.assertEqual(ChatMessage.objects.count(), 1)
        self.assertEqual(ChatMessage.objects.get().delegation, self.north)
        publish.assert_called_once()

        response = self.client.post(self.send_url, {"message": "Hola", "client_id": client_id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"]["id"], payload["id"])
        self.assertEqual(ChatMessage.objects.count(), 1)
        publish.assert_called_once()

    @patch("websocket.views.publish_chat_message")
    def test_duplicate_id_with_other_content_is_rejected(self, publish):
        self.login(self.alice)
        client_id = str(uuid.uuid4())
        self.client.post(self.send_url, {"message": "Uno", "client_id": client_id})
        response = self.client.post(self.send_url, {"message": "Dos", "client_id": client_id})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(ChatMessage.objects.count(), 1)

    @patch("websocket.views.publish_chat_message")
    def test_sender_can_edit_and_delete_own_message(self, publish):
        self.login(self.alice)
        response = self.client.post(self.send_url, {"message": "Original"})
        message_id = response.json()["message"]["id"]

        response = self.client.post(
            reverse("websocket:edit", args=[message_id]), {"message": "Editado"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"]["message"], "Editado")
        self.assertTrue(response.json()["message"]["is_edited"])

        response = self.client.post(reverse("websocket:delete", args=[message_id]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["message"]["is_deleted"])
        self.assertEqual(self.client.get(self.history_url).json()["messages"][0]["message"], "")
        self.assertEqual(publish.call_count, 3)

    @patch("websocket.views.publish_chat_message")
    def test_sender_cannot_edit_or_delete_other_users_message(self, publish):
        self.login(self.alice)
        message_id = self.client.post(
            self.send_url, {"message": "Privado"}
        ).json()["message"]["id"]
        self.login(self.bob)
        self.assertEqual(
            self.client.post(
                reverse("websocket:edit", args=[message_id]), {"message": "No"},
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(reverse("websocket:delete", args=[message_id])).status_code,
            404,
        )

    @patch("websocket.views.publish_chat_message")
    def test_no_cross_delegation_leakage(self, publish):
        self.login(self.carol)
        self.client.post(self.send_url, {"message": "Secreto sur"})
        self.login(self.alice)
        data = self.client.get(self.history_url).json()
        self.assertEqual(data["messages"], [])
        self.assertEqual(data["unread_count"], 0)
        self.client.post(self.send_url, {"message": "Norte"})
        self.login(self.carol)
        data = self.client.get(self.history_url).json()
        self.assertEqual([x["message"] for x in data["messages"]], ["Secreto sur"])

    @patch("websocket.views.publish_chat_message")
    def test_unread_and_read_cursor_by_user(self, publish):
        self.login(self.alice)
        self.client.post(self.send_url, {"message": "Hola Bob"})
        self.assertEqual(self.client.get(self.history_url).json()["unread_count"], 0)
        self.login(self.bob)
        data = self.client.get(self.history_url).json()
        self.assertEqual(data["unread_count"], 1)
        last_id = data["messages"][-1]["id"]
        response = self.client.post(self.read_url, {"last_message_id": str(last_id + 1000)})
        self.assertEqual(response.json()["unread_count"], 0)
        self.assertEqual(ChatReadState.objects.get(user=self.bob, delegation=self.north).last_read_id, last_id)
        self.login(self.alice)
        self.client.post(self.send_url, {"message": "Segundo"})
        self.login(self.bob)
        self.assertEqual(self.client.get(self.history_url).json()["unread_count"], 1)

    @patch("websocket.views.publish_chat_message")
    def test_sender_validation_and_authentication(self, publish):
        self.assertEqual(self.client.get(self.history_url).status_code, 302)
        self.assertEqual(self.client.post(self.send_url, {"message": "X"}).status_code, 302)
        self.login(self.alice)
        self.assertEqual(self.client.get(self.send_url).status_code, 405)
        self.assertEqual(self.client.post(self.send_url, {"message": " "}).status_code, 400)
        self.assertEqual(self.client.post(self.send_url, {"message": "x" * 301}).status_code, 400)
        self.assertEqual(self.client.post(self.send_url, {"message": "ok", "client_id": "not-a-uuid"}).status_code, 400)
        self.assertEqual(self.client.get(self.history_url + "?after=invalid").status_code, 400)
        self.assertEqual(self.client.post(self.read_url, {"last_message_id": "-1"}).status_code, 400)
        self.assertEqual(ChatMessage.objects.count(), 0)

    def test_realtime_delivery_failure_does_not_erase_message(self):
        class OfflineLayer:
            async def group_send(self, group, event):
                raise RuntimeError("Socket temporalmente no disponible")

        with patch("websocket.services.get_channel_layer", return_value=OfflineLayer()):
            self.login(self.alice)
            response = self.client.post(self.send_url, {"message": "Persistente"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(ChatMessage.objects.count(), 1)

    @patch("websocket.views.publish_chat_message")
    def test_active_delegation_selection_is_respected(self, publish):
        self.alice.profile.authorized_delegations.add(self.south)
        self.login(self.alice)
        session = self.client.session
        session["sgr_active_delegation"] = self.south.pk
        session.save()
        response = self.client.post(self.send_url, {"message": "Solo sur"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ChatMessage.objects.get().delegation_id, self.south.pk)
        session = self.client.session
        session["sgr_active_delegation"] = self.north.pk
        session.save()
        self.assertEqual(self.client.get(self.history_url).json()["messages"], [])


    def test_user_without_delegation_cannot_use_chat(self):
        user = get_user_model().objects.create_user(username="no_chat_scope")
        self.login(user)
        self.assertEqual(self.client.get(self.history_url).status_code, 403)
        self.assertEqual(self.client.post(self.send_url, {"message": "Hola"}).status_code, 403)
        self.assertEqual(self.client.post(self.read_url, {"last_message_id": "10"}).status_code, 403)

    def test_history_pagination_cursor(self):
        for number in range(104):
            ChatMessage.objects.create(sender=self.alice, delegation=self.north, message=str(number))
        self.login(self.bob)
        recent = self.client.get(self.history_url).json()["messages"]
        self.assertEqual(len(recent), 100)
        self.assertEqual(recent[0]["message"], "4")
        incremental = self.client.get(self.history_url + f"?after={recent[-2]['id']}").json()["messages"]
        self.assertEqual(len(incremental), 1)
        self.assertEqual(incremental[0]["message"], "103")


class UpdatesWebsocketTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="updates_user", password="testpass"
        )

    def communicator(self, user=None):
        headers = [(b"host", b"127.0.0.1")]
        if user is not None:
            consumer_application = UpdatesConsumer.as_asgi()

            async def authenticated_application(scope, receive, send):
                scope = dict(scope, user=user)
                return await consumer_application(scope, receive, send)

            return WebsocketCommunicator(
                authenticated_application, "/ws/updates/", headers=headers
            )
        return WebsocketCommunicator(application, "/ws/updates/", headers=headers)

    def test_authenticated_user_receives_delegation_change(self):
        communicator = self.communicator(self.user)
        async def receive_change():
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await database_sync_to_async(Delegation.objects.create)(
                name="Actualizada", status="Active", scope="Urbano"
            )
            payload = await communicator.receive_json_from()
            await communicator.disconnect()
            return payload

        payload = async_to_sync(receive_change)()
        self.assertEqual(
            payload,
            {"type": "data_changed", "model": "organization.delegation"},
        )

    def test_authenticated_user_receives_citizen_change(self):
        communicator = self.communicator(self.user)

        async def receive_change():
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await database_sync_to_async(Citizen.objects.create)(
                rut="12.345.678-5",
                full_name="Ciudadano de prueba",
                address="Domicilio de prueba",
            )
            payload = await communicator.receive_json_from()
            await communicator.disconnect()
            return payload

        payload = async_to_sync(receive_change)()
        self.assertEqual(
            payload,
            {"type": "data_changed", "model": "citizen_registry.citizen"},
        )

    def test_anonymous_user_is_rejected(self):
        communicator = self.communicator()
        connected, _ = async_to_sync(communicator.connect)()
        self.assertFalse(connected)
