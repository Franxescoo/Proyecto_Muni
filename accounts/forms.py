from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import Group, Permission
from django.db.models import Q

from organization.models import (
    Delegation,
    Employee,
    PositionFunction,
)

from .models import UserProfile
from .models import RoleScope


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

    permissions = forms.ModelMultipleChoiceField(
        label="Permisos",
        queryset=Permission.objects.filter(
            content_type__app_label__in=[
                "organization",
                "planning_measurements",
                "registration_validation",
                "monitoring_traceability",
            ],
        )
        .select_related("content_type")
        .order_by(
            "content_type__app_label",
            "content_type__model",
            "codename",
        ),
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


class RoleForm(BootstrapMixin, forms.ModelForm):
    """Edita un rol, sus permisos y su alcance por delegación."""

    permissions = GroupForm.base_fields["permissions"]
    all_delegations = forms.BooleanField(
        label="Acceso a todas las delegaciones",
        required=False,
        help_text=(
            "Usa esta opción solo para el rol Administrador General."
        ),
    )
    delegations = forms.ModelMultipleChoiceField(
        label="Delegaciones autorizadas",
        queryset=Delegation.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        help_text=(
            "Si no seleccionas una, la cuenta queda limitada a la "
            "delegación de su funcionario."
        ),
    )

    class Meta:
        model = Group
        fields = ["name", "permissions"]
        labels = {"name": "Nombre del rol"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["delegations"].queryset = Delegation.objects.filter(
            deleted_at__isnull=True
        ).order_by("name")

        if self.instance and self.instance.pk:
            try:
                scope = self.instance.role_scope
            except RoleScope.DoesNotExist:
                scope = None

            if scope is not None:
                self.fields["all_delegations"].initial = scope.all_delegations
                self.fields["delegations"].initial = scope.delegations.all()

        self.apply_bootstrap()

    def clean(self):
        cleaned_data = super().clean()
        if (
            not cleaned_data.get("all_delegations")
            and not cleaned_data.get("delegations")
        ):
            # No es un error: se usa la delegación del funcionario.
            return cleaned_data
        return cleaned_data

    def save(self, commit=True):
        group = super().save(commit=commit)
        if not commit:
            return group

        scope, _ = RoleScope.objects.get_or_create(group=group)
        scope.all_delegations = self.cleaned_data["all_delegations"]
        scope.save(update_fields=["all_delegations", "updated_at"])
        scope.delegations.set(self.cleaned_data["delegations"])
        return group


class PositionForm(BootstrapMixin, forms.ModelForm):
    """Gestiona cargos sin asignarles grupos de permisos."""

    class Meta:
        model = PositionFunction
        fields = [
            "position_name",
            "measurable_items",
            "services",
            "weightings",
            "validity_start",
            "validity_end",
        ]
        labels = {
            "position_name": "Nombre del cargo",
            "measurable_items": "Ítems medibles",
            "services": "Servicios",
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
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap()


class EmployeeForm(BootstrapMixin, forms.ModelForm):
    """Permite crear y editar funcionarios."""

    class Meta:
        model = Employee
        fields = [
            "name",
            "photo",
            "delegation",
            "position",
            "roles",
            "status",
        ]
        labels = {
            "name": "Nombre",
            "photo": "Foto de perfil",
            "delegation": "Delegación",
            "position": "Cargo",
            "roles": "Descripción de funciones",
            "status": "Estado",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["photo"].required = False
        self.fields["photo"].widget.attrs.update({"accept": "image/*"})
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


class AccountCreateForm(BootstrapMixin, UserCreationForm):
    """Crea una cuenta vinculada a un funcionario y sus grupos."""

    employee = forms.ModelChoiceField(
        label="Funcionario",
        queryset=Employee.objects.none(),
    )

    employee_code = forms.CharField(
        label="Código de funcionario",
        max_length=30,
    )
    avatar = forms.ImageField(label="Foto de perfil", required=False)

    groups = forms.ModelMultipleChoiceField(
        label="Roles",
        queryset=Group.objects.order_by("name"),
        widget=forms.CheckboxSelectMultiple,
        required=True,
        help_text="Selecciona el rol que definirá sus permisos y alcance.",
    )

    class Meta:
        model = get_user_model()
        fields = [
            "username",
            "email",
            "employee",
            "employee_code",
            "avatar",
            "groups",
            "password1",
            "password2",
        ]
        labels = {
            "username": "Nombre de usuario",
            "email": "Correo",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["employee"].queryset = (
            Employee.objects.filter(
                deleted_at__isnull=True,
                user_profile__isnull=True,
                position__deleted_at__isnull=True,
                delegation__deleted_at__isnull=True,
            )
            .select_related("position", "delegation")
            .order_by("name")
        )

        self.fields["password1"].label = "Contraseña"
        self.fields["password2"].label = "Confirmar contraseña"

        self.apply_bootstrap()

    def clean_employee_code(self):
        code = self.cleaned_data["employee_code"].strip()

        if UserProfile.objects.filter(
            employee_code=code
        ).exists():
            raise forms.ValidationError(
                "El código ya pertenece a otra cuenta."
            )

        return code


class AccountEditForm(BootstrapMixin, forms.ModelForm):
    """Edita datos de acceso y los datos básicos del perfil asociado."""

    groups = forms.ModelMultipleChoiceField(
        label="Roles",
        queryset=Group.objects.order_by("name"),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        help_text="Los roles determinan los permisos que recibe la cuenta.",
    )
    employee_code = forms.CharField(
        label="Código de funcionario",
        max_length=30,
        required=False,
    )
    phone = forms.CharField(
        label="Teléfono de contacto",
        max_length=20,
        required=False,
    )
    avatar = forms.ImageField(label="Foto de perfil", required=False)
    employee = forms.ModelChoiceField(
        label="Funcionario asociado",
        queryset=Employee.objects.none(),
        required=False,
        help_text="Cambiarlo actualiza la asociación del perfil y su delegación.",
    )

    class Meta:
        model = get_user_model()
        fields = [
            "username",
            "first_name",
            "last_name",
            "email",
            "is_active",
            "groups",
            "employee_code",
            "phone",
            "avatar",
            "employee",
        ]
        labels = {
            "username": "Nombre de usuario",
            "first_name": "Nombre",
            "last_name": "Apellidos",
            "email": "Correo electrónico",
            "is_active": "Cuenta activa",
        }
        help_texts = {
            "is_active": "Desactiva la cuenta para impedir que inicie sesión sin eliminarla.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        profile = getattr(self.instance, "profile", None) if self.instance and self.instance.pk else None
        if profile:
            self.fields["employee_code"].initial = profile.employee_code
            self.fields["employee_code"].required = True
            self.fields["phone"].initial = profile.phone
            self.fields["avatar"].initial = profile.avatar
            self.fields["employee"].initial = profile.employee
        else:
            self.fields["employee_code"].help_text = "Esta cuenta no tiene un perfil asociado; no se creará uno automáticamente."
        available_employees = Employee.objects.filter(
            deleted_at__isnull=True,
            position__deleted_at__isnull=True,
            delegation__deleted_at__isnull=True,
        ).filter(
            Q(user_profile__isnull=True) | Q(user_profile=profile)
        ).distinct().order_by("name")
        self.fields["employee"].queryset = available_employees
        if not profile:
            self.fields["employee"].disabled = True
            self.fields["employee"].help_text = "Esta cuenta no tiene un perfil de funcionario que pueda modificarse."
        self.apply_bootstrap()
        self.fields["is_active"].widget.attrs["class"] = "form-check-input"

    def clean_employee_code(self):
        code = self.cleaned_data.get("employee_code", "").strip()
        profile = getattr(self.instance, "profile", None) if self.instance and self.instance.pk else None
        if code and UserProfile.objects.filter(employee_code=code).exclude(pk=getattr(profile, "pk", None)).exists():
            raise forms.ValidationError("Ese código ya está asignado a otra cuenta.")
        return code

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            profile = UserProfile.objects.filter(user=user).first()
            if profile:
                profile.employee_code = self.cleaned_data.get("employee_code", profile.employee_code)
                profile.phone = self.cleaned_data.get("phone", profile.phone)
                if self.cleaned_data.get("avatar"):
                    profile.avatar = self.cleaned_data["avatar"]
                selected_employee = self.cleaned_data.get("employee")
                if selected_employee:
                    profile.employee = selected_employee
                    profile.delegation = selected_employee.delegation
                profile.save(update_fields=["employee_code", "phone", "avatar", "employee", "delegation", "updated_at"])
        return user


class ProfileLinkForm(BootstrapMixin, forms.ModelForm):
    """Vincula un perfil existente con un funcionario."""

    class Meta:
        model = UserProfile
        fields = ["employee"]
        labels = {
            "employee": "Funcionario",
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

        self.fields["employee"].required = True
        self.apply_bootstrap()


class MyAccountForm(BootstrapMixin, forms.ModelForm):
    """Permite al usuario editar solo los datos personales modificables."""

    phone = forms.CharField(
        label="Teléfono",
        max_length=20,
        required=False,
    )
    avatar = forms.ImageField(
        label="Foto de perfil",
        required=False,
        help_text="Si no subes una foto, se mostrará el avatar predeterminado.",
    )

    class Meta:
        model = get_user_model()
        fields = ["first_name", "last_name", "email"]
        labels = {
            "first_name": "Nombre",
            "last_name": "Apellidos",
            "email": "Correo electrónico",
        }

    def __init__(self, *args, profile=None, **kwargs):
        self.profile = profile
        super().__init__(*args, **kwargs)
        if profile:
            self.fields["phone"].initial = profile.phone
            self.fields["avatar"].initial = profile.avatar
        self.fields["avatar"].widget.attrs.update({"accept": "image/*"})
        self.apply_bootstrap()

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit and self.profile:
            self.profile.phone = self.cleaned_data.get("phone", "")
            if self.cleaned_data.get("avatar"):
                self.profile.avatar = self.cleaned_data["avatar"]
            self.profile.save(update_fields=["phone", "avatar", "updated_at"])
        return user
