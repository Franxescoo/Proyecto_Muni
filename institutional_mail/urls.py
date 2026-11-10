from django.urls import path
from . import views

app_name = 'institutional_mail'

urlpatterns = [
    path('api/unread/', views.unread_count, name='unread'),
    path('api/recipients/', views.recipients, name='recipients'),
    path('api/messages/', views.messages, name='messages'),
    path('api/messages/send/', views.send_message, name='send'),
    path('api/messages/<int:pk>/', views.message_detail, name='detail'),
    path('api/messages/<int:pk>/read/', views.mark_read, name='read'),
    path('api/messages/<int:pk>/archive/', views.set_archive, name='archive'),
]
