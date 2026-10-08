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

    employee = models.OneToOneField(
    "organization.Employee",
    on_delete=models.PROTECT,
    null=True,
    blank=True,
    related_name="user_profile",
    verbose_name="Funcionario",
)

    def __str__(self):
        return self.user.username

    delegation = models.ForeignKey(
       "organization.Delegation",
       on_delete=models.PROTECT,
       null=True, blank=True,
       related_name="user_profiles",
   )