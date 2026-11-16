"""Fuente de permisos: roles asociados al cargo actual del funcionario."""
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import UserProfile


def position_groups(employee):
    """Roles autorizados por el cargo actual; no utiliza los roles de la cuenta."""
    if not employee or not employee.position_id or employee.deleted_at is not None:
        return employee.assigned_groups.none() if employee else None
    if (employee.position.deleted_at is not None
        or employee.status.casefold() not in ("active", "activo")):
        return employee.position.role_groups.none()
    return employee.position.role_groups.all()


def validate_employee_role_scope(employee, delegations):
    """Valida la delegación del empleado; los roles NO tienen delegación propia.

    Los permisos vienen del cargo y su aplicación territorial se limita a las
    delegaciones autorizadas en la CUENTA, nunca a campos antiguos del rol.
    """
    authorized_ids = {delegation.pk for delegation in delegations}
    if employee.delegation_id not in authorized_ids:
        raise ValidationError("Incluye la delegación principal del empleado.")
    for group in position_groups(employee):
        if not hasattr(group, "organization_role"):
            raise ValidationError(
                f"El rol '{group.name}' no fue creado en Roles y Permisos."
            )


def sync_profile(profile):
    """La delegación principal se valida y actualiza en los formularios."""
    return


@transaction.atomic
def sync_user_groups(user):
    """El cargo reemplaza TODOS los grupos del usuario vinculado y del empleado."""
    profile = (UserProfile.objects.select_related("employee__position")
        .filter(user=user, deleted_at__isnull=True).first())
    if not profile or not profile.employee_id:
        return  # Las cuentas sin empleado conservan su configuración independiente.
    employee = profile.employee
    delegations = list(profile.authorized_delegations.all())
    if not delegations and profile.delegation_id:
        delegations = [profile.delegation]
    validate_employee_role_scope(employee, delegations)
    group_ids = list(position_groups(employee).values_list("pk", flat=True))
    # Eliminar permisos individuales previos evita excepciones al esquema por cargo.
    user.user_permissions.clear()
    user.groups.set(group_ids)
    employee.assigned_groups.set(group_ids)
    for attr in ("_perm_cache", "_group_perm_cache", "_user_perm_cache"):
        if hasattr(user, attr):
            delattr(user, attr)


@transaction.atomic
def sync_employee(employee):
    # Un empleado sin cuenta también debe mostrar los roles de su cargo.
    group_ids = list(position_groups(employee).values_list("pk", flat=True))
    employee.assigned_groups.set(group_ids)
    profiles = UserProfile.objects.filter(
        employee=employee, deleted_at__isnull=True
    ).select_related("user")
    for profile in profiles:
        sync_user_groups(profile.user)


@transaction.atomic
def sync_position(position):
    """Actualiza inmediatamente las cuentas cuando cambian los roles del cargo."""
    from organization.models import Employee
    for employee in Employee.objects.filter(position=position).select_related("position"):
        sync_employee(employee)


@transaction.atomic
def create_user_account(form):
    """Crear cuenta; si tiene empleado, manda el cargo y nunca el formulario."""
    user = form.save(commit=False)
    user.is_staff = False
    user.is_superuser = False
    user.save()
    employee = form.cleaned_data.get("employee")
    delegations = form.cleaned_data["authorized_delegations"]
    delegation = employee.delegation if employee else delegations.first()
    profile = UserProfile.objects.create(
        user=user, employee=employee,
        employee_code=form.cleaned_data["employee_code"],
        delegation=delegation,
        profile_photo=form.cleaned_data.get("profile_photo"),
    )
    profile.authorized_delegations.set(delegations)
    if employee:
        sync_user_groups(user)
    else:
        user.groups.set(form.cleaned_data.get("groups") or [])
    return user
