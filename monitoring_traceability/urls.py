from django.urls import path

from . import views

app_name = "monitoring"

urlpatterns = [
    path("resumen/", views.executive_dashboard, name="executive_dashboard"),
    path("resumen/exportar/", views.dashboard_export, name="dashboard_export"),
    path("actividad/", views.activity_control, name="activity_control"),
    path("indicadores/", views.indicator_list, name="indicator_list"),
    path("indicadores/exportar/", views.indicator_export, name="indicator_export"),
    path("compromisos/", views.commitment_list, name="commitment_list"),
    path("compromisos/nuevo/", views.commitment_create, name="commitment_create"),
    path("compromisos/<int:commitment_id>/editar/", views.commitment_edit, name="commitment_edit"),
    path("compromisos/exportar/", views.commitment_export, name="commitment_export"),
    path("auditoria/", views.audit_list, name="audit_list"),
]
