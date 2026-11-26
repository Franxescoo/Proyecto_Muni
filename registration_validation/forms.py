from django import forms
from django.core.validators import MaxLengthValidator
from accounts.permissions import allowed_delegation_ids
from django.core.validators import FileExtensionValidator
from django.db.models import Q
from django.utils import timezone
from organization.models import Delegation, Employee
from citizen_registry.models import Citizen
from planning_measurements.models import Goal, Period
from .models import (
    Activity,
    Evidence,
    Validation,
    AttentionType,
    ActivityType,
    SubAttention,
    AttentionEntry,
    Service,
    MIN_EVIDENCE_FILES,
    MAX_EVIDENCE_FILES,
    MAX_EVIDENCE_TOTAL_SIZE,
    EVIDENCE_ALLOWED_EXTENSIONS,
    validate_evidence_file_link,
)

# ---------------------------------------------------------
# Estilos reutilizables

# ---------------------------------------------------------


class BootstrapMixin:
    """Agrega clases de Bootstrap a los campos del formulario."""

    def _apply_bootstrap(self):
        for field in self.fields.values():
            # Traduce los textos vacíos de los selectores de relaciones.
            # No cambia el valor que se guarda en la base de datos.
            if isinstance(field, forms.ModelChoiceField):
                if field.empty_label == "---------":
                    field.empty_label = "Seleccione una opción"
            if isinstance(field.widget, forms.Select):
                css_class = "form-select"
                # Útil si la plantilla utiliza un selector enriquecido.
                field.widget.attrs.setdefault(
                    "data-placeholder", "Seleccione una opción"
                )
            elif isinstance(field.widget, forms.CheckboxInput):
                css_class = "form-check-input"
            else:
                css_class = "form-control"
            field.widget.attrs["class"] = css_class


def _set_text_limit(field, limit, label):
    """Aplica el límite tanto al formulario como al control HTML."""
    field.widget.attrs["maxlength"] = limit
    if field.required:
        field.error_messages["required"] = "Este campo es obligatorio."
    field.validators = [
        validator
        for validator in field.validators
        if not isinstance(validator, MaxLengthValidator)
    ]
    field.validators.append(
        MaxLengthValidator(
            limit,
            message=f"{label} no puede superar los {limit} caracteres.",
        )
    )


def _set_form_text_limits(form, limits):
    for field_name, limit, label in limits:
        _set_text_limit(form.fields[field_name], limit, label)


# ---------------------------------------------------------
# Campos para múltiples archivos

# ---------------------------------------------------------


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """
    Permite recibir y validar varios archivos
    desde un único campo del formulario.
    """

    def clean(self, data, initial=None):
        if not data:
            if self.required:
                raise forms.ValidationError(
                    "Debes seleccionar archivos."
                )
            return []
        if not isinstance(data, (list, tuple)):
            data = [data]
        cleaned_files = []
        for uploaded_file in data:
            cleaned_file = super().clean(uploaded_file)
            cleaned_files.append(cleaned_file)
        return cleaned_files

# ---------------------------------------------------------
# Formulario de Actividades

