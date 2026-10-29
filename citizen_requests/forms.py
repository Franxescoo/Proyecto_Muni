from django import forms

from .models import CitizenRequest


class CitizenRequestForm(forms.ModelForm):
    """Formulario público; los campos de control los establece la vista."""

    class Meta:
        model = CitizenRequest
        fields = [
            "requester_name",
            "requester_email",
            "requester_phone",
            "address",
            "subject",
            "description",
        ]
        labels = {
            "requester_name": "Nombre",
            "requester_email": "Correo electrónico",
            "requester_phone": "Teléfono",
            "address": "Dirección",
            "subject": "Asunto",
            "description": "Descripción",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["requester_email"].required = True

    def clean_requester_name(self):
        return self._clean_required_text("requester_name")

    def clean_requester_email(self):
        return self.cleaned_data.get("requester_email", "").strip()

    def clean_requester_phone(self):
        return self.cleaned_data.get("requester_phone", "").strip()

    def clean_address(self):
        return self._clean_required_text("address")

    def clean_subject(self):
        return self._clean_required_text("subject")

    def clean_description(self):
        return self._clean_required_text("description")

    def _clean_required_text(self, field_name):
        value = self.cleaned_data[field_name].strip()
        if not value:
            self.add_error(field_name, "Este campo es obligatorio.")
        return value
