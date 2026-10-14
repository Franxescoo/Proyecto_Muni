from django import forms

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
    class Meta:
        model = Employee
        fields = ["name", "delegation", "position", "roles", "status"]
        labels = {
            "name": "Nombre",
            "delegation": "Delegación",
            "position": "Cargo y función",
            "roles": "Funciones",
            "status": "Estado",
        }

    def __init__(self, *args, delegation_ids=None, **kwargs):
        super().__init__(*args, **kwargs)
        delegations = Delegation.objects.filter(deleted_at__isnull=True)
        if delegation_ids is not None:
            delegations = delegations.filter(pk__in=delegation_ids)
        self.fields["delegation"].queryset = delegations.order_by("name")
        self.fields["position"].queryset = PositionFunction.objects.filter(
            deleted_at__isnull=True
        ).order_by("position_name")
