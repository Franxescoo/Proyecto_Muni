from django.urls import path

from . import views


app_name = "citizen_requests"

urlpatterns = [
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
        "solicitudes/bandeja/<int:request_id>/",
        views.request_detail,
        name="request_detail",
    ),
    path(
        "solicitudes/registrar/",
        views.register_public_request,
        name="register_public_request",
    ),
]
