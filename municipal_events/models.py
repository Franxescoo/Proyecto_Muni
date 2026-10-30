"""Eventos recurrentes, campañas municipales e inscripciones auditables.

No modifica el esquema de Registro y Validación: las inscripciones referencian
AttentionEntry existente y las campañas referencian AttentionType por PK.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


def normalized_rut(value):
    """Rut chileno canónico sin puntos/guion, con DV. No registra el RUT en logs."""
    return (value or "").replace(".", "").replace("-", "").replace(" ", "").upper()


def validate_rut(value):
    value = normalized_rut(value)
    if len(value) < 2 or not value[:-1].isdigit() or len(value[:-1]) > 8:
        raise ValidationError("Ingresa un RUT chileno válido, incluyendo dígito verificador.")
    base, dv = value[:-1], value[-1]
    if int(base) == 0:
        raise ValidationError("El RUT no es válido.")
    total = sum(int(n) * (2 + i % 6) for i, n in enumerate(reversed(base)))
    check = 11 - (total % 11)
    expected = "0" if check == 11 else "K" if check == 10 else str(check)
    if dv != expected:
        raise ValidationError("El dígito verificador del RUT no es válido.")


class MunicipalEvent(models.Model):
    name = models.CharField("Nombre del evento", max_length=160)
    description = models.TextField("Descripción", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    class Meta:
        ordering = ("name", "pk")
        verbose_name = "Evento municipal"
        verbose_name_plural = "Eventos municipales"

    def __str__(self):
        return self.name


class EventEdition(models.Model):
    STATUS = [("PLANNED", "Planificada"), ("ACTIVE", "En ejecución"), ("FINISHED", "Finalizada")]
    event = models.ForeignKey(MunicipalEvent, on_delete=models.PROTECT, related_name="editions")
    year = models.PositiveIntegerField("Año")
    date = models.DateField("Fecha del evento")
    place = models.CharField("Lugar", max_length=200)
    delegation = models.ForeignKey("organization.Delegation", on_delete=models.PROTECT, related_name="municipal_event_editions")
    status = models.CharField("Estado", max_length=12, choices=STATUS, default="PLANNED")
    responsible = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="municipal_edition_responsibilities")
    notes = models.TextField("Observaciones", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-year", "-date")
        constraints = [models.UniqueConstraint(fields=["event", "year"], name="unique_municipal_event_year")]
        verbose_name = "Edición de evento municipal"
        verbose_name_plural = "Ediciones de eventos"

    def clean(self):
        if self.date and self.year and self.date.year != self.year:
            raise ValidationError({"year": "El año debe coincidir con la fecha del evento."})
        if self.pk and self.campaigns.exists():
            original = type(self).objects.get(pk=self.pk)
            if self.year != original.year:
                raise ValidationError({"year": "Una edición vinculada a campañas no puede cambiar de año."})

    def __str__(self):
        return f"{self.event.name} {self.year}"


class Campaign(models.Model):
    STATUS = [("DRAFT", "Borrador"), ("OPEN", "Inscripciones abiertas"), ("CLOSED", "Inscripciones cerradas")]
    title = models.CharField("Nombre de la campaña", max_length=160)
    year = models.PositiveIntegerField("Año")
    attention_type = models.ForeignKey("registration_validation.AttentionType", on_delete=models.PROTECT, related_name="municipal_campaigns", verbose_name="Tipo de atención relacionado")
    edition = models.ForeignKey(EventEdition, on_delete=models.PROTECT, blank=True, null=True, related_name="campaigns", verbose_name="Edición de evento (opcional)")
    organizing_delegation = models.ForeignKey("organization.Delegation", on_delete=models.PROTECT, related_name="organized_campaigns", verbose_name="Delegación organizadora")
    description = models.TextField("Descripción", blank=True)
    opens_on = models.DateField("Inicio de inscripciones")
    closes_on = models.DateField("Fin de inscripciones")
    status = models.CharField("Estado", max_length=10, choices=STATUS, default="DRAFT")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-year", "title")
        verbose_name = "Campaña municipal"
        verbose_name_plural = "Campañas municipales"

    def __str__(self):
        return f"{self.title} ({self.year})"

    def clean(self):
        if self.opens_on and self.closes_on and self.closes_on < self.opens_on:
            raise ValidationError({"closes_on": "La fecha de cierre no puede ser anterior a la apertura."})
        if self.edition_id and self.year and self.edition.year != self.year:
            raise ValidationError({"edition": "La edición debe pertenecer al año de la campaña."})
        if self.attention_type_id and not self.attention_type.status:
            raise ValidationError({"attention_type": "Selecciona un tipo de atención activo."})
        if self.pk and self.enrollments.exists():
            original = type(self).objects.get(pk=self.pk)
            locked = ("attention_type_id", "year", "edition_id", "organizing_delegation_id")
            if any(getattr(self, attr) != getattr(original, attr) for attr in locked):
                raise ValidationError("Una campaña con inscripciones no puede cambiar tipo de atención, año, edición o delegación organizadora. Conserva el historial.")

    @property
    def accepts_enrollments(self):
        now = timezone.localdate()
        return self.status == "OPEN" and self.opens_on <= now <= self.closes_on


class Beneficiary(models.Model):
    name = models.CharField("Nombre del beneficiario", max_length=160)
    rut = models.CharField("RUT del beneficiario", max_length=9, unique=True)
    birth_date = models.DateField("Fecha de nacimiento")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "Beneficiario"
        verbose_name_plural = "Beneficiarios"

    def clean(self):
        self.rut = normalized_rut(self.rut)
        validate_rut(self.rut)
        if self.birth_date and self.birth_date > timezone.localdate():
            raise ValidationError({"birth_date": "La fecha de nacimiento no puede ser futura."})

    def save(self, *args, **kwargs):
        self.rut = normalized_rut(self.rut)
        validate_rut(self.rut)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Enrollment(models.Model):
    STATUS = [("PENDING", "Pendiente"), ("APPROVED", "Aprobada"), ("REJECTED", "Rechazada")]
    campaign = models.ForeignKey(Campaign, on_delete=models.PROTECT, related_name="enrollments")
    beneficiary = models.ForeignKey(Beneficiary, on_delete=models.PROTECT, related_name="enrollments")
    attention = models.ForeignKey("registration_validation.AttentionEntry", on_delete=models.PROTECT, related_name="campaign_enrollments")
    delegation = models.ForeignKey("organization.Delegation", on_delete=models.PROTECT, related_name="campaign_enrollments")
    status = models.CharField("Estado", max_length=10, choices=STATUS, default="PENDING")
    observation = models.TextField("Observación", blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="municipal_enrollments_created")
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="municipal_enrollments_reviewed")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [models.UniqueConstraint(fields=["campaign", "beneficiary"], name="unique_beneficiary_per_campaign")]
        verbose_name = "Inscripción a campaña"
        verbose_name_plural = "Inscripciones a campañas"

    def clean(self):
        if self.attention_id and self.campaign_id and self.attention.attention_type_id != self.campaign.attention_type_id:
            raise ValidationError("El tipo de atención no coincide con el de la campaña.")
        if self.attention_id and self.delegation_id and self.attention.delegation_id != self.delegation_id:
            raise ValidationError("La delegación debe coincidir con la atención de origen.")

    def __str__(self):
        return f"Inscripción {self.pk or 'nueva'} — {self.campaign}"


class GiftDelivery(models.Model):
    enrollment = models.OneToOneField(Enrollment, on_delete=models.PROTECT, related_name="delivery")
    delivered_at = models.DateTimeField(default=timezone.now, verbose_name="Fecha de entrega")
    delivered_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    notes = models.TextField("Constancia / observaciones", blank=True)

    class Meta:
        verbose_name = "Entrega de regalo"
        verbose_name_plural = "Entregas de regalos"

    def clean(self):
        if self.enrollment_id and self.enrollment.status != "APPROVED":
            raise ValidationError("Solo se puede registrar la entrega de una inscripción aprobada.")

    def __str__(self):
        return f"Entrega de inscripción {self.enrollment_id}"


class CampaignAudit(models.Model):
    enrollment = models.ForeignKey(Enrollment, on_delete=models.PROTECT, related_name="history")
    action = models.CharField(max_length=40)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "pk")
        verbose_name = "Historial de inscripción"
        verbose_name_plural = "Historial de inscripciones"
