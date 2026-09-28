# accounts/models.py
from django.conf import settings
from django.db import models
from core.models import BaseModel


class UserProfile(BaseModel):

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )

    employee_code = models.CharField(max_length=30, unique=True)
    phone = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return self.user.username