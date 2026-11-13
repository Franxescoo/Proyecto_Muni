import uuid
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import (
    FileExtensionValidator,
    URLValidator,
    validate_email,
)
from django.db import IntegrityError, models, transaction

from core.models import BaseModel


MIN_EVIDENCE_FILES = 2
MAX_EVIDENCE_FILES = 5
MAX_EVIDENCE_TOTAL_SIZE = 50 * 1024 * 1024  # 50 MB

EVIDENCE_ALLOWED_EXTENSIONS = [
    "pdf",
    "jpg",
    "jpeg",
    "png",
    "doc",
    "docx",
]

EVIDENCE_FILE_LINK_SCHEMES = ("http", "https")
EVIDENCE_CODE_GENERATION_ATTEMPTS = 5


def _new_evidence_code():
    return f"EVID-{uuid.uuid4().hex.upper()}"


def is_safe_evidence_file_link(value):
    """Return whether an evidence link is safe to validate or render."""
    if not isinstance(value, str):
        return False

    value = value.strip()
    if not value:
        return True

    if "\\" in value or any(character.isspace() for character in value):
        return False

    try:
        parsed_url = urlsplit(value)
    except ValueError:
        return False

    if parsed_url.scheme:
        if parsed_url.scheme.lower() not in EVIDENCE_FILE_LINK_SCHEMES:
            return False

        try:
            URLValidator(schemes=EVIDENCE_FILE_LINK_SCHEMES)(value)
        except ValidationError:
            return False
        return True

    return not parsed_url.netloc


def validate_evidence_file_link(value):
    if not is_safe_evidence_file_link(value):
        raise ValidationError(
            "Ingresa una URL HTTP o HTTPS válida, o una ruta relativa segura.",
            code="invalid",
        )


def _validate_changed_text_lengths(instance, limits):
    oversized_fields = {
        field_name: (limit, label)
        for field_name, (limit, label) in limits.items()
        if len(getattr(instance, field_name) or "") > limit
    }
    if not oversized_fields:
        return

    previous_values = {}
    if not instance._state.adding:
        previous_values = (
            type(instance)
            .objects.filter(pk=instance.pk)
            .values(*oversized_fields)
            .first()
            or {}
        )

    errors = {}
    for field_name, (limit, label) in oversized_fields.items():
        value = getattr(instance, field_name) or ""
        if (
            instance._state.adding
            or previous_values.get(field_name) != value
        ):
            errors[field_name] = (
                f"{label} no puede superar los {limit} caracteres."
            )
    if errors:
        raise ValidationError(errors)


def _relationship_fields_changed(instance, field_names, update_fields=None):
    if instance._state.adding:
        return {
            field.attname: getattr(instance, field.attname)
            for field in (
                instance._meta.get_field(name)
                for name in field_names
            )
        }

    fields = [instance._meta.get_field(name) for name in field_names]
    original_values = (
        type(instance)
        .objects.filter(pk=instance.pk)
        .values(*(field.attname for field in fields))
        .first()
    )
    if original_values is None:
        return {
            field.attname: getattr(instance, field.attname)
            for field in fields
        }

    requested_fields = (
        set(update_fields) if update_fields is not None else None
    )
    effective_values = {}
    changed = False
    for field in fields:
        included = requested_fields is None or (
            field.name in requested_fields
            or field.attname in requested_fields
        )
        value = (
            getattr(instance, field.attname)
            if included
            else original_values[field.attname]
        )
        effective_values[field.attname] = value
        changed = changed or value != original_values[field.attname]

    return effective_values if changed else None


def _validate_changed_relationships(instance, field_names, update_fields):
    effective_values = _relationship_fields_changed(
        instance,
        field_names,
        update_fields,
    )
    if effective_values is None:
        return

    original_values = {
        field_name: getattr(instance, field_name)
        for field_name in effective_values
    }
    try:
        for field_name, value in effective_values.items():
            setattr(instance, field_name, value)
        instance._validate_relationships()
    finally:
        for field_name, value in original_values.items():
            setattr(instance, field_name, value)


def validate_evidence_file_size(file):
    """
    Valida que un archivo individual no supere 50 MB.

    El límite real de la evidencia será de 50 MB
    considerando la suma de todos sus archivos.
    Esa validación se realizará en el formulario.
    """
    if file.size > MAX_EVIDENCE_TOTAL_SIZE:
        raise ValidationError(
            "El archivo supera el máximo permitido de 50 MB."
        )


