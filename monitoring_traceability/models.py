from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone

from core.models import BaseModel


class Indicator(BaseModel):
    indicator_id = models.BigAutoField(primary_key=True)

    goal = models.ForeignKey(
        "planning_measurements.Goal",
        on_delete=models.PROTECT,
        related_name="indicators",
        verbose_name="Goal",
    )

    employee = models.ForeignKey(
        "organization.Employee",
        on_delete=models.PROTECT,
        related_name="indicators",
        verbose_name="Employee",
    )

    expected_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Expected value",
    )

    actual_progress = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Actual progress",
    )

    green_progress = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Green progress",
    )

    expected_progress = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        default=0,
        verbose_name="Expected progress",
    )

    difference = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Difference",
    )

    compliance = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        verbose_name="Compliance",
    )

    weighting = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        verbose_name="Weighting",
    )

    weighted_result = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        default=0,
        verbose_name="Weighted result",
    )

    approved_activities = models.PositiveIntegerField(
        default=0,
        verbose_name="Approved activities",
    )

    approved_evidences = models.PositiveIntegerField(
        default=0,
        verbose_name="Approved evidences",
    )

    adjustment = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        default=0,
        verbose_name="Adjustment",
    )

    traffic_light = models.CharField(
        max_length=30,
        verbose_name="Traffic light",
    )

    calculation_date = models.DateField(
        verbose_name="Calculation date",
    )

    class Meta:
        verbose_name = "Indicator"
        verbose_name_plural = "Indicators"
        ordering = ("-calculation_date", "indicator_id")

    @property
    def effective_evidence_requirement(self):
        """Exigencia de evidencias ajustada por ausencias justificadas."""
        from .absence_rules import effective_goal_values
        _target, required, _expected, _lost = effective_goal_values(self.goal)
        return required

    @property
    def absent_computable_days(self):
        from .absence_rules import effective_goal_values
        _target, _required, _expected, lost = effective_goal_values(self.goal)
        return lost

    @property
    def evidence_remaining(self):
        """Evidencias independientes pendientes (no archivos adjuntos)."""
        required = self.effective_evidence_requirement
        return max(0, required - (self.approved_evidences or 0))

    @property
    def evidence_accreditation_met(self):
        """Acreditación documental independiente del avance calculado."""
        return self.evidence_remaining == 0

    @property
    def accreditation_label(self):
        return (
            "Acreditada" if self.evidence_accreditation_met
            else "Pendiente de evidencias"
        )

    @property
    def effective_traffic_light(self):
        """Evita declarar verde una meta sin evidencias suficientes."""
        return self.traffic_light if self.evidence_accreditation_met else "Pending"

    def clean(self):
        super().clean()

        if self.employee_id and self.goal_id:
            if self.goal.employee_id != self.employee_id:
                raise ValidationError(
                    {
                        "employee": (
                            "The employee must be assigned "
                            "to the selected goal."
                        )
                    }
                )

        if self.compliance is not None and self.compliance < 0:
            raise ValidationError(
                {
                    "compliance": (
                        "Compliance cannot be negative."
                    )
                }
            )

        if self.expected_progress is not None and self.expected_progress < 0:
            raise ValidationError(
                {"expected_progress": "Expected progress cannot be negative."}
            )

        if (
            self.weighting is not None
            and not 0 <= self.weighting <= 100
        ):
            raise ValidationError(
                {
                    "weighting": (
                        "Weighting must be between 0 and 100."
                    )
                }
            )

    def __str__(self):
        return (
            f"Indicator {self.indicator_id} - "
            f"{self.goal.item}"
        )


