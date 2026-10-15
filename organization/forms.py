from django import forms
from django.core.exceptions import ValidationError

from accounts.forms import (
    BootstrapMixin,
    EmployeeForm as AccountsEmployeeForm,
    PositionForm as AccountsPositionForm,
)

from .models import Delegation, PositionFunction

STATUS_CHOICES = (
    ("", "Selecciona un estado"),
    ("Active", "Activo"),
    ("Inactive", "Inactivo"),
)


def _configure_status_choices(form):
    choices = list(STATUS_CHOICES)
    current_status = getattr(form.instance, "status", "")
    if current_status and current_status not in dict(choices):
        choices.append((current_status, current_status))
    form.fields["status"].choices = choices


def mark_invalid_fields(form):
    for field_name in form.errors:
        field = form.fields.get(field_name)
        if field is None:
            continue
        classes = field.widget.attrs.get("class", "").split()
        if "is-invalid" not in classes:
            classes.append("is-invalid")
        field.widget.attrs["class"] = " ".join(classes)


class DelegationForm(BootstrapMixin, forms.ModelForm):
    status = forms.ChoiceField(choices=STATUS_CHOICES, label="Estado")

    class Meta:
        model = Delegation
        fields = ["name", "scope", "status"]
        labels = {
            "name": "Nombre de la delegación",
            "scope": "Ámbito",
            "status": "Estado",
        }
        widgets = {
            "name": forms.TextInput(
                attrs={"placeholder": "Ej. Delegación Centro"}
            ),
            "scope": forms.TextInput(
                attrs={"placeholder": "Ej. Urbano o rural"}
            ),
            "status": forms.TextInput(
                attrs={"placeholder": "Ej. Active"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap()
        _configure_status_choices(self)

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if len(name) < 3:
            raise ValidationError(
                "El nombre debe tener al menos 3 caracteres."
            )
        duplicates = Delegation.objects.filter(
            name__iexact=name,
            deleted_at__isnull=True,
        )
        if self.instance.pk:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise ValidationError(
                "Ya existe una delegación activa con ese nombre."
            )
        return name

    def clean_scope(self):
        scope = self.cleaned_data["scope"].strip()
        if len(scope) < 2:
            raise ValidationError(
                "El ámbito debe tener al menos 2 caracteres."
            )
        return scope


class EmployeeForm(AccountsEmployeeForm):
    status = forms.ChoiceField(choices=STATUS_CHOICES, label="Estado")

    class Meta(AccountsEmployeeForm.Meta):
        pass

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _configure_status_choices(self)

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if len(name) < 2:
            raise ValidationError(
                "El nombre debe tener al menos 2 caracteres."
            )
        return name

    def clean_roles(self):
        roles = self.cleaned_data["roles"].strip()
        if len(roles) < 3:
            raise ValidationError(
                "La descripción de funciones debe tener al menos 3 caracteres."
            )
        return roles


class PositionForm(AccountsPositionForm):
    class Meta(AccountsPositionForm.Meta):
        pass

    def clean_position_name(self):
        name = self.cleaned_data["position_name"].strip()
        if len(name) < 3:
            raise ValidationError(
                "El nombre del cargo debe tener al menos 3 caracteres."
            )
        duplicates = PositionFunction.objects.filter(
            position_name__iexact=name,
            deleted_at__isnull=True,
        )
        if self.instance.pk:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise ValidationError(
                "Ya existe un cargo activo con ese nombre."
            )
        return name

    def clean_measurable_items(self):
        value = self.cleaned_data["measurable_items"].strip()
        if len(value) < 2:
            raise ValidationError(
                "Indica al menos 2 caracteres para los ítems medibles."
            )
        return value

    def clean_services(self):
        value = self.cleaned_data["services"].strip()
        if len(value) < 2:
            raise ValidationError(
                "Indica al menos 2 caracteres para los servicios."
            )
        return value

    def clean_weightings(self):
        value = self.cleaned_data["weightings"].strip()
        if len(value) < 2:
            raise ValidationError(
                "Indica al menos 2 caracteres para las ponderaciones."
            )
        return value