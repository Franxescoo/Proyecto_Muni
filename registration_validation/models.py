from django.core.exceptions import ValidationError
from django.db import models

from core.models import BaseModel


class Activity(BaseModel):
    activity_id = models.BigAutoField(
        primary_key=True,
        verbose_name="Activity ID",
    )

    goal = models.ForeignKey(
        "planning_measurements.Goal",
        on_delete=models.PROTECT,
        related_name="activities",
        verbose_name="Goal",
    )

    author = models.ForeignKey(
        "organization.Employee",
        on_delete=models.PROTECT,
        related_name="activities_created",
        verbose_name="Author",
    )

    date = models.DateField(
        verbose_name="Date",
    )

    request_problem = models.TextField(
        verbose_name="Request or problem",
    )

    action = models.TextField(
        verbose_name="Action",
    )

    contact = models.CharField(
        max_length=150,
        verbose_name="Contact",
    )

    phone = models.CharField(
        max_length=20,
        verbose_name="Phone",
    )

    status = models.CharField(
        max_length=50,
        default="Pending",
        verbose_name="Status",
    )

    class Meta:
        verbose_name = "Activity"
        verbose_name_plural = "Activities"
        ordering = ("-date", "activity_id")

    def clean(self):
        super().clean()

        if self.goal_id and self.author_id:
            if self.goal.employee_id != self.author_id:
                raise ValidationError(
                    {
                        "author": (
                            "The activity author must match the "
                            "employee assigned to the selected goal."
                        )
                    }
                )

    def __str__(self):
        return (
            f"Activity {self.activity_id} - "
            f"{self.goal.item}"
        )


class Evidence(BaseModel):
    evidence_id = models.BigAutoField(
        primary_key=True,
        verbose_name="Evidence ID",
    )

    code = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="Code",
    )

    activity = models.ForeignKey(
        Activity,
        on_delete=models.PROTECT,
        related_name="evidences",
        verbose_name="Activity",
    )

    author = models.ForeignKey(
        "organization.Employee",
        on_delete=models.PROTECT,
        related_name="evidences_created",
        verbose_name="Author",
    )

    file_link = models.CharField(
        max_length=500,
        verbose_name="File or link",
    )

    date = models.DateTimeField(
        verbose_name="Date",
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Metadata",
    )

    review_status = models.CharField(
        max_length=50,
        default="Pending",
        verbose_name="Review status",
    )

    class Meta:
        verbose_name = "Evidence"
        verbose_name_plural = "Evidences"
        ordering = ("-date", "evidence_id")

    def __str__(self):
        return self.code


class Validation(BaseModel):
    validation_id = models.BigAutoField(
        primary_key=True,
        verbose_name="Validation ID",
    )

    evidence = models.ForeignKey(
        Evidence,
        on_delete=models.PROTECT,
        related_name="validations",
        verbose_name="Evidence",
    )

    verifier = models.ForeignKey(
        "organization.Employee",
        on_delete=models.PROTECT,
        related_name="validations_performed",
        verbose_name="Verifier",
    )

    decision = models.CharField(
        max_length=50,
        verbose_name="Decision",
    )

    date = models.DateTimeField(
        verbose_name="Date",
    )

    observation = models.TextField(
        blank=True,
        verbose_name="Observation",
    )

    result = models.CharField(
        max_length=100,
        verbose_name="Result",
    )

    version = models.PositiveIntegerField(
        default=1,
        verbose_name="Version",
    )

    class Meta:
        verbose_name = "Validation"
        verbose_name_plural = "Validations"
        ordering = ("-date", "-version")

    def __str__(self):
        return (
            f"Validation {self.validation_id} - "
            f"{self.decision}"
        )