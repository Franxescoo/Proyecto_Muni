from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path(
        "manage/",
        views.access_home,
        name="access_home",
    ),

    # Grupos y permisos
    path(
        "groups/add/",
        views.group_form,
        name="group_create",
    ),
    path(
        "groups/<int:pk>/edit/",
        views.group_form,
        name="group_edit",
    ),

    # Cargos
    path(
        "positions/add/",
        views.position_form,
        name="position_create",
    ),
    path(
        "positions/<int:pk>/edit/",
        views.position_form,
        name="position_edit",
    ),

    # Funcionarios
    path(
        "employees/add/",
        views.employee_form,
        name="employee_create",
    ),
    path(
        "employees/<int:pk>/edit/",
        views.employee_form,
        name="employee_edit",
    ),

    # Cuentas de usuario
    path(
        "users/add/",
        views.account_create,
        name="account_create",
    ),
    path(
        "users/<int:pk>/edit/",
        views.account_edit,
        name="account_edit",
    ),

    # Vinculación de perfiles existentes
    path(
        "profiles/<int:pk>/link/",
        views.profile_link,
        name="profile_link",
    ),
]