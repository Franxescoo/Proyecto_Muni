from django import forms
from django.contrib.auth import get_user_model

from organization.models import Delegation, Employee
from registration_validation.models import Activity

from .models import Commitment, MonitoringSettings


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
            "origin": "Origen o meta",
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
        self.fields["activity"].empty_label = "Sin actividad (compromiso manual)"
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
        self.fields["status"].required = False
        # Django must ignore injected POST values, not only disable the HTML widget.
        self.fields["status"].disabled = True
        self.fields["status"].initial = (
            self.instance.status
            if self.instance.pk
            else Commitment.Status.PENDING
        )
        self.fields["activity"].required = False
        self.fields["activity"].help_text = (
            "Opcional: si proviene de una actividad, selecciónala. "
            "Para solicitudes internas/externas sin actividad, indica responsable y origen."
        )
        if not self.instance.pk:
            self.fields["responsible"].required = False
            self.fields["responsible"].help_text = (
                "Necesario si el compromiso no está asociado a una actividad."
            )
        for field_name in ("origin", "requester"):
            self.fields[field_name].required = False
            self.fields[field_name].help_text = (
                "Se completa desde la actividad o se escribe si el compromiso es manual."
            )
            if self.instance.pk:
                # La fuente y el solicitante original son referencias históricas.
                self.fields[field_name].disabled = True
        # On creation the period end is the default, not an unchangeable due date.
        # Existing due dates remain locked to prevent silent alteration of alerts.
        self.fields["commitment_date"].required = False
        if self.instance.pk:
            self.fields["commitment_date"].disabled = True
        self.fields["commitment_date"].help_text = (
            "Fecha acordada; si se omite, se utiliza el término del período."
            if not self.instance.pk else
            "Fecha original del compromiso (no editable desde este formulario)."
        )
        if self.instance.pk:
            # A normal edit cannot bypass reassignment and change historical links.
            for field_name in ("delegation", "responsible", "activity"):
                self.fields[field_name].disabled = True
            self.fields["responsible"].help_text = (
                "Para cambiarlo utiliza Reasignación; queda registrado en el historial."
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
            if attention is None:
                attention = activity.assigned_attentions.filter(
                    deleted_at__isnull=True
                ).order_by("pk").first()
            widget.activity_metadata[str(activity.pk)] = {
                "delegation-id": str(
                    activity.author.delegation_id
                ),
                "goal": activity.goal.item or "",
                "origin": activity.goal.item or "",
                "commitment-date": activity.goal.period.end_date.isoformat(),
                "status": activity.status,
                "responsible-id": str(activity.author_id),
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
        if self.instance.pk:
            # Ninguna edición normal altera vínculos, responsable, fuente ni plazo.
            for field_name in (
                "responsible", "delegation", "activity", "status",
                "commitment_date", "origin", "requester",
            ):
                cleaned[field_name] = getattr(self.instance, field_name)
            return cleaned

        activity = cleaned.get("activity")
        delegation = cleaned.get("delegation")
        if activity:
            duplicate = Commitment.objects.filter(
                activity=activity, deleted_at__isnull=True,
            ).exists()
            if duplicate:
                self.add_error(
                    "activity", "Ya existe un compromiso asociado a esta actividad."
                )
            if delegation and activity.author.delegation_id != delegation.pk:
                self.add_error(
                    "activity", "La actividad no pertenece a la delegación seleccionada."
                )
            cleaned["responsible"] = activity.author
            cleaned["commitment_date"] = (
                cleaned.get("commitment_date") or activity.goal.period.end_date
            )
            cleaned["origin"] = activity.goal.item
            attention = activity.attention
            if attention is None:
                attention = activity.assigned_attentions.filter(
                    deleted_at__isnull=True
                ).order_by("pk").first()
            cleaned["requester"] = (
                attention.requester if attention and attention.requester
                else activity.contact
            )
            if attention and attention.address and not cleaned.get("territory"):
                cleaned["territory"] = attention.address
        else:
            # Los compromisos internos/externos también pueden registrarse
            # sin una actividad previa. No se atribuyen a una meta artificial.
            for field_name, label in (
                ("responsible", "responsable"),
                ("origin", "origen"),
                ("requester", "solicitante"),
                ("commitment_date", "fecha comprometida"),
            ):
                if not cleaned.get(field_name):
                    self.add_error(field_name, f"Indica el {label} del compromiso.")
        cleaned["status"] = Commitment.Status.PENDING
        return cleaned


class CommitmentReassignmentForm(forms.Form):
    CAUSE_CHOICES = (
        ("absence", "Ausencia del funcionario"),
        ("overdue", "Compromiso vencido"),
    )
    cause = forms.ChoiceField(
        choices=CAUSE_CHOICES,
        label="Causa de la reasignación",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    responsible = forms.ModelChoiceField(
        queryset=Employee.objects.none(),
        label="Nuevo responsable",
        empty_label="Selecciona un responsable",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    reason = forms.CharField(
        label="Justificación de la reasignación",
        help_text="Explica brevemente la ausencia o el vencimiento. Es obligatorio.",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )

    def __init__(self, *args, employees=None, is_overdue=False,
                 employee_unavailable=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["responsible"].queryset = (
            employees if employees is not None else Employee.objects.none()
        )
        causes = []
        if employee_unavailable:
            causes.append(self.CAUSE_CHOICES[0])  # Ausencia: solo Inactivo o Con licencia.
        if is_overdue:
            causes.append(self.CAUSE_CHOICES[1])  # Vencimiento: regla independiente.
        self.fields["cause"].choices = causes


class MonitoringSettingsForm(forms.ModelForm):
    class Meta:
        model = MonitoringSettings
        fields = (
            "low_compliance_threshold", "inactivity_workdays", "due_soon_days",
            "positive_adjustment_max", "negative_adjustment_max", "recipient_users",
        )
        labels = {
            "low_compliance_threshold": "Umbral de cumplimiento bajo (%)",
            "inactivity_workdays": "Días hábiles sin actividad",
            "due_soon_days": "Días de aviso antes del vencimiento",
            "positive_adjustment_max": "Máximo de bonificación (+ puntos)",
            "negative_adjustment_max": "Máximo de penalización (- puntos)",
            "recipient_users": "Destinatarios adicionales de avisos de compromisos vencidos",
        }
        widgets = {
            "recipient_users": forms.SelectMultiple(attrs={"class": "form-select", "size": 6}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["recipient_users"].queryset = get_user_model().objects.filter(
            is_active=True,
        ).order_by("username")
        for key, field in self.fields.items():
            field.widget.attrs.setdefault("class", "form-control")
            if key != "recipient_users":
                field.widget.attrs.setdefault("step", "1" if "days" in key or "workdays" in key else "0.01")
