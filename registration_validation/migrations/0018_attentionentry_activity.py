# SGR-0018: actividad principal de cada atención.
from django.db import migrations, models
import django.db.models.deletion


def backfill_from_legacy(apps, schema_editor):
    Attention = apps.get_model("registration_validation", "AttentionEntry")
    Activity = apps.get_model("registration_validation", "Activity")
    db = schema_editor.connection.alias
    # Relación histórica: muchas actividades podían apuntar a una atención.
    # Elegir la primera por fecha/ID como actividad principal, conservando
    # las otras relaciones históricas Activity.attention sin borrarlas.
    for attention in Attention.objects.using(db).filter(activity__isnull=True).iterator():
        first = (Activity.objects.using(db).filter(attention_id=attention.pk,
                  deleted_at__isnull=True).order_by("date", "activity_id")
                 .values_list("pk", flat=True).first())
        if first is not None:
            Attention.objects.using(db).filter(pk=attention.pk).update(activity_id=first)


class Migration(migrations.Migration):
    dependencies = [
        ("registration_validation", "0017_respaldo_formal_felicitaciones"),
    ]
    operations = [
        migrations.AddField(
            model_name="attentionentry", name="activity",
            field=models.ForeignKey(
                to="registration_validation.activity",
                on_delete=django.db.models.deletion.PROTECT,
                null=True, blank=True, related_name="assigned_attentions",
                verbose_name="Actividad asociada",
            ),
        ),
        migrations.RunPython(backfill_from_legacy, migrations.RunPython.noop),
    ]
