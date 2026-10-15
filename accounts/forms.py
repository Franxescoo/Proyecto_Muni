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
            "delegation",
            "position",
            "roles",
            "status",
        ]
        labels = {
            "name": "Nombre",
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

    groups = forms.ModelMultipleChoiceField(
        label="Grupos",
        queryset=Group.objects.order_by("name"),
        widget=forms.CheckboxSelectMultiple,
        required=True,
        help_text="Puedes seleccionar uno o varios grupos.",
    )

    class Meta:
        model = get_user_model()
        fields = [
            "username",
            "email",
            "employee",
            "employee_code",
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
    """Edita una cuenta y los grupos asignados."""

    groups = forms.ModelMultipleChoiceField(
        label="Grupos",
        queryset=Group.objects.order_by("name"),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        help_text=(
            "Puedes seleccionar varios grupos. Sin grupos, "
            "la cuenta no recibe permisos mediante grupos."
        ),
    )

    class Meta:
        model = get_user_model()
        fields = [
            "username",
            "email",
            "is_active",
            "groups",
        ]
        labels = {
            "username": "Nombre de usuario",
            "email": "Correo",
            "is_active": "Cuenta activa",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap()


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