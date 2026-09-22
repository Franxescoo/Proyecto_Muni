from django.db import models

# Create your models here.
# planning_measurements/models.py
from django.db import models
from core.models import BaseModel

class Period(BaseModel):
    start_date = models.DateField()
    end_date = models.DateField()
    computable_days = models.IntegerField()
    status = models.CharField(max_length=50)
    thresholds = models.JSONField(default=dict)
    parameter_version = models.CharField(max_length=50)

    def __str__(self):
        return f"{self.start_date} - {self.end_date}"

class Goal(BaseModel):
    period = models.ForeignKey(
        Period,
        on_delete=models.PROTECT,
        related_name="goals",
    )
    employee = models.ForeignKey(
        "organization.Employee",
        on_delete=models.PROTECT,
        related_name="goals",
    )
    position = models.ForeignKey(
        "organization.PositionFunction",
        on_delete=models.PROTECT,
        related_name="goals",
    )
    item = models.CharField(max_length=150)
    objective_value = models.DecimalField(max_digits=10, decimal_places=2)
    unit = models.CharField(max_length=50)
    weighting = models.DecimalField(max_digits=5, decimal_places=2)

    def __str__(self):
        return self.item