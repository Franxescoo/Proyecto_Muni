from django.core.exceptions import ValidationError
from django.db import models

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

    def clean(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError(
                "La fecha de inicio no puede ser posterior a la fecha de término."
            )

    def __str__(self):
        return f"Period {self.start_date} to {self.end_date}"


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
    item = models.CharField(max_length=150, verbose_name="Item")
    objective_value = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="Objective value"
    )
    unit = models.CharField(max_length=50, verbose_name="Unit")
    weight = models.DecimalField(
        max_digits=5, decimal_places=2, verbose_name="Weight"
    )

    class Meta:
        verbose_name = "Goal"
        verbose_name_plural = "Goals"

    def clean(self):
        # El cargo de la meta debe ser el cargo actual del funcionario.
        if (
            self.employee_id
            and self.position_id
            and self.employee.position_id != self.position_id
        ):
            raise ValidationError(
                "El cargo asignado a la meta no coincide con el cargo actual del funcionario."
            )

    def __str__(self):
        return f"Goal: {self.item} - {self.employee}"