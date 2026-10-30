from django import forms
from django.core.validators import MaxLengthValidator
from accounts.permissions import allowed_delegation_ids
from django.core.validators import FileExtensionValidator
from django.db.models import Q
from organization.models import Delegation, Employee
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
)

# ---------------------------------------------------------
# Estilos reutilizables

# ---------------------------------------------------------


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


def _set_text_limit(field, limit, label):
    """Aplica el límite tanto al formulario como al control HTML."""
    field.widget.attrs["maxlength"] = limit
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

    class Meta:
        model = Activity
        fields = [
            "goal",
            "author",
            "activity_type",
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

# ---------------------------------------------------------
# Formulario de Evidencias

# ---------------------------------------------------------


class EvidenceForm(BootstrapMixin, forms.ModelForm):
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
            "code",
            "activity",
            "author",
            "file_link",
            "date",
            "review_status",
        ]
        labels = {
            "code": "Código",
            "activity": "Actividad",
            "author": "Funcionario",
            "file_link": "Enlace de evidencia",
            "date": "Fecha y hora",
            "review_status": "Estado de revisión",
        }
        widgets = {
            "code": forms.TextInput(
                attrs={"placeholder": "Ej.: EVID-001"},
            ),
            "file_link": forms.TextInput(
                attrs={"placeholder": "https://..."},
            ),
            "review_status": forms.TextInput(
                attrs={"placeholder": "Ej.: Pending (pendiente)"},
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
            "Para indicar que una evidencia está pendiente, ingresa Pending. "
            "Se conserva ese valor por compatibilidad con el sistema."
        )
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
        self._apply_bootstrap()

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
    date = forms.DateTimeField(
        label="Fecha y hora",
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local"},
            format="%Y-%m-%dT%H:%M",
        ),
    )

    class Meta:
        model = Validation
        fields = [
            "evidence",
            "verifier",
            "decision",
            "date",
            "observation",
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
            "decision": forms.TextInput(
                attrs={"placeholder": "Ingrese la decisión"},
            ),
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
        self.fields["version"].help_text = (
            "Número de versión de la validación."
        )
        self._apply_bootstrap()

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
        _set_text_limit(self.fields["code"], 50, "El código")
        _set_text_limit(self.fields["name"], 150, "El nombre")
        _set_text_limit(
            self.fields["description"],
            300,
            "La descripción",
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
        _set_text_limit(self.fields["code"], 50, "El código")
        _set_text_limit(self.fields["name"], 150, "El nombre")
        _set_text_limit(
            self.fields["description"],
            300,
            "La descripción",
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
        existing = bool(self.instance.pk)
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
        # registration_date se genera automáticamente en el modelo.
        self._apply_bootstrap()

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
        attention_type = cleaned_data.get("attention_type")
        sub_attention = cleaned_data.get("sub_attention")
        delegation = cleaned_data.get("delegation")
        employee = cleaned_data.get("responsible_employee")
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
