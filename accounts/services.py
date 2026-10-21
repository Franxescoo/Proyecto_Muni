
from django.db import transaction

from .models import UserProfile


def sync_profile(profile):
    """Mantiene sincronizada la delegación del perfil."""

    if not profile.employee_id:
        return

    delegation_id = profile.employee.delegation_id

    if profile.delegation_id != delegation_id:
        UserProfile.objects.filter(pk=profile.pk).update(
            delegation_id=delegation_id
        )


def sync_employee(employee):
    """
    El Usuario controla los roles.
    El Funcionario recibe los roles del Usuario vinculado.
    """

    profiles = UserProfile.objects.filter(
        employee=employee,
        deleted_at__isnull=True,
    ).select_related("employee", "user")

    for profile in profiles:
        sync_user_groups(profile.user)
        sync_profile(profile)


def sync_user_groups(user):
    """
    Copia los roles del Usuario al Funcionario vinculado.
    Nunca sobrescribe los roles del Usuario.
    """

    profile = UserProfile.objects.filter(
        user=user,
        deleted_at__isnull=True,
    ).select_related("employee").first()

    if profile and profile.employee_id:
        profile.employee.assigned_groups.set(
            user.groups.all()
        )


def sync_position(position):
    """Sincroniza los perfiles asociados a un cargo."""

    profiles = UserProfile.objects.filter(
        employee__position=position
    ).select_related("employee")

    for profile in profiles:
        sync_profile(profile)


@transaction.atomic
def create_user_account(form):
    """
    Crea el Usuario con sus roles.
    El Funcionario puede vincularse posteriormente.
    """

    # Crear el Usuario con su contraseña protegida.
    user = form.save(commit=False)

    user.is_staff = False
    user.is_superuser = False
    user.save()

    # Obtener los datos seleccionados.
    employee = form.cleaned_data.get("employee")
    delegation = form.cleaned_data["delegation"]

    # Crear el perfil, con o sin Funcionario.
    UserProfile.objects.create(
        user=user,
        employee=employee,
        employee_code=form.cleaned_data["employee_code"],
        delegation=delegation,
    )

    # Guardar los roles seleccionados en Usuarios.
    user.groups.set(
        form.cleaned_data["groups"]
    )

    # Reflejar esos roles en el Funcionario, si existe.
    sync_user_groups(user)

    return user


