# Parche local SGR, respaldo formal de felicitaciones.
import re
import unicodedata
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def mark_previous_congratulation_types(apps, schema_editor):
    """Sólo durante migración: detectar tipos históricamente inequívocos.

    Después de migrar, nombres y códigos NO determinan el comportamiento.
    Tipos ambiguos deben marcarse manualmente desde el catálogo.
    """
    Type = apps.get_model("registration_validation", "ActivityType")
    alias = schema_editor.connection.alias
    for item in Type.objects.using(alias).all().iterator():
        text = unicodedata.normalize(
            "NFKD", f"{item.code} {item.name}".casefold(),
        )
        text = "".join(c for c in text if not unicodedata.combining(c))
        if "felicit" in text and not item.is_preparatory_coordination:
            Type.objects.using(alias).filter(pk=item.pk).update(
                is_congratulation=True,
            )


class Migration(migrations.Migration):
    dependencies = [
        ("registration_validation", "0016_clasificacion_coordinaciones_preparatorias"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="activitytype", name="is_congratulation",
            field=models.BooleanField(
                default=False,
                verbose_name="¿Es una felicitación?",
                help_text="Requiere evidencia aprobada y respaldo formal del delegado para sumar a una meta.",
            ),
        ),
        migrations.AddField(
            model_name="validation", name="formal_delegate_endorsement",
            field=models.BooleanField(
                default=False, verbose_name="Respaldo formal del delegado",
            ),
        ),
        migrations.AddField(
            model_name="validation", name="delegate_endorsed_by",
            field=models.ForeignKey(
                to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.PROTECT,
                null=True, blank=True, editable=False,
                related_name="formal_congratulations_endorsements",
                verbose_name="Cuenta delegada que respaldó",
            ),
        ),
        migrations.AddField(
            model_name="validation", name="delegate_endorsed_at",
            field=models.DateTimeField(
                null=True, blank=True, editable=False,
                verbose_name="Fecha y hora del respaldo formal",
            ),
        ),
        migrations.RunPython(mark_previous_congratulation_types, migrations.RunPython.noop),
    ]