class Commitment(BaseModel):
    commitment_id = models.BigAutoField(
        primary_key=True,
    )

    delegation = models.ForeignKey(
        "organization.Delegation",
        on_delete=models.PROTECT,
        related_name="commitments",
        verbose_name="Delegation",
    )

    responsible = models.ForeignKey(
        "organization.Employee",
        on_delete=models.PROTECT,
        related_name="commitments",
        verbose_name="Responsible employee",
    )

    activity = models.ForeignKey(
        "registration_validation.Activity",
        on_delete=models.PROTECT,
        related_name="commitments",
        null=True,
        blank=True,
        verbose_name="Activity reference",
    )

    origin = models.CharField(
        max_length=150,
        verbose_name="Origin",
    )

    requester = models.CharField(
        max_length=150,
        verbose_name="Requester",
    )

    territory = models.CharField(
        max_length=150,
        verbose_name="Territory",
    )

    commitment_date = models.DateField(
        verbose_name="Commitment date",
    )

    support = models.TextField(
        blank=True,
        verbose_name="Support",
    )

    status = models.CharField(
        max_length=50,
        default="Pending",
        verbose_name="Status",
    )

    observation = models.TextField(
        blank=True,
        verbose_name="Observation",
    )

    class Meta:
        verbose_name = "Commitment"
        verbose_name_plural = "Commitments"
        ordering = (
            "-commitment_date",
            "commitment_id",
        )

    class Status(models.TextChoices):
        PENDING = "Pending", "No iniciado"
        IN_PROGRESS = "In progress", "En progreso"
        COMPLETED = "Completed", "Completado"
        VALIDATED = "Validated", "Validado"
        CANCELLED = "Cancelled", "Cancelado"

    # Estados heredados conservados por compatibilidad con la base y la UI.
    # Los cambios se realizan con observación, no mediante edición normal.
    ALLOWED_TRANSITIONS = {
        "Pending": {"In progress", "Completed", "Cancelled"},
        "In progress": {"Pending", "Completed", "Cancelled"},
        "Completed": {"In progress", "Validated"},
        "Validated": set(),
        "Cancelled": {"Pending"},
    }

    LEGACY_STATUS_MAP = {
        "Pendiente": "Pending", "No iniciado": "Pending",
        "En progreso": "In progress", "En proceso": "In progress",
        "Realizado": "Completed", "Completado": "Completed",
        "Validado": "Validated", "Cancelado": "Cancelled",
    }

    def can_transition_to(self, new_status):
        current = self.LEGACY_STATUS_MAP.get(self.status, self.status)
        return new_status in self.ALLOWED_TRANSITIONS.get(current, set())

    def available_transitions(self):
        labels = dict(self.Status.choices)
        current = self.LEGACY_STATUS_MAP.get(self.status, self.status)
        return [(value, labels[value]) for value in sorted(self.ALLOWED_TRANSITIONS.get(current, ()))]

    def clean(self):
        super().clean()

        if self.activity_id:
            duplicate = Commitment.objects.filter(
                activity_id=self.activity_id,
                deleted_at__isnull=True,
            ).exclude(pk=self.pk)
            if duplicate.exists():
                raise ValidationError(
                    {"activity": "Ya existe un compromiso asociado a esta actividad."}
                )

        if self.responsible_id and self.delegation_id:
            if (
                self.responsible.delegation_id
                != self.delegation_id
            ):
                raise ValidationError(
                    {
                        "responsible": (
                            "The employee must belong to "
                            "the selected delegation."
                        )
                    }
                )

    def __str__(self):
        return (
            f"Commitment {self.commitment_id} - "
            f"{self.territory}"
        )

    @property
    def effective_status(self):
        return self.status

    @property
    def is_completed(self):
        return self.effective_status.lower() in {
            "completed", "completado", "realizado", "validated", "validado",
        }

    @property
    def is_completed_late(self):
        """RF-019: identifica compromisos realizados después de su plazo."""
        if not self.is_completed:
            return False
        completion = self.status_history.filter(
            new_status__in=["Completed", "Validated", "Completado", "Realizado", "Validado"],
        ).order_by("created_at", "pk").first()
        if completion is None:
            return False  # No inferir una fecha histórica inexistente.
        return timezone.localtime(completion.created_at).date() > self.commitment_date

    @property
    def is_overdue(self):
        return (
            not self.is_completed
            and self.status.casefold() not in {"cancelled", "cancelado"}
            and self.commitment_date < timezone.localdate()
        )


