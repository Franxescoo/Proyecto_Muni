from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings

class Migration(migrations.Migration):
    dependencies = [
        ("planning_measurements", "0005_goal_measurement_item"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.AlterModelOptions(name="period", options={
            "verbose_name": "Period", "verbose_name_plural": "Periods",
            "permissions": [("delete_closed_period", "Puede archivar períodos cerrados sin historial")]
        }),
        migrations.CreateModel(name="PeriodArchiveLog", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("archived_at", models.DateTimeField(auto_now_add=True)),
            ("was_closed", models.BooleanField(default=False)),
            ("period", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="archive_logs", to="planning_measurements.period")),
            ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="period_archive_logs", to=settings.AUTH_USER_MODEL)),
        ], options={"verbose_name":"Registro de archivado de período", "verbose_name_plural":"Registros de archivado de períodos"}),
    ]
