"""Etiquetas de lectura para permisos de Django (no modifica sus códigos)."""
from django import forms

APP_NAMES = {
    "accounts": "Cuentas",
    "municipal_events": "Eventos y campañas",
    "citizen_requests": "Solicitudes ciudadanas",
    "organization": "Organización",
    "planning_measurements": "Planificación y medición",
    "registration_validation": "Registro y validación",
    "monitoring_traceability": "Monitoreo y trazabilidad",
}
MODEL_NAMES = {
    "municipalevent": "Eventos municipales",
    "eventedition": "Ediciones anuales",
    "campaign": "Campañas municipales",
    "beneficiary": "Beneficiarios",
    "enrollment": "Inscripciones a campañas",
    "giftdelivery": "Entregas de regalos",
    "campaignaudit": "Historial de campañas",
    "delegation": "Delegaciones",
    "delegationresponsibilitylog": "Historial de responsables de delegación",
    "employee": "Empleados",
    "organizationrole": "Roles y permisos",
    "positionfunction": "Cargos y funciones",
    "userprofile": "Perfiles de usuario",
    "period": "Períodos",
    "goal": "Metas",
    "measurementitem": "Ítems de medición",
    "activity": "Actividades",
    "activitytype": "Tipos de actividad",
    "evidence": "Evidencias",
    "validation": "Validaciones",
    "service": "Servicios",
    "attentiontype": "Tipos de atención",
    "subattention": "Subatenciones",
    "attentionentry": "Atenciones ciudadanas",
    "indicator": "Indicadores",
    "commitment": "Compromisos",
    "audit": "Auditorías",
    "comment": "Comentarios",
    "commitmentcomment": "Comentarios de compromisos",
    "citizenrequest": "Solicitudes ciudadanas",
    "requestevent": "Historial de solicitudes",
    "passwordrecoverycode": "Códigos de recuperación",
    "periodarchivelog": "Historial de archivado de períodos",
}
ACTIONS = {
    "add": "Puede crear",
    "change": "Puede modificar",
    "delete": "Puede eliminar",
    "view": "Puede consultar",
}
SPECIAL = {
    "delete_closed_period": "Puede eliminar períodos cerrados",
    "derivar_solicitud": "Puede derivar solicitudes ciudadanas",
}

CATALOG_MODELS = {
    "municipal_events": {
        "municipalevent", "eventedition", "campaign", "enrollment", "giftdelivery",
    },
    "accounts": {
        "userprofile",
    },
    "citizen_requests": {
        "citizenrequest",
    },
    "organization": {
        "delegation",
        "employee",
        "organizationrole",
        "positionfunction",
    },
    "planning_measurements": {
        "goal",
        "measurementitem",
        "period",
    },
    "registration_validation": {
        "activity",
        "activitytype",
        "attentionentry",
        "attentiontype",
        "evidence",
        "evidencefile",
        "service",
        "subattention",
        "validation",
    },
    "monitoring_traceability": {
        "activity",
        "audit",
        "commitment",
        "commitmentcomment",
        "evidence",
        "indicator",
    },
}

CATALOG_ACTIONS = {
    ("municipal_events", "municipalevent"): {"delete_municipalevent", "add_municipalevent", "change_municipalevent", "view_municipalevent"},
    ("municipal_events", "eventedition"): {"delete_eventedition", "add_eventedition", "change_eventedition"},
    ("municipal_events", "campaign"): {"delete_campaign", "add_campaign", "change_campaign", "view_campaign"},
    ("municipal_events", "enrollment"): {"add_enrollment", "change_enrollment", "view_enrollment"},
    ("municipal_events", "giftdelivery"): {"add_giftdelivery", "view_giftdelivery"},
    ("citizen_requests", "citizenrequest"): {"derivar_solicitud"},
    ("monitoring_traceability", "activity"): {
        "add_activity",
        "change_activity",
        "delete_activity",
        "view_activity",
    },
    ("monitoring_traceability", "evidence"): {
        "add_evidence",
        "change_evidence",
        "delete_evidence",
        "view_evidence",
    },
    ("monitoring_traceability", "commitment"): {"view_commitment"},
    ("monitoring_traceability", "indicator"): {"view_indicator"},
    ("monitoring_traceability", "audit"): {"view_audit"},
    ("monitoring_traceability", "commitmentcomment"): {
        "add_commitmentcomment",
        "delete_commitmentcomment",
    },
}


def catalog_permission_queryset(queryset):
    """Return only permissions backed by real application operations."""
    from django.db.models import Q

    permission_filter = Q()
    for app_label, models in CATALOG_MODELS.items():
        for model in models:
            actions = CATALOG_ACTIONS.get((app_label, model))
            model_filter = Q(
                content_type__app_label=app_label,
                content_type__model=model,
            )
            if actions is not None:
                model_filter &= Q(codename__in=actions)
            permission_filter |= model_filter

    return queryset.filter(permission_filter).order_by(
        "content_type__app_label",
        "content_type__model",
        "codename",
    )


def permission_label(permission):
    app = APP_NAMES.get(permission.content_type.app_label, permission.content_type.app_label)
    model = MODEL_NAMES.get(permission.content_type.model)
    if model is None:
        model = permission.content_type.name.capitalize()
    action = SPECIAL.get(permission.codename)
    if action is None:
        for prefix, verb in ACTIONS.items():
            if permission.codename.startswith(prefix + "_"):
                action = f"{verb} {model.lower()}"
                break
    if action is None:
        action = permission.name
    return f"{app} | {model} | {action}"


class SpanishPermissionMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        return permission_label(obj)
