from django import forms
from django.core.exceptions import ValidationError
from .models import Citizen
from .rut import normalize_rut, validate_rut


class CitizenForm(forms.ModelForm):
    class Meta:
        model = Citizen
        fields = (
            "rut", "full_name", "birth_date", "phone", "email", "address",
            "rsh_folio", "rsh_bracket", "is_neighborhood_member",
            "neighborhood_group", "organization_role",
        )
        widgets = {
            "birth_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "neighborhood_group": forms.TextInput(attrs={"list": "citizen-groups", "placeholder": "Escribe o selecciona una agrupación"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["birth_date"].input_formats = ["%Y-%m-%d"]
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "form-check-input"
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs["class"] = "form-select"
            else:
                field.widget.attrs["class"] = "form-control"
        self.fields["address"].required = True
        self.fields["organization_role"].required = False

    def clean_rut(self):
        rut = normalize_rut(self.cleaned_data["rut"])
        validate_rut(rut)
        if self.instance.pk and rut != self.instance.rut:
            raise ValidationError("No se puede cambiar el RUT de un ciudadano existente.")
        return rut


class CitizenRutForm(forms.Form):
    rut = forms.CharField(max_length=16)

    def clean_rut(self):
        value = normalize_rut(self.cleaned_data["rut"])
        validate_rut(value)
        return value
