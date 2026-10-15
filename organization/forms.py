from django import forms
from django.contrib.auth.models import Group

from .models import Delegation, Employee, PositionFunction


class BootstrapModelForm(forms.ModelForm):
    """Aplica las clases visuales usadas por los formularios del proyecto."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                css_class = "form-check-input"
            elif isinstance(field.widget, forms.Select):
                css_class = "form-select"
            else:
                css_class = "form-control"
            field.widget.attrs["class"] = css_class


class DelegationForm(BootstrapModelForm):
    status = forms.ChoiceField(
        label="Estado",
        choices=(("", "Selecciona un estado"), ("Activo", "Activo"), ("Inactivo", "Inactivo")),
        required=True,
    )

    class Meta:
        model = Delegation
        fields = ["name", "scope", "status"]
        labels = {
            "name": "Nombre",
            "scope": "Alcance",
            "status": "Estado",
        }


class PositionFunctionForm(BootstrapModelForm):
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
            "validity_start": forms.DateInput(attrs={"type": "date"}),
            "validity_end": forms.DateInput(attrs={"type": "date"}),
        }


class EmployeeForm(BootstrapModelForm):
    # Los nombres se consultan en cada petición, así que los roles creados
    # en "Roles y Permisos" aparecen automáticamente al crear un funcionario.
    roles = forms.ChoiceField(
        label="Rol de acceso",
        choices=(),
        required=True,
        help_text="Selecciona uno de los roles configurados en Roles y Permisos.",
    )
    status = forms.ChoiceField(
        label="Estado",
        choices=(
            ("", "Selecciona un estado"),
            ("Activo", "Activo"),
            ("Inactivo", "Inactivo"),
            ("Licencia", "Licencia"),
        ),
        required=True,
    )

    class Meta:
        model = Employee
        fields = ["name", "photo", "delegation", "position", "roles", "status"]
        labels = {
            "name": "Nombre",
            "photo": "Foto de perfil",
            "delegation": "Delegación",
            "position": "Cargo y función",
            "roles": "Rol de acceso",
            "status": "Estado",
        }

    def __init__(self, *args, delegation_ids=None, **kwargs):
        super().__init__(*args, **kwargs)

        role_names = list(Group.objects.order_by("name").values_list("name", flat=True))
        choices = [("", "Selecciona un rol")]
        choices.extend((name, name) for name in role_names)

        # Si el rol antiguo ya no existe, conservarlo como opción para que
        # editar un funcionario no lo cambie silenciosamente.
        current_role = getattr(self.instance, "roles", "")
        if current_role and current_role not in role_names:
            choices.append((current_role, f"{current_role} (rol actual no existente)"))
        self.fields["photo"].required = False
        self.fields["photo"].widget.attrs.update({"accept": "image/*"})
        self.fields["roles"].choices = choices
        if current_role:
            self.fields["roles"].initial = current_role

        delegations = Delegation.objects.filter(deleted_at__isnull=True)
        if delegation_ids is not None:
            delegations = delegations.filter(pk__in=delegation_ids)
        self.fields["delegation"].queryset = delegations.order_by("name")
        self.fields["position"].queryset = PositionFunction.objects.filter(
            deleted_at__isnull=True
        ).order_by("position_name")
