from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from accounts.permissions import allowed_delegation_ids
from organization.models import Delegation
from registration_validation.models import AttentionType

from .models import Beneficiary, Campaign, EventEdition, GiftDelivery, MunicipalEvent, normalized_rut, validate_rut


class DateInput(forms.DateInput):
    input_type = "date"


class BootstrapModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control" if not isinstance(field.widget, forms.Select) else "form-select"


class EventForm(BootstrapModelForm):
    class Meta:
        model = MunicipalEvent
        fields = ("name", "description")
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


class EditionForm(BootstrapModelForm):
    class Meta:
        model = EventEdition
        fields = ("year", "date", "place", "delegation", "status", "notes")
        widgets = {"date": DateInput(), "notes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, user=None, permission="municipal_events.add_eventedition", **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            ids = allowed_delegation_ids(user, permission)
            self.fields["delegation"].queryset = Delegation.objects.filter(pk__in=ids) if ids is not None else Delegation.objects.all()


class CampaignForm(BootstrapModelForm):
    class Meta:
        model = Campaign
        fields = ("title", "year", "description", "attention_type", "edition", "organizing_delegation", "opens_on", "closes_on", "status")
        widgets = {"opens_on": DateInput(), "closes_on": DateInput(), "description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, user=None, permission="municipal_events.add_campaign", **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["attention_type"].queryset = AttentionType.objects.filter(status=True, deleted_at__isnull=True)
        self.fields["edition"].required = False
        if user is not None:
            ids = allowed_delegation_ids(user, permission)
            self.fields["organizing_delegation"].queryset = Delegation.objects.filter(pk__in=ids) if ids is not None else Delegation.objects.all()


class EnrollmentForm(forms.Form):
    name = forms.CharField(label="Nombre completo del niño/a", max_length=160)
    rut = forms.CharField(label="RUT del niño/a (con dígito verificador)", max_length=16)
    birth_date = forms.DateField(label="Fecha de nacimiento", widget=DateInput())
    observation = forms.CharField(label="Observaciones", required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"

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


class DeliveryForm(BootstrapModelForm):
    class Meta:
        model = GiftDelivery
        fields = ("notes",)
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}
