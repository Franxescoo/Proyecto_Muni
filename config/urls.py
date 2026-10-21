
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
from django.contrib.auth.views import PasswordResetView
from accounts.forms import (
    InstitutionalPasswordResetForm,
    UsuarioOCorreoAuthenticationForm,
)


urlpatterns = [
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
        PasswordResetView.as_view(
            form_class=InstitutionalPasswordResetForm,
            email_template_name="registration/password_reset_email.txt",
            html_email_template_name="registration/password_reset_email.html",
            subject_template_name="registration/password_reset_subject.txt",
        ),
        name="password_reset",
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
]


# ---------------------------------------------------------
# Archivos multimedia durante desarrollo
# ---------------------------------------------------------

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )
