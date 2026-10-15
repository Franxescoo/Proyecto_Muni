
from django import forms
from django.core.validators import FileExtensionValidator

from organization.models import Employee
from planning_measurements.models import Goal, Period

from .models import (
    Activity,
    Evidence,
    Validation,
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
                    "placeholder": "Nombre o medio de contacto",
                },
            ),
            "phone": forms.TextInput(
                attrs={
                    "placeholder": "Ej.: +56 9 1234 5678",
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
                attrs={
                    "placeholder": "Ej.: EVID-001",
                },
            ),
            "file_link": forms.TextInput(
                attrs={
                    "placeholder": "https://...",
                },
            ),
            "review_status": forms.TextInput(
                attrs={
                    "placeholder": "Ej.: Pending",
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
            profile = getattr(user, "profile", None)

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
                    author__delegation_id=delegation_id,
                )

                employees = employees.filter(
                    delegation_id=delegation_id,
                )

        self.fields["activity"].queryset = activities
        self.fields["author"].queryset = employees

        self.fields["file_link"].required = False

        # La vista utilizará esta colección al guardar
        # para eliminar los adjuntos seleccionados.
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

        # Si hubo errores al validar los archivos nuevos,
        # no continuamos con el cálculo de cantidad y peso.
        if "new_files" in self.errors:
            return cleaned_data

        # Los IDs enviados para eliminar adjuntos serán
        # comprobados contra los archivos de ESTA evidencia.
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

        # Compatibilidad temporal con el campo único
        # antiguo Evidence.file.
        #
        # Evitamos contar dos veces un archivo si ya
        # está representado en EvidenceFile.
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

        # Se cuentan los archivos que quedarán guardados
        # después de la operación.
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

        # El límite de 50 MB corresponde a la suma:
        # archivos conservados + archivos nuevos +
        # archivo antiguo, cuando corresponda.
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
                attrs={
                    "placeholder": "Ingrese la decisión",
                },
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
                attrs={
                    "placeholder": "Ingrese el resultado",
                },
            ),
            "version": forms.NumberInput(
                attrs={
                    "min": 1,
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
            profile = getattr(user, "profile", None)

            delegation_id = (
                profile.delegation_id
                if profile is not None
                else None
            )

            if delegation_id is None:
                evidences = evidences.none()
                employees = employees.none()

            else:
                evidences = evidences.filter(
                    activity__author__delegation_id=delegation_id,
                )

                employees = employees.filter(
                    delegation_id=delegation_id,
                )

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
