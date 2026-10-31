from django.urls import path

from . import views

app_name = "organization"

urlpatterns = [
    path("preferencias/registros-por-pagina/", views.set_page_size, name="set_page_size"),
    path("roles-permisos/", views.role_list, name="role_list"),
    path("empleados/", views.employee_list, name="employee_list"),
    path("funcionarios/", views.employee_list, name="employee_legacy"),
    path("delegaciones/", views.delegation_list, name="delegation_list"),
    path("cargos-funciones/", views.position_list, name="position_list"),
    path("usuarios/", views.user_list, name="user_list"),
    path("delegaciones/exportar/", views.delegation_export, name="delegation_export"),
    path("roles-permisos/exportar/", views.role_export, name="role_export"),
    path("usuarios/exportar/", views.user_export, name="user_export"),
]