from django.urls import path

from . import views

app_name = "organization"

urlpatterns = [
    path("employees/", views.employee_list, name="employee_list"),
    path("employees/add/", views.employee_create, name="employee_create"),
    path("employees/<int:pk>/edit/", views.employee_edit, name="employee_edit"),
    path("delegations/", views.delegation_list, name="delegation_list"),
    path("delegations/add/", views.delegation_create, name="delegation_create"),
    path("delegations/<int:pk>/edit/", views.delegation_edit, name="delegation_edit"),
    path("positions/", views.position_list, name="position_list"),
    path("positions/add/", views.position_create, name="position_create"),
    path("positions/<int:pk>/edit/", views.position_edit, name="position_edit"),
]
