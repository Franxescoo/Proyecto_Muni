from django.urls import path
from . import views

app_name = "websocket"

urlpatterns = [
    path("", views.chat_room, name="chat"),
    path("send/", views.send_message, name="send"),
]
