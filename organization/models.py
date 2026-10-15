from django.db import models
from django.core.exceptions import ValidationError

from core.models import BaseModel


class Delegation(BaseModel):
    delegation_id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=150)
    status = models.CharField(max_length=50)
    scope = models.CharField(max_length=150)

    class Meta:
        verbose_name = "Delegation"
        verbose_name_plural = "Delegations"

    def __str__(self):
        return self.name


class PositionFunction(BaseModel):
    position_id = models.BigAutoField(primary_key=True)
    position_name = models.CharField(max_length=150)
    measurable_items = models.TextField()
    services = models.TextField()
    weightings = models.TextField()
    validity_start = models.DateField()
    validity_end = models.DateField()

    group = models.ForeignKey(
    "auth.Group",
    on_delete=models.PROTECT,
    null=True,
    blank=True,
    related_name="positions",
    verbose_name="Grupo de permisos",
)

    class Meta:
        verbose_name = "Position and Role"
        verbose_name_plural = "Positions and Roles"

    def clean(self):
        if self.validity_start > self.validity_end:
            raise ValidationError(
                "Start date cannot be later than end date."
            )

    def __str__(self):
        return self.position_name


class Employee(BaseModel):
    employee_id = models.BigAutoField(primary_key=True)

    delegation = models.ForeignKey(
        Delegation,
        on_delete=models.PROTECT,
        related_name="employees",
    )

    position = models.ForeignKey(
        PositionFunction,
        on_delete=models.PROTECT,
        related_name="employees",
    )

    name = models.CharField(max_length=150)
    roles = models.TextField()
    status = models.CharField(max_length=50)

    class Meta:
        verbose_name = "Employee"
        verbose_name_plural = "Employees"

    def __str__(self):
        return self.name

    