"""Etiquetas de lectura para permisos de Django (no modifica sus códigos)."""
from django import forms

APP_NAMES = {
    "accounts": "Cuentas",
    "organization": "Organización",
    "planning_measurements": "Planificación y medición",
    "registration_validation": "Registro y validación",
    "monitoring_traceability": "Monitoreo y trazabilidad",
}
MODEL_NAMES = {
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
}
ACTIONS = {
    "add": "Puede crear",
    "change": "Puede modificar",
    "delete": "Puede eliminar",
    "view": "Puede consultar",
}
SPECIAL = {
    "delete_closed_period": "Puede eliminar períodos cerrados (permiso individual)",
}


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
