from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("planning_measurements", "0006_closed_period_archive_permission_log"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PeriodParameterSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("revision", models.PositiveIntegerField()),
                ("event", models.CharField(choices=[
                    ("CREATED", "Creación"),
                    ("CONFIGURED", "Actualización de parámetros"),
                    ("GOALS_UPDATED", "Modificación de metas"),
                    ("CATALOG_UPDATED", "Cambio de ítem"),
                    ("CLOSED", "Cierre"),
                    ("REOPENED", "Reapertura"),
                ], max_length=20)),
                ("saved_at", models.DateTimeField(auto_now_add=True)),
                ("content", models.JSONField(default=dict)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="period_parameter_snapshots", to=settings.AUTH_USER_MODEL)),
                ("period", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="parameter_snapshots", to="planning_measurements.period")),
            ],
            options={
                "ordering": ("-revision",),
                "verbose_name": "Versión histórica del período",
                "verbose_name_plural": "Versiones históricas del período",
            },
        ),
        migrations.AddConstraint(
            model_name="periodparametersnapshot",
            constraint=models.UniqueConstraint(
                fields=("period", "revision"),
                name="unique_period_parameter_revision",
            ),
        ),
    ]