class Activity(BaseModel):
    activity_id = models.BigAutoField(
        primary_key=True,
        verbose_name="ID de actividad",
    )

    goal = models.ForeignKey(
        "planning_measurements.Goal",
        on_delete=models.PROTECT,
        related_name="activities",
        verbose_name="Meta",
    )

    author = models.ForeignKey(
        "organization.Employee",
        on_delete=models.PROTECT,
        related_name="activities_created",
        verbose_name="Funcionario autor",
    )
    activity_type = models.ForeignKey(
        "registration_validation.ActivityType",
        on_delete=models.PROTECT,
        related_name="activities",
        null=True,
        blank=True,
        verbose_name="Tipo de actividad",
    )
    attention = models.ForeignKey(
        "registration_validation.AttentionEntry",
        on_delete=models.PROTECT,
        related_name="activities",
        null=True,
        blank=True,
        verbose_name="Atención asociada",
    )

    date = models.DateField(
        verbose_name="Fecha",
    )

    request_problem = models.TextField(
        verbose_name="Solicitud o problema",
    )

    action = models.TextField(
        verbose_name="Acción realizada",
    )

    contact = models.CharField(
        max_length=150,
        verbose_name="Contacto",
    )

    phone = models.CharField(
        max_length=20,
        verbose_name="Teléfono",
    )

    status = models.CharField(
        max_length=50,
        default="Pending",
        verbose_name="Estado",
    )

    class Meta:
        verbose_name = "Actividad"
        verbose_name_plural = "Actividades"
        ordering = ("-date", "activity_id")

    def clean(self):
        super().clean()
        _validate_changed_text_lengths(
            self,
            {
                "request_problem": (2000, "La solicitud o problema"),
                "action": (2000, "La acción realizada"),
            },
        )
        if _relationship_fields_changed(self, ("goal", "author")):
            self._validate_relationships()

    def _validate_relationships(self):
        if not self.goal_id or not self.author_id:
            return

        if self.pk:
            original_goal_id = (
                type(self).objects.filter(pk=self.pk)
                .values_list("goal_id", flat=True)
                .first()
            )
            if (
                original_goal_id is not None
                and original_goal_id != self.goal_id
            ):
                raise ValidationError(
                    {
                        "goal": (
                            "No se puede reasignar una actividad a otra "
                            "meta, porque afectaría el recálculo de sus "
                            "indicadores."
                        )
                    }
                )

        from planning_measurements.models import Goal

        goal_employee_id = (
            Goal.objects.filter(pk=self.goal_id)
            .values_list("employee_id", flat=True)
            .first()
        )
        if goal_employee_id is not None and goal_employee_id != self.author_id:
            raise ValidationError(
                {
                    "author": (
                        "El funcionario autor debe coincidir con "
                        "el funcionario asignado a la meta."
                    )
                }
            )

    def save(self, *args, **kwargs):
        _validate_changed_relationships(
            self,
            ("goal", "author"),
            kwargs.get("update_fields"),
        )
        return super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"Actividad {self.activity_id} - "
            f"{self.goal.item}"
        )


