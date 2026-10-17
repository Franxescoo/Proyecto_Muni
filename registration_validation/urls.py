
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
    AttentionTypeCreateView,
    AttentionTypeDeleteView,
    AttentionTypeListView,
    AttentionTypeUpdateView,
    SubAttentionCreateView,
    SubAttentionDeleteView,
    SubAttentionListView,
    SubAttentionUpdateView,
    AttentionEntryCreateView,
    AttentionEntryDeleteView,
    AttentionEntryListView,
    AttentionEntryUpdateView,
    set_page_size,
)


app_name = "registration"


urlpatterns = [
    # -----------------------------------------------------
    # Preferencias de paginación
    # -----------------------------------------------------
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

    # -----------------------------------------------------
    # Tipo de Atención
    # -----------------------------------------------------
    path(
        "attention-types/",
        AttentionTypeListView.as_view(),
        name="attention_type_list",
    ),
    path(
        "attention-types/new/",
        AttentionTypeCreateView.as_view(),
        name="attention_type_create",
    ),
    path(
        "attention-types/<int:attention_type_id>/edit/",
        AttentionTypeUpdateView.as_view(),
        name="attention_type_update",
    ),
    path(
        "attention-types/<int:attention_type_id>/delete/",
        AttentionTypeDeleteView.as_view(),
        name="attention_type_delete",
    ),

    # -----------------------------------------------------
    # Sub Atención
    # -----------------------------------------------------
    path(
        "sub-attentions/",
        SubAttentionListView.as_view(),
        name="sub_attention_list",
    ),
    path(
        "sub-attentions/new/",
        SubAttentionCreateView.as_view(),
        name="sub_attention_create",
    ),
    path(
        "sub-attentions/<int:sub_attention_id>/edit/",
        SubAttentionUpdateView.as_view(),
        name="sub_attention_update",
    ),
    path(
        "sub-attentions/<int:sub_attention_id>/delete/",
        SubAttentionDeleteView.as_view(),
        name="sub_attention_delete",
    ),

    # -----------------------------------------------------
    # Ingreso de Atención - NUEVO
    # -----------------------------------------------------
    path(
        "attention-entries/",
        AttentionEntryListView.as_view(),
        name="attention_entry_list",
    ),
    path(
        "attention-entries/new/",
        AttentionEntryCreateView.as_view(),
        name="attention_entry_create",
    ),
    path(
        "attention-entries/<int:attention_entry_id>/edit/",
        AttentionEntryUpdateView.as_view(),
        name="attention_entry_update",
    ),
    path(
        "attention-entries/<int:attention_entry_id>/delete/",
        AttentionEntryDeleteView.as_view(),
        name="attention_entry_delete",
    ),
]
