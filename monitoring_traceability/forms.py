from django import forms

from organization.models import Delegation, Employee
from registration_validation.models import Activity

from .models import Commitment


class ActivitySelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(
            name, value, label, selected, index, subindex, attrs
        )
        metadata = getattr(self, "activity_metadata", {}).get(str(value))
        if metadata:
            option["attrs"].update({
                f"data-{key}": item for key, item in metadata.items()
            })
        return option


class EmployeeSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(
            name, value, label, selected, index, subindex, attrs
        )
        delegation_id = getattr(self, "employee_delegations", {}).get(str(value))
        if delegation_id:
            option["attrs"]["data-delegation-id"] = delegation_id
        return option


class CommitmentForm(forms.ModelForm):
    class Meta:
        model = Commitment
        fields = (
            "delegation",
            "responsible",
            "activity",
            "origin",
            "requester",
            "territory",
            "commitment_date",
            "support",
            "status",
            "observation",
        )
        widgets = {
            "delegation": forms.Select(attrs={"class": "form-select"}),
            "responsible": EmployeeSelect(attrs={"class": "form-select"}),
            "activity": ActivitySelect(attrs={"class": "form-select"}),
            "origin": forms.TextInput(attrs={"class": "form-control"}),
            "requester": forms.TextInput(attrs={"class": "form-control"}),
            "territory": forms.TextInput(attrs={"class": "form-control"}),
            "commitment_date": forms.DateInput(
                attrs={"class": "form-control", "type": "date"}
            ),
            "support": forms.Textarea(
                attrs={"class": "form-control", "rows": 3}
            ),
            "status": forms.Select(attrs={"class": "form-select"}),
            "observation": forms.Textarea(
                attrs={"class": "form-control", "rows": 3}
            ),
        }
        labels = {
            "delegation": "Delegación",
            "responsible": "Responsable",
            "activity": "Actividad",
            "origin": "Meta",
            "requester": "Solicitante",
            "territory": "Territorio",
            "commitment_date": "Fecha de cumplimiento",
            "support": "Apoyo requerido",
            "status": "Estado",
            "observation": "Observación",
        }

    def __init__(
        self,
        *args,
        employees=None,
        delegations=None,
        activities=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        if employees is not None:
            self.fields["responsible"].queryset = employees
        if delegations is not None:
            self.fields["delegation"].queryset = delegations
        if activities is not None:
            self.fields["activity"].queryset = activities
        self.fields["activity"].empty_label = "Selecciona una actividad"
        self.fields["delegation"].empty_label = "Selecciona una delegación"
        self.fields["responsible"].empty_label = "Selecciona un responsable"
        status_choices = [
            (
                value,
                "No iniciado" if value == Commitment.Status.PENDING else label,
            )
            for value, label in Commitment.Status.choices
        ]
        self.fields["status"].choices = status_choices
        self.fields["status"].widget.choices = status_choices
        self.fields["status"].widget.attrs.update({
            "disabled": "disabled",
            "readonly": "readonly",
            "tabindex": "-1",
            "style": "pointer-events: none;",
        })
        self.fields["status"].initial = (
            self.instance.activity.status
            if self.instance.activity_id
            else Commitment.Status.PENDING
        )
        self.fields["activity"].required = not bool(self.instance.pk)
        if not self.instance.pk:
            self.fields["responsible"].required = False
            self.fields["responsible"].widget = forms.HiddenInput()
        for field_name in ("origin", "requester"):
            self.fields[field_name].widget.attrs["disabled"] = "disabled"
            self.fields[field_name].widget.attrs["readonly"] = "readonly"
            self.fields[field_name].widget.attrs["tabindex"] = "-1"
            self.fields[field_name].widget.attrs["style"] = (
                "pointer-events: none;"
            )
            self.fields[field_name].help_text = (
                "Se completa automáticamente desde la actividad."
            )
        self.fields["commitment_date"].widget.attrs["disabled"] = "disabled"
        self.fields["commitment_date"].widget.attrs["readonly"] = "readonly"
        self.fields["commitment_date"].widget.attrs["tabindex"] = "-1"
        self.fields["commitment_date"].widget.attrs["style"] = (
            "pointer-events: none;"
        )
        self.fields["commitment_date"].help_text = (
            "Se completa automáticamente desde el período de la meta."
        )
        if not self.instance.delegation_id:
            self.fields["responsible"].widget.attrs["disabled"] = "disabled"
        if not self.instance.delegation_id:
            self.fields["activity"].widget.attrs["disabled"] = "disabled"
        self._add_employee_metadata()
        self._add_activity_metadata()

    def _add_activity_metadata(self):
        widget = self.fields["activity"].widget
        widget.activity_metadata = {}
        for activity in self.fields["activity"].queryset.select_related(
            "goal", "goal__period", "attention", "author"
        ):
            if activity is None:
                continue
            attention = activity.attention
            widget.activity_metadata[str(activity.pk)] = {
                "delegation-id": str(
                    activity.author.delegation_id
                ),
                "goal": activity.goal.item or "",
                "origin": activity.goal.item or "",
                "commitment-date": activity.goal.period.end_date.isoformat(),
                "status": activity.status,
                "requester": (
                    attention.requester
                    if attention and attention.requester
                    else activity.contact
                ),
                "territory": (
                    attention.address
                    if attention and attention.address
                    else ""
                ),
            }

    def _add_employee_metadata(self):
        widget = self.fields["responsible"].widget
        widget.employee_delegations = {
            str(employee.pk): str(employee.delegation_id)
            for employee in self.fields["responsible"].queryset
        }

    def clean(self):
        cleaned = super().clean()
        activity = cleaned.get("activity")
        delegation = cleaned.get("delegation")
        if activity:
            cleaned["responsible"] = activity.author
            cleaned["status"] = activity.status
            cleaned["commitment_date"] = activity.goal.period.end_date
            attention = activity.attention
            if attention:
                if delegation and activity.author.delegation_id != delegation.pk:
                    self.add_error(
                        "activity",
                        "La actividad no pertenece a la delegación seleccionada.",
                    )
                cleaned["origin"] = activity.goal.item
                cleaned["requester"] = attention.requester
                cleaned["territory"] = attention.address
            else:
                cleaned["origin"] = activity.goal.item
                cleaned["requester"] = activity.contact
                cleaned["territory"] = ""
        return cleaned


class CommitmentReassignmentForm(forms.Form):
    responsible = forms.ModelChoiceField(
        queryset=Employee.objects.none(),
        label="Nuevo responsable",
        empty_label="Selecciona un responsable",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    reason = forms.CharField(
        label="Motivo de reasignación",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )

    def __init__(self, *args, employees=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["responsible"].queryset = employees or Employee.objects.none()
