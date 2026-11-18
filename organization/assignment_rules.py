"""Validaciones para nuevas asignaciones; se conservan las referencias históricas.
No se alteran permisos ni roles heredados del cargo.
"""


def delegation_available(delegation):
    return bool(delegation and delegation.deleted_at is None and
                str(delegation.status).casefold() in ("active", "activo"))


def position_available(position):
    return bool(position and position.deleted_at is None)


def validate_employee_assignment(form, delegation, position, previous=None):
    """Editar sin cambiar un vínculo antiguo está permitido; crear uno nuevo no."""
    old_delegation = getattr(previous, "delegation_id", None)
    old_position = getattr(previous, "position_id", None)
    if delegation and delegation.pk != old_delegation and not delegation_available(delegation):
        form.add_error("delegation", "No puedes asignar una delegación inactiva o archivada.")
    if position and position.pk != old_position and not position_available(position):
        form.add_error("position", "No puedes asignar un cargo archivado.")


def validate_delegation_authorizations(form, delegations, previous_ids=()):
    """Impide autorizaciones nuevas a delegaciones inactivas o archivadas."""
    old_ids = set(previous_ids)
    for delegation in delegations or ():
        if delegation.pk not in old_ids and not delegation_available(delegation):
            form.add_error("authorized_delegations",
                           "No puedes agregar delegaciones inactivas o archivadas.")
            break