class Evidence(BaseModel):
    evidence_id = models.BigAutoField(
        primary_key=True,
        verbose_name="ID de evidencia",
    )

    code = models.CharField(
        max_length=100,
        unique=True,
        editable=False,
        verbose_name="Código",
    )

    activity = models.ForeignKey(
        Activity,
        on_delete=models.PROTECT,
        related_name="evidences",
        verbose_name="Actividad",
    )

    author = models.ForeignKey(
        "organization.Employee",
        on_delete=models.PROTECT,
        related_name="evidences_created",
        verbose_name="Funcionario que registra",
    )

    file_link = models.CharField(
        max_length=500,
        blank=True,
        verbose_name="Archivo o enlace",
    )

    # Campo anterior.
    # Se mantiene temporalmente para conservar archivos existentes.
    file = models.FileField(
        upload_to="evidences/%Y/%m/",
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(
                allowed_extensions=EVIDENCE_ALLOWED_EXTENSIONS
            ),
            validate_evidence_file_size,
        ],
        verbose_name="Archivo de evidencia",
    )

    date = models.DateTimeField(
        verbose_name="Fecha",
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Metadatos",
    )

    review_status = models.CharField(
        max_length=50,
        default="Pending",
        verbose_name="Estado de revisión",
    )

    class Meta:
        verbose_name = "Evidencia"
        verbose_name_plural = "Evidencias"
        ordering = ("-date", "evidence_id")

    def clean(self):
        super().clean()
        self.file_link = (self.file_link or "").strip()
        try:
            validate_evidence_file_link(self.file_link)
        except ValidationError as exc:
            raise ValidationError(
                {"file_link": exc.messages}
            ) from exc
        if _relationship_fields_changed(self, ("activity", "author")):
            self._validate_relationships()

    def _validate_relationships(self):
        if not self.activity_id or not self.author_id:
            return

        if self.pk:
            original_goal_id = (
                type(self).objects.filter(pk=self.pk)
                .values_list("activity__goal_id", flat=True)
                .first()
            )
            new_goal_id = (
                Activity.objects.filter(pk=self.activity_id)
                .values_list("goal_id", flat=True)
                .first()
            )
            if (
                original_goal_id is not None
                and new_goal_id is not None
                and original_goal_id != new_goal_id
            ):
                raise ValidationError(
                    {
                        "activity": (
                            "No se puede trasladar una evidencia a una "
                            "actividad de otra meta, porque afectaría el "
                            "recálculo de sus indicadores."
                        )
                    }
                )

        from organization.models import Employee

        activity_delegations = (
            Activity.objects.filter(pk=self.activity_id)
            .values_list(
                "author_id",
                "goal__employee_id",
                "author__delegation_id",
                "goal__employee__delegation_id",
            )
            .first()
        )
        author_delegation_id = (
            Employee.objects.filter(pk=self.author_id)
            .values_list("delegation_id", flat=True)
            .first()
        )
        if activity_delegations is None or author_delegation_id is None:
            return

        (
            activity_author_id,
            goal_employee_id,
            activity_author_delegation_id,
            goal_employee_delegation_id,
        ) = activity_delegations
        if activity_author_id != goal_employee_id:
            raise ValidationError(
                {
                    "activity": (
                        "La actividad asociada no mantiene la relación "
                        "entre su meta y el funcionario autor."
                    )
                }
            )
        if activity_author_delegation_id != goal_employee_delegation_id:
            raise ValidationError(
                {
                    "activity": (
                        "La actividad asociada no mantiene la relación "
                        "entre su meta y el funcionario autor."
                    )
                }
            )
        if author_delegation_id != activity_author_delegation_id:
            raise ValidationError(
                {
                    "author": (
                        "El funcionario que registra la evidencia debe "
                        "pertenecer a la misma delegación de la actividad."
                    )
                }
            )

    def save(self, *args, **kwargs):
        manager = type(self)._default_manager
        using = kwargs.get("using") or self._state.db

        if self._state.adding and not self.code:
            for _ in range(EVIDENCE_CODE_GENERATION_ATTEMPTS):
                self.code = _new_evidence_code()
                if manager.using(using).filter(code=self.code).exists():
                    continue
                try:
                    with transaction.atomic(using=using):
                        return super().save(*args, **kwargs)
                except IntegrityError:
                    if manager.using(using).filter(code=self.code).exists():
                        continue
                    raise
            raise ValidationError(
                {
                    "code": (
                        "No se pudo generar un código único para la evidencia. "
                        "Inténtalo nuevamente."
                    )
                }
            )

        if not self._state.adding:
            stored_code = (
                manager.using(using)
                .filter(pk=self.pk)
                .values_list("code", flat=True)
                .first()
            )
            if stored_code is not None and self.code != stored_code:
                update_fields = kwargs.get("update_fields")
                if update_fields is not None and "code" not in update_fields:
                    self.code = stored_code
                else:
                    raise ValidationError(
                        {"code": "El código de una evidencia no se puede modificar."}
                    )

        _validate_changed_relationships(
            self,
            ("activity", "author"),
            kwargs.get("update_fields"),
        )
        return super().save(*args, **kwargs)

    @property
    def review_status_label(self):
        if (self.review_status or "").strip().casefold() in {
            "pending",
            "pendiente",
        }:
            return "Pendiente"
        return self.review_status

    @property
    def safe_file_link(self):
        value = (self.file_link or "").strip()
        return value if is_safe_evidence_file_link(value) else ""

    def __str__(self):
        return self.code


class EvidenceFile(BaseModel):
    evidence_file_id = models.BigAutoField(
        primary_key=True,
        verbose_name="ID de archivo de evidencia",
    )

    evidence = models.ForeignKey(
        Evidence,
        on_delete=models.CASCADE,
        related_name="files",
        verbose_name="Evidencia",
    )

    file = models.FileField(
        upload_to="evidences/%Y/%m/",
        validators=[
            FileExtensionValidator(
                allowed_extensions=EVIDENCE_ALLOWED_EXTENSIONS
            ),
            validate_evidence_file_size,
        ],
        verbose_name="Archivo",
    )

    class Meta:
        verbose_name = "Archivo de evidencia"
        verbose_name_plural = "Archivos de evidencia"
        ordering = (
            "evidence_id",
            "evidence_file_id",
        )

    def __str__(self):
        return self.file.name


