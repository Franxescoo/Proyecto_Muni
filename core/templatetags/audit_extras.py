
from datetime import date
from django import template

register = template.Library()

NOMBRES = {
    "start_date": "Fecha de inicio",
    "end_date": "Fecha de término",
    "computable_days": "Días computables",
    "status": "Estado",
    "thresholds": "Umbrales",
    "green": "Verde",
    "yellow": "Amarillo",
    "red": "Rojo",
    "parameters_version": "Versión de parámetros",
    "goals": "Metas asociadas",
    "employee_id": "Funcionario (ID)",
    "period_id": "Período (ID)",
    "position_id": "Cargo (ID)",
    "measurement_item_id": "Ítem de medición (ID)",
    "item": "Ítem",
    "objective_value": "Valor objetivo",
    "required_evidence_count": "Evidencias requeridas",
    "unit": "Unidad",
    "weight": "Ponderador",
    "count_completed_commitments": "Contar compromisos completados",
    "name": "Nombre",
    "code": "Código",
    "description": "Descripción",
    "formula": "Fórmula",
    "is_active": "Activo",
    "deleted_at": "Fecha de eliminación",
    "date": "Fecha",
    "observation": "Observación",
    "result": "Resultado",
    "decision": "Decisión",
    "review_status": "Estado de revisión",
    "author_id": "Autor (ID)",
    "verifier_id": "Verificador (ID)",
    "activity_id": "Actividad (ID)",
    "evidence_id": "Evidencia (ID)",
    "permissions": "Permisos (IDs)",
    "authorized_delegations": "Delegaciones autorizadas (IDs)",
    "assigned_groups": "Roles asignados (IDs)",
}

ESTADOS = {
    "ACTIVE": "Activo",
    "CLOSED": "Cerrado",
    "APPROVED": "Aprobado",
    "REJECTED": "Rechazado",
    "PENDING": "Pendiente",
    "COMPLETED": "Completado",
}

CAMPOS_SENSIBLES = {
    "password", "token", "secret",
    "api_key", "secret_key",
}


def normalizar(valor, origen=None):
    if isinstance(valor, dict):
        return {
            NOMBRES.get(k, str(k).replace("_", " ").capitalize()):
                normalizar(v, k)
            for k, v in valor.items()
            if k not in CAMPOS_SENSIBLES
        }

    if origen == "goals" and isinstance(valor, list):
        return {
            f"Meta #{fila.get('id', numero)}": normalizar({
                k: v for k, v in fila.items() if k != "id"
            })
            for numero, fila in enumerate(valor, 1)
            if isinstance(fila, dict)
        }

    return valor


def mostrar_valor(valor):
    if valor is None or valor == "":
        return "—"

    if isinstance(valor, bool):
        return "Sí" if valor else "No"

    if isinstance(valor, list):
        return ", ".join(str(v) for v in valor) if valor else "Ninguno"

    if isinstance(valor, str):
        if valor.upper() in ESTADOS:
            return ESTADOS[valor.upper()]

        try:
            if len(valor) == 10 and valor[4] == "-" and valor[7] == "-":
                return date.fromisoformat(valor).strftime("%d/%m/%Y")
        except ValueError:
            pass

    return str(valor)


def comparar(antes, despues, ruta, cambios):
    if isinstance(antes, dict) or isinstance(despues, dict):
        anterior = antes if isinstance(antes, dict) else {}
        nuevo = despues if isinstance(despues, dict) else {}

        for campo in dict.fromkeys([*anterior, *nuevo]):
            nombre = f"{ruta} / {campo}" if ruta else campo
            comparar(
                anterior.get(campo),
                nuevo.get(campo),
                nombre,
                cambios,
            )
        return

    if antes != despues:
        cambios.append({
            "campo": ruta or "Valor",
            "antes": mostrar_valor(antes),
            "despues": mostrar_valor(despues),
        })


@register.inclusion_tag("shared/_audit_changes.html")
def mostrar_cambios(antes, despues):
    cambios = []

    comparar(
        normalizar(antes),
        normalizar(despues),
        "",
        cambios,
    )

    return {"cambios": cambios}
