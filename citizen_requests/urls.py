from django.urls import path

from . import views


app_name = "citizen_requests"

urlpatterns = [
    path(
        "portal/",
        views.public_portal,
        name="public_portal",
    ),
    path(
        "solicitudes/confirmacion/<uuid:tracking_code>/",
        views.public_request_confirmation,
        name="public_request_confirmation",
    ),
    path(
        "solicitudes/bandeja/<int:request_id>/derivar/",
        views.assign_request,
        name="assign_request",
    ),
    path(
        "solicitudes/bandeja/<int:request_id>/cambiar-derivacion/",
        views.change_request_delegation,
        name="change_request_delegation",
    ),
    path(
        "solicitudes/bandeja/",
        views.request_inbox,
        name="request_inbox",
    ),
    path(
        "solicitudes/bandeja/pendientes/conteo/",
        views.pending_request_count,
        name="pending_request_count",
    ),
    path(
        "solicitudes/bandeja/<int:request_id>/",
        views.request_detail,
        name="request_detail",
    ),
    path(
        "solicitudes/bandeja/<int:request_id>/crear-atencion/",
        views.create_attention_from_request,
        name="create_attention_from_request",
    ),
    path(
        "solicitudes/bandeja/<int:request_id>/atencion/",
        views.view_attention_from_request,
        name="view_attention_from_request",
    ),
    path(
        "solicitudes/registrar/",
        views.register_public_request,
        name="register_public_request",
    ),
]
