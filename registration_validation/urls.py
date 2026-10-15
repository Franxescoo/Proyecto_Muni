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
    ValidationCreateView,
    ValidationDeleteView,
    ValidationListView,
    ValidationUpdateView,
    set_page_size,
)


app_name = "registration"


urlpatterns = [
    path(
        "preferences/page-size/",
        set_page_size,
        name="set_page_size",
    ),
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

    # -----------------------------------------------------
    # Validation
    # -----------------------------------------------------
    path(
        "validations/",
        ValidationListView.as_view(),
        name="validation_list",
    ),
    path(
        "validations/new/",
        ValidationCreateView.as_view(),
        name="validation_create",
    ),
    path(
        "validations/<int:validation_id>/edit/",
        ValidationUpdateView.as_view(),
        name="validation_update",
    ),
    path(
        "validations/<int:validation_id>/delete/",
        ValidationDeleteView.as_view(),
        name="validation_delete",
    ),
]