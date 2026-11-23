# Restriccion SGR: creador real de la actividad, sin alterar historicos.
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("registration_validation", "0014_alter_evidence_code"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="activity",
            name="created_by_user",
            field=models.ForeignKey(
                to=settings.AUTH_USER_MODEL,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="sgr_activities_registered",
                verbose_name="Usuario que registró la actividad",
                null=True, blank=True, editable=False,
            ),
        ),
        migrations.AddField(
            model_name="activity",
            name="created_by_employee",
            field=models.ForeignKey(
                to="organization.employee",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="sgr_activities_registered_by_employee",
                verbose_name="Funcionario que registró la actividad",
                null=True, blank=True, editable=False,
            ),
        ),
    ]
