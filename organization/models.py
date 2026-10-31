from django.db import models
from django.core.exceptions import ValidationError

from core.models import BaseModel


class Delegation(BaseModel):
    delegation_id = models.BigAutoField(primary_key=True)
    code = models.CharField(max_length=30, unique=True, null=True, blank=True)
    name = models.CharField(max_length=150)
    address = models.CharField(max_length=200, blank=True)
    commune = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=50)
    scope = models.CharField(max_length=150)
    responsible = models.ForeignKey(
        "organization.Employee", null=True, blank=True,
        on_delete=models.PROTECT, related_name="responsible_for_delegations",
        verbose_name="Responsable de delegación",
    )

    class Meta:
        verbose_name = "Delegation"
        verbose_name_plural = "Delegations"

    def __str__(self):
        return self.name


class DelegationResponsibilityLog(models.Model):
    delegation = models.ForeignKey("organization.Delegation", on_delete=models.PROTECT,
                                   related_name="responsibility_history")
    previous_responsible = models.ForeignKey("organization.Employee", null=True, blank=True,
        on_delete=models.PROTECT, related_name="previous_responsibility_changes")
    new_responsible = models.ForeignKey("organization.Employee", null=True, blank=True,
        on_delete=models.PROTECT, related_name="new_responsibility_changes")
    changed_by = models.ForeignKey("auth.User", on_delete=models.PROTECT)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Cambio de responsable de delegación"
        verbose_name_plural = "Cambios de responsable de delegación"


class OrganizationRole(models.Model):
    description = models.TextField(blank=True, verbose_name="Descripción")
    group = models.OneToOneField(
        "auth.Group",
        on_delete=models.CASCADE,
        related_name="organization_role",
    )
    delegation = models.ForeignKey(
        Delegation,
        on_delete=models.PROTECT,
        related_name="organization_roles",
    )
    application_delegations = models.ManyToManyField(
        Delegation,
        blank=True,
        related_name="application_roles",
        verbose_name="Delegaciones de aplicación",
    )

    class Meta:
        verbose_name = "Organization role"
        verbose_name_plural = "Organization roles"

    def __str__(self):
        return f"{self.group.name} - {self.delegation.name}"


class PositionFunction(BaseModel):
    position_id = models.BigAutoField(primary_key=True)
    position_name = models.CharField(max_length=150)
    measurable_items = models.TextField()
    catalog_items = models.ManyToManyField(
        "planning_measurements.MeasurementItem",
        blank=True,
        related_name="associated_positions",
        verbose_name="Ítems de medición del catálogo",
    )
    services = models.TextField()
    catalog_services = models.ManyToManyField(
        "registration_validation.Service",
        blank=True,
        related_name="positions",
        verbose_name="Servicios del catálogo",
    )
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

    assigned_groups = models.ManyToManyField(
        "auth.Group",
        blank=True,
        related_name="assigned_employees",
        verbose_name="Roles asignados",
    )

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
    profile_photo = models.ImageField(
        upload_to="profile_photos/",
        blank=True,
        null=True,
        verbose_name="Foto de perfil",
    )

    class Meta:
        verbose_name = "Employee"
        verbose_name_plural = "Employees"

    def __str__(self):
        return self.name

    