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
        return self.activity.status if self.activity_id and self.activity else self.status

    @property
    def is_completed(self):
        return self.effective_status.lower() in {
            "completed", "completado", "realizado", "validated", "validado",
        }

    @property
    def is_overdue(self):
        return not self.is_completed and self.commitment_date < timezone.localdate()


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