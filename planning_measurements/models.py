from django.core.exceptions import ValidationError
from django.db import models

from core.models import BaseModel


class Periodo(BaseModel):
    id_periodo = models.BigAutoField(primary_key=True)
    fecha_inicio = models.DateField(verbose_name="Inicio")
    fecha_termino = models.DateField(verbose_name="Término")
    dias_computables = models.IntegerField(verbose_name="Días computables")
    estado = models.CharField(
        max_length=50, default="Activo", verbose_name="Estado"
    )
    umbrales = models.CharField(max_length=255, verbose_name="Umbrales")
    version_parametros = models.CharField(
        max_length=50, verbose_name="Versión de parámetros"
    )

    class Meta:
        verbose_name = "Período"
        verbose_name_plural = "Períodos"

    def clean(self):
        if (
            self.fecha_inicio
            and self.fecha_termino
            and self.fecha_inicio > self.fecha_termino
        ):
            raise ValidationError(
                "La fecha de inicio no puede ser posterior a la fecha de término."
            )

    def __str__(self):
        return f"Período {self.fecha_inicio} al {self.fecha_termino}"


class MetaDesempeno(BaseModel):
    """Meta del diagrama MER (se llama MetaDesempeno para no chocar con
    la clase interna `Meta` de Django)."""

    id_meta = models.BigAutoField(primary_key=True)

    periodo = models.ForeignKey(
        Periodo,
        on_delete=models.PROTECT,
        related_name="metas",
    )
    funcionario = models.ForeignKey(
        "organization.Funcionario",
        on_delete=models.PROTECT,
        related_name="metas",
    )
    cargo = models.ForeignKey(
        "organization.CargoFuncion",
        on_delete=models.PROTECT,
        related_name="metas",
        verbose_name="Cargo",
    )

    item = models.CharField(max_length=150, verbose_name="Ítem")
    valor_objetivo = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="Valor objetivo"
    )
    unidad = models.CharField(max_length=50, verbose_name="Unidad")
    ponderador = models.DecimalField(
        max_digits=5, decimal_places=2, verbose_name="Ponderador"
    )

    class Meta:
        verbose_name = "Meta"
        verbose_name_plural = "Metas"

    def clean(self):
        # El cargo de la meta debe ser el cargo actual del funcionario.
        if (
            self.funcionario_id
            and self.cargo_id
            and self.funcionario.cargo_id != self.cargo_id
        ):
            raise ValidationError(
                "El cargo asignado a la meta no coincide con el cargo actual del funcionario."
            )

    def __str__(self):
        return f"Meta: {self.item} - {self.funcionario}"