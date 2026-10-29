import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, validate_email
from django.db import models

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
        verbose_name="Activity ID",
    )

    goal = models.ForeignKey(
        "planning_measurements.Goal",
        on_delete=models.PROTECT,
        related_name="activities",
        verbose_name="Goal",
    )

    author = models.ForeignKey(
        "organization.Employee",
        on_delete=models.PROTECT,
        related_name="activities_created",
        verbose_name="Author",
    )
    activity_type = models.ForeignKey(
        "registration_validation.ActivityType",
        on_delete=models.PROTECT,
        related_name="activities",
        null=True,
        blank=True,
        verbose_name="Tipo de actividad",
    )

    date = models.DateField(
        verbose_name="Date",
    )

    request_problem = models.TextField(
        verbose_name="Request or problem",
    )

    action = models.TextField(
        verbose_name="Action",
    )

    contact = models.CharField(
        max_length=150,
        verbose_name="Contact",
    )

    phone = models.CharField(
        max_length=20,
        verbose_name="Phone",
    )

    status = models.CharField(
        max_length=50,
        default="Pending",
        verbose_name="Status",
    )

    class Meta:
        verbose_name = "Activity"
        verbose_name_plural = "Activities"
        ordering = ("-date", "activity_id")

    def clean(self):
        super().clean()

        if self.goal_id and self.author_id:
            if self.goal.employee_id != self.author_id:
                raise ValidationError(
                    {
                        "author": (
                            "The activity author must match the "
                            "employee assigned to the selected goal."
                        )
                    }
                )

    def __str__(self):
        return (
            f"Activity {self.activity_id} - "
            f"{self.goal.item}"
        )


class Evidence(BaseModel):
    evidence_id = models.BigAutoField(
        primary_key=True,
        verbose_name="Evidence ID",
    )

    code = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="Code",
    )

    activity = models.ForeignKey(
        Activity,
        on_delete=models.PROTECT,
        related_name="evidences",
        verbose_name="Activity",
    )

    author = models.ForeignKey(
        "organization.Employee",
        on_delete=models.PROTECT,
        related_name="evidences_created",
        verbose_name="Author",
    )

    file_link = models.CharField(
        max_length=500,
        blank=True,
        verbose_name="File or link",
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
        verbose_name="Evidence file",
    )

    date = models.DateTimeField(
        verbose_name="Date",
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Metadata",
    )

    review_status = models.CharField(
        max_length=50,
        default="Pending",
        verbose_name="Review status",
    )

    class Meta:
        verbose_name = "Evidence"
        verbose_name_plural = "Evidences"
        ordering = ("-date", "evidence_id")

    def __str__(self):
        return self.code


class EvidenceFile(BaseModel):
    evidence_file_id = models.BigAutoField(
        primary_key=True,
        verbose_name="Evidence File ID",
    )

    evidence = models.ForeignKey(
        Evidence,
        on_delete=models.CASCADE,
        related_name="files",
        verbose_name="Evidence",
    )

    file = models.FileField(
        upload_to="evidences/%Y/%m/",
        validators=[
            FileExtensionValidator(
                allowed_extensions=EVIDENCE_ALLOWED_EXTENSIONS
            ),
            validate_evidence_file_size,
        ],
        verbose_name="File",
    )

    class Meta:
        verbose_name = "Evidence File"
        verbose_name_plural = "Evidence Files"
        ordering = (
            "evidence_id",
            "evidence_file_id",
        )

    def __str__(self):
        return self.file.name


class Validation(BaseModel):
    validation_id = models.BigAutoField(
        primary_key=True,
        verbose_name="Validation ID",
    )

    evidence = models.ForeignKey(
        Evidence,
        on_delete=models.PROTECT,
        related_name="validations",
        verbose_name="Evidence",
    )

    verifier = models.ForeignKey(
        "organization.Employee",
        on_delete=models.PROTECT,
        related_name="validations_performed",
        verbose_name="Verifier",
    )

    decision = models.CharField(
        max_length=50,
        verbose_name="Decision",
    )

    date = models.DateTimeField(
        verbose_name="Date",
    )

    observation = models.TextField(
        blank=True,
        verbose_name="Observation",
    )

    result = models.CharField(
        max_length=100,
        verbose_name="Result",
    )

    version = models.PositiveIntegerField(
        default=1,
        verbose_name="Version",
    )

    class Meta:
        verbose_name = "Validation"
        verbose_name_plural = "Validations"
        ordering = ("-date", "-version")

    def __str__(self):
        return (
            f"Validation {self.validation_id} - "
            f"{self.decision}"
        )

