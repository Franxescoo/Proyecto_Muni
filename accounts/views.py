from functools import wraps

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from organization.models import Employee, PositionFunction

from .forms import (
    AccountCreateForm,
    AccountEditForm,
    EmployeeForm,
    PositionForm,
    ProfileLinkForm,
)
from .models import UserProfile
from .models import PasswordRecoveryCode
from .recovery import create_recovery_code, send_recovery_code, valid_recovery_code
from .recovery_forms import (
    RecoveryCodeForm,
    RecoveryPasswordForm,
    RecoveryRequestForm,
)
from .services import (
    sync_employee,
    sync_position,
    sync_profile,
    sync_user_groups,
)
from .services import create_user_account


RECOVERY_SESSION_KEY = "password_recovery_code_id"
RECOVERY_VERIFIED_SESSION_KEY = "password_recovery_verified"


def password_reset_request(request):
    form = RecoveryRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.find_user()
        if user is not None and user.email:
            recovery, code = create_recovery_code(user)
            send_recovery_code(request, user, code)
            request.session[RECOVERY_SESSION_KEY] = recovery.pk
            return redirect("password_reset_verify")
        return redirect("password_reset_done")

    return render(
        request,
        "registration/password_reset_form.html",
        {"form": form},
    )


def password_reset_verify(request):
    recovery_id = request.session.get(RECOVERY_SESSION_KEY)
    if not recovery_id:
        return redirect("password_reset")

    recovery = get_object_or_404(
        PasswordRecoveryCode.objects.select_related("user"),
        pk=recovery_id,
    )
    form = RecoveryCodeForm(request.POST or None)
    if request.method == "POST":
        if not valid_recovery_code(recovery, request.POST.get("code", "")):
            form.add_error("code", "El código es incorrecto o ya expiró.")
        elif form.is_valid():
            request.session[RECOVERY_VERIFIED_SESSION_KEY] = True
            return redirect("password_reset_password")

    return render(
        request,
        "registration/password_reset_verify.html",
        {"form": form, "expires_at": recovery.expires_at},
    )


def password_reset_password(request):
    recovery_id = request.session.get(RECOVERY_SESSION_KEY)
    if not request.session.get(RECOVERY_VERIFIED_SESSION_KEY) or not recovery_id:
        return redirect("password_reset")

    recovery = get_object_or_404(
        PasswordRecoveryCode.objects.select_related("user"),
        pk=recovery_id,
    )
    if recovery.expires_at <= timezone.now() or recovery.used_at is not None:
        request.session.pop(RECOVERY_SESSION_KEY, None)
        request.session.pop(RECOVERY_VERIFIED_SESSION_KEY, None)
        return redirect("password_reset")

    form = RecoveryPasswordForm(recovery.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            locked = PasswordRecoveryCode.objects.select_for_update().get(
                pk=recovery.pk,
            )
            if locked.used_at is not None or locked.expires_at <= timezone.now():
                form.add_error(
                    None,
                    "El código ha expirado. Solicita uno nuevo.",
                )
            else:
                user = locked.user
                user.set_password(form.cleaned_data["new_password1"])
                user.save(update_fields=["password"])
                locked.used_at = timezone.now()
                locked.save(update_fields=["used_at"])
                request.session.pop(RECOVERY_SESSION_KEY, None)
                request.session.pop(RECOVERY_VERIFIED_SESSION_KEY, None)
                return redirect("login")

    return render(
        request,
        "registration/password_reset_password.html",
        {"form": form},
    )


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
    """Muestra grupos, cargos, empleados y cuentas."""

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
    """Envía la gestión de roles al espacio dedicado de Organización."""
    url = reverse("organization:role_list")
    if pk is not None:
        return redirect(f"{url}?modal=edit&id={pk}")
    return redirect(f"{url}?modal=create")


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
    """Crea o edita un empleado y sincroniza su delegación."""

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
        "Editar empleado" if pk is not None else "Crear empleado",
        on_save=sync_employee,
    )



@administrator_required
def account_create(request):
    """Crea una cuenta heredando los roles del empleado."""

    form = AccountCreateForm(
        request.POST if request.method == "POST" else None
    )

    if request.method == "POST" and form.is_valid():
        try:
            create_user_account(form)

        except IntegrityError:
            form.add_error(
                None,
                "No se pudo crear la cuenta. "
                "El usuario, código o empleado "
                "podría estar registrado."
            )

        else:
            messages.success(
                request,
                "Cuenta creada correctamente."
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
        profile__isnull=False,
        profile__deleted_at__isnull=True,
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


def sync_profile_access(profile):
    sync_profile(profile)
    if profile.employee_id:
        sync_employee(profile.employee)


@administrator_required
def profile_link(request, pk):
    """Vincula un perfil existente con un empleado."""

    profile = get_object_or_404(
        UserProfile,
        pk=pk,
        deleted_at__isnull=True,
    )

    form = ProfileLinkForm(
        request.POST if request.method == "POST" else None,
        request.FILES if request.method == "POST" else None,
        instance=profile,
    )

    return save_model_form(
        request,
        form,
        f"Vincular cuenta: {profile.user.username}",
        on_save=sync_profile_access,
    )