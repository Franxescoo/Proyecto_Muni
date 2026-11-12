from django import forms
from django.db.models import Q

from accounts.permissions import allowed_delegation_ids
from organization.models import Employee

from .models import CitizenRequest, CitizenRequestAction


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


class CitizenRequestActionForm(forms.ModelForm):
    performed_at = forms.DateTimeField(
        label="Fecha y hora de realización",
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local", "class": "form-control"},
            format="%Y-%m-%dT%H:%M",
        ),
    )

    class Meta:
        model = CitizenRequestAction
        fields = [
            "responsible",
            "action_type",
            "performed_at",
            "description",
            "outcome",
        ]
        labels = {
            "responsible": "Funcionario responsable",
            "action_type": "Tipo de actuación",
            "description": "Descripción de la actuación",
            "outcome": "Resultado u observaciones",
        }
        widgets = {
            "responsible": forms.Select(attrs={"class": "form-select"}),
            "action_type": forms.Select(attrs={"class": "form-select"}),
            "description": forms.Textarea(
                attrs={"class": "form-control", "rows": 4},
            ),
            "outcome": forms.Textarea(
                attrs={"class": "form-control", "rows": 3},
            ),
        }

    def __init__(self, *args, citizen_request, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.citizen_request = citizen_request
        self.user = user
        self.is_editing = self.instance.pk is not None
        self.original_values = None

        if self.is_editing:
            self.original_values = (
                CitizenRequestAction.objects
                .filter(pk=self.instance.pk)
                .values(
                    "request_id",
                    "delegation_id",
                    "registered_by_id",
                    "responsible_id",
                )
                .first()
            )

        self.action_delegation_id = (
            self.original_values["delegation_id"]
            if self.original_values
            else getattr(citizen_request, "delegation_id", None)
        )

        permission_action = "change" if self.is_editing else "add"
        self.action_permission = (
            f"citizen_requests.{permission_action}_citizenrequestaction"
        )
        allowed_ids = (
            allowed_delegation_ids(user, self.action_permission)
            if user is not None
            else set()
        )
        delegation_is_allowed = (
            self.action_delegation_id is not None
            and (
                allowed_ids is None
                or self.action_delegation_id in allowed_ids
            )
        )

        if delegation_is_allowed:
            employees = Employee.objects.filter(
                delegation_id=self.action_delegation_id,
                deleted_at__isnull=True,
            )
            if self.original_values:
                employees = Employee.objects.filter(
                    Q(
                        delegation_id=self.action_delegation_id,
                        deleted_at__isnull=True,
                    )
                    | Q(pk=self.original_values["responsible_id"])
                )
            self.fields["responsible"].queryset = employees.order_by(
                "name", "employee_id",
            )
        else:
            self.fields["responsible"].queryset = Employee.objects.none()

    def clean(self):
        cleaned_data = super().clean()

        if not getattr(self.user, "is_authenticated", False) or not getattr(
            self.user, "is_active", False
        ):
            raise forms.ValidationError(
                "Debes iniciar sesión con una cuenta activa para registrar "
                "gestiones."
            )

        if self.is_editing:
            if (
                self.original_values is None
                or self.original_values["request_id"] != self.citizen_request.pk
            ):
                raise forms.ValidationError(
                    "La gestión no pertenece a la solicitud autorizada."
                )
            request_delegation_id = self.action_delegation_id
        else:
            request_values = (
                CitizenRequest.objects
                .filter(pk=self.citizen_request.pk)
                .values(
                    "delegation_id",
                    "attention_entry__delegation_id",
                )
                .first()
            )
            if request_values is None or request_values["delegation_id"] is None:
                raise forms.ValidationError(
                    "La solicitud debe tener una delegación asignada."
                )
            request_delegation_id = request_values["delegation_id"]
            attention_delegation_id = request_values[
                "attention_entry__delegation_id"
            ]
            if (
                attention_delegation_id is not None
                and attention_delegation_id != request_delegation_id
            ):
                raise forms.ValidationError(
                    "La atención vinculada no coincide con la delegación "
                    "de la solicitud."
                )
            if request_delegation_id != self.action_delegation_id:
                raise forms.ValidationError(
                    "La delegación de la solicitud cambió. Vuelve a cargar "
                    "el formulario."
                )

        responsible = cleaned_data.get("responsible")
        if responsible is not None:
            is_historical_responsible = bool(
                self.original_values
                and responsible.pk == self.original_values["responsible_id"]
            )
            if (
                not is_historical_responsible
                and responsible.delegation_id != request_delegation_id
            ):
                self.add_error(
                    "responsible",
                    "El funcionario debe pertenecer a la delegación "
                    "autorizada de la solicitud.",
                )

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.is_editing:
            if self.original_values is None:
                raise ValueError("No se encontró la gestión que se está editando.")
            if self.original_values["request_id"] != self.citizen_request.pk:
                raise ValueError("La gestión no pertenece a la solicitud autorizada.")
            instance.request_id = self.original_values["request_id"]
            instance.delegation_id = self.original_values["delegation_id"]
            instance.registered_by_id = self.original_values["registered_by_id"]
        else:
            instance.request = self.citizen_request
            instance.delegation_id = self.action_delegation_id
            instance.registered_by = self.user

        if commit:
            instance.save()
            self.save_m2m()
        return instance


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
