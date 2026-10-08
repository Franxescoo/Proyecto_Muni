from django import forms

from organization.models import Employee
from planning_measurements.models import Goal

from .models import Activity


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
        }

        widgets = {
            "date": forms.DateInput(
                attrs={"type": "date"},
                format="%Y-%m-%d",
            ),
            "request_problem": forms.Textarea(
                attrs={"rows": 3},
            ),
            "action": forms.Textarea(
                attrs={"rows": 3},
            ),
            "contact": forms.TextInput(
                attrs={
                    "placeholder": "Nombre o medio de contacto",
                },
            ),
            "phone": forms.TextInput(
                attrs={
                    "placeholder": "Ej.: +56 9 1234 5678",
                },
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        goals = (
            Goal.objects
            .filter(
                deleted_at__isnull=True,
                period__deleted_at__isnull=True,
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

        if user is not None and not user.is_superuser:
            profile = getattr(user, "profile", None)

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
                    employee__delegation_id=delegation_id,
                )

                employees = employees.filter(
                    delegation_id=delegation_id,
                )

        self.fields["goal"].queryset = goals
        self.fields["author"].queryset = employees

        self._apply_bootstrap()