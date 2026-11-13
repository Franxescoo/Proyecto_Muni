from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("planning_measurements", "0007_period_parameter_snapshot"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="period",
            options={
                "verbose_name": "Period",
                "verbose_name_plural": "Periods",
                "permissions": [
                    ("delete_closed_period", "Puede archivar períodos cerrados sin historial"),
                    ("reopen_closed_period", "Puede reabrir períodos cerrados"),
                ],
            },
        ),
    ]
