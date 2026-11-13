from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator
from django.db.models import Q
from django.utils import timezone

from accounts.permissions import allowed_delegation_ids
from organization.models import Delegation
from registration_validation.models import AttentionType

from .models import (Beneficiary, Campaign, EventEdition, GiftDelivery, MunicipalEvent,
                     EventParticipation, normalized_rut, validate_rut)


class DateInput(forms.DateInput):
    input_type = "date"


def configure_text_limits(form, limits=None):
    """Limitación visual y del servidor, incluso para TextField sin max_length DB.

    Los campos de fecha, números, casillas y selección no usan maxlength.
    """
    limits = limits or {}
    for name, field in form.fields.items():
        if not isinstance(field, forms.CharField):
            continue
        if name in limits:
            limit = limits[name]
        elif field.max_length is not None:
            limit = field.max_length  # Respeta los límites originales del modelo.
        elif isinstance(field.widget, forms.Textarea):
            limit = 1500
        else:
            limit = 254
        # Nunca ampliar el máximo explícito de un modelo CharField.
        if field.max_length is not None:
            limit = min(limit, field.max_length)
        # Cambiar .max_length después de construir el campo no actualiza por sí
        # solo sus validadores; registrar MaxLengthValidator explícitamente.
        if not any(isinstance(v, MaxLengthValidator) and v.limit_value == limit for v in field.validators):
            field.validators.append(MaxLengthValidator(limit))
        field.max_length = limit
        field.widget.attrs["maxlength"] = str(limit)


class BootstrapModelForm(forms.ModelForm):
    text_limits = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control" if not isinstance(field.widget, forms.Select) else "form-select"
        configure_text_limits(self, self.text_limits)


class EventForm(BootstrapModelForm):
    text_limits = {"description": 2000}
    class Meta:
        model = MunicipalEvent
        fields = ("name", "description")
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


class EditionForm(BootstrapModelForm):
    text_limits = {"notes": 1200, "participation_requirements": 2000}
    class Meta:
        model = EventEdition
        fields = ("year", "date", "place", "delegation", "status", "participation_mode",
                  "participation_capacity", "participation_requirements", "notes")
        widgets = {"date": DateInput(), "notes": forms.Textarea(attrs={"rows": 3}),
                   "participation_requirements": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, user=None, permission="municipal_events.add_eventedition", **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            ids = allowed_delegation_ids(user, permission)
            self.fields["delegation"].queryset = Delegation.objects.filter(pk__in=ids) if ids is not None else Delegation.objects.all()


class CampaignForm(BootstrapModelForm):
    text_limits = {"description": 2000}
    class Meta:
        model = Campaign
        fields = ("title", "year", "description", "attention_type", "edition",
                  "organizing_delegation", "opens_on", "closes_on", "max_age",
                  "status")
        widgets = {"opens_on": DateInput(), "closes_on": DateInput(), "description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, user=None, permission="municipal_events.add_campaign", **kwargs):
        super().__init__(*args, **kwargs)
        active_attention_types = AttentionType.objects.filter(
            status=True, deleted_at__isnull=True
        )
        if self.instance and self.instance.pk and self.instance.attention_type_id:
            active_attention_types = active_attention_types.filter(
                Q(pk=self.instance.attention_type_id)
                | Q(pk__in=active_attention_types.values("pk"))
            )
        self.fields["attention_type"].queryset = active_attention_types
        self.fields["max_age"].help_text = (
            "Edad calculada al 31 de diciembre del año de la campaña."
        )
        self.fields["edition"].required = False
        self.fields["edition"].queryset = EventEdition.objects.filter(deleted_at__isnull=True, event__deleted_at__isnull=True)
        if user is not None:
            ids = allowed_delegation_ids(user, permission)
            self.fields["organizing_delegation"].queryset = Delegation.objects.filter(pk__in=ids) if ids is not None else Delegation.objects.all()


class EnrollmentForm(forms.Form):
    name = forms.CharField(label="Nombre completo del niño/a", max_length=160)
    rut = forms.CharField(label="RUT del niño/a (con dígito verificador)", max_length=16)
    birth_date = forms.DateField(label="Fecha de nacimiento", widget=DateInput())
    sex = forms.ChoiceField(label="Sexo del niño/a", choices=[("", "Seleccione"), ("M", "Masculino"), ("F", "Femenino")])
    observation = forms.CharField(label="Observaciones", required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["birth_date"].help_text = (
            "La edad se calculará al 31 de diciembre del año de la campaña."
        )

        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"
        configure_text_limits(self, {"observation": 1200})

    def clean_rut(self):
        result = normalized_rut(self.cleaned_data["rut"])
        validate_rut(result)
        return result

    def clean_birth_date(self):
        birth_date = self.cleaned_data["birth_date"]
        if birth_date > timezone.localdate():
            raise ValidationError("La fecha de nacimiento no puede ser futura.")
        return birth_date


class ReviewForm(forms.Form):
    status = forms.ChoiceField(label="Decisión", choices=[("APPROVED", "Aprobar"), ("REJECTED", "Rechazar")])
    reason = forms.CharField(label="Motivo de la decisión", widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
        configure_text_limits(self, {"reason": 500})


class DeliveryForm(BootstrapModelForm):
    text_limits = {"notes": 1200}
    class Meta:
        model = GiftDelivery
        fields = ("notes",)
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}


class EventParticipationForm(BootstrapModelForm):
    # El formulario acepta puntos/guion, pero se normaliza a RUT canónico (9) al guardar.
    rut = forms.CharField(label="RUT del participante", max_length=16)
    text_limits = {"description": 1200}

    class Meta:
        model = EventParticipation
        fields = ("full_name", "rut", "email", "description")
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def clean_rut(self):
        value = normalized_rut(self.cleaned_data["rut"])
        validate_rut(value)
        return value


class EventParticipationEditForm(BootstrapModelForm):
    """Solo corrige contacto y antecedentes; RUT, edición y decisión se conservan."""
    text_limits = {"description": 1200}

    class Meta:
        model = EventParticipation
        fields = ("full_name", "email", "description")
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


class EventParticipationReviewForm(forms.Form):
    decision = forms.ChoiceField(label="Decisión", choices=[
        ("ACCEPTED", "Aceptar postulación"), ("REJECTED", "Rechazar postulación"),
    ], widget=forms.Select(attrs={"class": "form-select"}))
    reason = forms.CharField(label="Motivo de la decisión", max_length=500,
                             widget=forms.Textarea(attrs={"rows": 3, "class": "form-control", "maxlength": "500"}))
