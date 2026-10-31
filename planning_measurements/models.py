from django.core.exceptions import ValidationError
from django.db import models
from django.core.validators import MinValueValidator

from core.models import BaseModel


class Period(BaseModel):
    period_id = models.BigAutoField(primary_key=True)
    start_date = models.DateField(verbose_name="Start date")
    end_date = models.DateField(verbose_name="End date")
    computable_days = models.IntegerField(verbose_name="Computable days")
    status = models.CharField(
        max_length=50, default="Active", verbose_name="Status"
    )
    thresholds = models.CharField(max_length=255, verbose_name="Thresholds")
    parameters_version = models.CharField(
        max_length=50, verbose_name="Parameters version"
    )

    class Meta:
        verbose_name = "Period"
        verbose_name_plural = "Periods"
        permissions = [("delete_closed_period", "Puede archivar períodos cerrados sin historial")]

    class Status(models.TextChoices):
        ACTIVE = "Active", "Activo"
        CLOSED = "Closed", "Cerrado"

    def clean(self):
        super().clean()
        errors = {}

        if self.computable_days is not None:
            if self.computable_days <= 0:
                errors["computable_days"] = (
                    "Los días computables deben ser mayores que cero."
                )

        if self.status not in self.Status.values:
            errors["status"] = "Selecciona un estado válido."

        if self.start_date and self.end_date:
            if self.start_date > self.end_date:
                errors["end_date"] = (
                    "La fecha de término no puede ser anterior al inicio."
                )
            elif self.computable_days is not None:
                duration = (
                    self.end_date - self.start_date
                ).days + 1

                if self.computable_days > duration:
                    errors["computable_days"] = (
                        "Los días computables no pueden superar "
                        "la duración del período."
                    )

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"Period {self.start_date} to {self.end_date}"


class PeriodArchiveLog(models.Model):
    period = models.ForeignKey("planning_measurements.Period", on_delete=models.PROTECT, related_name="archive_logs")
    user = models.ForeignKey("auth.User", on_delete=models.PROTECT, related_name="period_archive_logs")
    archived_at = models.DateTimeField(auto_now_add=True)
    was_closed = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Registro de archivado de período"
        verbose_name_plural = "Registros de archivado de períodos"


class Goal(BaseModel):
    goal_id = models.BigAutoField(primary_key=True)
    period = models.ForeignKey(
        Period,
        on_delete=models.PROTECT,
        related_name="goals",
        verbose_name="Period",
    )
    employee = models.ForeignKey(
        "organization.Employee",
        on_delete=models.PROTECT,
        related_name="goals",
        verbose_name="Employee",
    )
    position = models.ForeignKey(
        "organization.PositionFunction",
        on_delete=models.PROTECT,
        related_name="goals",
        verbose_name="Position",
    )
    measurement_item = models.ForeignKey(
        "planning_measurements.MeasurementItem",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="goals",
        verbose_name="Ítem de medición",
    )
    item = models.CharField(max_length=150, verbose_name="Item")
    objective_value = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="Objective value"
    )
    required_evidence_count = models.PositiveIntegerField(
        default=5,
        validators=[MinValueValidator(2)],
        verbose_name="Required evidence count",
    )
    unit = models.CharField(max_length=50, verbose_name="Unit")
    weight = models.DecimalField(
        max_digits=5, decimal_places=2, verbose_name="Weight"
    )

    class Meta:
        verbose_name = "Goal"
        verbose_name_plural = "Goals"

    def clean(self):
        super().clean()
        errors = {}

        # Objetivo válido.
        if self.objective_value is not None:
            if self.objective_value <= 0:
                errors["objective_value"] = (
                    "El valor objetivo debe ser mayor que cero."
                )

        if self.required_evidence_count is not None:
            if self.required_evidence_count < 2:
                errors["required_evidence_count"] = (
                    "La cantidad de evidencias requeridas debe ser "
                    "mayor o igual a 2."
                )

        # Ponderación individual válida.
        if self.weight is not None:
            if not 0 <= self.weight <= 100:
                errors["weight"] = (
                    "El ponderador debe estar entre 0 y 100."
                )

        # Comprueba el período seleccionado.
        if self.period_id:
            period = self.period

            if period.deleted_at is not None:
                errors.setdefault("__all__", []).append(
                    "No se pueden guardar metas "
                    "en un período archivado."
                )

            elif period.status == Period.Status.CLOSED:
                errors.setdefault("__all__", []).append(
                    "No se pueden crear ni modificar metas "
                    "en un período cerrado."
                )

        # Comprueba el período original de una meta existente.
        # Evita trasladarla desde un período cerrado a uno abierto.
        if self.pk:
            original = (
                type(self).objects
                .filter(pk=self.pk)
                .select_related("period")
                .first()
            )

            if original is not None:
                original_period = original.period

                if original_period.deleted_at is not None:
                    errors.setdefault("__all__", []).append(
                        "La meta pertenece a un período archivado."
                    )

                elif original_period.status == Period.Status.CLOSED:
                    errors.setdefault("__all__", []).append(
                        "La meta pertenece a un período cerrado. "
                        "Primero debe reabrirse mediante "
                        "el procedimiento autorizado."
                    )

        # Correspondencia entre funcionario y cargo.
        if (
            self.employee_id
            and self.position_id
            and self.employee.position_id != self.position_id
        ):
            errors.setdefault("__all__", []).append(
                "El cargo de la meta no coincide con "
                "el cargo actual del funcionario."
            )

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"Goal: {self.item} - {self.employee}"


class MeasurementItem(BaseModel):
    item_id = models.BigAutoField(primary_key=True)

    code = models.CharField(
        max_length=20,
        unique=True,
        verbose_name="Código"
    )

    name = models.CharField(
        max_length=150,
        verbose_name="Nombre"
    )

    description = models.TextField(
        blank=True,
        verbose_name="Descripción"
    )

    class ItemType(models.TextChoices):
        QUANTITATIVE = "quantitative", "Cuantitativo"
        PERCENTAGE = "percentage", "Porcentual"

    item_type = models.CharField(
        max_length=20,
        choices=ItemType.choices,
        default=ItemType.QUANTITATIVE,
        verbose_name="Tipo de medición"
    )

    unit = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Unidad de medida",
    )

    formula = models.TextField(
        blank=True,
        verbose_name="Descripción de la fórmula"
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Activo"
    )

    class Meta:
        verbose_name = "Ítem de medición"
        verbose_name_plural = "Ítems de medición"
        ordering = ["code"]

    def clean(self):
        super().clean()

        if (
            self.item_type == self.ItemType.PERCENTAGE
            and not self.formula.strip()
        ):
            raise ValidationError({
                "formula": (
                    "Los ítems porcentuales deben tener "
                    "una fórmula definida."
                )
            })

    def __str__(self):
        return f"{self.code} - {self.name}"
