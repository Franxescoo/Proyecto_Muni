"""Estado y auditoría de cierres semanales por delegación del SGR."""
from django.conf import settings
from django.db import models
from datetime import timedelta


class CitizenRequestActionWeek(models.Model):
    """Una fila por delegación y semana; puede cerrarse o reabrirse."""

    delegation = models.ForeignKey(
        "organization.Delegation",
        on_delete=models.PROTECT,
        related_name="request_action_weeks",
        verbose_name="Delegación",
    )
    week_start = models.DateField(verbose_name="Lunes de la semana")
    is_closed = models.BooleanField(default=True, verbose_name="Semana cerrada")
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="closed_request_action_weeks",
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "Cierre semanal de gestiones"
        verbose_name_plural = "Cierres semanales de gestiones"
        ordering = ("-week_start",)
        default_permissions = ()
        permissions = [
            (
                "manage_citizenrequestaction_week",
                "Puede cerrar y reabrir semanas de gestiones",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["delegation", "week_start"],
                name="sgr_actionweek_delegation_date",
            ),
        ]

    @property
    def week_end(self):
        return self.week_start + timedelta(days=6)

    def __str__(self):
        return f"{self.delegation} · {self.week_start:%d/%m/%Y}"


class CitizenRequestActionWeekEvent(models.Model):
    """Historial inmutable de aperturas y cierres (solo inserción)."""
    CLOSE = "CLOSE"
    REOPEN = "REOPEN"
    ACTIONS = [(CLOSE, "Cierre"), (REOPEN, "Reapertura")]

    week = models.ForeignKey(
        CitizenRequestActionWeek,
        on_delete=models.PROTECT,
        related_name="events",
    )
    action = models.CharField(max_length=6, choices=ACTIONS)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="request_action_week_events",
    )
    reason = models.CharField(max_length=500, blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        default_permissions = ()
        ordering = ("-occurred_at", "-pk")
        verbose_name = "Historial de cierre semanal"
        verbose_name_plural = "Historial de cierres semanales"

    def __str__(self):
        return f"{self.get_action_display()} {self.week}"
