# accounts/models.py
from django.conf import settings
from django.contrib.auth.models import Group
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


class RoleScope(BaseModel):
    """Define el alcance territorial de un rol basado en ``auth.Group``."""

    group = models.OneToOneField(
        Group,
        on_delete=models.CASCADE,
        related_name="role_scope",
        verbose_name="Rol",
    )
    all_delegations = models.BooleanField(
        default=False,
        verbose_name="Acceso a todas las delegaciones",
    )
    delegations = models.ManyToManyField(
        "organization.Delegation",
        blank=True,
        related_name="role_scopes",
        verbose_name="Delegaciones autorizadas",
    )

    class Meta:
        verbose_name = "Alcance de rol"
        verbose_name_plural = "Alcances de roles"

    def __str__(self):
        return f"Alcance de {self.group.name}"
