from django.db import models

# Create your models here.
from core.models import BaseModel
from django.db import models


class Organization(BaseModel):
    name = models.CharField(max_length=150)
    tax_id = models.CharField(max_length=20, unique=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

class Department(BaseModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="departments",
    )
    name = models.CharField(max_length=100)