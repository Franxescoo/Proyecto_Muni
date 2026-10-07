import json

from django import forms

from organization.models import Employee, PositionFunction

from .models import Goal, Period


class BootstrapMixin:
    """Agrega las clases de Bootstrap a los campos."""

    def _apply_bootstrap(self):
        for field in self.fields.values():
            css = (
                "form-select"
                if isinstance(field.widget, forms.Select)
                else "form-control"
            )
            field.widget.attrs["class"] = css


class PeriodForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Period
        fields = [
            "start_date",
            "end_date",
            "computable_days",
            "status",
            "thresholds",
            "parameters_version",
        ]
        widgets = {
            "start_date": forms.DateInput(
                attrs={"type": "date"},
                format="%Y-%m-%d",
            ),
            "end_date": forms.DateInput(
                attrs={"type": "date"},
                format="%Y-%m-%d",
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap()


class GoalScopeMixin(BootstrapMixin):
    """Limita funcionarios y asigna su cargo automáticamente."""

    def _apply_scope(self, user):
        self.fields["position"].queryset = (
            PositionFunction.objects.filter(
                deleted_at__isnull=True
            )
        )

        employees = Employee.objects.filter(
            deleted_at__isnull=True
        ).select_related("position")

        if user is not None and not user.is_superuser:
            profile = getattr(user, "profile", None)
            delegation_id = (
                profile.delegation_id if profile else None
            )
            employees = employees.filter(
                delegation_id=delegation_id
            )

        self.fields["employee"].queryset = employees
        self._apply_bootstrap()

        # Relaciona cada funcionario permitido con su cargo.
        positions = {
            str(employee.pk): employee.position_id
            for employee in employees
        }

        self.fields["employee"].widget.attrs[
            "data-goal-positions"
        ] = json.dumps(positions)

        # El usuario puede ver el cargo, pero no cambiarlo.
        position_field = self.fields["position"]
        position_field.disabled = True
        position_field.required = False
        position_field.label = "Cargo (automático)"
        position_field.help_text = (
            "Se asigna según el funcionario seleccionado."
        )

        # Cargo inicial al crear, editar o reenviar el formulario.
        selected = (
            self.data.get(self.add_prefix("employee"))
            if self.is_bound
            else self.initial.get("employee")
        )
        selected = getattr(selected, "pk", selected)
        self.initial["position"] = positions.get(str(selected))

    def clean_position(self):
        # El funcionario ya fue validado contra el queryset permitido.
        employee = self.cleaned_data.get("employee")

        if employee is None:
            return None

        position = employee.position

        if position.deleted_at is not None:
            raise forms.ValidationError(
                "El cargo del funcionario está archivado. "
                "Solicita su actualización."
            )

        # El servidor obtiene el cargo real del funcionario.
        return position


class GoalForm(GoalScopeMixin, forms.ModelForm):
    class Meta:
        model = Goal
        fields = [
            "period",
            "employee",
            "position",
            "item",
            "objective_value",
            "unit",
            "weight",
        ]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["period"].queryset = Period.objects.filter(
            deleted_at__isnull=True
        )

        self._apply_scope(user)


class GoalInlineForm(GoalScopeMixin, forms.ModelForm):
    """Metas dentro de la ficha del período."""

    class Meta:
        model = Goal
        fields = [
            "employee",
            "position",
            "item",
            "objective_value",
            "unit",
            "weight",
        ]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_scope(user)
