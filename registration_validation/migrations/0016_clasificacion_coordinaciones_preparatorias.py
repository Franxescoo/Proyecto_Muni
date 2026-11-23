# Generada para el parche local de clasificación preparatoria, 2026-11-21.
import re
import unicodedata

from django.db import migrations, models


def mark_previous_preparatory_types(apps, schema_editor):
    """Conservar tipos claramente clasificados por la regla antigua.

    Este reconocimiento se ejecuta UNA sola vez durante la migración.
    Después, la puntuación depende exclusivamente de la casilla guardada.
    """
    Type = apps.get_model("registration_validation", "ActivityType")
    alias = schema_editor.connection.alias

    def norm(text):
        text = unicodedata.normalize("NFKD", str(text or "").casefold())
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())

    for item in Type.objects.using(alias).all().iterator():
        label = norm(f"{item.code} {item.name}")
        old_preparatory = (
            ("preparator" in label and ("coordin" in label or "reunion" in label))
            or "coordprep" in label
        )
        if old_preparatory:
            Type.objects.using(alias).filter(pk=item.pk).update(
                is_preparatory_coordination=True
            )


class Migration(migrations.Migration):
    dependencies = [("registration_validation", "0015_activity_creator_sgr")]

    operations = [
        migrations.AddField(
            model_name="activitytype",
            name="is_preparatory_coordination",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Cuando está marcado, sus actividades no suman al cumplimiento "
                    "de las metas, aunque tengan evidencias aprobadas."
                ),
                verbose_name="¿Es una coordinación preparatoria?",
            ),
        ),
        migrations.RunPython(
            mark_previous_preparatory_types, migrations.RunPython.noop,
        ),
    ]
