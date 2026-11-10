from django.urls import path
from . import views
app_name = "citizen_registry"
urlpatterns = [
    path("", views.citizen_list, name="list"),
    path("crear/", views.citizen_create, name="create"),
    path("<int:pk>/modificar/", views.citizen_edit, name="edit"),
    path("<int:pk>/detalle/", views.citizen_detail, name="detail"),
    path("<int:pk>/desactivar/", views.citizen_deactivate, name="deactivate"),
    path("<int:pk>/reactivar/", views.citizen_reactivate, name="reactivate"),
    path("buscar-rut/", views.citizen_lookup, name="lookup"),
    path("solicitud/<int:pk>/vincular/", views.citizen_link_request, name="link_request"),
]
