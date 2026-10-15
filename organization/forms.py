from django import forms

from .models import Delegation, Employee, PositionFunction


class BootstrapModelForm(forms.ModelForm):
    """Aplica clases Bootstrap a los controles del formulario."""

    def apply_bootstrap(self):
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
        fields = ["name", "status", "scope"]
        labels = {"name": "Nombre", "status": "Estado", "scope": "Ámbito"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap()


class PositionFunctionForm(BootstrapModelForm):
    class Meta:
        model = PositionFunction
        fields = ["position_name", "measurable_items", "services", "weightings",
                  "validity_start", "validity_end", "group"]
        labels = {
            "position_name": "Nombre del cargo", "measurable_items": "Ítems medibles",
            "services": "Servicios", "weightings": "Ponderaciones",
            "validity_start": "Inicio de vigencia", "validity_end": "Fin de vigencia",
            "group": "Grupo de permisos asociado",
        }
        widgets = {
            "validity_start": forms.DateInput(attrs={"type": "date"}),
            "validity_end": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap()


class EmployeeForm(BootstrapModelForm):
    class Meta:
        model = Employee
        fields = ["name", "delegation", "position", "roles", "status"]
        labels = {
            "name": "Nombre completo", "delegation": "Delegación",
            "position": "Cargo y función", "roles": "Descripción de funciones",
            "status": "Estado",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["delegation"].queryset = Delegation.objects.filter(
            deleted_at__isnull=True
        ).order_by("name")
        self.fields["position"].queryset = PositionFunction.objects.filter(
            deleted_at__isnull=True
        ).order_by("position_name")
        self.apply_bootstrap()