class CommitmentComment(BaseModel):
    comment_id = models.BigAutoField(primary_key=True)

    commitment = models.ForeignKey(
        Commitment,
        on_delete=models.PROTECT,
        related_name="comments",
        verbose_name="Commitment",
    )

    author = models.ForeignKey(
        "organization.Employee",
        on_delete=models.PROTECT,
        related_name="commitment_comments",
        null=True,
        blank=True,
        verbose_name="Author",
    )

    created_by = models.ForeignKey(
        "auth.User",
        on_delete=models.PROTECT,
        related_name="commitment_comments",
        null=True,
        blank=True,
        verbose_name="User",
    )

    text = models.TextField(verbose_name="Comment")

    class Meta:
        verbose_name = "Commitment comment"
        verbose_name_plural = "Commitment comments"
        ordering = ("-created_at", "comment_id")

    def clean(self):
        super().clean()
        if (
            self.author_id
            and self.commitment_id
            and self.author.delegation_id != self.commitment.delegation_id
        ):
            raise ValidationError(
                {"author": "The author must belong to the commitment delegation."}
            )

    def __str__(self):
        return f"Comment {self.comment_id} - {self.commitment}"


class CommitmentStatusHistory(BaseModel):
    history_id = models.BigAutoField(primary_key=True)
    commitment = models.ForeignKey(
        Commitment,
        on_delete=models.PROTECT,
        related_name="status_history",
    )
    previous_status = models.CharField(max_length=50, blank=True)
    new_status = models.CharField(max_length=50)
    changed_by = models.ForeignKey(
        "auth.User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="commitment_status_changes",
    )
    observation = models.TextField(blank=True)

    class Meta:
        ordering = ("-created_at", "-history_id")


class CommitmentReassignment(BaseModel):
    reassignment_id = models.BigAutoField(primary_key=True)
    commitment = models.ForeignKey(
        Commitment,
        on_delete=models.PROTECT,
        related_name="reassignments",
    )
    previous_responsible = models.ForeignKey(
        "organization.Employee",
        on_delete=models.PROTECT,
        related_name="commitments_reassigned_from",
    )
    new_responsible = models.ForeignKey(
        "organization.Employee",
        on_delete=models.PROTECT,
        related_name="commitments_reassigned_to",
    )
    reason = models.TextField()
    changed_by = models.ForeignKey(
        "auth.User",
        on_delete=models.PROTECT,
        related_name="commitment_reassignments",
    )

    class Meta:
        ordering = ("-created_at", "-reassignment_id")


class CommitmentAlert(BaseModel):
    alert_id = models.BigAutoField(primary_key=True)
    commitment = models.ForeignKey(
        Commitment,
        on_delete=models.PROTECT,
        related_name="alerts",
    )
    alert_type = models.CharField(max_length=40)
    message = models.CharField(max_length=255)
    due_at = models.DateField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("resolved_at", "-due_at", "-created_at")
        constraints = [
            models.UniqueConstraint(
                fields=("commitment", "alert_type"),
                condition=models.Q(resolved_at=None),
                name="unique_active_commitment_alert",
            ),
        ]

    @property
    def is_open(self):
        return self.resolved_at is None


