from django.contrib import admin, messages
from django.utils import timezone

from .models import Periodo, MetaDesempeno


@admin.action(
    description="Archivar registros seleccionados", permissions=["change"]
)
def archivar_registros(modeladmin, request, queryset):
    actualizados = queryset.filter(deleted_at__isnull=True).update(
        deleted_at=timezone.now()
    )
    modeladmin.message_user(
        request,
        f"{actualizados} registro(s) archivado(s) exitosamente.",
        level=messages.SUCCESS,
    )


class MetaDesempenoInline(admin.TabularInline):
    model = MetaDesempeno
    extra = 0
    fields = (
        "funcionario",
        "cargo",
        "item",
        "valor_objetivo",
        "unidad",
        "ponderador",
    )
    show_change_link = True


@admin.register(Periodo)
class PeriodoAdmin(admin.ModelAdmin):
    list_display = (
        "id_periodo",
        "fecha_inicio",
        "fecha_termino",
        "dias_computables",
        "estado",
        "version_parametros",
    )
    list_filter = ("estado",)
    inlines = [MetaDesempenoInline]
    actions = [archivar_registros]

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).filter(deleted_at__isnull=True)


@admin.register(MetaDesempeno)
class MetaDesempenoAdmin(admin.ModelAdmin):
    list_display = (
        "id_meta",
        "item",
        "periodo",
        "funcionario",
        "cargo",
        "valor_objetivo",
        "unidad",
        "ponderador",
    )
    list_filter = ("periodo", "cargo")
    search_fields = ("item", "funcionario__nombre")
    actions = [archivar_registros]

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).filter(deleted_at__isnull=True)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "funcionario":
            kwargs["queryset"] = db_field.related_model.objects.filter(
                deleted_at__isnull=True
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)