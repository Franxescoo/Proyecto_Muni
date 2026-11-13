"""Capturas de auditoría sin contraseñas ni secretos (Empleado + Cuenta integrados)."""
from accounts.models import UserProfile
from .models import EmployeeHistory


def employee_snapshot(employee):
    if employee is None or not employee.pk:
        return {}
    profile = (UserProfile.objects.filter(employee_id=employee.pk, deleted_at__isnull=True)
               .select_related("user").first())
    return {
        "name": employee.name or "",
        "rut": employee.rut or "",
        "address": employee.address or "",
        "delegation": employee.delegation.name if employee.delegation_id else "",
        "position": employee.position.position_name if employee.position_id else "",
        "roles": employee.roles or "",
        "status": employee.status or "",
        "archived": "Sí" if employee.deleted_at else "No",
        "photo": employee.profile_photo.name if employee.profile_photo else "",
        "username": profile.user.username if profile else "",
        "email": profile.user.email if profile else "",
        "account_active": "Sí" if profile and profile.user.is_active else "No",
        "authorized_delegations": ", ".join(sorted(
            profile.authorized_delegations.values_list("name", flat=True)
        )) if profile else "",
        "assigned_groups": ", ".join(sorted(
            employee.assigned_groups.values_list("name", flat=True)
        )),
    }


def record_employee_change(employee, actor, event, previous):
    employee.refresh_from_db()
    current = employee_snapshot(employee)
    if previous == current and event != "Creación":
        return None
    return EmployeeHistory.objects.create(
        employee=employee, actor=actor, event=event,
        previous_value=previous, new_value=current,
    )


# Las acciones realizadas por el funcionario comparten la tabla de historial
# existente, pero se distinguen de los cambios recibidos por su prefijo.
ACTION_PREFIX = "Acción: "


def organization_snapshot(instance):
    """Solo datos operativos auditables; no serializar usuarios ni secretos."""
    from django.contrib.auth.models import Group
    from .models import Delegation, Employee, PositionFunction

    if instance is None or not instance.pk:
        return {}
    if isinstance(instance, Employee):
        return employee_snapshot(instance)
    if isinstance(instance, Delegation):
        return {
            "Nombre": instance.name, "Código": instance.code or "",
            "Dirección": instance.address, "Comuna": instance.commune,
            "Estado": instance.status, "Ámbito": instance.scope,
            "Responsable": instance.responsible.name if instance.responsible_id else "",
            "Archivado": "Sí" if instance.deleted_at else "No",
        }
    if isinstance(instance, PositionFunction):
        return {
            "Nombre": instance.position_name,
            "Funciones medibles": instance.measurable_items,
            "Servicios": instance.services, "Ponderaciones": instance.weightings,
            "Vigencia inicio": str(instance.validity_start),
            "Vigencia fin": str(instance.validity_end),
            "Roles asociados": ", ".join(sorted(instance.role_groups.values_list("name", flat=True)))
            if hasattr(instance, "role_groups") else (instance.group.name if instance.group_id else ""),
            "Ítems del catálogo": ", ".join(sorted(instance.catalog_items.values_list("name", flat=True))),
            "Servicios del catálogo": ", ".join(sorted(instance.catalog_services.values_list("name", flat=True))),
            "Archivado": "Sí" if instance.deleted_at else "No",
        }
    if isinstance(instance, Group):
        from .models import OrganizationRole
        role = OrganizationRole.objects.filter(group=instance).first()
        return {
            "Nombre": instance.name,
            "Descripción": role.description if role else "",
            "Permisos": ", ".join(sorted(
                f"{p.content_type.app_label}.{p.codename}"
                for p in instance.permissions.select_related("content_type")
            )),
        }
    raise TypeError("Entidad de Organización no admitida para auditoría")


def record_organization_action(actor, section, operation, instance, previous=None):
    """Asocia la acción al empleado que inició sesión, no a quien recibió el cambio."""
    if not actor or not actor.is_authenticated:
        return None
    profile = (UserProfile.objects.filter(
        user=actor, deleted_at__isnull=True, employee__isnull=False
    ).select_related("employee").first())
    if profile is None:
        # Cuentas sin empleado vinculado no tienen ficha en Organización > Empleados.
        return None
    current = organization_snapshot(instance) if operation != "Eliminó" else {}
    previous = previous or {}
    if operation == "Modificó" and current == previous:
        return None
    # Metadatos iguales a ambos lados para visualizar identidad del objeto.
    descriptor = f"{section}: {instance} (ID {instance.pk})"
    return EmployeeHistory.objects.create(
        employee=profile.employee, actor=actor,
        event=f"{ACTION_PREFIX}{operation} {section}"[:70],
        previous_value={"__target": descriptor, **previous},
        new_value={"__target": descriptor, **current},
    )
