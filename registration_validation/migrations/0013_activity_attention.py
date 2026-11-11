import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("registration_validation", "0012_alter_activity_options_alter_activitytype_options_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="activity",
            name="attention",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="activities",
                to="registration_validation.attentionentry",
                verbose_name="Atención asociada",
            ),
        ),
    ]
