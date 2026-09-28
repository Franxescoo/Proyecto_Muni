from django.contrib import admin
from .models import Delegacion, CargoFuncion, Funcionario


class FuncionarioInline(admin.TabularInline):
    model = Funcionario
    extra = 0


@admin.register(Delegacion)
class DelegacionAdmin(admin.ModelAdmin):
    list_display = (
        "id_delegacion",
        "nombre",
        "estado",
        "ambito",
    )

    inlines = [FuncionarioInline]


@admin.register(CargoFuncion)
class CargoFuncionAdmin(admin.ModelAdmin):
    list_display = (
        "id_cargo",
        "nombre_cargo",
        "vigencia_inicio",
        "vigencia_fin",
    )


@admin.action(description="Marcar funcionarios como inactivos")
def marcar_inactivos(modeladmin, request, queryset):
    queryset.update(estado="Inactivo")


@admin.register(Funcionario)
class FuncionarioAdmin(admin.ModelAdmin):
    list_display = (
        "id_funcionario",
        "nombre",
        "delegacion",
        "cargo",
        "estado",
    )

    search_fields = (
        "nombre",
    )

    list_filter = (
        "estado",
        "delegacion",
        "cargo",
    )

    actions = [marcar_inactivos]

    def get_actions(self, request):
        actions = super().get_actions(request)

        if not request.user.has_perm("organization.change_funcionario"):
            actions.pop("marcar_inactivos", None)

        return actions