from django.urls import path

from .views import (
    ActivityCreateView,
    ActivityDeleteView,
    ActivityListView,
    ActivityUpdateView,
    EvidenceCreateView,
    EvidenceDeleteView,
    EvidenceListView,
    EvidenceUpdateView,
)


app_name = "registration"


urlpatterns = [
    # -----------------------------------------------------
    # Activity
    # -----------------------------------------------------
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

    # -----------------------------------------------------
    # Evidence
    # -----------------------------------------------------
    path(
        "evidences/",
        EvidenceListView.as_view(),
        name="evidence_list",
    ),
    path(
        "evidences/new/",
        EvidenceCreateView.as_view(),
        name="evidence_create",
    ),
    path(
        "evidences/<int:evidence_id>/edit/",
        EvidenceUpdateView.as_view(),
        name="evidence_update",
    ),
    path(
        "evidences/<int:evidence_id>/delete/",
        EvidenceDeleteView.as_view(),
        name="evidence_delete",
    ),
]