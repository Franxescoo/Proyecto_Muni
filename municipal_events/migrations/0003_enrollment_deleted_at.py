# Generada para preservar inscripciones y su auditoría.
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("municipal_events", "0002_beneficiary_sex")]
    operations = [
        migrations.AddField(
            model_name="enrollment",
            name="deleted_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
    ]