class Audit(BaseModel):
    audit_id = models.BigAutoField(
        primary_key=True,
    )

    user = models.ForeignKey(
        "organization.Employee",
        on_delete=models.PROTECT,
        related_name="audit_events",
        verbose_name="Employee",
    )

    event = models.CharField(
        max_length=100,
        verbose_name="Event",
    )

    event_date = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Event date",
    )

    entity = models.CharField(
        max_length=100,
        verbose_name="Entity",
    )

    object_identifier = models.CharField(
        max_length=100,
        verbose_name="Object identifier",
    )

    previous_value = models.JSONField(
        null=True,
        blank=True,
        verbose_name="Previous value",
    )

    new_value = models.JSONField(
        null=True,
        blank=True,
        verbose_name="New value",
    )

    class Meta:
        verbose_name = "Audit event"
        verbose_name_plural = "Audit events"
        ordering = (
            "-event_date",
            "-audit_id",
        )

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError(
                "Los eventos de auditoría son inmutables."
            )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(
            "Los eventos de auditoría no se pueden eliminar."
        )

    def __str__(self):
        return (
            f"{self.event} - "
            f"{self.entity} {self.object_identifier}"
        )

class MonitoringSettings(models.Model):
    """Configuración global versionada, editable solo con permiso explícito."""
    key = models.CharField(max_length=20, primary_key=True, default="global", editable=False)
    low_compliance_threshold = models.DecimalField(max_digits=6, decimal_places=2, default=80)
    inactivity_workdays = models.PositiveSmallIntegerField(default=5)
    due_soon_days = models.PositiveSmallIntegerField(default=7)
    positive_adjustment_max = models.DecimalField(max_digits=6, decimal_places=2, default=100)
    negative_adjustment_max = models.DecimalField(max_digits=6, decimal_places=2, default=100)
    recipient_users = models.ManyToManyField(
        "auth.User", blank=True, related_name="monitoring_alert_recipient_settings"
    )
    effective_from = models.DateTimeField(default=timezone.now)
    updated_by = models.ForeignKey(
        "auth.User", null=True, blank=True, on_delete=models.PROTECT,
        related_name="monitoring_settings_updated",
    )

    class Meta:
        verbose_name = "Reglas operativas de monitoreo"
        verbose_name_plural = "Reglas operativas de monitoreo"
        default_permissions = ("view", "change")

    def clean(self):
        super().clean()
        errors = {}
        if not (0 <= self.low_compliance_threshold <= 150):
            errors["low_compliance_threshold"] = "Debe estar entre 0 y 150."
        if not (1 <= self.inactivity_workdays <= 365):
            errors["inactivity_workdays"] = "Debe estar entre 1 y 365."
        if not (0 <= self.due_soon_days <= 365):
            errors["due_soon_days"] = "Debe estar entre 0 y 365."
        if not (0 <= self.positive_adjustment_max <= 100):
            errors["positive_adjustment_max"] = "Debe estar entre 0 y 100."
        if not (0 <= self.negative_adjustment_max <= 100):
            errors["negative_adjustment_max"] = "Debe estar entre 0 y 100."
        if errors:
            raise ValidationError(errors)


class MonitoringSettingsRevision(models.Model):
    """Historial inmutable de los parámetros y destinatarios anteriores/nuevos."""
    changed_at = models.DateTimeField(auto_now_add=True)
    changed_by = models.ForeignKey("auth.User", on_delete=models.PROTECT)
    previous_value = models.JSONField(default=dict)
    new_value = models.JSONField(default=dict)

    class Meta:
        ordering = ("-changed_at", "-pk")
        default_permissions = ("add", "view")


class MonitoringAlertReview(models.Model):
    """Constancia de revisión; no elimina ni resuelve el evento original."""
    alert_key = models.CharField(max_length=200, unique=True)
    reviewed_by = models.ForeignKey("auth.User", on_delete=models.PROTECT)
    reviewed_at = models.DateTimeField(auto_now_add=True)
    comment = models.CharField(max_length=250, blank=True)

    class Meta:
        ordering = ("-reviewed_at", "-pk")
        default_permissions = ("add", "view")


