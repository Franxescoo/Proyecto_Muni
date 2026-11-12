import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import models

from core.models import BaseModel


class CitizenRequest(models.Model):
    citizen = models.ForeignKey("citizen_registry.Citizen", on_delete=models.PROTECT, null=True, blank=True, related_name="requests")
    # Identidad histórica: se asigna al corregir por primera vez una vinculación.
    original_citizen = models.ForeignKey(
        "citizen_registry.Citizen", on_delete=models.PROTECT, null=True,
        blank=True, related_name="requests_originally_linked",
    )
    # No enviar datos del caso al correo anterior tras cambiar de ciudadano.
    followup_email_paused = models.BooleanField(default=False)
    verified_followup_email = models.EmailField(blank=True)
    pending_followup_email = models.EmailField(blank=True)
    followup_verification_nonce = models.UUIDField(null=True, blank=True)

    @property
    def followup_recipient(self):
        if self.followup_email_paused:
            return ""
        return self.verified_followup_email or self.requester_email


    STATUS_CHOICES = [
        ("NEW", "Nueva"),
        ("IN_PROGRESS", "En proceso"),
        ("CLOSED", "Cerrada"),
    ]

    ORIGIN_CHOICES = [
        ("CITIZEN", "Vecinal"),
        ("INTERNAL", "Interna"),
    ]

    tracking_code = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )

    attention_entry = models.OneToOneField(
        "registration_validation.AttentionEntry",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="citizen_request",
    )

    delegation = models.ForeignKey(
        "organization.Delegation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="citizen_requests",
    )

    origin = models.CharField(
        max_length=12,
        choices=ORIGIN_CHOICES,
        default="CITIZEN",
    )

    requester_name = models.CharField(max_length=120)

    requester_email = models.EmailField(blank=True)

    requester_phone = models.CharField(
        max_length=25,
        blank=True,
    )

    address = models.CharField(max_length=250)

    subject = models.CharField(max_length=160)

    description = models.TextField()

    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default="NEW",
    )

    assigned_to = models.ForeignKey(
        "organization.Employee",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assigned_citizen_requests",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

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
                        "para las solicitudes vecinales."
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

    def save(self, *args, **kwargs):
        email_before_validation = self.requester_email
        self._validate_citizen_email()
        if (
            kwargs.get("update_fields") is not None
            and self.requester_email != email_before_validation
        ):
            kwargs["update_fields"] = set(kwargs["update_fields"])
            kwargs["update_fields"].add("requester_email")

        super().save(*args, **kwargs)

    def get_status_display(self):
        # Mismo nombre visible de estado que Ingreso de Atención.
        return "En gestión" if self.status == "IN_PROGRESS" else self._get_FIELD_display(self._meta.get_field("status"))

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Solicitud ciudadana"
        verbose_name_plural = "Solicitudes ciudadanas"
        permissions = [
            (
                "derivar_solicitud",
                "Puede derivar solicitudes ciudadanas",
            ),
        ]

    def __str__(self):
        return f"Solicitud {self.pk}: {self.subject}"


class CitizenRequestAction(BaseModel):
    ACTION_TYPE_CHOICES = [
        ("INSPECTION", "Inspección"),
        ("COORDINATION", "Coordinación"),
        ("VERIFICATION", "Verificación"),
        ("OTHER", "Otra"),
    ]

    request = models.ForeignKey(
        CitizenRequest,
        on_delete=models.PROTECT,
        related_name="actions",
        verbose_name="Solicitud ciudadana",
    )
    responsible = models.ForeignKey(
        "organization.Employee",
        on_delete=models.PROTECT,
        related_name="citizen_request_actions",
        verbose_name="Funcionario responsable",
    )
    delegation = models.ForeignKey(
        "organization.Delegation",
        on_delete=models.PROTECT,
        related_name="citizen_request_actions",
        verbose_name="Delegación de la gestión",
    )
    registered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="registered_citizen_request_actions",
        verbose_name="Usuario que registra",
    )
    action_type = models.CharField(
        max_length=20,
        choices=ACTION_TYPE_CHOICES,
        verbose_name="Tipo de actuación",
    )
    performed_at = models.DateTimeField(
        verbose_name="Fecha y hora de realización",
    )
    description = models.TextField(
        verbose_name="Descripción de la actuación",
    )
    outcome = models.TextField(
        blank=True,
        verbose_name="Resultado u observaciones",
    )

    class Meta:
        ordering = ("performed_at", "pk")
        indexes = [
            models.Index(
                fields=("request", "performed_at"),
                name="cra_req_perf_idx",
            ),
        ]
        default_permissions = ("add", "change", "view")
        verbose_name = "Gestión operativa de solicitud"
        verbose_name_plural = "Gestiones operativas de solicitudes"

    def clean(self):
        super().clean()
        errors = {}
        previous = None
        if self.pk:
            previous = (
                type(self).objects
                .filter(pk=self.pk)
                .values(
                    "request_id",
                    "delegation_id",
                    "registered_by_id",
                    "responsible_id",
                )
                .first()
            )

        if previous is None:
            if self.request_id:
                request_delegation_id, attention_delegation_id = (
                    CitizenRequest.objects
                    .filter(pk=self.request_id)
                    .values_list(
                        "delegation_id",
                        "attention_entry__delegation_id",
                    )
                    .first()
                    or (None, None)
                )
                if request_delegation_id is None:
                    errors["request"] = (
                        "La solicitud debe tener una delegación asignada."
                    )
                elif self.delegation_id != request_delegation_id:
                    errors["delegation"] = (
                        "La delegación debe coincidir con la de la solicitud."
                    )
                if (
                    attention_delegation_id is not None
                    and attention_delegation_id != self.delegation_id
                ):
                    errors["request"] = (
                        "La atención vinculada debe pertenecer a la misma "
                        "delegación de la solicitud y de la gestión."
                    )

            if self.responsible_id and self.delegation_id:
                responsible_model = (
                    self._meta.get_field("responsible").remote_field.model
                )
                responsible_delegation_id = (
                    responsible_model.objects
                    .filter(pk=self.responsible_id)
                    .values_list("delegation_id", flat=True)
                    .first()
                )
                if responsible_delegation_id != self.delegation_id:
                    errors["responsible"] = (
                        "El funcionario responsable debe pertenecer a la "
                        "delegación de la gestión."
                    )
        else:
            for field_name in ("request_id", "delegation_id", "registered_by_id"):
                if getattr(self, field_name) != previous[field_name]:
                    model_field = self._meta.get_field(field_name[:-3])
                    errors[model_field.name] = (
                        "Este dato forma parte del historial y no puede modificarse."
                    )

            if (
                self.responsible_id != previous["responsible_id"]
                and self.responsible_id
                and self.delegation_id
            ):
                responsible_model = (
                    self._meta.get_field("responsible").remote_field.model
                )
                responsible_delegation_id = (
                    responsible_model.objects
                    .filter(pk=self.responsible_id)
                    .values_list("delegation_id", flat=True)
                    .first()
                )
                if responsible_delegation_id != self.delegation_id:
                    errors["responsible"] = (
                        "El funcionario responsable debe pertenecer a la "
                        "delegación histórica de la gestión."
                    )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        restore_values = {}
        if self.pk and update_fields is not None:
            update_fields = set(update_fields)
            kwargs["update_fields"] = update_fields
            previous = (
                type(self).objects
                .filter(pk=self.pk)
                .values(
                    "request_id",
                    "delegation_id",
                    "registered_by_id",
                    "responsible_id",
                )
                .first()
            )
            if previous is not None:
                for field_name in (
                    "request",
                    "delegation",
                    "registered_by",
                    "responsible",
                ):
                    model_field = self._meta.get_field(field_name)
                    if (
                        model_field.name not in update_fields
                        and model_field.attname not in update_fields
                    ):
                        restore_values[model_field.attname] = getattr(
                            self, model_field.attname
                        )
                        setattr(
                            self,
                            model_field.attname,
                            previous[model_field.attname],
                        )

        try:
            self.full_clean()
            super().save(*args, **kwargs)
        finally:
            for field_name, value in restore_values.items():
                setattr(self, field_name, value)

    def __str__(self):
        return f"{self.get_action_type_display()} — Solicitud {self.request_id}"


class RequestEvent(models.Model):

    request = models.ForeignKey(
        CitizenRequest,
        on_delete=models.PROTECT,
        related_name="events",
    )

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )

    observation = models.TextField()

    previous_status = models.CharField(max_length=15)

    new_status = models.CharField(max_length=15)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        verbose_name = "Evento de solicitud"
        verbose_name_plural = "Eventos de solicitudes"