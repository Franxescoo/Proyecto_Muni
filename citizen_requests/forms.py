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
        widgets = {
            "requester_name": forms.TextInput(
                attrs={"class": "form-control", "autocomplete": "name"},
            ),
            "requester_email": forms.EmailInput(
                attrs={"class": "form-control", "autocomplete": "email"},
            ),
            "requester_phone": forms.TextInput(
                attrs={"class": "form-control", "autocomplete": "tel"},
            ),
            "address": forms.TextInput(
                attrs={"class": "form-control", "autocomplete": "street-address"},
            ),
            "subject": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(
                attrs={"class": "form-control", "rows": 5},
            ),
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


class PublicVerifiedRequestForm(forms.Form):
    """Solo datos propios de la solicitud; la identidad proviene de la sesión verificada."""

    subject = forms.CharField(
        label="Asunto", max_length=160,
        widget=forms.TextInput(attrs={"class": "form-control", "maxlength": "160"}),
    )
    description = forms.CharField(
        label="Descripción",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 5}),
    )

    def clean_subject(self):
        value = self.cleaned_data["subject"].strip()
        if not value:
            raise forms.ValidationError("Indica el asunto de la solicitud.")
        return value

    def clean_description(self):
        value = self.cleaned_data["description"].strip()
        if not value:
            raise forms.ValidationError("Describe la solicitud.")
        return value


class PublicTrackingCodeForm(forms.Form):
    tracking_code = forms.UUIDField(
        label="Código de seguimiento",
        error_messages={
            "required": "Ingresa un código de seguimiento.",
            "invalid": "Ingresa un código de seguimiento válido.",
        },
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
                "autocomplete": "off",
                "spellcheck": "false",
            },
        ),
    )
