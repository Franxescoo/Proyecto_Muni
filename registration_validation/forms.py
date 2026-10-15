from django import forms

from organization.models import Employee
from planning_measurements.models import Goal, Period

from .models import Activity, Evidence


class BootstrapMixin:
    """Agrega clases de Bootstrap a los campos del formulario."""

    def _apply_bootstrap(self):
        for field in self.fields.values():
            if isinstance(field.widget, forms.Select):
                css_class = "form-select"

            elif isinstance(field.widget, forms.CheckboxInput):
                css_class = "form-check-input"

            else:
                css_class = "form-control"

            field.widget.attrs["class"] = css_class


class ActivityForm(BootstrapMixin, forms.ModelForm):
    STATUS_CHOICES = [
        ("Pending", "Pendiente"),
        ("In progress", "En progreso"),
        ("Completed", "Completada"),
    ]

    status = forms.ChoiceField(
        label="Estado",
        choices=STATUS_CHOICES,
    )

    class Meta:
        model = Activity

        fields = [
            "goal",
            "author",
            "date",
            "request_problem",
            "action",
            "contact",
            "phone",
            "status",
        ]

        labels = {
            "goal": "Meta",
            "author": "Funcionario",
            "date": "Fecha",
            "request_problem": "Solicitud o problema",
            "action": "Acción realizada",
            "contact": "Contacto",
            "phone": "Teléfono",
            "status": "Estado",
        }

        widgets = {
            "date": forms.DateInput(
                attrs={
                    "type": "date",
                },
                format="%Y-%m-%d",
            ),

            "request_problem": forms.Textarea(
                attrs={
                    "rows": 3,
                },
            ),

            "action": forms.Textarea(
                attrs={
                    "rows": 3,
                },
            ),

            "contact": forms.TextInput(
                attrs={
                    "placeholder": (
                        "Nombre o medio de contacto"
                    ),
                },
            ),

            "phone": forms.TextInput(
                attrs={
                    "placeholder": (
                        "Ej.: +56 9 1234 5678"
                    ),
                },
            ),
        }

    def __init__(
        self,
        *args,
        user=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        goals = (
            Goal.objects
            .filter(
                deleted_at__isnull=True,
                period__deleted_at__isnull=True,
                period__status=Period.Status.ACTIVE,
            )
            .select_related(
                "employee",
                "period",
            )
            .order_by("item")
        )

        employees = (
            Employee.objects
            .filter(
                deleted_at__isnull=True,
            )
            .select_related(
                "delegation",
                "position",
            )
            .order_by("name")
        )

        if (
            user is not None
            and not user.is_superuser
        ):
            profile = getattr(
                user,
                "profile",
                None,
            )

            delegation_id = (
                profile.delegation_id
                if profile is not None
                else None
            )

            if delegation_id is None:
                goals = goals.none()
                employees = employees.none()

            else:
                goals = goals.filter(
                    employee__delegation_id=(
                        delegation_id
                    ),
                )

                employees = employees.filter(
                    delegation_id=delegation_id,
                )

        self.fields["goal"].queryset = goals
        self.fields["author"].queryset = employees

        self._apply_bootstrap()

    def clean(self):
        cleaned_data = super().clean()

        goal = cleaned_data.get("goal")

        if goal is not None:
            period = goal.period

            if period.deleted_at is not None:
                raise forms.ValidationError(
                    "No se puede registrar o modificar "
                    "una actividad asociada a un período "
                    "archivado."
                )

            if period.status == Period.Status.CLOSED:
                raise forms.ValidationError(
                    "No se puede registrar o modificar "
                    "una actividad asociada a un período "
                    "cerrado."
                )

        return cleaned_data


class EvidenceForm(
    BootstrapMixin,
    forms.ModelForm,
):
    date = forms.DateTimeField(
        label="Fecha y hora",
        input_formats=[
            "%Y-%m-%dT%H:%M",
        ],
        widget=forms.DateTimeInput(
            attrs={
                "type": "datetime-local",
            },
            format="%Y-%m-%dT%H:%M",
        ),
    )

    class Meta:
        model = Evidence

        fields = [
            "code",
            "activity",
            "author",
            "file_link",
            "file",
            "date",
            "review_status",
        ]

        labels = {
            "code": "Código",
            "activity": "Actividad",
            "author": "Funcionario",
            "file_link": "Enlace de evidencia",
            "file": "Archivo de evidencia",
            "date": "Fecha y hora",
            "review_status": "Estado de revisión",
        }

        widgets = {
            "code": forms.TextInput(
                attrs={
                    "placeholder": (
                        "Ej.: EVID-001"
                    ),
                },
            ),

            "file_link": forms.TextInput(
                attrs={
                    "placeholder": (
                        "https://..."
                    ),
                },
            ),

            "file": forms.ClearableFileInput(
                attrs={
                    "accept": (
                        ".pdf,.jpg,.jpeg,"
                        ".png,.doc,.docx"
                    ),
                },
            ),

            "review_status": forms.TextInput(
                attrs={
                    "placeholder": (
                        "Ej.: Pending"
                    ),
                },
            ),
        }

    def __init__(
        self,
        *args,
        user=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        activities = (
            Activity.objects
            .filter(
                deleted_at__isnull=True,
                goal__deleted_at__isnull=True,
                goal__period__deleted_at__isnull=True,
                goal__period__status=(
                    Period.Status.ACTIVE
                ),
            )
            .select_related(
                "goal",
                "goal__period",
                "author",
                "author__delegation",
            )
            .order_by(
                "-date",
                "activity_id",
            )
        )

        employees = (
            Employee.objects
            .filter(
                deleted_at__isnull=True,
            )
            .select_related(
                "delegation",
                "position",
            )
            .order_by("name")
        )

        if (
            user is not None
            and not user.is_superuser
        ):
            profile = getattr(
                user,
                "profile",
                None,
            )

            delegation_id = (
                profile.delegation_id
                if profile is not None
                else None
            )

            if delegation_id is None:
                activities = activities.none()
                employees = employees.none()

            else:
                activities = activities.filter(
                    author__delegation_id=(
                        delegation_id
                    ),
                )

                employees = employees.filter(
                    delegation_id=delegation_id,
                )

        self.fields[
            "activity"
        ].queryset = activities

        self.fields[
            "author"
        ].queryset = employees

        self.fields["file"].help_text = (
            "Formatos permitidos: PDF, JPG, JPEG, "
            "PNG, DOC y DOCX. Tamaño máximo: 5 MB."
        )

        self.fields["file_link"].required = False
        self.fields["file"].required = False

        self._apply_bootstrap()

    def clean(self):
        cleaned_data = super().clean()

        activity = cleaned_data.get("activity")
        file = cleaned_data.get("file")
        file_link = (
            cleaned_data
            .get(
                "file_link",
                "",
            )
            .strip()
        )

        if activity is not None:
            period = activity.goal.period

            if period.deleted_at is not None:
                raise forms.ValidationError(
                    "No se puede registrar o modificar "
                    "una evidencia asociada a un período "
                    "archivado."
                )

            if period.status == Period.Status.CLOSED:
                raise forms.ValidationError(
                    "No se puede registrar o modificar "
                    "una evidencia asociada a un período "
                    "cerrado."
                )

        existing_file = None

        if (
            self.instance
            and self.instance.pk
            and self.instance.file
        ):
            existing_file = self.instance.file

        if (
            not file
            and not existing_file
            and not file_link
        ):
            raise forms.ValidationError(
                "Debes adjuntar un archivo o ingresar "
                "un enlace de evidencia."
            )

        return cleaned_data