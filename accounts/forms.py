
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordResetForm,
    UserCreationForm,
)
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.models import Group, Permission
from organization.permission_labels import (
    SpanishPermissionMultipleChoiceField,
    catalog_permission_queryset,
)
from accounts.permissions import allowed_delegation_ids
from django.db.models import Q
from django.conf import settings
from django.core.exceptions import ValidationError

from organization.models import (
    Delegation,
    Employee,
    PositionFunction,
)

from .models import UserProfile
from registration_validation.models import Service
from planning_measurements.models import MeasurementItem
from organization.validators import normalize_rut


class ProfilePhotoForm(forms.ModelForm):
    """Permite al usuario actualizar únicamente su propia foto de perfil."""

    class Meta:
        model = UserProfile
        fields = ["profile_photo"]
        labels = {"profile_photo": "Nueva foto de perfil"}
        widgets = {
            "profile_photo": forms.ClearableFileInput(
                attrs={"accept": "image/jpeg,image/png,image/webp"}
            ),
        }

    def clean_profile_photo(self):
        photo = self.cleaned_data.get("profile_photo")
        if photo and photo.size > 5 * 1024 * 1024:
            raise ValidationError("La foto no puede superar los 5 MB.")
        return photo


class UsuarioOCorreoAuthenticationForm(AuthenticationForm):
    """Permite iniciar sesión únicamente con RUT o correo institucional."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].max_length = 254
        self.fields["username"].widget.attrs["maxlength"] = 254

    def clean(self):
        identificador = self.cleaned_data.get("username")

        if identificador:
            usuarios = get_user_model()._default_manager
            coincidencias = []
            if "@" in identificador:
                coincidencias = list(
                    usuarios.filter(
                        email__iexact=identificador.strip()
                    ).values_list("username", flat=True)[:2]
                )
            else:
                try:
                    rut = normalize_rut(identificador)
                except forms.ValidationError:
                    rut = None
                if rut:
                    coincidencias = list(
                        usuarios.filter(
                            profile__employee__rut=rut,
                            profile__deleted_at__isnull=True,
                        ).values_list("username", flat=True)[:2]
                    )

            if len(coincidencias) == 1:
                self.cleaned_data["username"] = coincidencias[0]
            else:
                self.add_error(
                    "username",
                    "Ingresa un RUT o correo institucional válido.",
                )

        return super().clean()


class InstitutionalPasswordResetForm(PasswordResetForm):
    """Envía enlaces con el dominio público configurado para cada entorno."""

    def save(self, *, use_https=False, token_generator=None,
             from_email=None, request=None, html_email_template_name=None,
             extra_email_context=None, subject_template_name=None,
             email_template_name="registration/password_reset_email.txt",
             domain_override=None):
        return super().save(
            use_https=use_https or settings.PASSWORD_RESET_USE_HTTPS,
            token_generator=token_generator or default_token_generator,
            from_email=from_email,
            request=request,
            html_email_template_name=(
                html_email_template_name
                or "registration/password_reset_email.html"
            ),
            extra_email_context={
                "site_name": settings.PASSWORD_RESET_SITE_NAME,
                **(extra_email_context or {}),
            },
            subject_template_name=(
                subject_template_name
                or "registration/password_reset_subject.txt"
            ),
            email_template_name=email_template_name,
            domain_override=(
                domain_override or settings.PASSWORD_RESET_DOMAIN
            ),
        )


class BootstrapMixin:
    """Aplica estilos de Bootstrap a los formularios."""

    def apply_bootstrap(self):
        for field in self.fields.values():
            if isinstance(
                field.widget,
                forms.CheckboxSelectMultiple,
            ):
                continue

            if isinstance(field.widget, forms.CheckboxInput):
                css = "form-check-input"
            elif isinstance(field.widget, forms.Select):
                css = "form-select"
            else:
                css = "form-control"

            field.widget.attrs["class"] = css


class GroupForm(BootstrapMixin, forms.ModelForm):
    """Permite crear y editar grupos y sus permisos."""

    permissions = SpanishPermissionMultipleChoiceField(
        label="Permisos",
        queryset=catalog_permission_queryset(
            Permission.objects.all()
        ).select_related("content_type"),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        help_text="Selecciona las acciones permitidas para este grupo.",
    )

    class Meta:
        model = Group
        fields = ["name", "permissions"]
        labels = {
            "name": "Nombre del grupo",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap()


class PositionForm(BootstrapMixin, forms.ModelForm):
    """Gestiona cargos y los roles definidos en Roles y Permisos."""

    class Meta:
        model = PositionFunction
        fields = [
            "position_name",
            "role_groups",
            "catalog_items",
            "catalog_services",
            "weightings",
            "validity_start",
            "validity_end",
        ]
        labels = {
            "position_name": "Nombre del cargo",
            "role_groups": "Roles asociados al cargo",
            "measurable_items": "Ítems medibles",
            "catalog_items": "Ítems de medición",
            "services": "Servicios",
            "catalog_services": "Servicios del catálogo",
            "weightings": "Ponderaciones",
            "validity_start": "Inicio de vigencia",
            "validity_end": "Fin de vigencia",
        }
        widgets = {
            "validity_start": forms.DateInput(
                attrs={"type": "date"},
                format="%Y-%m-%d",
            ),
            "validity_end": forms.DateInput(
                attrs={"type": "date"},
                format="%Y-%m-%d",
            ),
            "catalog_services": forms.CheckboxSelectMultiple(),
            "catalog_items": forms.CheckboxSelectMultiple(),
            "role_groups": forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Solo mostrar roles creados en Roles y Permisos.
        self.fields["role_groups"].queryset = Group.objects.filter(
            organization_role__isnull=False
        ).order_by("name")
        self.fields["role_groups"].required = True
        self.fields["role_groups"].help_text = (
            "Selecciona uno o varios roles existentes. "
            "Los empleados vinculados heredarán automáticamente estos roles."
        )

        # Servicios asociados previamente al cargo.
        selected_ids = (
            list(
                self.instance.catalog_services.values_list(
                    "pk", flat=True
                )
            )
            if self.instance.pk
            else []
        )

        # Mostrar servicios activos y conservar los que
        # ya estaban asociados, aunque estén inactivos.
        available_services = Service.objects.filter(
            Q(status=True, deleted_at__isnull=True)
            | Q(pk__in=selected_ids)
        ).distinct().order_by("name")

        self.fields["catalog_services"].queryset = (
            available_services
        )

        self.fields["catalog_services"].required = False

        self.fields["catalog_services"].help_text = (
            "Puedes seleccionar varios servicios. "
            "Los servicios inactivos no estarán disponibles "
            "para nuevas asignaciones."
        )

        # Ítems que ya están asociados al cargo
        selected_ids = (
            list(
                self.instance.catalog_items.values_list(
                    "pk", flat=True
                )
            )
            if self.instance.pk
            else []
        )

        # Mostrar ítems activos y conservar los históricos
        available_items = MeasurementItem.objects.filter(
            Q(is_active=True, deleted_at__isnull=True)
            | Q(pk__in=selected_ids)
        ).distinct().order_by("code")

        self.fields["catalog_items"].queryset = available_items

        # Obligatorio al crear; permite editar cargos antiguos
        self.fields["catalog_items"].required = not bool(
            self.instance.pk
        )

        self.fields["catalog_items"].label_from_instance = (
            lambda item: f"{item.code} - {item.name}"
        )

        self.apply_bootstrap()

    def save(self, commit=True):

        if self.instance.pk is None:

            selected_services = self.cleaned_data.get(
                "catalog_services"
            )

            self.instance.services = ", ".join(
                service.name
                for service in (selected_services or [])
            )

            selected_items = self.cleaned_data.get(
                "catalog_items"
            )

            self.instance.measurable_items = ", ".join(
                item.name
                for item in (selected_items or [])
            )

        return super().save(commit=commit)


class EmployeeForm(BootstrapMixin, forms.ModelForm):
    """Permite crear y editar funcionarios."""

    class Meta:
        model = Employee
        fields = [
            "name",
            "rut",
            "address",
            "delegation",
            "position",
            "roles",
            "status",
        ]
        labels = {
            "name": "Nombre",
            "rut": "RUT",
            "address": "Dirección",
            "delegation": "Delegación",
            "position": "Cargo",
            "roles": "Descripción de funciones",
            "status": "Estado",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["delegation"].queryset = (
            Delegation.objects.filter(
                deleted_at__isnull=True
            ).order_by("name")
        )

        self.fields["position"].queryset = (
            PositionFunction.objects.filter(
                deleted_at__isnull=True
            ).order_by("position_name")
        )

        self.apply_bootstrap()


def _active_delegations():
    return Delegation.objects.filter(deleted_at__isnull=True).order_by("name")


def _role_scope_valid(groups, delegations):
    """Los roles del catálogo operan solo en las delegaciones de la cuenta.

    No existen delegaciones seleccionables por rol. Conservar esta función
    valida que los grupos provengan del catálogo institucional.
    """
    return all(getattr(group, "organization_role", None) is not None
               for group in groups)


def _restrict_account_actor_choices(form, actor, action):
    """No permitir asignar delegaciones o roles fuera del alcance del administrador."""
    if actor is None or actor.is_superuser:
        return

    scope = allowed_delegation_ids(
        actor, f"accounts.{action}_userprofile", active_only=False,
    )

    form.fields["authorized_delegations"].queryset = form.fields[
        "authorized_delegations"
    ].queryset.filter(pk__in=scope)

    form.fields["employee"].queryset = form.fields["employee"].queryset.filter(
        delegation_id__in=scope
    )

    allowed_permissions = actor.get_all_permissions()
    permitted_groups = []

    for group in form.fields["groups"].queryset.prefetch_related(
        "permissions__content_type"
    ):
        if not hasattr(group, "organization_role"):
            continue
        if any(
            f"{perm.content_type.app_label}.{perm.codename}" not in allowed_permissions
            for perm in group.permissions.all()
        ):
            continue
        permitted_groups.append(group.pk)

    form.fields["groups"].queryset = form.fields["groups"].queryset.filter(
        pk__in=permitted_groups
    )



class AccountCreateForm(BootstrapMixin, UserCreationForm):
    """Crear cuenta, delegaciones y roles sin alterar la delegación del empleado."""

    profile_photo = forms.ImageField(
        label="Foto de perfil",
        required=False,
    )

    employee = forms.ModelChoiceField(
        label="Empleado vinculado (opcional)",
        queryset=Employee.objects.none(),
        required=False,
    )

    employee_code = forms.CharField(
        label="Código de empleado",
        max_length=30,
    )

    authorized_delegations = forms.ModelMultipleChoiceField(
        label="Delegaciones autorizadas",
        queryset=Delegation.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=True,
    )

    groups = forms.ModelMultipleChoiceField(
        label="Roles asignados (automáticos si hay empleado)",
        queryset=Group.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )

    class Meta:
        model = get_user_model()
        fields = [
            "username",
            "first_name",
            "last_name",
            "email",
            "employee",
            "employee_code",
            "authorized_delegations",
            "groups",
            "password1",
            "password2",
        ]
        labels = {
            "username": "Nombre de usuario",
            "first_name": "Nombre",
            "last_name": "Apellidos",
            "email": "Correo",
        }

    def __init__(self, *args, **kwargs):
        self.actor = kwargs.pop("actor", None)
        super().__init__(*args, **kwargs)

        self.fields["employee"].queryset = Employee.objects.filter(
            deleted_at__isnull=True,
            user_profile__isnull=True,
            delegation__deleted_at__isnull=True,
        ).select_related("delegation").order_by("name")

        self.fields["authorized_delegations"].queryset = _active_delegations()

        self.fields["groups"].queryset = Group.objects.filter(
            organization_role__isnull=False
        ).prefetch_related(
            "organization_role__application_delegations"
        ).order_by("name")

        self.fields["email"].required = True
        self.fields["password1"].label = "Contraseña"
        self.fields["password2"].label = "Confirmar contraseña"

        _restrict_account_actor_choices(self, self.actor, "add")
        self.apply_bootstrap()

    def clean_email(self):
        correo = self.cleaned_data["email"].strip()

        if get_user_model()._default_manager.filter(
            email__iexact=correo
        ).exists():
            raise forms.ValidationError(
                "Este correo ya pertenece a otra cuenta."
            )

        return correo

    def clean_employee_code(self):
        code = self.cleaned_data["employee_code"].strip()

        if UserProfile.objects.filter(
            employee_code__iexact=code
        ).exists():
            raise forms.ValidationError(
                "El código ya pertenece a otra cuenta."
            )

        return code

    def clean(self):
        data = super().clean()

        employee = data.get("employee")
        delegations = data.get("authorized_delegations")
        groups = data.get("groups")

        if employee:
            data["groups"] = employee.position.role_groups.all()
            groups = data["groups"]
            if self.actor and not self.actor.is_superuser:
                allowed_perms = self.actor.get_all_permissions()
                for group in groups.prefetch_related("permissions__content_type"):
                    if any(f"{perm.content_type.app_label}.{perm.codename}" not in allowed_perms
                           for perm in group.permissions.all()):
                        self.add_error("employee", "No puedes crear una cuenta con permisos superiores a los tuyos.")
                        break
            self.fields["groups"].required = False
        if (
            employee
            and delegations
            and not delegations.filter(
                pk=employee.delegation_id
            ).exists()
        ):
            self.add_error(
                "authorized_delegations",
                "Incluye la delegación principal del empleado.",
            )

        if groups and delegations and not _role_scope_valid(
            groups, delegations
        ):
            self.add_error(
                "groups",
                "Solo se permiten roles creados en Roles y Permisos.",
            )

        return data


class AccountEditForm(BootstrapMixin, forms.ModelForm):
    """Edita perfil, cuenta, roles y delegaciones autorizadas."""

    profile_photo = forms.ImageField(
        label="Foto de perfil",
        required=False,
    )

    employee = forms.ModelChoiceField(
        label="Empleado vinculado (opcional)",
        queryset=Employee.objects.none(),
        required=False,
    )

    employee_code = forms.CharField(
        label="Código de empleado",
        max_length=30,
    )

    authorized_delegations = forms.ModelMultipleChoiceField(
        label="Delegaciones autorizadas",
        queryset=Delegation.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=True,
    )

    groups = forms.ModelMultipleChoiceField(
        label="Roles asignados",
        queryset=Group.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )

    class Meta:
        model = get_user_model()
        fields = [
            "username",
            "first_name",
            "last_name",
            "email",
            "is_active",
            "employee",
            "employee_code",
            "authorized_delegations",
            "groups",
        ]

        labels = {
            "username": "Nombre de usuario",
            "first_name": "Nombre",
            "last_name": "Apellidos",
            "email": "Correo",
            "is_active": "Cuenta activa",
        }

    def __init__(self, *args, **kwargs):
        self.actor = kwargs.pop("actor", None)
        super().__init__(*args, **kwargs)

        self.profile = UserProfile.objects.filter(
            user=self.instance,
            deleted_at__isnull=True,
        ).first()

        self.fields["profile_photo"].initial = (
            self.profile.profile_photo if self.profile else None
        )

        selected = (
            list(
                self.profile.authorized_delegations.values_list(
                    "pk", flat=True
                )
            )
            if self.profile
            else []
        )

        if self.profile and self.profile.delegation_id and not selected:
            selected = [self.profile.delegation_id]

        self.fields["authorized_delegations"].initial = selected

        self.fields["authorized_delegations"].queryset = (
            Delegation.objects.filter(
                Q(deleted_at__isnull=True) | Q(pk__in=selected)
            ).distinct().order_by("name")
        )

        current_employee_id = (
            self.profile.employee_id if self.profile else None
        )

        self.fields["employee"].queryset = Employee.objects.filter(
            Q(deleted_at__isnull=True, user_profile__isnull=True)
            | Q(pk=current_employee_id)
        ).distinct().order_by("name")

        self.fields["employee"].initial = current_employee_id

        self.fields["employee_code"].initial = (
            self.profile.employee_code if self.profile else ""
        )

        self.fields["groups"].queryset = Group.objects.filter(
            organization_role__isnull=False
        ).prefetch_related(
            "organization_role__application_delegations"
        ).order_by("name")

        if self.profile and self.profile.employee_id:
            inherited = self.profile.employee.position.role_groups.all()
            self.fields["groups"].initial = inherited
            self.fields["groups"].required = False
            self.fields["groups"].disabled = True
            self.fields["groups"].help_text = (
                "Solo lectura: los roles se administran desde Cargos y Funciones."
            )
        else:
            self.fields["groups"].initial = self.instance.groups.all()

        self.fields["email"].required = True

        _restrict_account_actor_choices(
            self, self.actor, "change"
        )
        if self.profile and self.profile.employee_id:
            # La edición de otros datos no debe fallar porque el actor
            # no pueda delegar un rol que el cargo ya tiene.
            self.fields["groups"].queryset = (
                Group.objects.filter(pk__in=self.profile.employee.position.role_groups.values("pk"))
            )

        self.apply_bootstrap()

    def clean_email(self):
        correo = self.cleaned_data["email"].strip()

        existentes = get_user_model()._default_manager.filter(
            email__iexact=correo
        )

        if existentes.exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(
                "Este correo ya pertenece a otra cuenta."
            )

        return correo

    def clean_employee_code(self):
        code = self.cleaned_data["employee_code"].strip()

        duplicate = UserProfile.objects.filter(
            employee_code__iexact=code
        )

        if self.profile:
            duplicate = duplicate.exclude(pk=self.profile.pk)

        if duplicate.exists():
            raise forms.ValidationError(
                "El código ya pertenece a otra cuenta."
            )

        return code

    def clean(self):
        data = super().clean()

        employee = data.get("employee")
        delegations = data.get("authorized_delegations")
        groups = data.get("groups")
        if employee:
            data["groups"] = employee.position.role_groups.all()
            groups = data["groups"]
            if (self.actor and not self.actor.is_superuser and self.profile
                and self.profile.employee_id != employee.pk):
                allowed_perms = self.actor.get_all_permissions()
                for group in groups.prefetch_related("permissions__content_type"):
                    if any(f"{perm.content_type.app_label}.{perm.codename}" not in allowed_perms
                           for perm in group.permissions.all()):
                        self.add_error("employee", "No puedes vincular una cuenta con permisos superiores a los tuyos.")
                        break

        if not self.profile:
            raise forms.ValidationError(
                "La cuenta no tiene un perfil activo."
            )

        if (
            employee
            and delegations
            and not delegations.filter(
                pk=employee.delegation_id
            ).exists()
        ):
            self.add_error(
                "authorized_delegations",
                "Incluye la delegación principal del empleado.",
            )

        if groups and delegations and not _role_scope_valid(
            groups, delegations
        ):
            self.add_error(
                "groups",
                "Solo se permiten roles creados en Roles y Permisos.",
            )

        if (
            employee
            and UserProfile.objects.exclude(
                pk=self.profile.pk
            ).filter(employee=employee).exists()
        ):
            self.add_error(
                "employee",
                "Este empleado ya tiene otra cuenta, "
                "incluso si está archivada.",
            )

        # Impedir que el usuario modifique sus propios roles.
        if (
            self.actor is not None
            and self.actor.pk == self.instance.pk
            and groups is not None
            and set(groups.values_list("pk", flat=True))
            != set(
                self.instance.groups.values_list("pk", flat=True)
            )
        ):
            self.add_error(
                "groups",
                "No puedes modificar los roles asignados "
                "a tu propia cuenta.",
            )

        return data

    def save(self, commit=True):
        if not commit:
            return super().save(commit=False)

        from django.db import transaction
        from .services import sync_user_groups

        with transaction.atomic():
            account = super().save(commit=False)
            account.save()

            profile = UserProfile.objects.select_for_update().get(
                pk=self.profile.pk
            )

            old_employee = profile.employee
            new_employee = self.cleaned_data["employee"]
            delegations = self.cleaned_data["authorized_delegations"]

            primary = (
                new_employee.delegation
                if new_employee
                else delegations.first()
            )

            profile.employee = new_employee
            profile.employee_code = self.cleaned_data["employee_code"]
            profile.delegation = primary

            profile.profile_photo = (
                self.cleaned_data.get("profile_photo")
                or profile.profile_photo
            )

            profile.save(
                update_fields=[
                    "employee",
                    "employee_code",
                    "delegation",
                    "profile_photo",
                    "updated_at",
                ]
            )

            profile.authorized_delegations.set(delegations)

            if (
                old_employee
                and old_employee.pk != getattr(new_employee, "pk", None)
            ):
                from .services import sync_employee
                sync_employee(old_employee)  # El empleado conserva roles del cargo para su listado.

            if new_employee:
                sync_user_groups(account)
            elif old_employee:
                # Al desvincular una cuenta, nunca conservar roles heredados.
                account.groups.clear()
                account.user_permissions.clear()
            else:
                account.groups.set(self.cleaned_data.get("groups") or [])

            return account


class ProfileLinkForm(BootstrapMixin, forms.ModelForm):
    """Vincula un perfil existente con un empleado."""

    class Meta:
        model = UserProfile
        fields = ["employee", "profile_photo"]
        labels = {
            "employee": "Empleado",
            "profile_photo": "Foto de perfil",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        available = Employee.objects.filter(
            deleted_at__isnull=True,
            position__deleted_at__isnull=True,
            delegation__deleted_at__isnull=True,
        )

        self.fields["employee"].queryset = (
            available.filter(
                Q(user_profile__isnull=True)
                | Q(user_profile=self.instance)
            )
            .distinct()
            .order_by("name")
        )

        authorized = list(
            self.instance.authorized_delegations.values_list(
                "pk", flat=True
            )
        )

        if not authorized and self.instance.delegation_id:
            authorized = [self.instance.delegation_id]

        self.fields["employee"].queryset = (
            self.fields["employee"].queryset.filter(
                delegation_id__in=authorized
            )
        )

        self.fields["employee"].required = True

        self.apply_bootstrap()
