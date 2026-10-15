from django.urls import path

from . import views

app_name = "organization"

urlpatterns = [
    path("delegations/", views.delegation_list, name="delegation_list"),
    path("delegations/new/", views.delegation_create, name="delegation_create"),
    path("delegations/<int:pk>/", views.delegation_detail, name="delegation_detail"),
    path("delegations/<int:pk>/edit/", views.delegation_update, name="delegation_update"),
    path("delegations/<int:pk>/delete/", views.delegation_delete, name="delegation_delete"),
    path("positions/", views.position_list, name="position_list"),
    path("positions/new/", views.position_create, name="position_create"),
    path("positions/<int:pk>/", views.position_detail, name="position_detail"),
    path("positions/<int:pk>/edit/", views.position_update, name="position_update"),
    path("positions/<int:pk>/delete/", views.position_delete, name="position_delete"),
    path("employees/", views.employee_list, name="employee_list"),
    path("employees/new/", views.employee_create, name="employee_create"),
    path("employees/<int:pk>/", views.employee_detail, name="employee_detail"),
    path("employees/<int:pk>/edit/", views.employee_update, name="employee_update"),
    path("employees/<int:pk>/delete/", views.employee_delete, name="employee_delete"),
]
