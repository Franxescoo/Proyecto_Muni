from .models import UserProfile
from django.db import transaction



def sync_profile(profile):
    if not profile.employee_id:
        return

    delegation_id = profile.employee.delegation_id

    if profile.delegation_id != delegation_id:
        UserProfile.objects.filter(pk=profile.pk).update(
            delegation_id=delegation_id
        )


def sync_employee(employee):
    profiles = UserProfile.objects.filter(
        employee=employee
    ).select_related("employee", "user")

    for profile in profiles:
        profile.user.groups.set(employee.assigned_groups.all())
        sync_profile(profile)


def sync_user_groups(user):
    profile = UserProfile.objects.filter(
        user=user,
    ).select_related("employee").first()
    if profile and profile.employee_id:
        profile.employee.assigned_groups.set(user.groups.all())


def sync_position(position):
    profiles = UserProfile.objects.filter(
        employee__position=position
    ).select_related("employee")

    for profile in profiles:
        sync_profile(profile)



@transaction.atomic
def create_user_account(form):
    """Crea una cuenta y hereda los roles del funcionario."""

    # Crear la cuenta con su contraseña protegida.
    user = form.save(commit=False)

    # Una cuenta normal no tendrá acceso administrativo.
    user.is_staff = False
    user.is_superuser = False
    user.save()

    # Obtener el funcionario seleccionado.
    employee = form.cleaned_data["employee"]

    # Vincular la cuenta al funcionario existente.
    profile = UserProfile.objects.create(
        user=user,
        employee=employee,
        employee_code=form.cleaned_data["employee_code"],
        delegation=employee.delegation,
    )

    # Heredar los roles que ya tiene el funcionario.
    sync_employee(employee)

    return user

