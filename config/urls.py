"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views.
"""
from django.contrib import admin
from django.conf import settings
from django.urls import include, path
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("django.contrib.auth.urls")),
    path("planning/", include("planning_measurements.urls")),
    path("monitoring/", include("monitoring_traceability.urls")),
    path("organization/", include("organization.urls")),
    path("", include("core.urls")),
    path("accounts/", include("accounts.urls")),
    path("accounts/", include("django.contrib.auth.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
