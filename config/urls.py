
"""
URL configuration for config project.

The urlpatterns list routes URLs to views.
For more information, see:
https://docs.djangoproject.com/en/6.1/topics/http/urls/
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.contrib.auth.views import LoginView
from accounts.forms import (
    UsuarioOCorreoAuthenticationForm,
)
from accounts import views as account_views
from organization import error_views


handler400 = "organization.error_views.bad_request"
handler403 = "organization.error_views.permission_denied"
handler404 = "organization.error_views.page_not_found"
handler500 = "organization.error_views.server_error"


urlpatterns = [
    path("correo/", include("institutional_mail.urls")),
    # -----------------------------------------------------
    # Administración de Django
    # -----------------------------------------------------
    path(
        "admin/",
        admin.site.urls,
    ),

    # -----------------------------------------------------
    # Autenticación
    # -----------------------------------------------------
    path(
        "accounts/login/",
        LoginView.as_view(
            authentication_form=UsuarioOCorreoAuthenticationForm
        ),
        name="login",
    ),

    path(
        "accounts/password_reset/",
        account_views.password_reset_request,
        name="password_reset",
    ),
    path(
        "accounts/password_reset/verify/",
        account_views.password_reset_verify,
        name="password_reset_verify",
    ),
    path(
        "accounts/password_reset/password/",
        account_views.password_reset_password,
        name="password_reset_password",
    ),

    path(
        "accounts/",
        include("django.contrib.auth.urls"),
    ),

    # -----------------------------------------------------
    # Planificación y mediciones
    # -----------------------------------------------------
    path(
        "planning/",
        include("planning_measurements.urls"),
    ),

    # -----------------------------------------------------
    # Registro y validación
    # -----------------------------------------------------
    path(
        "registration/",
        include("registration_validation.urls"),
    ),

    # -----------------------------------------------------
    # Monitoreo y trazabilidad
    # -----------------------------------------------------
    path(
        "monitoring/",
        include("monitoring_traceability.urls"),
    ),

    # -----------------------------------------------------
    # Organización
    # -----------------------------------------------------
    path(
        "organization/",
        include("organization.urls"),
    ),

    # -----------------------------------------------------
    # -----------------------------------------------------
    # Solicitudes públicas de vecinos
    # -----------------------------------------------------
    path(
        "",
        include("citizen_requests.urls"),
    ),

    # -----------------------------------------------------
    # Eventos, campañas e inscripciones municipales
    # -----------------------------------------------------
    path("ciudadanos/", include("citizen_registry.urls")),

    path(
        "eventos-campanas/",
        include("municipal_events.urls"),
    ),

    # -----------------------------------------------------
    # Cuentas de usuario
    # -----------------------------------------------------
    path(
        "accounts/",
        include("accounts.urls"),
    ),

    # -----------------------------------------------------
    # Inicio y rutas generales
    # -----------------------------------------------------
    path(
        "",
        include("core.urls"),
    ),
    path("chat/", include("websocket.urls")),
    path(
        "organization/errores/<int:error_code>/",
        error_views.error_preview,
        name="organization_error_preview",
    ),
]


# ---------------------------------------------------------
# Archivos multimedia durante desarrollo
# ---------------------------------------------------------

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )

urlpatterns.append(
    path(
        "<path:unmatched_path>",
        error_views.unknown_route,
        name="unknown_route",
    )
)
