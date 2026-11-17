from decimal import Decimal
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("monitoring_traceability", "0006_commitmentreassignment_commitmentstatushistory_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="MonitoringSettings",
            fields=[
                ("key", models.CharField(default="global", editable=False, max_length=20, primary_key=True, serialize=False)),
                ("low_compliance_threshold", models.DecimalField(decimal_places=2, default=80, max_digits=6)),
                ("inactivity_workdays", models.PositiveSmallIntegerField(default=5)),
                ("due_soon_days", models.PositiveSmallIntegerField(default=7)),
                ("positive_adjustment_max", models.DecimalField(decimal_places=2, default=100, max_digits=6)),
                ("negative_adjustment_max", models.DecimalField(decimal_places=2, default=100, max_digits=6)),
                ("effective_from", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="monitoring_settings_updated", to=settings.AUTH_USER_MODEL)),
                ("recipient_users", models.ManyToManyField(blank=True, related_name="monitoring_alert_recipient_settings", to=settings.AUTH_USER_MODEL)),
            ],
            options={"verbose_name": "Reglas operativas de monitoreo", "verbose_name_plural": "Reglas operativas de monitoreo", "default_permissions": ("view", "change")},
        ),
        migrations.CreateModel(
            name="MonitoringSettingsRevision",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("changed_at", models.DateTimeField(auto_now_add=True)),
                ("previous_value", models.JSONField(default=dict)),
                ("new_value", models.JSONField(default=dict)),
                ("changed_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-changed_at", "-pk"), "default_permissions": ("add", "view")},
        ),
        migrations.CreateModel(
            name="MonitoringAlertReview",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("alert_key", models.CharField(max_length=200, unique=True)),
                ("reviewed_at", models.DateTimeField(auto_now_add=True)),
                ("comment", models.CharField(blank=True, max_length=250)),
                ("reviewed_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-reviewed_at", "-pk"), "default_permissions": ("add", "view")},
        ),
    ]
