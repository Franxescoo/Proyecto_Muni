from django.db import migrations, models
from django.core.validators import MinValueValidator


class Migration(migrations.Migration):

    dependencies = [
        ("planning_measurements", "0003_alter_measurementitem_unit"),
    ]

    operations = [
        migrations.AddField(
            model_name="goal",
            name="required_evidence_count",
            field=models.PositiveIntegerField(
                default=5,
                validators=[MinValueValidator(2)],
                verbose_name="Required evidence count",
            ),
        ),
    ]
