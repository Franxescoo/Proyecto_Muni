from functools import wraps

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render

from organization.models import Employee, PositionFunction

from .forms import (
    AccountCreateForm,
    AccountEditForm,
    EmployeeForm,
    GroupForm,
    PositionForm,
    ProfileLinkForm,
)
from .models import UserProfile
from .services import sync_employee, sync_position, sync_profile


def administrator_required(view):
    """Restringe la gestión de accesos al superusuario."""

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_superuser:
            raise PermissionDenied(
                "Solo el administrador puede gestionar accesos."
            )

        return view(request, *args, **kwargs)

    return login_required(wrapped)


@administrator_required
def access_home(request):
    """Muestra grupos, cargos, funcionarios y cuentas."""

    return render(
        request,
        "accounts/access_home.html",
        {
            "groups": Group.objects.order_by("name"),
            "positions": PositionFunction.objects.filter(
                deleted_at__isnull=True
            ).order_by("position_name"),
            "employees": (
                Employee.objects.filter(
                    deleted_at__isnull=True
                )
                .select_related("position", "delegation")
                .order_by("name")
            ),
            "profiles": (
                UserProfile.objects.filter(
                    deleted_at__isnull=True
                )
                .select_related("user", "employee")
                .order_by("user__username")
            ),
            "users": get_user_model().objects.filter(
                is_superuser=False
            ).order_by("username"),
        },
    )


def save_model_form(request, form, title, on_save=None):
    """Guarda el formulario y sus relaciones en una transacción."""

    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                obj = form.save()

                if on_save:
                    on_save(obj)

        except IntegrityError:
            form.add_error(
                None,
                "No se pudo guardar. Revisa si otra operación "
                "registró los mismos datos."
            )
        else:
            messages.success(
                request,
                "Datos guardados correctamente."
            )
            return redirect("accounts:access_home")

    return render(
        request,
        "accounts/manage_form.html",
        {
            "form": form,
            "title": title,
        },
    )


@administrator_required
def group_form(request, pk=None):
    """Crea o edita un grupo y sus permisos."""

    group = (
        get_object_or_404(Group, pk=pk)
        if pk is not None
        else None
    )

    form = GroupForm(
        request.POST if request.method == "POST" else None,
        instance=group,
    )

    return save_model_form(
        request,
        form,
        "Editar grupo" if pk is not None else "Crear grupo",
    )


@administrator_required
def position_form(request, pk=None):
    """Crea o edita un cargo, sin cambiar grupos de las cuentas."""

    position = (
        get_object_or_404(
            PositionFunction,
            pk=pk,
            deleted_at__isnull=True,
        )
        if pk is not None
        else None
    )

    form = PositionForm(
        request.POST if request.method == "POST" else None,
        instance=position,
    )

    return save_model_form(
        request,
        form,
        "Editar cargo" if pk is not None else "Crear cargo",
        on_save=sync_position,
    )


@administrator_required
def employee_form(request, pk=None):
    """Crea o edita un funcionario y sincroniza su delegación."""

    employee = (
        get_object_or_404(
            Employee,
            pk=pk,
            deleted_at__isnull=True,
        )
        if pk is not None
        else None
    )

    form = EmployeeForm(
        request.POST if request.method == "POST" else None,
        instance=employee,
    )

    return save_model_form(
        request,
        form,
        "Editar funcionario" if pk is not None else "Crear funcionario",
        on_save=sync_employee,
    )


@administrator_required
def account_create(request):
    """Crea una cuenta y asigna los grupos elegidos."""

    form = AccountCreateForm(
        request.POST if request.method == "POST" else None
    )

    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                user = form.save(commit=False)

                # No permite crear superusuarios ni acceso al panel admin.
                user.is_staff = False
                user.is_superuser = False
                user.save()

                user.groups.set(form.cleaned_data["groups"])

                employee = form.cleaned_data["employee"]

                profile = UserProfile.objects.create(
                    user=user,
                    employee=employee,
                    employee_code=form.cleaned_data["employee_code"],
                    delegation=employee.delegation,
                )

                sync_profile(profile)

        except IntegrityError:
            form.add_error(
                None,
                "No se pudo crear la cuenta. El usuario, "
                "el código o el funcionario podrían estar "
                "registrados."
            )
        else:
            messages.success(
                request,
                "Cuenta creada con los grupos seleccionados."
            )
            return redirect("accounts:access_home")

    return render(
        request,
        "accounts/manage_form.html",
        {
            "form": form,
            "title": "Crear cuenta",
        },
    )


@administrator_required
def account_edit(request, pk):
    """Edita una cuenta de trabajador y sus grupos."""

    user = get_object_or_404(
        get_user_model(),
        pk=pk,
        is_superuser=False,
    )

    form = AccountEditForm(
        request.POST if request.method == "POST" else None,
        instance=user,
    )

    return save_model_form(
        request,
        form,
        f"Editar cuenta: {user.username}",
    )


@administrator_required
def profile_link(request, pk):
    """Vincula un perfil existente con un funcionario."""

    profile = get_object_or_404(
        UserProfile,
        pk=pk,
        deleted_at__isnull=True,
    )

    form = ProfileLinkForm(
        request.POST if request.method == "POST" else None,
        instance=profile,
    )

    return save_model_form(
        request,
        form,
        f"Vincular cuenta: {profile.user.username}",
        on_save=sync_profile,
    )