# ---------------------------------------------------------


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
    # Una actividad puede gestionar varias atenciones. La relación persistida
    # está en AttentionEntry.activity (una atención tiene una actividad).
    attentions = forms.ModelMultipleChoiceField(
        label="Atenciones asociadas",
        queryset=AttentionEntry.objects.none(),
        widget=forms.CheckboxSelectMultiple(),
        required=False,
        help_text="Marca una o varias atenciones existentes. También puedes vincular nuevas desde Ingreso de Atención.",
    )

    class Meta:
        model = Activity
        fields = [
            "goal",
            "author",
            "activity_type",
            "attentions",
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
            "activity_type": "Tipo de actividad",
            "attentions": "Atenciones asociadas",
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
        if user is not None and not user.is_superuser:
            action = "change" if self.instance.pk else "add"
            permitted = allowed_delegation_ids(user, f"registration_validation.{action}_activity")
            goals = goals.filter(employee__delegation_id__in=permitted)
            employees = employees.filter(delegation_id__in=permitted)
        self.fields["goal"].queryset = goals
        self.fields["author"].queryset = employees
        attentions = (
            AttentionEntry.objects
            .filter(deleted_at__isnull=True)
            .select_related("delegation", "citizen")
            .order_by("-registration_date", "attention_entry_id")
        )
        if user is not None and not user.is_superuser:
            permitted = allowed_delegation_ids(
                user,
                "registration_validation.change_activity"
                if self.instance.pk
                else "registration_validation.add_activity",
            )
            attentions = attentions.filter(delegation_id__in=permitted)
        # Evitar transferencias implícitas entre actividades. Si la atención
        # ya tiene actividad, únicamente puede marcarla esa misma actividad.
        attentions = attentions.filter(
            Q(activity__isnull=True) | Q(activity_id=self.instance.pk)
        ).distinct()
        self.fields["attentions"].queryset = attentions
        self.fields["attentions"].label_from_instance = (
            lambda attention: (
                f"#{attention.pk} · {attention.requester} - "
                f"{attention.subject.strip() if attention.subject else 'Sin asunto'} "
                f"({attention.get_status_display()})"
            )
        )
        if self.instance.pk:
            self.fields["attentions"].initial = list(
                AttentionEntry.objects.filter(
                    activity=self.instance, deleted_at__isnull=True
                ).values_list("pk", flat=True)
            )
            # Compatibilidad con vínculos anteriores a este cambio.
            if self.instance.attention_id and not self.fields["attentions"].initial:
                self.fields["attentions"].initial = [self.instance.attention_id]

        # Mostrar solamente tipos de actividad activos
        # y que no estén archivados.
        activity_types = ActivityType.objects.filter(
            status=True,
            deleted_at__isnull=True,
        )

        # Si estamos editando una actividad, conservar
        # su tipo anterior aunque esté inactivo.
        if self.instance.pk and self.instance.activity_type_id:
            activity_types = ActivityType.objects.filter(
                Q(status=True, deleted_at__isnull=True)
                | Q(pk=self.instance.activity_type_id)
            )

        self.fields["activity_type"].queryset = (
            activity_types.order_by("name")
        )

        # Obligatorio para actividades nuevas.
        # Opcional para actividades antiguas sin clasificar.
        self.fields["activity_type"].required = (
            self.instance.pk is None
        )

        _set_form_text_limits(
            self,
            (
                ("request_problem", 2000, "La solicitud o problema"),
                ("action", 2000, "La acción realizada"),
                ("contact", 150, "El contacto"),
                ("phone", 20, "El teléfono"),
            ),
        )
        self._apply_bootstrap()
        # SGR-CASILLAS-VISIBLES-20261125
        # El BootstrapMixin original asigna 'form-control' al CONTENEDOR
        # de CheckboxSelectMultiple, en vez de tratarlo como una lista.
        # Este cambio solo modifica el estilo; no los permisos ni el queryset.
        self.fields["attentions"].widget.attrs["class"] = (
            "sgr-attention-checkbox-options"
        )

    def clean(self):
        cleaned_data = super().clean()
        goal = cleaned_data.get("goal")
        selected = cleaned_data.get("attentions")
        author = cleaned_data.get("author")
        # La actividad puede crearse antes de su primera atención. Así no se
        # produce un bloqueo circular al registrar una atención nueva.
        if selected is not None and author is not None:
            for attention in selected:
                if attention.deleted_at is not None:
                    self.add_error("attentions", "Hay una atención archivada.")
                    break
                if attention.delegation_id != author.delegation_id:
                    self.add_error(
                        "attentions", "Las atenciones deben pertenecer a la "
                        "delegación del funcionario autor.")
                    break
                if attention.activity_id not in (None, self.instance.pk):
                    self.add_error("attentions", "Una atención ya pertenece a otra actividad.")
                    break
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
        # SGR-REGLAS-ACTIVIDADES-20261119: todas las metas comparten el cupo.
        from .activity_rules import daily_capacity_exceeded
        employee = cleaned_data.get("author")
        day = cleaned_data.get("date")
        if employee is not None and day is not None:
            if daily_capacity_exceeded(
                employee.pk, day, activity_pk=self.instance.pk,
            ):
                self.add_error(
                    "date",
                    "El funcionario ya tiene siete actividades registradas "
                    "en este día, incluyendo las de otras metas.",
                )
        return cleaned_data

# ---------------------------------------------------------
# Formulario de Evidencias

# ---------------------------------------------------------


class EvidenceForm(BootstrapMixin, forms.ModelForm):
    # Los códigos almacenados se conservan para no romper filtros o registros.
    REVIEW_STATUS_CHOICES = [
        ("Pending", "Pendiente"),
        ("In review", "En revisión"),
        ("Observed", "Con observaciones"),
        ("Approved", "Aprobada"),
        ("Rejected", "Rechazada"),
    ]
    # CharField conserva la validación histórica del largo máximo (50).
    # El widget muestra únicamente las opciones disponibles y el método
    # clean_review_status verifica la selección también en el servidor.
    review_status = forms.CharField(
        label="Estado de revisión",
        widget=forms.Select(
            choices=[
                ("", "Seleccione un estado de revisión"),
                *REVIEW_STATUS_CHOICES,
            ],
        ),
        required=True,
        error_messages={
            "required": "Selecciona un estado de revisión.",
        },
    )

    code = forms.CharField(
        label="Código",
        required=False,
        disabled=True,
        help_text="Código único generado automáticamente.",
    )

    date = forms.DateTimeField(
        label="Fecha y hora",
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local"},
            format="%Y-%m-%dT%H:%M",
        ),
    )
    new_files = MultipleFileField(
        label="Archivos de evidencia",
        required=False,
        widget=MultipleFileInput(
            attrs={
                "multiple": True,
                "accept": ".pdf,.jpg,.jpeg,.png,.doc,.docx",
            },
        ),
        validators=[
            FileExtensionValidator(
                allowed_extensions=EVIDENCE_ALLOWED_EXTENSIONS
            ),
        ],
        help_text=(
            "Debes mantener entre 2 y 5 archivos por evidencia. "
            "El peso total no puede superar 50 MB. "
            "Formatos permitidos: PDF, JPG, JPEG, PNG, DOC y DOCX."
        ),
    )

    class Meta:
        model = Evidence
        fields = [
            "activity",
            "author",
            "file_link",
            "date",
            "review_status",
        ]
        labels = {
            "activity": "Actividad",
            "author": "Funcionario",
            "file_link": "Enlace de evidencia",
            "date": "Fecha y hora",
            "review_status": "Estado de revisión",
        }
        widgets = {
            "file_link": forms.TextInput(
                attrs={"placeholder": "https://..."},
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        activities = (
            Activity.objects
            .filter(
                deleted_at__isnull=True,
                goal__deleted_at__isnull=True,
                goal__period__deleted_at__isnull=True,
                goal__period__status=Period.Status.ACTIVE,
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
        if user is not None and not user.is_superuser:
            action = "change" if self.instance.pk else "add"
            permitted = allowed_delegation_ids(user, f"registration_validation.{action}_evidence")
            activities = activities.filter(author__delegation_id__in=permitted)
            employees = employees.filter(delegation_id__in=permitted)
        self.fields["activity"].queryset = activities
        self.fields["author"].queryset = employees
        self.fields["file_link"].required = False
        self.fields["review_status"].help_text = (
            "Selecciona el estado correspondiente a la revisión de la evidencia."
        )
        # Al editar una evidencia histórica, permite conservar su estado
        # original aunque no forme parte de los estados predefinidos nuevos.
        previous_status = (
            (self.instance.review_status or "").strip()
            if self.instance.pk else ""
        )
        status_widget = self.fields["review_status"].widget
        allowed_status_values = {
            value for value, _label in status_widget.choices
        }
        if previous_status and previous_status not in allowed_status_values:
            current_choices = list(status_widget.choices)
            current_choices.append(
                (previous_status, f"{previous_status} (estado anterior)")
            )
            status_widget.choices = current_choices
        # Archivos que se seleccionan para quitar.
        self.files_to_remove = []
        # Archivos que ya pertenecen a esta evidencia.
        self.existing_evidence_files = []
        if self.instance.pk:
            self.existing_evidence_files = list(
                self.instance.files.filter(
                    deleted_at__isnull=True,
                )
            )
        _set_form_text_limits(
            self,
            (
                ("code", 100, "El código"),
                ("file_link", 500, "El enlace de evidencia"),
                ("review_status", 50, "El estado de revisión"),
            ),
        )
        self._apply_bootstrap()

    def clean_review_status(self):
        """Acepta solo estados del selector, incluso al manipular el POST."""
        status = self.cleaned_data["review_status"]
        allowed_values = {
            value for value, _label in self.fields["review_status"].widget.choices
            if value
        }
        if status not in allowed_values:
            raise forms.ValidationError(
                "Selecciona un estado de revisión válido.",
                code="invalid_choice",
            )
        return status

    def clean_file_link(self):
        file_link = (self.cleaned_data.get("file_link") or "").strip()
        try:
            validate_evidence_file_link(file_link)
        except forms.ValidationError as exc:
            raise forms.ValidationError(
                exc.messages,
                code="invalid",
            ) from exc
        return file_link

    def clean(self):
        cleaned_data = super().clean()
        activity = cleaned_data.get("activity")
        uploaded_files = cleaned_data.get("new_files", [])
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
        if "new_files" in self.errors:
            return cleaned_data
        raw_ids = (
            self.data.getlist("remove_file_ids")
            if hasattr(self.data, "getlist")
            else self.data.get("remove_file_ids", [])
        )
        if isinstance(raw_ids, str):
            raw_ids = [raw_ids]
        try:
            ids_to_remove = {
                int(value) for value in raw_ids
            }
        except (TypeError, ValueError):
            raise forms.ValidationError(
                "La selección de archivos a eliminar no es válida."
            )
        existing_by_id = {
            item.pk: item
            for item in self.existing_evidence_files
        }
        if not ids_to_remove.issubset(existing_by_id.keys()):
            raise forms.ValidationError(
                "Se seleccionó un archivo que no pertenece "
                "a esta evidencia."
            )
        self.files_to_remove = [
            existing_by_id[file_id]
            for file_id in ids_to_remove
        ]
        remaining_files = [
            item
            for item in self.existing_evidence_files
            if item.pk not in ids_to_remove
        ]
        # Compatibilidad con el antiguo Evidence.file.
        legacy_file = None
        if self.instance.pk and self.instance.file:
            legacy_file = self.instance.file
        all_existing_names = {
            item.file.name
            for item in self.existing_evidence_files
        }
        if (
            legacy_file
            and legacy_file.name in all_existing_names
        ):
            legacy_file = None
        final_count = (
            len(remaining_files)
            + len(uploaded_files)
            + (1 if legacy_file else 0)
        )
        if final_count < MIN_EVIDENCE_FILES:
            raise forms.ValidationError(
                "La evidencia debe tener al menos "
                f"{MIN_EVIDENCE_FILES} archivos. "
                f"Actualmente quedaría con {final_count}."
            )
        if final_count > MAX_EVIDENCE_FILES:
            raise forms.ValidationError(
                "La evidencia puede tener como máximo "
                f"{MAX_EVIDENCE_FILES} archivos. "
                f"Actualmente quedaría con {final_count}."
            )
        total_size = sum(
            uploaded_file.size
            for uploaded_file in uploaded_files
        )
        try:
            for existing_file in remaining_files:
                total_size += existing_file.file.size
            if legacy_file:
                total_size += legacy_file.size
        except (OSError, ValueError):
            raise forms.ValidationError(
                "No fue posible comprobar el tamaño de "
                "uno de los archivos existentes. "
                "Revisa los archivos de esta evidencia."
            )
        if total_size > MAX_EVIDENCE_TOTAL_SIZE:
            raise forms.ValidationError(
                "La suma de todos los archivos no puede "
                "superar los 50 MB."
            )
        return cleaned_data

# ---------------------------------------------------------
# Formulario de Validaciones

# ---------------------------------------------------------


class ValidationForm(BootstrapMixin, forms.ModelForm):
    DECISION_CHOICES = [
        ("Approved", "Aprobada"),
        ("Observed", "Con observaciones"),
        ("Rejected", "Rechazada"),
    ]
    decision = forms.CharField(
        label="Decisión",
        widget=forms.Select(
            choices=[
                ("", "Seleccione una decisión"),
                *DECISION_CHOICES,
            ],
        ),
        required=True,
        error_messages={
            "required": "Seleccione una decisión.",
        },
    )
    version = forms.IntegerField(
        label="Versión",
        min_value=1,
        widget=forms.NumberInput(attrs={"min": 1}),
    )
    date = forms.DateTimeField(
        label="Fecha y hora",
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local"},
            format="%Y-%m-%dT%H:%M",
        ),
    )

    # SGR-AUSENCIAS-RESULTADOS-20261121: valores internos estables.
    # "Approved" es el valor que exige el cómputo actual de evidencias.
    result = forms.ChoiceField(
        label="Resultado",
        required=True,
        choices=[
            ("", "Seleccione un resultado"),
            ("Approved", "Aprobada"),
            ("Observed", "Con observaciones"),
            ("Rejected", "Rechazada"),
            ("MoreInfo", "Solicitar más antecedentes"),
            ("Conforme", "Conforme (sinónimo de aprobada)"),
        ],
        widget=forms.Select,
    )

    class Meta:
        model = Validation
        fields = [
            "evidence",
            "verifier",
            "decision",
            "date",
            "observation",
            "formal_delegate_endorsement",
            "result",
            "version",
        ]
        labels = {
            "evidence": "Evidencia",
            "verifier": "Funcionario verificador",
            "decision": "Decisión",
            "date": "Fecha y hora",
            "observation": "Observación",
            "result": "Resultado",
            "version": "Versión",
        }
        widgets = {
            "observation": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": (
                        "Ingrese una observación "
                        "si corresponde"
                    ),
                },
            ),
            "result": forms.TextInput(
                attrs={"placeholder": "Ingrese el resultado"},
            ),
            "version": forms.NumberInput(
                attrs={"min": 1},
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        # SGR-RESPALDO-FELICITACIONES-20261121: identidad del autenticado, jamás el nombre del selector.
        self._sgr_endorsement_user = user
        if self.instance.pk:
            # Aval formal ya emitido: no puede revocarse editando el registro.
            self.fields["formal_delegate_endorsement"].disabled = True
        self.fields["formal_delegate_endorsement"].help_text = (
            "Solo para felicitaciones: requiere carta o documento, una observación "
            "fundada y la cuenta del delegado responsable autenticada. "
            "La decisión y el resultado deben ser Approved."
        )
        # La fecha de validación refleja cuándo se tomó la decisión.
        # No aceptamos fechas enviadas por el navegador, tampoco al editar.
        self.fields["date"].disabled = True
        if self.instance.pk:
            self.fields["date"].help_text = (
                "Fecha y hora originales de la validación. "
                "No se modifican al editar."
            )
        else:
            self.fields["date"].initial = (
                timezone.localtime().replace(second=0, microsecond=0)
            )
            self.fields["date"].help_text = (
                "Fecha y hora actuales de Chile, asignadas "
                "automáticamente al guardar."
            )
        if self.instance.pk and self.instance.version < 1:
            self.fields["version"].min_value = None
        evidences = (
            Evidence.objects
            .filter(
                deleted_at__isnull=True,
                activity__deleted_at__isnull=True,
                activity__goal__deleted_at__isnull=True,
                activity__goal__period__deleted_at__isnull=True,
                activity__goal__period__status=Period.Status.ACTIVE,
            )
            .select_related(
                "activity",
                "activity__goal",
                "activity__goal__period",
                "author",
                "author__delegation",
            )
            .order_by(
                "-date",
                "evidence_id",
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
        if user is not None and not user.is_superuser:
            action = "change" if self.instance.pk else "add"
            permitted = allowed_delegation_ids(user, f"registration_validation.{action}_validation")
            evidences = evidences.filter(activity__author__delegation_id__in=permitted)
            employees = employees.filter(delegation_id__in=permitted)
        self.fields["evidence"].queryset = evidences
        self.fields["verifier"].queryset = employees
        self.fields["observation"].required = False
        previous_decision = (
            (self.instance.decision or "").strip()
            if self.instance.pk else ""
        )
        decision_widget = self.fields["decision"].widget
        allowed_decisions = {
            value for value, _label in decision_widget.choices
        }
        if previous_decision and previous_decision not in allowed_decisions:
            current_choices = list(decision_widget.choices)
            current_choices.append(
                (previous_decision, f"{previous_decision} (valor histórico)")
            )
            decision_widget.choices = current_choices
        self.fields["version"].help_text = (
            "Número de versión de la validación."
        )
        _set_form_text_limits(
            self,
            (
                ("decision", 50, "La decisión"),
                ("observation", 1000, "La observación"),
                ("result", 100, "El resultado"),
            ),
        )
        # Un resultado histórico no catalogado puede consultarse/editarse sin
        # alterar silenciosamente su valor anterior. No aparece en altas nuevas.
        if self.instance.pk and self.instance.result:
            choices = list(self.fields["result"].choices)
            if self.instance.result not in {value for value, _ in choices}:
                choices.append((self.instance.result, f"{self.instance.result} (histórico)"))
                self.fields["result"].choices = choices
        self._apply_bootstrap()

    def clean_decision(self):
        decision = self.cleaned_data["decision"].strip()
        allowed_decisions = {
            value for value, _label in self.fields["decision"].widget.choices
            if value
        }
        # Formularios antiguos podían enviar la etiqueta en español.
        if decision == "Aprobada" and decision not in allowed_decisions:
            return "Approved"
        if decision not in allowed_decisions:
            raise forms.ValidationError(
                "Seleccione una decisión válida.",
                code="invalid_choice",
            )
        return decision

    def clean_result(self):
        value = self.cleaned_data["result"]
        return "Approved" if value == "Conforme" else value

    def clean(self):
        cleaned_data = super().clean()
        evidence = cleaned_data.get("evidence")
        if evidence is not None:
            period = evidence.activity.goal.period
            if period.deleted_at is not None:
                raise forms.ValidationError(
                    "No se puede registrar o modificar "
                    "una validación asociada a un período "
                    "archivado."
                )
            if period.status == Period.Status.CLOSED:
                raise forms.ValidationError(
                    "No se puede registrar o modificar "
                    "una validación asociada a un período "
                    "cerrado."
                )
        # SGR-RESPALDO-FELICITACIONES-20261121: autorización formal independiente de la revisión común.
        if cleaned_data.get("formal_delegate_endorsement") and not self.instance.pk:
            from .congratulation_endorsement import (
                actual_delegate_employee, supporting_document_exists,
            )
            user = self._sgr_endorsement_user
            evidence = cleaned_data.get("evidence")
            verifier = cleaned_data.get("verifier")
            if evidence is not None and verifier is not None:
                kind = evidence.activity.activity_type
                if kind is None or not kind.is_congratulation:
                    self.add_error("formal_delegate_endorsement",
                                   "El aval formal solo corresponde a tipos clasificados como felicitación.")
                delegate = actual_delegate_employee(user, evidence)
                if delegate is None or delegate.pk != verifier.pk:
                    self.add_error("formal_delegate_endorsement",
                                   "Solo el delegado responsable autenticado puede respaldar, "
                                   "y debe figurar como verificador.")
                if not supporting_document_exists(evidence):
                    self.add_error("formal_delegate_endorsement",
                                   "Debe existir una carta o documento de respaldo en Evidencias.")
                if cleaned_data.get("decision") != "Approved":
                    self.add_error("formal_delegate_endorsement",
                                   "El aval exige una decisión Aprobada.")
                result = (cleaned_data.get("result") or "").strip()
                if result.casefold() in ("approved", "aprobado", "aprobada"):
                    cleaned_data["result"] = "Approved"
                else:
                    self.add_error("result", "El resultado del aval debe ser Approved.")
                if not (cleaned_data.get("observation") or "").strip():
                    self.add_error("observation", "El delegado debe fundamentar formalmente el aval.")
                if not self.errors:
                    # La firma procede de la sesión autenticada, NO del POST.
                    self.instance.delegate_endorsed_by = user
                    self.instance.delegate_endorsed_at = timezone.now()
                    self.instance._sgr_endorsement_actor = user
        if cleaned_data.get("formal_delegate_endorsement") and self.instance.pk:
            if not self.instance.formal_delegate_endorsement:
                self.add_error("formal_delegate_endorsement",
                               "Para emitir un aval nuevo, registra una validación nueva.")
        return cleaned_data

# ---------------------------------------------------------
# Formulario de Tipo de Actividad
# ---------------------------------------------------------

class ActivityTypeForm(BootstrapMixin, forms.ModelForm):

    STATUS_CHOICES = [
        ("True", "Activo"),
        ("False", "Inactivo"),
    ]

    status = forms.TypedChoiceField(
        label="Estado",
        choices=STATUS_CHOICES,
        coerce=lambda value: value == "True",
        empty_value=None,
        required=True,
    )

    class Meta:
        model = ActivityType

        fields = [
            "code",
            "name",
            "description",
            "is_preparatory_coordination",
            "is_congratulation",
            "status",
        ]

        labels = {
            "code": "Código",
            "name": "Nombre",
            "description": "Descripción",
            "status": "Estado",
        }

        widgets = {
            "code": forms.TextInput(
                attrs={
                    "placeholder": "Ej.: ACT-001",
                    "maxlength": 50,
                },
            ),
            "name": forms.TextInput(
                attrs={
                    "placeholder": "Nombre del tipo de actividad",
                    "maxlength": 150,
                },
            ),
            "description": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": (
                        "Descripción del tipo de actividad (opcional)"
                    ),
                },
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["description"].required = False
        self._apply_bootstrap()
        _set_form_text_limits(
            self,
            (
                ("code", 50, "El código"),
                ("name", 150, "El nombre"),
                ("description", 300, "La descripción"),
            ),
        )

    def clean_code(self):
        code = self.cleaned_data["code"].strip()

        if (
            ActivityType.objects
            .filter(code__iexact=code)
            .exclude(pk=self.instance.pk)
            .exists()
        ):
            raise forms.ValidationError(
                "Ya existe un tipo de actividad con este código."
            )

        return code

    def clean_name(self):
        name = self.cleaned_data["name"].strip()

        if not name:
            raise forms.ValidationError(
                "Debes ingresar el nombre del tipo de actividad."
            )

        return name

    def clean_description(self):
        return self.cleaned_data.get(
            "description", ""
        ).strip()

# ---------------------------------------------------------
# Formulario de Servicios
# ---------------------------------------------------------

class ServiceForm(BootstrapMixin, forms.ModelForm):

    STATUS_CHOICES = [
        ("True", "Activo"),
        ("False", "Inactivo"),
    ]

    status = forms.TypedChoiceField(
        label="Estado",
        choices=STATUS_CHOICES,
        coerce=lambda value: value == "True",
        empty_value=None,
        required=True,
    )

    class Meta:
        model = Service

        fields = [
            "code",
            "name",
            "description",
            "status",
        ]

        labels = {
            "code": "Código",
            "name": "Nombre",
            "description": "Descripción",
            "status": "Estado",
        }

        widgets = {
            "code": forms.TextInput(
                attrs={
                    "placeholder": "Ej.: SER-001",
                    "maxlength": 50,
                },
            ),
            "name": forms.TextInput(
                attrs={
                    "placeholder": "Nombre del servicio",
                    "maxlength": 150,
                },
            ),
            "description": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Descripción del servicio (opcional)",
                },
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["description"].required = False

        self._apply_bootstrap()
        _set_form_text_limits(
            self,
            (
                ("code", 50, "El código"),
                ("name", 150, "El nombre"),
                ("description", 300, "La descripción"),
            ),
        )

    def clean_code(self):
        code = self.cleaned_data["code"].strip()

        if (
            Service.objects
            .filter(code__iexact=code)
            .exclude(pk=self.instance.pk)
            .exists()
        ):
            raise forms.ValidationError(
                "Ya existe un servicio con este código."
            )

        return code

    def clean_name(self):
        name = self.cleaned_data["name"].strip()

        if not name:
            raise forms.ValidationError(
                "Debes ingresar el nombre del servicio."
            )

        return name

    def clean_description(self):
        return self.cleaned_data.get(
            "description", ""
        ).strip()

# ---------------------------------------------------------
# Formulario de Tipo de Atención
# ---------------------------------------------------------


class AttentionTypeForm(BootstrapMixin, forms.ModelForm):
    STATUS_CHOICES = [
        ("True", "Activo"),
        ("False", "Inactivo"),
    ]
    status = forms.TypedChoiceField(
        label="Estado",
        choices=STATUS_CHOICES,
        coerce=lambda value: value == "True",
        empty_value=None,
        required=True,
    )

    class Meta:
        model = AttentionType
        fields = [
            "code",
            "name",
            "description",
            "status",
        ]
        labels = {
            "code": "Código",
            "name": "Nombre",
            "description": "Descripción",
            "status": "Estado",
        }
        widgets = {
            "code": forms.TextInput(
                attrs={
                    "placeholder": "Ej.: AT-001",
                    "maxlength": 50,
                },
            ),
            "name": forms.TextInput(
                attrs={
                    "placeholder": "Nombre del tipo de atención",
                    "maxlength": 150,
                },
            ),
            "description": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": (
                        "Descripción del tipo de atención (opcional)"
                    ),
                },
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["description"].required = False
        self._apply_bootstrap()
        _set_form_text_limits(
            self,
            (
                ("code", 50, "El código"),
                ("name", 150, "El nombre"),
                ("description", 300, "La descripción"),
            ),
        )

    def clean_code(self):
        code = self.cleaned_data["code"].strip()
        if (
            AttentionType.objects
            .filter(code__iexact=code)
            .exclude(pk=self.instance.pk)
            .exists()
        ):
            raise forms.ValidationError(
                "Ya existe un tipo de atención con este código."
            )
        return code

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError(
                "Debes ingresar el nombre del tipo de atención."
            )
        return name

    def clean_description(self):
        return self.cleaned_data.get(
            "description", ""
        ).strip()

# ---------------------------------------------------------
# Formulario de Subatención

# ---------------------------------------------------------


class SubAttentionForm(BootstrapMixin, forms.ModelForm):
    STATUS_CHOICES = [
        ("True", "Activo"),
        ("False", "Inactivo"),
    ]
    status = forms.TypedChoiceField(
        label="Estado",
        choices=STATUS_CHOICES,
        coerce=lambda value: value == "True",
        empty_value=None,
        required=True,
    )

    class Meta:
        model = SubAttention
        fields = [
            "code",
            "name",
            "attention_type",
            "status",
        ]
        labels = {
            "code": "Código",
            "name": "Nombre",
            "attention_type": "Tipo de atención asociado",
            "status": "Estado",
        }
        widgets = {
            "code": forms.TextInput(
                attrs={
                    "placeholder": "Ej.: SUB-001",
                    "maxlength": 50,
                },
            ),
            "name": forms.TextInput(
                attrs={
                    "placeholder": "Nombre de la subatención",
                    "maxlength": 150,
                },
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        allowed_types = Q(
            deleted_at__isnull=True,
            status=True,
        )
        # Si una subatención existente está vinculada
        # a un tipo desactivado posteriormente,
        # se permite conservar esa relación al editar.
        if self.instance.pk and self.instance.attention_type_id:
            allowed_types |= Q(
                pk=self.instance.attention_type_id
            )
        self.fields["attention_type"].queryset = (
            AttentionType.objects
            .filter(allowed_types)
            .order_by("name", "attention_type_id")
        )
        self.fields["attention_type"].empty_label = (
            "Seleccione un tipo de atención"
        )
        self.fields["attention_type"].help_text = (
            "Solo se pueden crear nuevas asociaciones "
            "con tipos de atención activos y no eliminados."
        )
        _set_form_text_limits(
            self,
            (
                ("code", 50, "El código"),
                ("name", 150, "El nombre"),
            ),
        )
        self._apply_bootstrap()

    def clean_code(self):
        code = self.cleaned_data["code"].strip()
        if (
            SubAttention.objects
            .filter(code__iexact=code)
            .exclude(pk=self.instance.pk)
            .exists()
        ):
            raise forms.ValidationError(
                "Ya existe una subatención con este código."
            )
        return code

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError(
                "Debes ingresar el nombre de la subatención."
            )
        return name

    def clean_attention_type(self):
        attention_type = self.cleaned_data["attention_type"]
        previous_type_id = (
            self.instance.attention_type_id
            if self.instance.pk
            else None
        )
        if (
            attention_type.deleted_at is not None
            or not attention_type.status
        ) and attention_type.pk != previous_type_id:
            raise forms.ValidationError(
                "Solo puedes seleccionar un tipo de atención "
                "activo y no eliminado."
            )
        return attention_type

# ---------------------------------------------------------
# Formulario de Ingreso de Atención

# ---------------------------------------------------------


class AttentionEntryForm(BootstrapMixin, forms.ModelForm):
    closing_observation = forms.CharField(
        label="Observación del cambio de estado",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Resultado de la gestión"}),
    )
    citizen_rut = forms.CharField(label="RUT del ciudadano (búsqueda)", max_length=16, required=False, widget=forms.TextInput(attrs={"class":"form-control", "placeholder":"12.345.678-5", "autocomplete":"off"}))
    confirm_citizen_change = forms.BooleanField(required=False, widget=forms.HiddenInput(), label="Confirmar cambio de ciudadano")

    """Registra solicitudes con relaciones y delegación validadas."""

    class Meta:
        model = AttentionEntry
        fields = [
            "requester",
            "requester_email",
            "requester_phone",
            "address",
            "subject",
            "attention_type",
            "sub_attention",
            "description",
            "delegation",
            "responsible_employee",
            "activity",
            "status",
        ]
        labels = {
            "requester": "Solicitante",
            "requester_email": "Correo electrónico",
            "requester_phone": "Teléfono",
            "address": "Dirección",
            "subject": "Asunto",
            "attention_type": "Tipo de atención",
            "sub_attention": "Subatención",
            "description": "Descripción de la solicitud",
            "delegation": "Delegación responsable",
            "responsible_employee": "Funcionario responsable",
            "activity": "Actividad asociada",
        }
        widgets = {
            "requester": forms.TextInput(attrs={
                "placeholder": "Nombre de quien realiza la solicitud",
                "maxlength": 150,
            }),
            "requester_email": forms.EmailInput(attrs={
                "placeholder": "correo@ejemplo.cl",
            }),
            "requester_phone": forms.TextInput(attrs={
                "placeholder": "Teléfono de contacto",
                "maxlength": 25,
            }),
            "address": forms.TextInput(attrs={
                "placeholder": "Dirección",
                "maxlength": 250,
            }),
            "subject": forms.TextInput(attrs={
                "placeholder": "Asunto de la solicitud",
                "maxlength": 160,
            }),
            "description": forms.Textarea(attrs={
                "rows": 4,
                "placeholder": "Describe la solicitud de atención",
            }),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        _set_form_text_limits(
            self,
            (
                ("closing_observation", 1000, "La observación"),
                ("citizen_rut", 16, "El RUT"),
            ),
        )
        existing = bool(self.instance.pk)
        # SGR: para crear una atención se debe identificar un ciudadano
        # registrado y activo; las atenciones antiguas conservan su edición.
        if not existing:
            self.fields["citizen_rut"].required = True
            self.fields["citizen_rut"].error_messages["required"] = (
                "Debes ingresar el RUT de un ciudadano registrado."
            )
            self.fields["citizen_rut"].help_text = (
                "El ciudadano debe estar activo en el mantenedor Ciudadanos."
            )
        if existing:
            self.fields["status"].required = False  # Formularios anteriores siguen siendo válidos.
            self.fields["status"].label = "Estado de la atención"
            statuses = [
                ("IN_PROGRESS", "En gestión"), ("RESOLVED", "Resuelta"),
                ("CLOSED", "Cerrada"), ("REJECTED", "No procede"),
            ]
            if self.instance.status not in dict(statuses):
                statuses.insert(0, (self.instance.status, self.instance.get_status_display()))
            self.fields["status"].choices = statuses
        else:
            self.fields.pop("status", None)
            self.fields.pop("closing_observation", None)
        if getattr(self.instance, "citizen_id", None):
            citizen = self.instance.citizen
            self.fields["citizen_rut"].initial = citizen.rut
            # Mostrar información actual del mantenedor Ciudadanos, aunque
            # la atención guarde una copia histórica anterior.
            self.initial.update({
                "requester": citizen.full_name,
                "requester_email": citizen.email,
                "requester_phone": citizen.phone,
                "address": citizen.address,
            })

        # Solo el RUT permite seleccionar a otro ciudadano. Los datos personales
        # se editan exclusivamente desde el mantenedor Ciudadanos.
        for field in ("requester", "requester_email", "requester_phone", "address"):
            self.fields[field].widget.attrs["readonly"] = "readonly"
            self.fields[field].help_text = "Se obtiene del RUT. Para corregirlo, modifica Ciudadanos."

        self.request_user = user
        # Solo relaciones activas y no archivadas para nuevos registros.
        type_condition = Q(deleted_at__isnull=True, status=True)
        sub_condition = Q(
            deleted_at__isnull=True,
            status=True,
            attention_type__deleted_at__isnull=True,
            attention_type__status=True,
        )
        # Algunas versiones del módulo Organización no archivan
        # delegaciones. Evitamos consultar un campo inexistente.
        delegation_has_deleted_at = any(
            field.name == "deleted_at" for field in Delegation._meta.fields
        )
        delegation_condition = (
            Q(deleted_at__isnull=True) if delegation_has_deleted_at else Q()
        )
        employee_condition = Q(deleted_at__isnull=True)
        if delegation_has_deleted_at:
            employee_condition &= Q(delegation__deleted_at__isnull=True)
        # En edición se permite conservar relaciones históricas que
        # después hayan quedado inactivas o archivadas, sin crear otras.
        if existing:
            if self.instance.attention_type_id:
                type_condition |= Q(pk=self.instance.attention_type_id)
            if self.instance.sub_attention_id:
                sub_condition |= Q(pk=self.instance.sub_attention_id)
            if self.instance.delegation_id and delegation_has_deleted_at:
                delegation_condition |= Q(pk=self.instance.delegation_id)
            if self.instance.responsible_employee_id:
                employee_condition |= Q(pk=self.instance.responsible_employee_id)
        attention_types = AttentionType.objects.filter(type_condition)
        sub_attentions = SubAttention.objects.filter(sub_condition)
        delegations = Delegation.objects.filter(delegation_condition)
        employees = Employee.objects.filter(employee_condition)
        # Los usuarios normales solo trabajan en su delegación.
        if user is not None and not user.is_superuser:
            action = "change" if self.instance.pk else "add"
            permitted = allowed_delegation_ids(user, f"registration_validation.{action}_attentionentry")
            delegations = delegations.filter(pk__in=permitted)
            employees = employees.filter(delegation_id__in=permitted)
        self.fields["attention_type"].queryset = attention_types.order_by(
            "name", "attention_type_id"
        )
        self.fields["sub_attention"].queryset = sub_attentions.select_related(
            "attention_type"
        ).order_by("name", "sub_attention_id")
        self.fields["delegation"].queryset = delegations.order_by("pk")
        self.fields["responsible_employee"].queryset = employees.select_related(
            "delegation"
        ).order_by("name")
        # Solo actividades vigentes del área autorizada y sus metas activas.
        activity_choices = Activity.objects.filter(
            deleted_at__isnull=True,
            goal__deleted_at__isnull=True,
            goal__period__deleted_at__isnull=True,
            goal__period__status=Period.Status.ACTIVE,
        ).select_related("goal", "author").order_by("-date", "-activity_id")
        if user is not None and not user.is_superuser:
            action = "change" if existing else "add"
            ids = allowed_delegation_ids(user, f"registration_validation.{action}_attentionentry")
            activity_choices = activity_choices.filter(author__delegation_id__in=ids)
        if existing and self.instance.activity_id:
            activity_choices = (
                activity_choices | Activity.objects.filter(pk=self.instance.activity_id)
            ).distinct().order_by("-date", "-activity_id")
        self.fields["activity"].queryset = activity_choices
        self.fields["activity"].empty_label = "Seleccione una actividad"
        # SGR-ATENCION-ACTIVIDAD-OPCIONAL-20261125
        # La solicitud puede convertirse en atención antes de crear la actividad.
        # Después se vincula desde Actividades (casillas múltiples).
        self.fields["activity"].required = False
        # El enlace principal se fija al crear. Un cambio posterior requiere
        # un proceso de reasignación auditado, no editarlo silenciosamente.
        self.fields["activity"].disabled = existing
        self.fields["activity"].help_text = (
            "Opcional: puedes vincular una actividad ahora o hacerlo después "
            "desde Actividades, usando las casillas de atenciones. "
            "La atención siempre debe originarse en una solicitud previa. "
            "Una vez creada, este campo es de solo lectura."
        )
        self.fields["activity"].label_from_instance = (
            lambda obj: f"#{obj.pk} · {obj.goal.item} · {obj.action[:70]}"
        )
        self.fields["attention_type"].empty_label = "Seleccione un tipo de atención"
        self.fields["sub_attention"].empty_label = "Seleccione una subatención"
        self.fields["delegation"].empty_label = "Seleccione una delegación"
        self.fields["responsible_employee"].empty_label = "Seleccione un funcionario"
        self.fields["sub_attention"].help_text = (
            "La subatención debe pertenecer al tipo de atención seleccionado."
        )
        self.fields["responsible_employee"].help_text = (
            "El empleado debe pertenecer a la delegación elegida."
        )
        # La delegación activa se obtiene del contexto validado por middleware.
        # Para una cuenta sin perfil empleado se conserva la selección explícita
        # de responsable, pero SIEMPRE se registra su cuenta en registered_by.
        if user is not None and not user.is_superuser:
            selected_id = getattr(user, "sgr_active_delegation_id", None)
            if selected_id is not None:
                self.fields["delegation"].initial = selected_id
                self.fields["delegation"].disabled = True
            profile = getattr(user, "profile", None)
            linked_employee = getattr(profile, "employee", None)
            if (
                linked_employee is not None and not existing
                and (selected_id is None or linked_employee.delegation_id == selected_id)
            ):
                self.initial["responsible_employee"] = linked_employee.pk
                self.fields["responsible_employee"].initial = linked_employee.pk
                self.fields["responsible_employee"].disabled = True
                self.fields["responsible_employee"].help_text = (
                    "Se asigna automáticamente tu empleado vinculado."
                )

        for field_name in (
            "attention_type", "sub_attention", "delegation", "responsible_employee"
        ):
            self.fields[field_name].error_messages["invalid_choice"] = (
                "Selecciona una opción válida de la lista."
            )
        _set_form_text_limits(
            self,
            (
                ("requester", 150, "El nombre del solicitante"),
                ("requester_email", 254, "El correo electrónico"),
                ("requester_phone", 25, "El teléfono"),
                ("address", 250, "La dirección"),
                ("subject", 160, "El asunto"),
                ("description", 4000, "La descripción"),
            ),
        )
        # registration_date se genera automáticamente en el modelo.
        self._apply_bootstrap()

    def clean_citizen_rut(self):
        from citizen_registry.rut import normalize_rut, validate_rut

        rut = normalize_rut(self.cleaned_data.get("citizen_rut"))
        if rut:
            validate_rut(rut)
            # No basta con que el RUT tenga dígito verificador válido:
            # al ingresar una atención debe existir en Ciudadanos y estar activo.
            if not self.instance.pk and not Citizen.objects.filter(
                rut=rut, is_active=True
            ).exists():
                raise forms.ValidationError(
                    "El RUT no está registrado como ciudadano activo. "
                    "Regístralo o reactívalo en Ciudadanos."
                )
        return rut

    def clean_requester(self):
        requester = self.cleaned_data["requester"].strip()
        if not requester:
            raise forms.ValidationError("Ingresa el nombre del solicitante.")
        return requester

    def clean_description(self):
        description = self.cleaned_data["description"].strip()
        if not description:
            raise forms.ValidationError("Ingresa una descripción de la solicitud.")
        return description

    def clean(self):
        cleaned_data = super().clean()
        # La protección también es del servidor: ignorar datos personales
        # manipulados en el POST cuando existe un ciudadano vinculado.
        rut = cleaned_data.get("citizen_rut")
        citizen = None
        if rut:
            citizen = Citizen.objects.filter(rut=rut, is_active=True).first()
        if citizen is None and getattr(self.instance, "citizen_id", None):
            citizen = self.instance.citizen
        if citizen is not None:
            cleaned_data.update({
                "requester": citizen.full_name,
                # Para una atención nacida del portal se mantiene el correo
                # histórico si el contacto actual del CRUD quedó vacío.
                "requester_email": (citizen.email or self.instance.requester_email)
                if self.instance.origin == "CITIZEN" else citizen.email,
                "requester_phone": citizen.phone,
                "address": citizen.address,
            })
        elif self.instance.pk:
            # Atenciones históricas sin ciudadano vinculado: permitir modificar
            # el caso, no sus datos personales almacenados como referencia.
            for key in ("requester", "requester_email", "requester_phone", "address"):
                cleaned_data[key] = getattr(self.instance, key)

        # La atención se crea solo cuando el ciudadano tiene correo y dirección
        # en el mantenedor. Esos campos son de solo lectura en este formulario,
        # por lo que NO se aceptan valores del POST como sustituto del catálogo.
        if not self.instance.pk and citizen is not None:
            email = (citizen.email or "").strip()
            if not email:
                self.add_error(
                    "requester_email",
                    "El ciudadano no tiene correo registrado. "
                    "Completa su ficha en Ciudadanos antes de crear la atención.",
                )
            else:
                try:
                    forms.EmailField().clean(email)
                except forms.ValidationError:
                    self.add_error(
                        "requester_email",
                        "El correo registrado en Ciudadanos no es válido. "
                        "Corrígelo en el mantenedor.",
                    )
            if not (citizen.address or "").strip():
                self.add_error(
                    "address",
                    "El ciudadano no tiene dirección registrada. "
                    "Completa su ficha en Ciudadanos antes de crear la atención.",
                )
        attention_type = cleaned_data.get("attention_type")
        sub_attention = cleaned_data.get("sub_attention")
        delegation = cleaned_data.get("delegation")
        employee = cleaned_data.get("responsible_employee")
        activity = cleaned_data.get("activity")
        if activity is not None and delegation is not None:
            if activity.author.delegation_id != delegation.pk:
                self.add_error(
                    "activity", "La actividad debe corresponder a la misma delegación."
                )
            if activity.goal.period.status == Period.Status.CLOSED and (
                not self.instance.pk or activity.pk != self.instance.activity_id
            ):
                self.add_error("activity", "No se puede vincular una actividad de período cerrado.")
        # Permitir conservar una relación histórica solo si no cambió.
        if attention_type is not None:
            old_type_id = self.instance.attention_type_id if self.instance.pk else None
            if (
                attention_type.deleted_at is not None or not attention_type.status
            ) and attention_type.pk != old_type_id:
                self.add_error(
                    "attention_type",
                    "Selecciona un tipo de atención activo y no eliminado.",
                )
        if sub_attention is not None:
            old_sub_id = self.instance.sub_attention_id if self.instance.pk else None
            if (
                sub_attention.deleted_at is not None
                or not sub_attention.status
                or sub_attention.attention_type.deleted_at is not None
                or not sub_attention.attention_type.status
            ) and sub_attention.pk != old_sub_id:
                self.add_error(
                    "sub_attention",
                    "Selecciona una subatención activa de un tipo vigente.",
                )
            if (
                attention_type is not None
                and sub_attention.attention_type_id != attention_type.pk
            ):
                self.add_error(
                    "sub_attention",
                    "La subatención no pertenece al tipo de atención seleccionado.",
                )
        if delegation is not None:
            old_delegation_id = self.instance.delegation_id if self.instance.pk else None
            if (
                getattr(delegation, "deleted_at", None) is not None
                and delegation.pk != old_delegation_id
            ):
                self.add_error(
                    "delegation", "Selecciona una delegación no eliminada."
                )
        if self.instance.pk:
            if self.instance.status == "CLOSED":
                raise forms.ValidationError("La atención cerrada está protegida. Debe reabrirse primero.")
            state = cleaned_data.get("status") or self.instance.status
            cleaned_data["status"] = state
            if state != self.instance.status and state in ("RESOLVED", "CLOSED", "REJECTED"):
                if not (cleaned_data.get("closing_observation") or "").strip():
                    self.add_error("closing_observation", "Indica el resultado de la gestión.")
        user = self.request_user
        if user is not None and not user.is_superuser:
            active = getattr(user, "sgr_active_delegation_id", None)
            if active is not None and delegation is not None and delegation.pk != active:
                self.add_error("delegation", "La delegación no coincide con el contexto activo.")
            profile = getattr(user, "profile", None)
            linked_employee = getattr(profile, "employee", None)
            if (
                linked_employee is not None and not self.instance.pk
                and (active is None or linked_employee.delegation_id == active)
            ):
                if employee is None or employee.pk != linked_employee.pk:
                    self.add_error("responsible_employee", "El responsable debe ser tu empleado vinculado.")
        if employee is not None:
            old_employee_id = (
                self.instance.responsible_employee_id if self.instance.pk else None
            )
            if (
                employee.deleted_at is not None
                or getattr(employee.delegation, "deleted_at", None) is not None
            ) and employee.pk != old_employee_id:
                self.add_error(
                    "responsible_employee",
                    "Selecciona un funcionario activo en una delegación vigente.",
                )
            if delegation is not None and employee.delegation_id != delegation.pk:
                self.add_error(
                    "responsible_employee",
                    "El funcionario no pertenece a la delegación seleccionada.",
                )
        return cleaned_data
