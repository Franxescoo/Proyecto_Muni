# Migración manual para añadir múltiples roles por cargo sin perder el grupo histórico.
from django.db import migrations, models


def migrate_legacy_group(apps, schema_editor):
    Position = apps.get_model("organization", "PositionFunction")
    through = Position.role_groups.through
    for position in Position.objects.exclude(group_id__isnull=True).iterator():
        through.objects.get_or_create(
            positionfunction_id=position.pk,
            group_id=position.group_id,
        )


class Migration(migrations.Migration):
    dependencies = [("organization", "0019_delegation_created_by")]

    operations = [
        migrations.AddField(
            model_name="positionfunction",
            name="role_groups",
            field=models.ManyToManyField(
                blank=True,
                related_name="role_positions",
                to="auth.group",
                verbose_name="Roles del cargo",
            ),
        ),
        migrations.RunPython(migrate_legacy_group, migrations.RunPython.noop),
    ]
