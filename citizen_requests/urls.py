from django.urls import path

from . import views
from .history import public_request_history
from .verify_followup import verify_followup_email


app_name = "citizen_requests"

urlpatterns = [
    path("portal/verificar-correo/<str:token>/", verify_followup_email, name="verify_followup_email"),
    path(
        "portal/mis-solicitudes/",
        public_request_history,
        name="public_request_history",
    ),
    path(
        "portal/nueva-solicitud/",
        views.public_request_form,
        name="public_request_form",
    ),
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
        "solicitudes/bandeja/<int:request_id>/gestiones/",
        views.request_action_list,
        name="request_action_list",
    ),
    path(
        "solicitudes/bandeja/<int:request_id>/gestiones/nueva/",
        views.create_request_action,
        name="create_request_action",
    ),
    path(
        "solicitudes/bandeja/<int:request_id>/gestiones/<int:action_id>/editar/",
        views.edit_request_action,
        name="edit_request_action",
    ),
    path(
        "solicitudes/bandeja/<int:request_id>/gestiones/<int:action_id>/adjuntos/<int:attachment_id>/descargar/",
        views.download_request_action_attachment,
        name="download_request_action_attachment",
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
