# accounts/models.py
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from core.models import BaseModel


class UserProfile(BaseModel):
    """
    Perfil de usuario que conecta la cuenta de autenticación de Django 
    con la estructura organizacional (Organización y Departamento).
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        related_name="user_profiles",
    )
    department = models.ForeignKey(
        "organizations.Department",
        on_delete=models.PROTECT,
        related_name="user_profiles",
        null=True,
        blank=True,
    )
    employee_code = models.CharField(max_length=30, unique=True)
    phone = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return f"{self.user.username} · {self.organization}"

    def clean(self):
        super().clean()
        # Regla de negocio: Validar que el departamento pertenezca a la organización seleccionada
        if (
            self.department_id
            and self.department.organization_id
            != self.organization_id
        ):
            raise ValidationError({
                "department": (
                    "El departamento debe pertenecer "
                    "a la organización seleccionada."
                )
            })

    def save(self, *args, **kwargs):
        # Asegura que las validaciones de clean() se ejecuten también al guardar por código
        self.full_clean()
        super().save(*args, **kwargs)