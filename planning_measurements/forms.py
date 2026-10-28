import json

from django import forms
from accounts.permissions import allowed_delegation_ids

from organization.models import Employee, PositionFunction

from .models import Goal, Period, MeasurementItem

from .working_days import calculate_computable_days
import re
from decimal import Decimal


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

    
    def clean_thresholds(self):
        valor = self.cleaned_data["thresholds"].strip()

        # Conservar configuraciones históricas sin modificar.
        if self.instance.pk and valor == self.instance.thresholds:
            return valor

        patron = (
            r"Verde\s*:\s*(\d+(?:\.\d+)?)\s*,\s*"
            r"Amarillo\s*:\s*(\d+(?:\.\d+)?)\s*,\s*"
            r"Rojo\s*:\s*(\d+(?:\.\d+)?)"
        )

        resultado = re.fullmatch(
            patron, valor, flags=re.IGNORECASE
        )

        if not resultado:
            raise forms.ValidationError(
                "Utiliza el formato: "
                "Verde: 100, Amarillo: 80, Rojo: 60."
            )

        verde, amarillo, rojo = (
            Decimal(numero)
            for numero in resultado.groups()
        )

        if not (0 <= rojo < amarillo < verde <= 100):
            raise forms.ValidationError(
                "Los umbrales deben estar entre 0 y 100, "
                "cumpliendo: Verde > Amarillo > Rojo."
            )

        return valor

    
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

    def _configure_evidence_count(self):
        field = self.fields["required_evidence_count"]
        field.required = False
        field.initial = self.instance.required_evidence_count or 5

    def clean_required_evidence_count(self):
        return self.cleaned_data.get("required_evidence_count") or 5

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
            permitted = allowed_delegation_ids(
                user, "planning_measurements.change_goal" if self.instance.pk
                else "planning_measurements.add_goal"
            )
            employees = employees.filter(delegation_id__in=permitted)

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
        """Carga los ítems por ID y conserva los datos históricos."""

        items = MeasurementItem.objects.filter(
            deleted_at__isnull=True,
            is_active=True,
        ).order_by("code")

        # Si la meta ya tiene un ítem vinculado, también se
        # permite mostrarlo aunque esté inactivo o archivado.
        if self.instance.pk and self.instance.measurement_item_id:
            items = (
                MeasurementItem.objects.filter(
                    pk__in=items.values("pk")
                )
                | MeasurementItem.objects.filter(
                    pk=self.instance.measurement_item_id
                )
            ).distinct().order_by("code")

        field = self.fields["measurement_item"]
        field.queryset = items
        field.label = "Ítem de medición"
        field.required = not bool(self.instance.pk)
        field.empty_label = "Seleccione un ítem"
        field.widget.attrs["class"] = "form-select"

        # Ítems permitidos según el cargo del funcionario.
        cargos = PositionFunction.objects.filter(
            pk__in=self.fields["employee"].queryset.values_list(
                "position_id", flat=True
            )
        ).prefetch_related("catalog_items")

        items_por_cargo = {
            str(cargo.pk): [
                str(item.pk)
                for item in cargo.catalog_items.all()
            ]
            for cargo in cargos
        }

        field.widget.attrs["data-items-by-position"] = json.dumps(
            items_por_cargo
        )

        # Conserva el ítem de una meta histórica.
        field.widget.attrs["data-original-item"] = str(
            self.instance.measurement_item_id or ""
        )
        field.widget.attrs["data-original-employee"] = str(
            self.instance.employee_id or ""
        )

        
        # Identifica visualmente los ítems históricos desactivados.
        field.label_from_instance = lambda item: (
            f"{item.code} - {item.name}"
            + (
                " (histórico - inactivo)"
                if not item.is_active or item.deleted_at is not None
                else ""
            )
        )


        # El nombre antiguo se conserva para compatibilidad.
        self.fields["item"].widget = forms.HiddenInput()
        self.fields["item"].required = False

        # La unidad no se modifica manualmente.
        unit_field = self.fields["unit"]
        unit_field.required = False
        unit_field.label = "Unidad de medida (automática)"
        unit_field.widget.attrs["readonly"] = "readonly"
        unit_field.help_text = (
            "Se obtiene automáticamente del ítem seleccionado."
        )

        detalles = {}

        for item in items:
            detalles[str(item.pk)] = {
                "codigo": item.code,
                "descripcion": item.description,
                "tipo": item.get_item_type_display(),
                "unidad": item.unit,
                "formula": item.formula,
            }

        field.widget.attrs["data-item-details"] = json.dumps(
            detalles
        )

    def clean(self):
        cleaned_data = super().clean()

        item = cleaned_data.get("measurement_item")

        # Si el formulario ya tiene errores en el selector,
        # no continuar con la validación del ítem.
        if "measurement_item" in self.errors:
            return cleaned_data

        # Metas antiguas sin relación: permitir conservar
        # sus datos históricos, pero no inventar un código.
        if item is None:
            if self.instance.pk and not self.instance.measurement_item_id:
                cleaned_data["item"] = self.instance.item
                cleaned_data["unit"] = self.instance.unit
                return cleaned_data

            self.add_error(
                "measurement_item",
                "Debe seleccionar un ítem de medición."
            )
            return cleaned_data

        # Una meta vinculada puede conservar su ítem histórico,
        # aunque posteriormente haya sido desactivado o archivado.
        es_historico = (
            bool(self.instance.pk)
            and self.instance.measurement_item_id == item.pk
        )

        empleado = cleaned_data.get("employee")

        misma_meta = (
            es_historico
            and empleado is not None
            and self.instance.employee_id == empleado.pk
        )

        if empleado and not misma_meta:
            if not empleado.position.catalog_items.filter(
                pk=item.pk
            ).exists():
                self.add_error(
                    "measurement_item",
                    "Este ítem no corresponde al cargo del funcionario."
                )
                return cleaned_data


        if (
            item.deleted_at is not None or not item.is_active
        ) and not es_historico:
            self.add_error(
                "measurement_item",
                "El ítem seleccionado no está activo."
            )
            return cleaned_data

        # Conserva la unidad histórica de una meta vinculada
        # si su ítem fue desactivado o archivado.
        if es_historico and (
            item.deleted_at is not None or not item.is_active
        ):
            cleaned_data["item"] = self.instance.item
            cleaned_data["unit"] = self.instance.unit
            return cleaned_data

        # Validación del ítem activo seleccionado.
        if not item.unit or not item.unit.strip():
            self.add_error(
                "measurement_item",
                "Este ítem no tiene unidad de medida. "
                "Complétela primero en el catálogo."
            )
            return cleaned_data

        # Mantener compatibilidad con los demás módulos.
        cleaned_data["item"] = item.name
        cleaned_data["unit"] = item.unit

        return cleaned_data





class GoalForm(GoalScopeMixin, forms.ModelForm):
    version = forms.CharField(
        widget=forms.HiddenInput(),
        required=False,
    )
    class Meta:
        model = Goal
        fields = [
            "period",
            "employee",
            "position",
            "measurement_item",
            "item",
            "objective_value",
            "required_evidence_count",
            "unit",
            "weight",
        ]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and not self.is_bound:
            self.fields["version"].initial = (
                self.instance.updated_at.isoformat()
            )
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
        self._configure_evidence_count()
        self._configure_items()


class GoalInlineForm(GoalScopeMixin, forms.ModelForm):
    """Metas dentro de la ficha del período."""

    class Meta:
        model = Goal
        fields = [
            "employee",
            "position",
            "measurement_item",
            "item",
            "objective_value",
            "required_evidence_count",
            "unit",
            "weight",
        ]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_scope(user)
        self._configure_evidence_count()
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