# SGR-AUSENCIAS-RESULTADOS-20261121: ausencia histórica informada por delegado.
class EmployeeAbsence(BaseModel):
    ABSENCE_TYPES = [
        ('LICENSE', 'Licencia'),
        ('VACATION', 'Vacaciones'),
        ('PERMISSION', 'Permiso'),
        ('OTHER', 'Otra ausencia justificada'),
    ]
    employee = models.ForeignKey(
        'organization.Employee', on_delete=models.PROTECT,
        related_name='reported_absences', verbose_name='Funcionario ausente',
    )
    delegation = models.ForeignKey(
        'organization.Delegation', on_delete=models.PROTECT,
        related_name='employee_absences', verbose_name='Delegación que informa',
    )
    reported_by = models.ForeignKey(
        'auth.User', on_delete=models.PROTECT,
        related_name='reported_absences', verbose_name='Usuario delegado informante',
    )
    start_date = models.DateField(verbose_name='Desde')
    end_date = models.DateField(verbose_name='Hasta')
    absence_type = models.CharField(max_length=12, choices=ABSENCE_TYPES)
    reason = models.TextField(verbose_name='Motivo del reporte')
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        'auth.User', on_delete=models.PROTECT, null=True, blank=True,
        related_name='cancelled_employee_absences',
    )
    cancel_reason = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Ausencia informada por delegado'
        verbose_name_plural = 'Ausencias informadas por delegado'
        ordering = ('-created_at', '-pk')
        indexes = [models.Index(fields=['employee', 'start_date', 'end_date'], name='sgr_abs_emp_dates_idx')]

    def clean(self):
        super().clean()
        errors = {}
        if self.start_date and self.end_date:
            if self.end_date < self.start_date:
                errors['end_date'] = 'La fecha final debe ser igual o posterior al inicio.'
            elif (self.end_date - self.start_date).days > 366:
                errors['end_date'] = 'El reporte no puede abarcar más de 367 días.'
            elif not self.cancelled_at and self.employee_id:
                active = type(self).objects.filter(
                    employee_id=self.employee_id, cancelled_at__isnull=True,
                    start_date__lte=self.end_date, end_date__gte=self.start_date,
                )
                if self.pk:
                    active = active.exclude(pk=self.pk)
                if active.exists():
                    errors['start_date'] = 'Ya existe una ausencia vigente en esas fechas.'
        if self.employee_id and self.delegation_id:
            from organization.models import Employee
            if not Employee.objects.filter(pk=self.employee_id, delegation_id=self.delegation_id).exists():
                errors['employee'] = 'El funcionario debe pertenecer a la delegación informante.'
        if not (self.reason or '').strip():
            errors['reason'] = 'Debes escribir el motivo de la ausencia.'
        elif len(self.reason) > 1000:
            errors['reason'] = 'El motivo no puede superar 1000 caracteres.'
        if self.cancelled_at and not (self.cancel_reason or '').strip():
            errors['cancel_reason'] = 'La anulación necesita un motivo.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.pk:
            historic = type(self).objects.filter(pk=self.pk).values(
                'employee_id', 'delegation_id', 'reported_by_id', 'start_date',
                'end_date', 'absence_type', 'reason', 'cancelled_at',
                'cancelled_by_id', 'cancel_reason', 'deleted_at',
            ).first()
            if historic:
                for key in ('employee_id', 'delegation_id', 'reported_by_id',
                            'start_date', 'end_date', 'absence_type', 'reason', 'deleted_at'):
                    if getattr(self, key) != historic[key]:
                        raise ValidationError('Los datos de una ausencia registrada son históricos e inmutables.')
                if historic['cancelled_at'] and any(
                    getattr(self, k) != historic[k]
                    for k in ('cancelled_at', 'cancelled_by_id', 'cancel_reason')
                ):
                    raise ValidationError('Una ausencia anulada no se puede modificar ni reactivar.')
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'Ausencia {self.employee_id} {self.start_date} a {self.end_date}'

