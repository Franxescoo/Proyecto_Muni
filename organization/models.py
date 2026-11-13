from django.db import models
from django.core.exceptions import ValidationError

from core.models import BaseModel


class Delegation(BaseModel):
    delegation_id = models.BigAutoField(primary_key=True)
    created_by = models.ForeignKey(
        "auth.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_delegations",
    )
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
        null=True,
        blank=True,
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

    # Campo heredado: se conserva para no perder datos históricos.
    # Las nuevas asignaciones se administran mediante role_groups.
    group = models.ForeignKey(
        "auth.Group",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="positions",
        verbose_name="Grupo de permisos",
    )
    role_groups = models.ManyToManyField(
        "auth.Group",
        blank=True,
        related_name="role_positions",
        verbose_name="Roles del cargo",
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
    rut = models.CharField(
        max_length=12,
        unique=True,
        null=True,
        blank=True,
        verbose_name="RUT",
    )
    address = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Dirección",
    )
    roles = models.TextField(max_length=1000)
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



class EmployeeHistory(models.Model):
    """Auditoría individual y de solo lectura de empleado + cuenta vinculada."""
    employee = models.ForeignKey(
        Employee, on_delete=models.PROTECT, related_name="history_events"
    )
    actor = models.ForeignKey(
        "auth.User", null=True, on_delete=models.SET_NULL,
        related_name="organization_employee_changes",
    )
    event = models.CharField(max_length=70)
    previous_value = models.JSONField(default=dict, blank=True)
    new_value = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "Historial individual del empleado"
        verbose_name_plural = "Historial individual de empleados"

    @property
    def is_performed_action(self):
        return self.event.startswith("Acción: ")

    @property
    def target_description(self):
        return (self.new_value or self.previous_value or {}).get("__target", "")

    @property
    def action_changes(self):
        old = self.previous_value or {}
        new = self.new_value or {}
        keys = sorted((old.keys() | new.keys()) - {"__target"})
        return [{"label": key, "before": old.get(key) or "—", "after": new.get(key) or "—"}
                for key in keys if old.get(key) != new.get(key)]

    @property
    def changes(self):
        labels = {
            "name": "Nombre", "rut": "RUT", "address": "Dirección",
            "delegation": "Delegación", "position": "Cargo",
            "roles": "Funciones", "status": "Estado",
            "photo": "Fotografía", "archived": "Archivado", "username": "Usuario",
            "email": "Correo", "account_active": "Cuenta activa",
            "authorized_delegations": "Delegaciones autorizadas",
            "assigned_groups": "Roles heredados",
        }
        previous, current = self.previous_value or {}, self.new_value or {}
        return [
            {"label": labels.get(key, key), "before": previous.get(key, "—") or "—",
             "after": current.get(key, "—") or "—"}
            for key in labels
            if previous.get(key) != current.get(key)
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("No es posible modificar un evento de historial.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("No es posible eliminar un evento de historial.")
