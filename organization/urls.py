from django.urls import path

from . import views

app_name = "organization"

urlpatterns = [
    path("roles-permisos/", views.role_list, name="role_list"),
    path("funcionarios/", views.employee_list, name="employee_list"),
    path("delegaciones/", views.delegation_list, name="delegation_list"),
    path("cargos-funciones/", views.position_list, name="position_list"),
]