from django.contrib import admin
from .models import Delegacion, CargoFuncion, Funcionario


@admin.register(Delegacion)
class DelegacionAdmin(admin.ModelAdmin):
    list_display = (
        "id_delegacion",
        "nombre",
        "estado",
        "ambito",
    )


@admin.register(CargoFuncion)
class CargoFuncionAdmin(admin.ModelAdmin):
    list_display = (
        "id_cargo",
        "nombre_cargo",
        "vigencia_inicio",
        "vigencia_fin",
    )


@admin.register(Funcionario)
class FuncionarioAdmin(admin.ModelAdmin):
    list_display = (
        "id_funcionario",
        "nombre",
        "delegacion",
        "cargo",
        "estado",
    )