from django.db import models
from django.core.exceptions import ValidationError

from core.models import BaseModel


class Delegacion(BaseModel):
    delegation_id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=150)
    status = models.CharField(max_length=50)
    scope = models.CharField(max_length=150)

    class Meta:
        verbose_name = "Delegation"
        verbose_name_plural = "Delegations"

    def __str__(self):
        return self.name


class CargoFuncion(BaseModel):
    position_id = models.BigAutoField(primary_key=True)
    position_name = models.CharField(max_length=150)
    measurable_items = models.TextField()
    services = models.TextField()
    weightings = models.TextField()
    validity_start = models.DateField()
    validity_end = models.DateField()

    class Meta:
        verbose_name = "Position and Role"
        verbose_name_plural = "Positions and Roles"

    def clean(self):
        if self.validity_start > self.validity_end:
            raise ValidationError(
                "La fecha de inicio no puede ser posterior a la fecha de fin."
            )

    def __str__(self):
        return self.position_name


class Funcionario(BaseModel):
    employee_id = models.BigAutoField(primary_key=True)

    delegation = models.ForeignKey(
        Delegacion,
        on_delete=models.PROTECT,
        related_name="employees",
    )

    position = models.ForeignKey(
        CargoFuncion,
        on_delete=models.PROTECT,
        related_name="employees",
    )

    name = models.CharField(max_length=150)
    roles = models.TextField()
    status = models.CharField(max_length=50)

    class Meta:
        verbose_name = "Functionary"
        verbose_name_plural = "Functionaries"

    def __str__(self):
        return self.name