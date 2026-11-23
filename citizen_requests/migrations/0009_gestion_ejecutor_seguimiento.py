# Generada para SGR sobre citizen_requests 0008. No modifica datos históricos.
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("citizen_requests", "0008_citizenrequestactionattachment"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="citizenrequestaction", name="executor_type",
            field=models.CharField(max_length=20, blank=True, default="", choices=[("MUNICIPAL", "Funcionario municipal"), ("TECHNICIAN", "Técnico externo"), ("COMPANY", "Empresa externa")], verbose_name="Tipo de ejecutor"),
        ),
        migrations.AddField(
            model_name="citizenrequestaction", name="executor_name",
            field=models.CharField(max_length=160, blank=True, verbose_name="Nombre del ejecutor"),
        ),
        migrations.AddField(
            model_name="citizenrequestaction", name="executor_contact",
            field=models.CharField(max_length=200, blank=True, verbose_name="Contacto del ejecutor"),
        ),
        migrations.AddField(
            model_name="citizenrequestaction", name="expected_execution_date",
            field=models.DateField(null=True, blank=True, verbose_name="Fecha prevista de ejecución"),
        ),
        migrations.AddField(
            model_name="citizenrequestaction", name="execution_status",
            field=models.CharField(max_length=20, blank=True, default="", choices=[("PENDING", "Pendiente de coordinación"), ("COORDINATED", "Coordinado"), ("IN_PROGRESS", "En ejecución"), ("FINISHED", "Finalizado")], verbose_name="Estado del encargo"),
        ),
        migrations.CreateModel(
            name="CitizenRequestActionProgress",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("previous_status", models.CharField(max_length=20, blank=True)),
                ("new_status", models.CharField(max_length=20)),
                ("note", models.TextField(verbose_name="Motivo u observación")),
                ("recorded_at", models.DateTimeField(auto_now_add=True)),
                ("action", models.ForeignKey(to="citizen_requests.citizenrequestaction", on_delete=django.db.models.deletion.PROTECT, related_name="progress_events", verbose_name="Gestión operativa")),
                ("recorded_by", models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.PROTECT, related_name="sgr_action_progress_events")),
            ],
            options={
                "ordering": ("recorded_at", "id"),
                "default_permissions": (),
                "verbose_name": "Seguimiento de gestión operativa",
                "verbose_name_plural": "Seguimientos de gestiones operativas",
            },
        ),
    ]
