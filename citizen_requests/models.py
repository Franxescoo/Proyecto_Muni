import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import models


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