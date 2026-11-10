from django.urls import path
from .consumers import ChatConsumer, UpdatesConsumer

websocket_urlpatterns = [
    path("ws/chat/", ChatConsumer.as_asgi()),
    path("ws/updates/", UpdatesConsumer.as_asgi()),
]