# ---------------------------------------------------------
# Catálogo de Tipos de Actividad
# ---------------------------------------------------------

class ActivityType(BaseModel):
    activity_type_id = models.BigAutoField(
        primary_key=True,
        verbose_name="Activity Type ID",
    )

    code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Code",
    )

    name = models.CharField(
        max_length=150,
        verbose_name="Name",
    )

    description = models.TextField(
        blank=True,
        verbose_name="Description",
    )

    status = models.BooleanField(
        default=True,
        verbose_name="Status",
    )

    class Meta:
        verbose_name = "Activity Type"
        verbose_name_plural = "Activity Types"
        ordering = ("name", "activity_type_id")

    def __str__(self):
        return f"{self.code} - {self.name}"
# ---------------------------------------------------------
# Tipo de Atención
# ---------------------------------------------------------


class AttentionType(BaseModel):
    attention_type_id = models.BigAutoField(
        primary_key=True,
        verbose_name="Attention Type ID",
    )

    code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Code",
    )

    name = models.CharField(
        max_length=150,
        verbose_name="Name",
    )

    description = models.TextField(
        blank=True,
        verbose_name="Description",
    )

    status = models.BooleanField(
        default=True,
        verbose_name="Status",
    )

    class Meta:
        verbose_name = "Attention Type"
        verbose_name_plural = "Attention Types"
        ordering = ("name", "attention_type_id")

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

    def __str__(self):
        return f"{self.code} - {self.name}"


# ---------------------------------------------------------
# Sub Atención
# ---------------------------------------------------------


class SubAttention(BaseModel):
    sub_attention_id = models.BigAutoField(
        primary_key=True,
        verbose_name="Sub Attention ID",
    )

    code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Code",
    )

    name = models.CharField(
        max_length=150,
        verbose_name="Name",
    )

    attention_type = models.ForeignKey(
        AttentionType,
        on_delete=models.PROTECT,
        related_name="sub_attentions",
        verbose_name="Attention Type",
    )

    status = models.BooleanField(
        default=True,
        verbose_name="Status",
    )

    class Meta:
        verbose_name = "Sub Attention"
        verbose_name_plural = "Sub Attentions"
        ordering = ("name", "sub_attention_id")

    def __str__(self):
        return f"{self.code} - {self.name}"


# ---------------------------------------------------------
# Ingreso de Atención
# ---------------------------------------------------------


class AttentionEntry(BaseModel):
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
        verbose_name="Attention Entry ID",
    )

    origin = models.CharField(
        max_length=12,
        choices=ORIGIN_CHOICES,
        default="LEGACY",
        verbose_name="Origin",
    )

    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default="NEW",
        verbose_name="Status",
    )

    tracking_code = models.UUIDField(
        unique=True,
        null=True,
        blank=True,
        editable=False,
        verbose_name="Tracking code",
    )

    requester = models.CharField(
        max_length=150,
        verbose_name="Requester",
    )

    requester_email = models.EmailField(
        blank=True,
        verbose_name="Requester email",
    )

    requester_phone = models.CharField(
        max_length=25,
        blank=True,
        verbose_name="Requester phone",
    )

    subject = models.CharField(
        max_length=160,
        blank=True,
        verbose_name="Subject",
    )

    address = models.CharField(
        max_length=250,
        blank=True,
        verbose_name="Address",
    )

    attention_type = models.ForeignKey(
        AttentionType,
        on_delete=models.PROTECT,
        related_name="attention_entries",
        verbose_name="Attention Type",
    )

    sub_attention = models.ForeignKey(
        SubAttention,
        on_delete=models.PROTECT,
        related_name="attention_entries",
        verbose_name="Sub Attention",
    )

    description = models.TextField(
        verbose_name="Description",
    )

    delegation = models.ForeignKey(
        "organization.Delegation",
        on_delete=models.PROTECT,
        related_name="attention_entries",
        verbose_name="Delegation",
    )

    responsible_employee = models.ForeignKey(
        "organization.Employee",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="attention_entries_responsible",
        verbose_name="Responsible employee",
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
        verbose_name="Registration date",
    )

    closed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Closed at",
    )

    class Meta:
        verbose_name = "Attention Entry"
        verbose_name_plural = "Attention Entries"
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
            f"Attention {self.attention_entry_id} - "
            f"{self.requester}"
        )