class Validation(BaseModel):
    validation_id = models.BigAutoField(
        primary_key=True,
        verbose_name="ID de validación",
    )

    evidence = models.ForeignKey(
        Evidence,
        on_delete=models.PROTECT,
        related_name="validations",
        verbose_name="Evidencia",
    )

    verifier = models.ForeignKey(
        "organization.Employee",
        on_delete=models.PROTECT,
        related_name="validations_performed",
        verbose_name="Funcionario verificador",
    )

    decision = models.CharField(
        max_length=50,
        verbose_name="Decisión",
    )

    date = models.DateTimeField(
        verbose_name="Fecha",
    )

    observation = models.TextField(
        blank=True,
        verbose_name="Observación",
    )

    result = models.CharField(
        max_length=100,
        verbose_name="Resultado",
    )

    version = models.PositiveIntegerField(
        default=1,
        verbose_name="Versión",
    )

    class Meta:
        verbose_name = "Validación"
        verbose_name_plural = "Validaciones"
        ordering = ("-date", "-version")

    def clean(self):
        super().clean()
        _validate_changed_text_lengths(
            self,
            {"observation": (1000, "La observación")},
        )
        if self.version is not None and self.version < 1:
            previous_version = None
            if self.pk:
                previous_version = (
                    type(self)
                    .objects.filter(pk=self.pk)
                    .values_list("version", flat=True)
                    .first()
                )
            if self._state.adding or previous_version != self.version:
                raise ValidationError(
                    {"version": "La versión debe ser igual o mayor que 1."}
                )
        if _relationship_fields_changed(self, ("evidence", "verifier")):
            self._validate_relationships()

    def _validate_relationships(self):
        if not self.evidence_id or not self.verifier_id:
            return

        if self.pk:
            original_goal_id = (
                type(self).objects.filter(pk=self.pk)
                .values_list(
                    "evidence__activity__goal_id",
                    flat=True,
                )
                .first()
            )
            new_goal_id = (
                Evidence.objects.filter(pk=self.evidence_id)
                .values_list("activity__goal_id", flat=True)
                .first()
            )
            if (
                original_goal_id is not None
                and new_goal_id is not None
                and original_goal_id != new_goal_id
            ):
                raise ValidationError(
                    {
                        "evidence": (
                            "No se puede trasladar una validación a una "
                            "evidencia de otra meta, porque afectaría el "
                            "recálculo de sus indicadores."
                        )
                    }
                )

        from organization.models import Employee

        evidence_relationship = (
            Evidence.objects.filter(pk=self.evidence_id)
            .values_list(
                "activity__author_id",
                "activity__goal__employee_id",
                "activity__author__delegation_id",
                "activity__goal__employee__delegation_id",
                "author__delegation_id",
            )
            .first()
        )
        verifier_delegation_id = (
            Employee.objects.filter(pk=self.verifier_id)
            .values_list("delegation_id", flat=True)
            .first()
        )
        if evidence_relationship is None:
            return

        (
            activity_author_id,
            goal_employee_id,
            activity_delegation_id,
            goal_delegation_id,
            evidence_author_delegation_id,
        ) = evidence_relationship
        if (
            activity_author_id != goal_employee_id
            or activity_delegation_id != goal_delegation_id
            or evidence_author_delegation_id != activity_delegation_id
        ):
            raise ValidationError(
                {
                    "evidence": (
                        "La evidencia asociada no mantiene relaciones "
                        "coherentes con la delegación de su actividad."
                    )
                }
            )
        if (
            verifier_delegation_id is not None
            and activity_delegation_id != verifier_delegation_id
        ):
            raise ValidationError(
                {
                    "verifier": (
                        "El funcionario verificador debe pertenecer "
                        "a la misma delegación de la actividad."
                    )
                }
            )

    def save(self, *args, **kwargs):
        if self.version is not None and self.version < 1:
            update_fields = kwargs.get("update_fields")
            version_included = update_fields is None or (
                "version" in update_fields
            )
            previous_version = None
            if self.pk:
                previous_version = (
                    type(self)
                    .objects.filter(pk=self.pk)
                    .values_list("version", flat=True)
                    .first()
                )
            if self._state.adding or (
                version_included and previous_version != self.version
            ):
                raise ValidationError(
                    {"version": "La versión debe ser igual o mayor que 1."}
                )
        _validate_changed_relationships(
            self,
            ("evidence", "verifier"),
            kwargs.get("update_fields"),
        )
        return super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"Validación {self.validation_id} - "
            f"{self.decision}"
        )

