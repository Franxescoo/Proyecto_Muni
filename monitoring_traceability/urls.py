from django.urls import path

from . import views

app_name = "monitoring"

urlpatterns = [
    path("resumen/", views.executive_dashboard, name="executive_dashboard"),
    path("actividad/", views.activity_control, name="activity_control"),
    path("indicadores/", views.indicator_list, name="indicator_list"),
    path("compromisos/", views.commitment_list, name="commitment_list"),
    path("auditoria/", views.audit_list, name="audit_list"),
]
