from django.urls import path

from . import views

app_name = "organization"

urlpatterns = [
    path("funcionarios/", views.employee_list, name="employee_list"),
    path("delegaciones/", views.delegation_list, name="delegation_list"),
    path("cargos-funciones/", views.position_list, name="position_list"),
]