# ---------------------------------------------------------
# Catálogo de Tipos de Actividad
# ---------------------------------------------------------

class ActivityType(BaseModel):
    activity_type_id = models.BigAutoField(
        primary_key=True,
        verbose_name="ID de tipo de actividad",
    )

    code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Código",
    )

    name = models.CharField(
        max_length=150,
        verbose_name="Nombre",
    )

    description = models.TextField(
        blank=True,
        verbose_name="Descripción",
    )

    status = models.BooleanField(
        default=True,
        verbose_name="Estado",
    )

    class Meta:
        verbose_name = "Tipo de actividad"
        verbose_name_plural = "Tipos de actividad"
        ordering = ("name", "activity_type_id")

    def clean(self):
        super().clean()
        _validate_changed_text_lengths(
            self,
            {"description": (300, "La descripción")},
        )

    def __str__(self):
        return f"{self.code} - {self.name}"
# ---------------------------------------------------------
# Tipo de Atención
# ---------------------------------------------------------


class AttentionType(BaseModel):
    attention_type_id = models.BigAutoField(
        primary_key=True,
        verbose_name="ID de tipo de atención",
    )

    code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Código",
    )

    name = models.CharField(
        max_length=150,
        verbose_name="Nombre",
    )

    description = models.TextField(
        blank=True,
        verbose_name="Descripción",
    )

    status = models.BooleanField(
        default=True,
        verbose_name="Estado",
    )

    class Meta:
        verbose_name = "Tipo de atención"
        verbose_name_plural = "Tipos de atención"
        ordering = ("name", "attention_type_id")

    def clean(self):
        super().clean()
        _validate_changed_text_lengths(
            self,
            {"description": (300, "La descripción")},
        )

    def __str__(self):
        return f"{self.code} - {self.name}"

# ---------------------------------------------------------
# Catálogo de Servicios
# ---------------------------------------------------------

class Service(BaseModel):
    service_id = models.BigAutoField(
        primary_key=True,
        verbose_name="ID del servicio",
    )

    code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Código",
    )

    name = models.CharField(
        max_length=150,
        verbose_name="Nombre",
    )

    description = models.TextField(
        blank=True,
        verbose_name="Descripción",
    )

    status = models.BooleanField(
        default=True,
        verbose_name="Estado",
    )

    class Meta:
        verbose_name = "Servicio"
        verbose_name_plural = "Servicios"
        ordering = ("name", "service_id")

    def clean(self):
        super().clean()
        _validate_changed_text_lengths(
            self,
            {"description": (300, "La descripción")},
        )

    def __str__(self):
        return f"{self.code} - {self.name}"


# ---------------------------------------------------------
# Sub Atención
# ---------------------------------------------------------


class SubAttention(BaseModel):
    sub_attention_id = models.BigAutoField(
        primary_key=True,
        verbose_name="ID de subatención",
    )

    code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Código",
    )

    name = models.CharField(
        max_length=150,
        verbose_name="Nombre",
    )

    attention_type = models.ForeignKey(
        AttentionType,
        on_delete=models.PROTECT,
        related_name="sub_attentions",
        verbose_name="Tipo de atención",
    )

    status = models.BooleanField(
        default=True,
        verbose_name="Estado",
    )

    class Meta:
        verbose_name = "Subatención"
        verbose_name_plural = "Subatenciones"
        ordering = ("name", "sub_attention_id")

    def __str__(self):
        return f"{self.code} - {self.name}"


# ---------------------------------------------------------
# Ingreso de Atención
# ---------------------------------------------------------


