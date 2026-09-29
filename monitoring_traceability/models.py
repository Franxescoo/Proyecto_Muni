from django.db import models

from django.core.exceptions import ValidationError

from core.models import BaseModel


class Activity(BaseModel):
	activity_id = models.BigAutoField(primary_key=True)
	name = models.CharField(max_length=150, verbose_name="Name")

	class Meta:
		verbose_name = "Activity reference"
		verbose_name_plural = "Activity references"

	def __str__(self):
		return self.name


class Evidence(BaseModel):
	evidence_id = models.BigAutoField(primary_key=True)
	name = models.CharField(max_length=150, verbose_name="Name")

	class Meta:
		verbose_name = "Evidence reference"
		verbose_name_plural = "Evidence references"

	def __str__(self):
		return self.name


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
		max_digits=12, decimal_places=2, verbose_name="Expected value"
	)
	actual_progress = models.DecimalField(
		max_digits=12, decimal_places=2, verbose_name="Actual progress"
	)
	green_progress = models.DecimalField(
		max_digits=12, decimal_places=2, verbose_name="Green progress"
	)
	difference = models.DecimalField(
		max_digits=12, decimal_places=2, verbose_name="Difference"
	)
	compliance = models.DecimalField(
		max_digits=7, decimal_places=2, verbose_name="Compliance"
	)
	weighting = models.DecimalField(
		max_digits=7, decimal_places=2, verbose_name="Weighting"
	)
	adjustment = models.DecimalField(
		max_digits=7, decimal_places=2, default=0, verbose_name="Adjustment"
	)
	traffic_light = models.CharField(max_length=30, verbose_name="Traffic light")
	calculation_date = models.DateField(verbose_name="Calculation date")

	class Meta:
		verbose_name = "Indicator"
		verbose_name_plural = "Indicators"
		ordering = ("-calculation_date", "indicator_id")

	def clean(self):
		super().clean()
		if self.employee_id and self.goal_id:
			if self.goal.employee_id != self.employee_id:
				raise ValidationError({
					"employee": "The employee must be assigned to the selected goal."
				})
		if self.compliance is not None and self.compliance < 0:
			raise ValidationError({"compliance": "Compliance cannot be negative."})
		if self.weighting is not None and not 0 <= self.weighting <= 100:
			raise ValidationError({"weighting": "Weighting must be between 0 and 100."})

	def __str__(self):
		return f"Indicator {self.indicator_id} - {self.goal.item}"


class Commitment(BaseModel):
	commitment_id = models.BigAutoField(primary_key=True)
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
		Activity,
		on_delete=models.PROTECT,
		related_name="commitments",
		null=True,
		blank=True,
		verbose_name="Activity reference",
	)
	evidence = models.ForeignKey(
		Evidence,
		on_delete=models.PROTECT,
		related_name="commitments",
		null=True,
		blank=True,
		verbose_name="Evidence reference",
	)
	requester = models.CharField(max_length=150, verbose_name="Requester")
	territory = models.CharField(max_length=150, verbose_name="Territory")
	commitment_date = models.DateField(verbose_name="Commitment date")
	support = models.TextField(blank=True, verbose_name="Support")
	status = models.CharField(max_length=50, default="Pending", verbose_name="Status")
	observation = models.TextField(blank=True, verbose_name="Observation")

	class Meta:
		verbose_name = "Commitment"
		verbose_name_plural = "Commitments"
		ordering = ("-commitment_date", "commitment_id")

	def clean(self):
		super().clean()
		if self.responsible_id and self.delegation_id:
			if self.responsible.delegation_id != self.delegation_id:
				raise ValidationError({
					"responsible": "The employee must belong to the selected delegation."
				})

	def __str__(self):
		return f"Commitment {self.commitment_id} - {self.territory}"


class Audit(BaseModel):
	audit_id = models.BigAutoField(primary_key=True)
	user = models.ForeignKey(
		"organization.Employee",
		on_delete=models.PROTECT,
		related_name="audit_events",
		verbose_name="Employee",
	)
	event = models.CharField(max_length=100, verbose_name="Event")
	event_date = models.DateTimeField(auto_now_add=True, verbose_name="Event date")
	entity = models.CharField(max_length=100, verbose_name="Entity")
	object_identifier = models.CharField(max_length=100, verbose_name="Object identifier")
	previous_value = models.JSONField(null=True, blank=True, verbose_name="Previous value")
	new_value = models.JSONField(null=True, blank=True, verbose_name="New value")

	class Meta:
		verbose_name = "Audit event"
		verbose_name_plural = "Audit events"
		ordering = ("-event_date", "-audit_id")

	def __str__(self):
		return f"{self.event} - {self.entity} {self.object_identifier}"

# Create your models here.
