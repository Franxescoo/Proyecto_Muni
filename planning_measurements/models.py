from django.core.exceptions import ValidationError
from django.conf import settings
from django.db import models
import re

from django.core.validators import MinValueValidator

from core.models import BaseModel

_PARAMETERS_VERSION_PATTERN = re.compile(
    r"^(?:[A-Za-z0-9_-]*v)?\d+(?:\.\d+)*$",
    re.I,
)


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
        max_length=50,
        verbose_name="Parameters version",
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

        if not _PARAMETERS_VERSION_PATTERN.fullmatch(
            (self.parameters_version or "").strip()
        ):
            errors["parameters_version"] = (
                "La versión debe tener un formato numérico, por ejemplo "
                "SGR050-v1, v1 o SGR044-v1.3."
            )

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
            else:
                # Los períodos vigentes comparten un mismo calendario de medición.
                # Se incluye el día inicial y final: compartir cualquiera de ellos
                # también cuenta como solapamiento. El registro propio se excluye
                # al editar y los períodos archivados no bloquean nuevas fechas.
                overlapping = type(self).objects.filter(
                    deleted_at__isnull=True,
                    start_date__lte=self.end_date,
                    end_date__gte=self.start_date,
                ).exclude(pk=self.pk)
                if overlapping.exists():
                    errors["start_date"] = (
                        "Las fechas se superponen con otro período no archivado. "
                        "Selecciona un rango que no esté ocupado."
                    )

                if self.computable_days is not None:
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

        if self.measurement_item_id and self.position_id:
            historical_item = False
            if self.pk:
                previous = (
                    type(self).objects
                    .filter(pk=self.pk)
                    .values(
                        "measurement_item_id", "employee_id", "position_id"
                    )
                    .first()
                )
                historical_item = bool(
                    previous
                    and previous["measurement_item_id"] == self.measurement_item_id
                    and previous["employee_id"] == self.employee_id
                    and previous["position_id"] == self.position_id
                )

            item = self.measurement_item
            if not historical_item and (
                item.deleted_at is not None
                or not item.is_active
                or not self.position.catalog_items.filter(pk=item.pk).exists()
            ):
                errors.setdefault("measurement_item", []).append(
                    "El ítem debe estar activo y autorizado para el cargo."
                )

            if (
                item.item_type == MeasurementItem.ItemType.PERCENTAGE
                and not historical_item
            ):
                from .measurement_rules import canonical_percentage_formula

                if not canonical_percentage_formula(item.formula):
                    errors.setdefault("measurement_item", []).append(
                        "El ítem porcentual no tiene una fórmula compatible."
                    )


        # Evitar metas duplicadas en el mismo período.
        if (
            self.period_id
            and self.employee_id
            and self.position_id
            and self.measurement_item_id
        ):
            duplicada = Goal.objects.filter(
                period_id=self.period_id,
                employee_id=self.employee_id,
                position_id=self.position_id,
                measurement_item_id=self.measurement_item_id,
                deleted_at__isnull=True,
            ).exclude(pk=self.pk).exists()

            if duplicada:
                errors.setdefault("__all__", []).append(
                    "Ya existe una meta con este período, "
                    "funcionario, cargo e ítem de medición."
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


class PeriodParameterSnapshot(models.Model):
    """Copia histórica de la configuración vigente al registrar el evento.

    Las revisiones se agregan; no se editan o eliminan por la aplicación.
    Esta tabla NO sustituye el motor de indicadores ni su histórico de resultados.
    """

    class Event(models.TextChoices):
        CREATED = "CREATED", "Creación"
        CONFIGURED = "CONFIGURED", "Actualización de parámetros"
        GOALS_UPDATED = "GOALS_UPDATED", "Modificación de metas"
        CATALOG_UPDATED = "CATALOG_UPDATED", "Cambio de ítem"
        CLOSED = "CLOSED", "Cierre"
        REOPENED = "REOPENED", "Reapertura"

    period = models.ForeignKey(
        Period, on_delete=models.PROTECT, related_name="parameter_snapshots"
    )
    revision = models.PositiveIntegerField()
    event = models.CharField(max_length=20, choices=Event.choices)
    saved_at = models.DateTimeField(auto_now_add=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="period_parameter_snapshots"
    )
    content = models.JSONField(default=dict)

    class Meta:
        ordering = ("-revision",)
        constraints = [
            models.UniqueConstraint(
                fields=("period", "revision"),
                name="unique_period_parameter_revision",
            ),
        ]
        verbose_name = "Versión histórica del período"
        verbose_name_plural = "Versiones históricas del período"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError(
                "Las versiones históricas son inmutables: crea otra revisión."
            )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("No se pueden eliminar versiones históricas.")

    def __str__(self):
        return f"Período {self.period_id} - revisión {self.revision}"
