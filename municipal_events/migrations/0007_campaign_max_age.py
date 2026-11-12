from django.db import migrations, models
from django.core.validators import MaxValueValidator, MinValueValidator


class Migration(migrations.Migration):

    dependencies = [
        ("municipal_events", "0006_alter_eventparticipation_options"),
    ]

    operations = [
        migrations.AddField(
            model_name="campaign",
            name="max_age",
            field=models.PositiveIntegerField(
                default=10,
                help_text="Edad calculada al 31 de diciembre del año de la campaña.",
                validators=[
                    MinValueValidator(0),
                    MaxValueValidator(120),
                ],
                verbose_name="Edad máxima permitida",
            ),
        ),
    ]
