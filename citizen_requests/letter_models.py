"""Datos propios de correspondencia sin duplicar las solicitudes existentes.

Una carta ingresa como una CitizenRequest ordinaria; la relación 1:1 conserva
el documento de origen y permite reutilizar estados, atenciones e historial.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone


class CitizenRequestLetter(models.Model):
    class Kind(models.TextChoices):
        CARTA = "CARTA", "Carta"
        OFICIO = "OFICIO", "Oficio"

    request = models.OneToOneField(
        "citizen_requests.CitizenRequest",
        on_delete=models.PROTECT,
        related_name="letter_record",
        verbose_name="Solicitud vinculada",
    )
    kind = models.CharField(
        "Tipo de correspondencia", max_length=10, choices=Kind.choices,
        default=Kind.CARTA,
    )
    external_folio = models.CharField(
        "Folio o número externo", max_length=80, blank=True,
    )
    sender_institution = models.CharField(
        "Remitente institucional", max_length=160, blank=True,
    )
    received_at = models.DateTimeField(
        "Fecha de recepción", default=timezone.now,
    )
    registered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="registered_sgr_letters",
        verbose_name="Registrado por",
    )

    class Meta:
        ordering = ("-received_at", "-pk")
        verbose_name = "Carta recibida"
        verbose_name_plural = "Cartas recibidas"

    def __str__(self):
        return f"{self.get_kind_display()} — Solicitud {self.request_id}"
