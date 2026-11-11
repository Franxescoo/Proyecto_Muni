from django.urls import path
from . import views

app_name = "websocket"

urlpatterns = [
    path("", views.chat_room, name="chat"),
    path("send/", views.send_message, name="send"),
    path("message/<int:message_id>/edit/", views.edit_message, name="edit"),
    path("message/<int:message_id>/delete/", views.delete_message, name="delete"),
    path("history/", views.message_history, name="history"),
    path("read/", views.mark_messages_read, name="read"),
]
