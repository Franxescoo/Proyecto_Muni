import json

from django import forms

from organization.models import Employee, PositionFunction

from .models import Goal, Period, MeasurementItem

from .working_days import calculate_computable_days


class BootstrapMixin:
    """Agrega las clases de Bootstrap a los campos."""

    
    def _apply_bootstrap(self):
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                css = "form-check-input"
            elif isinstance(field.widget, forms.Select):
                css = "form-select"
            else:
                css = "form-control"

            field.widget.attrs["class"] = css





class PeriodForm(BootstrapMixin, forms.ModelForm):

    status = forms.ChoiceField(
        label="Estado",
        choices=Period.Status.choices,
    )

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

        # El administrador no ingresa manualmente los días.
        self.fields["computable_days"].required = False

        self.fields["computable_days"].widget.attrs.update({
            "readonly": "readonly",
            "placeholder": "Se calcula al guardar",
        })

        self.fields["computable_days"].help_text = (
            "Calculado automáticamente: lunes a viernes, "
            "excluyendo feriados de Chile."
        )

    def clean(self):
        cleaned_data = super().clean()

        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")

        if start_date and end_date:

            if end_date < start_date:
                self.add_error(
                    "end_date",
                    "La fecha de término no puede ser "
                    "anterior al inicio."
                )

            else:
                computable_days = calculate_computable_days(
                    start_date,
                    end_date
                )

                if computable_days <= 0:
                    self.add_error(
                        "computable_days",
                        "El período debe tener al menos "
                        "un día hábil no feriado."
                    )

                else:
                    cleaned_data["computable_days"] = (
                        computable_days
                    )

        return cleaned_data






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
    
    def _configure_items(self):
        """Carga los ítems del catálogo y protege la unidad."""

        items = MeasurementItem.objects.filter(
            deleted_at__isnull=True,
            is_active=True,
        ).order_by("code")

        # Los ítems se siguen guardando como texto en Goal.item.
        choices = [("", "Seleccione un ítem")]

        
        unidades = {}
        detalles = {}

        for item in items:
            choices.append(
                (item.name, f"{item.code} - {item.name}")
            )

            unidades[item.name] = item.unit

            detalles[item.name] = {
                "codigo": item.code,
                "descripcion": item.description,
                "tipo": item.get_item_type_display(),
                "unidad": item.unit,
                "formula": item.formula,
            }


        # Permite mostrar ítems históricos al editar una meta.
        if self.instance.pk:
            nombre_actual = self.instance.item

            if nombre_actual and nombre_actual not in unidades:
                choices.append(
                    (nombre_actual, f"{nombre_actual} (histórico)")
                )

        self.fields["item"].widget = forms.Select(
            choices=choices
        )
        self.fields["item"].widget.attrs["class"] = "form-select"

        self.fields["item"].label = "Ítem de medición"
        self.fields["item"].help_text = (
            "Seleccione un ítem registrado en el catálogo."
        )

        self.fields["unit"].required = False
        self.fields["unit"].label = "Unidad de medida (automática)"
        self.fields["unit"].widget.attrs["readonly"] = "readonly"
        self.fields["unit"].help_text = (
            "Se obtiene automáticamente del ítem seleccionado."
        )

        self.fields["item"].widget.attrs[
            "data-item-units"
        ] = json.dumps(unidades)
        
        self.fields["item"].widget.attrs[
            "data-item-details"
        ] = json.dumps(detalles)


    def clean(self):
        cleaned_data = super().clean()

        nombre = cleaned_data.get("item")

        if not nombre:
            return cleaned_data

        items = MeasurementItem.objects.filter(
            name=nombre,
            deleted_at__isnull=True,
        )

        if items.count() != 1:
            self.add_error(
                "item",
                "El ítem debe existir una sola vez en el catálogo."
            )
            return cleaned_data

        item = items.first()

        if not item.is_active:
            self.add_error(
                "item",
                "El ítem seleccionado no está activo."
            )
            return cleaned_data

        if not item.unit.strip():
            self.add_error(
                "item",
                "Este ítem no tiene unidad de medida. "
                "Complétela primero en el catálogo."
            )
            return cleaned_data

        # La unidad real se obtiene del catálogo,
        # nunca del valor enviado por el navegador.
        cleaned_data["unit"] = item.unit

        return cleaned_data



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

        periods = Period.objects.filter(
            deleted_at__isnull=True
        )

        if self.instance.pk:
            # Al consultar o editar una meta existente,
            # permite mostrar su período.
            self.fields["period"].queryset = periods
        else:
            # Al crear una meta, muestra solo períodos activos.
            self.fields["period"].queryset = periods.filter(
                status=Period.Status.ACTIVE
            )

        self._apply_scope(user)
        self._configure_items()


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
        self._configure_items()


class MeasurementItemForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = MeasurementItem

        fields = [
            "code",
            "name",
            "description",
            "item_type",
            "unit",
            "formula",
            "is_active",
        ]

        widgets = {
            "description": forms.Textarea(
                attrs={"rows": 3}
            ),
            "formula": forms.Textarea(
                attrs={"rows": 3}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap()

        self.fields["formula"].help_text = (
            "Obligatoria para ítems porcentuales."
        )

