from django.urls import path

from . import views

app_name = "planning"

urlpatterns = [
    path("", views.index, name="index"),
    path("preferences/page-size/", views.set_page_size, name="set_page_size"),
    # Períodos
    path("periods/", views.period_list, name="period_list"),
    path("periods/add/", views.period_create, name="period_create"),
    path("periods/<int:period_id>/", views.period_edit, name="period_edit"),
    path("periods/<int:period_id>/delete/", views.period_delete, name="period_delete"),
    path(
        "periods/<int:period_id>/assign-goals/",
        views.period_assign_existing_goals,
        name="period_assign_existing_goals",
    ),
    # Metas
    path("goals/", views.goal_list, name="goal_list"),
    path("goals/add/", views.goal_create, name="goal_create"),
    path("goals/<int:goal_id>/", views.goal_edit, name="goal_edit"),
    path("goals/<int:goal_id>/delete/", views.goal_delete, name="goal_delete"),
    
    # ---------- CATÁLOGO DE ÍTEMS ----------

    path("items/", views.item_list, name="item_list"),
    path("items/create/", views.item_create, name="item_create"),
    path("items/<int:item_id>/", views.item_detail, name="item_detail"),
    path("items/<int:item_id>/edit/", views.item_edit, name="item_edit"),
    path("items/<int:item_id>/delete/", views.item_delete, name="item_delete"),


]

