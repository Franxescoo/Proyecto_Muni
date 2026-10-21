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
from registration_validation.models import Service
from planning_measurements.models import MeasurementItem


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
            "catalog_items",
            "catalog_services",
            "weightings",
            "validity_start",
            "validity_end",
        ]
        labels = {
            "position_name": "Nombre del cargo",
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
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

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
        label="Funcionario existente (opcional)",
        queryset=Employee.objects.none(),
        required=False,
    )

    delegation = forms.ModelChoiceField(
        label="Delegación autorizada",
        queryset=Delegation.objects.none(),
        required=True,
    )

    employee_code = forms.CharField(
        label="Código de funcionario",
        max_length=30,
    )

    groups = forms.ModelMultipleChoiceField(
        label="Roles asignados",
        queryset=Group.objects.filter(
            organization_role__isnull=False
        ).select_related(
            "organization_role__delegation"
        ).order_by("organization_role__delegation__name", "name"),
        widget=forms.CheckboxSelectMultiple,
        required=True,
        help_text="Selecciona uno o varios roles creados en Organización.",
    )

    class Meta:
        model = get_user_model()
        fields = [
            "username",
            "email",
            "employee",
            "delegation",
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

        self.fields["delegation"].queryset = (
            Delegation.objects.filter(
                deleted_at__isnull=True
            ).order_by("name")
        )

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

    def clean(self):
        cleaned_data = super().clean()

        employee = cleaned_data.get("employee")
        delegation = cleaned_data.get("delegation")
        groups = cleaned_data.get("groups")

        if employee and delegation:
            if employee.delegation_id != delegation.pk:
                self.add_error(
                    "delegation",
                    "La delegación debe coincidir con la del funcionario.",
                )

        if delegation and groups:
            if groups.exclude(
                organization_role__delegation_id=delegation.pk
            ).exists():
                self.add_error(
                    "groups",
                    "Solo puedes asignar roles de la delegación seleccionada.",
                )

        return cleaned_data



class AccountEditForm(BootstrapMixin, forms.ModelForm):
    """Permite editar la cuenta y sus roles de acceso."""

    groups = forms.ModelMultipleChoiceField(
        label="Roles asignados",
        queryset=Group.objects.none(),
        widget=forms.CheckboxSelectMultiple(),
        required=True,
        help_text="Selecciona los roles que tendrá el usuario.",
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

        profile = UserProfile.objects.filter(
            user=self.instance,
            deleted_at__isnull=True,
        ).first()

        current_group_ids = list(
            self.instance.groups.values_list("pk", flat=True)
        )

        group_scope = Q(pk__in=current_group_ids)

        if profile and profile.delegation_id:
            group_scope |= Q(
                organization_role__delegation_id=profile.delegation_id
            )

        self.fields["groups"].queryset = (
            Group.objects.filter(
                group_scope,
                organization_role__isnull=False,
            )
            .distinct()
            .select_related("organization_role__delegation")
            .order_by("name")
        )

        self.fields["email"].required = True

        self.apply_bootstrap()

    def clean_groups(self):
        groups = self.cleaned_data["groups"]

        profile = UserProfile.objects.filter(
            user=self.instance,
            deleted_at__isnull=True,
        ).first()

        if not profile or not profile.delegation_id:
            raise forms.ValidationError(
                "El usuario debe tener una delegación autorizada."
            )

        if groups.exclude(
            organization_role__delegation_id=profile.delegation_id
        ).exists():
            raise forms.ValidationError(
                "Solo puedes asignar roles de la delegación del usuario."
            )

        return groups

    def save(self, commit=True):
        account = super().save(commit=commit)

        if commit:
            from .services import sync_user_groups
            sync_user_groups(account)

        return account



class ProfileLinkForm(BootstrapMixin, forms.ModelForm):
    """Vincula un perfil existente con un funcionario."""

    class Meta:
        model = UserProfile
        fields = ["employee", "profile_photo"]
        labels = {
            "employee": "Funcionario",
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

        self.fields["employee"].required = True
        self.apply_bootstrap()