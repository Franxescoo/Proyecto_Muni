from django.urls import path
from . import views

app_name = "municipal_events"
urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("inscripciones/", views.enrollment_list, name="enrollment_list"),
    path("entregas/", views.delivery_list, name="delivery_list"),
    path("historial/", views.history_list, name="history_list"),
    path("eventos/", views.event_list, name="event_list"),
    path("eventos/<int:pk>/ver/", views.event_detail, name="event_detail"),
    path("eventos/<int:pk>/eliminar/", views.event_delete, name="event_delete"),
    path("ediciones/<int:pk>/ver/", views.edition_detail, name="edition_detail"),
    path("ediciones/<int:pk>/eliminar/", views.edition_delete, name="edition_delete"),
    path("eventos/nuevo/", views.event_create, name="event_create"),
    path("eventos/<int:pk>/editar/", views.event_edit, name="event_edit"),
    path("ediciones/<int:pk>/editar/", views.edition_edit, name="edition_edit"),
    path("eventos/<int:event_id>/ediciones/nueva/", views.edition_create, name="edition_create"),
    path("campanas/", views.campaign_list, name="campaign_list"),
    path("campanas/nueva/", views.campaign_create, name="campaign_create"),
    path("campanas/<int:pk>/", views.campaign_detail, name="campaign_detail"),
    path("campanas/<int:pk>/editar/", views.campaign_edit, name="campaign_edit"),
    path("campanas/<int:pk>/eliminar/", views.campaign_delete, name="campaign_delete"),
    path("inscripciones/<int:pk>/detalle/", views.enrollment_detail, name="enrollment_detail"),
    path("inscripciones/<int:pk>/constancia/", views.delivery_detail, name="delivery_detail"),
    path("atenciones/<int:attention_id>/campanas/", views.campaigns_for_attention, name="campaigns_for_attention"),
    path("campanas/<int:pk>/inscribir/", views.enrollment_create, name="enrollment_create"),
    path("inscripciones/<int:pk>/evaluar/", views.enrollment_review, name="enrollment_review"),
    path("inscripciones/<int:pk>/entregar/", views.delivery_create, name="delivery_create"),
]
