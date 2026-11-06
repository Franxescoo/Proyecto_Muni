from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import models
from django.utils import timezone
from .rut import normalize_rut, validate_rut

RSH_OPTIONS = [
    ("", "Sin registrar"),
    ("0-40", "0–40 %"),
    ("41-50", "41–50 %"),
    ("51-60", "51–60 %"),
    ("61-70", "61–70 %"),
    ("71-80", "71–80 %"),
    ("81-90", "81–90 %"),
    ("91-100", "91–100 %"),
]
ROLE_OPTIONS = [
    ("NONE", "Ninguno"),
    ("PRESIDENT", "Presidente/a"),
    ("SECRETARY", "Secretario/a"),
    ("TREASURER", "Tesorero/a"),
    ("DELEGATE", "Delegado/a"),
]


class Citizen(models.Model):
    rut = models.CharField("RUT", max_length=16, unique=True)
    full_name = models.CharField("Nombre completo", max_length=160)
    birth_date = models.DateField("Fecha de nacimiento", null=True, blank=True)
    phone = models.CharField("Teléfono", max_length=25, blank=True)
    email = models.EmailField("Correo electrónico", blank=True)
    address = models.CharField("Dirección", max_length=250)
    rsh_folio = models.CharField("Folio Cartola RSH", max_length=80, blank=True)
    rsh_bracket = models.CharField("Tramo RSH", max_length=7, choices=RSH_OPTIONS, blank=True)
    is_neighborhood_member = models.BooleanField("Pertenece a Junta de Vecinos", default=False)
    neighborhood_group = models.CharField("Junta de Vecinos o agrupación", max_length=180, blank=True)
    organization_role = models.CharField("Cargo en la organización", max_length=12, choices=ROLE_OPTIONS, default="NONE", blank=True)
    is_active = models.BooleanField("Activo", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="citizens_created")

    class Meta:
        ordering = ("full_name", "pk")
        verbose_name = "Ciudadano"
        verbose_name_plural = "Ciudadanos"

    @property
    def age(self):
        if not self.birth_date:
            return None
        today = timezone.localdate()
        return today.year - self.birth_date.year - ((today.month, today.day) < (self.birth_date.month, self.birth_date.day))

    def clean(self):
        self.rut = normalize_rut(self.rut)
        validate_rut(self.rut)
        if not (self.full_name or "").strip():
            raise ValidationError({"full_name": "El nombre es obligatorio."})
        self.full_name = self.full_name.strip()
        if self.birth_date and self.birth_date > timezone.localdate():
            raise ValidationError({"birth_date": "La fecha de nacimiento no puede ser futura."})
        if self.email:
            validate_email(self.email)
            self.email = self.email.strip().lower()
        if not self.is_neighborhood_member:
            self.neighborhood_group = ""
            self.organization_role = "NONE"
        elif not (self.neighborhood_group or "").strip():
            raise ValidationError({"neighborhood_group": "Indica la Junta de Vecinos o agrupación."})

    def save(self, *args, **kwargs):
        self.rut = normalize_rut(self.rut)
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.full_name} · {self.rut}"


class CitizenAudit(models.Model):
    citizen = models.ForeignKey(Citizen, on_delete=models.PROTECT, related_name="audit_events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    action = models.CharField(max_length=20)
    changed_at = models.DateTimeField(auto_now_add=True)
    description = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ("-changed_at", "-pk")
        verbose_name = "Auditoría de ciudadano"
        verbose_name_plural = "Auditoría de ciudadanos"