class AttentionEntry(BaseModel):
    citizen = models.ForeignKey("citizen_registry.Citizen", on_delete=models.PROTECT, null=True, blank=True, related_name="attention_entries")
    ORIGIN_CHOICES = [
        ("LEGACY", "Sin clasificar"),
        ("CITIZEN", "Vecinal"),
        ("INTERNAL", "Interna"),
    ]

    STATUS_CHOICES = [
        ("NEW", "Nueva"),
        ("PENDING", "Pendiente"),
        ("IN_PROGRESS", "En proceso"),
        ("RESOLVED", "Resuelta"),
        ("CLOSED", "Cerrada"),
        ("REJECTED", "No procede"),
    ]

    attention_entry_id = models.BigAutoField(
        primary_key=True,
        verbose_name="ID de ingreso de atención",
    )

    origin = models.CharField(
        max_length=12,
        choices=ORIGIN_CHOICES,
        default="LEGACY",
        verbose_name="Origen",
    )

    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default="NEW",
        verbose_name="Estado",
    )

    tracking_code = models.UUIDField(
        unique=True,
        null=True,
        blank=True,
        editable=False,
        verbose_name="Código de seguimiento",
    )

    requester = models.CharField(
        max_length=150,
        verbose_name="Solicitante",
    )

    requester_email = models.EmailField(
        blank=True,
        verbose_name="Correo electrónico del solicitante",
    )

    requester_phone = models.CharField(
        max_length=25,
        blank=True,
        verbose_name="Teléfono del solicitante",
    )

    subject = models.CharField(
        max_length=160,
        blank=True,
        verbose_name="Asunto",
    )

    address = models.CharField(
        max_length=250,
        blank=True,
        verbose_name="Dirección",
    )

    attention_type = models.ForeignKey(
        AttentionType,
        on_delete=models.PROTECT,
        related_name="attention_entries",
        verbose_name="Tipo de atención",
    )

    sub_attention = models.ForeignKey(
        SubAttention,
        on_delete=models.PROTECT,
        related_name="attention_entries",
        verbose_name="Subatención",
    )

    description = models.TextField(
        verbose_name="Descripción",
    )

    delegation = models.ForeignKey(
        "organization.Delegation",
        on_delete=models.PROTECT,
        related_name="attention_entries",
        verbose_name="Delegación",
    )

    responsible_employee = models.ForeignKey(
        "organization.Employee",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="attention_entries_responsible",
        verbose_name="Funcionario responsable",
    )

    registered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name="registered_attention_entries",
        verbose_name="Usuario que registra",
    )

    registration_date = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de registro",
    )

    closed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha de cierre",
    )

    def get_status_display(self):
        # El seguimiento público e interno usan la misma etiqueta.
        return "En gestión" if self.status == "IN_PROGRESS" else self._get_FIELD_display(self._meta.get_field("status"))

    class Meta:
        verbose_name = "Ingreso de atención"
        verbose_name_plural = "Ingresos de atención"
        ordering = (
            "-registration_date",
            "attention_entry_id",
        )

    def full_clean(self, *args, **kwargs):
        if self.origin == "CITIZEN":
            self.requester_email = (self.requester_email or "").strip()
        super().full_clean(*args, **kwargs)

    def _validate_citizen_email(self):
        if self.origin != "CITIZEN":
            return

        email = (self.requester_email or "").strip()
        if not email:
            raise ValidationError(
                {
                    "requester_email": (
                        "El correo electrónico es obligatorio "
                        "para las atenciones vecinales."
                    )
                }
            )

        try:
            validate_email(email)
        except ValidationError as exc:
            raise ValidationError(
                {
                    "requester_email": (
                        "Ingresa un correo electrónico válido."
                    )
                }
            ) from exc

        self.requester_email = email

    def clean(self):
        super().clean()

        _validate_changed_text_lengths(
            self,
            {"description": (4000, "La descripción")},
        )
        self._validate_citizen_email()

        if (
            self.attention_type_id
            and self.sub_attention_id
            and self.sub_attention.attention_type_id
            != self.attention_type_id
        ):
            raise ValidationError(
                {
                    "sub_attention": (
                        "La sub atención seleccionada no pertenece "
                        "al tipo de atención indicado."
                    )
                }
            )

    def save(self, *args, **kwargs):
        email_before_validation = self.requester_email
        self._validate_citizen_email()
        if (
            kwargs.get("update_fields") is not None
            and self.requester_email != email_before_validation
        ):
            kwargs["update_fields"] = set(kwargs["update_fields"])
            kwargs["update_fields"].add("requester_email")

        if self._state.adding:
            if self.tracking_code is None:
                self.tracking_code = uuid.uuid4()
        elif self.pk:
            stored_tracking_code = (
                type(self)
                .objects
                .only("tracking_code")
                .get(pk=self.pk)
                .tracking_code
            )
            self.tracking_code = stored_tracking_code

        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"Atención {self.attention_entry_id} - "
            f"{self.requester}"
        )