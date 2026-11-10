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
    profile_photo = models.ImageField(
        upload_to="profile_photos/",
        blank=True,
        null=True,
        verbose_name="Foto de perfil",
    )

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

    authorized_delegations = models.ManyToManyField(
        "organization.Delegation",
        blank=True,
        related_name="authorized_user_profiles",
        verbose_name="Delegaciones autorizadas",
    )


class PasswordRecoveryCode(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="password_recovery_codes",
    )
    code_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("user", "expires_at")),
        ]