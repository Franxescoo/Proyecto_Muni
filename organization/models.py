from django.db import models
from core.models import BaseModel


class Delegacion(BaseModel):
    id_delegacion = models.BigAutoField(primary_key=True)
    nombre = models.CharField(max_length=150)
    estado = models.CharField(max_length=50)
    ambito = models.CharField(max_length=150)

    class Meta:
        verbose_name = "Delegación"
        verbose_name_plural = "Delegaciones"

    def __str__(self):
        return self.nombre


class CargoFuncion(BaseModel):
    id_cargo = models.BigAutoField(primary_key=True)
    nombre_cargo = models.CharField(max_length=150)
    items_medibles = models.TextField()
    servicios = models.TextField()
    ponderaciones = models.TextField()
    vigencia_inicio = models.DateField()
    vigencia_fin = models.DateField()

    class Meta:
        verbose_name = "Cargo y Función"
        verbose_name_plural = "Cargos y Funciones"

    def __str__(self):
        return self.nombre_cargo


class Funcionario(BaseModel):
    id_funcionario = models.BigAutoField(primary_key=True)

    delegacion = models.ForeignKey(
        Delegacion,
        on_delete=models.PROTECT,
        related_name="funcionarios",
    )

    cargo = models.ForeignKey(
        CargoFuncion,
        on_delete=models.PROTECT,
        related_name="funcionarios",
    )

    nombre = models.CharField(max_length=150)
    roles = models.TextField()
    estado = models.CharField(max_length=50)

    class Meta:
        verbose_name = "Funcionario"
        verbose_name_plural = "Funcionarios"

    def __str__(self):
        return self.nombre