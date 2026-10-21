
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
    ActivityTypeCreateView,
    ActivityTypeDeleteView,
    ActivityTypeListView,
    ActivityTypeUpdateView,
    ServiceListView,
    ServiceCreateView,
    ServiceUpdateView,
    ServiceDeleteView,
    set_page_size,
    attention_type_export,
    sub_attention_export,
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
    # Servicios
    # -----------------------------------------------------

    path(
        "services/",
        ServiceListView.as_view(),
        name="service_list",
    ),

    path(
        "services/new/",
        ServiceCreateView.as_view(),
        name="service_create",
    ),

    path(
        "services/<int:service_id>/edit/",
        ServiceUpdateView.as_view(),
        name="service_update",
    ),

    path(
        "services/<int:service_id>/delete/",
        ServiceDeleteView.as_view(),
        name="service_delete",
    ),
    # -----------------------------------------------------
    # Tipos de actividad
    # -----------------------------------------------------

    path(
        "activity-types/",
        ActivityTypeListView.as_view(),
        name="activity_type_list",
    ),

    path(
        "activity-types/new/",
        ActivityTypeCreateView.as_view(),
        name="activity_type_create",
    ),

    path(
        "activity-types/<int:activity_type_id>/edit/",
        ActivityTypeUpdateView.as_view(),
        name="activity_type_update",
    ),

    path(
        "activity-types/<int:activity_type_id>/delete/",
        ActivityTypeDeleteView.as_view(),
        name="activity_type_delete",
    ),

    # -----------------------------------------------------
    # Tipo de Atención
    # -----------------------------------------------------
    path("attention-types/exportar/", attention_type_export, name="attention_type_export"),
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
    path("sub-attentions/exportar/", sub_attention_export, name="sub_attention_export"),
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
