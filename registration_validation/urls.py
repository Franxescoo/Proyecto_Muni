from django.urls import path

from .views import (
    ActivityCreateView,
    ActivityDeleteView,
    ActivityListView,
    ActivityUpdateView,
)


app_name = "registration"


urlpatterns = [
    path(
        "activities/",
        ActivityListView.as_view(),
        name="activity_list",
    ),
    path(
        "activities/new/",
        ActivityCreateView.as_view(),
        name="activity_create",
    ),
    path(
        "activities/<int:activity_id>/edit/",
        ActivityUpdateView.as_view(),
        name="activity_update",
    ),
    path(
        "activities/<int:activity_id>/delete/",
        ActivityDeleteView.as_view(),
        name="activity_delete",
    ),
]