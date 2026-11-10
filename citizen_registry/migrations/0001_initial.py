from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="Citizen",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("rut", models.CharField(max_length=16, unique=True, verbose_name="RUT")),
                ("full_name", models.CharField(max_length=160, verbose_name="Nombre completo")),
                ("birth_date", models.DateField(blank=True, null=True, verbose_name="Fecha de nacimiento")),
                ("phone", models.CharField(blank=True, max_length=25, verbose_name="Teléfono")),
                ("email", models.EmailField(blank=True, max_length=254, verbose_name="Correo electrónico")),
                ("address", models.CharField(max_length=250, verbose_name="Dirección")),
                ("rsh_folio", models.CharField(blank=True, max_length=80, verbose_name="Folio Cartola RSH")),
                ("rsh_bracket", models.CharField(blank=True, choices=[("", "Sin registrar"), ("0-40", "0–40 %"), ("41-50", "41–50 %"), ("51-60", "51–60 %"), ("61-70", "61–70 %"), ("71-80", "71–80 %"), ("81-90", "81–90 %"), ("91-100", "91–100 %")], max_length=7, verbose_name="Tramo RSH")),
                ("is_neighborhood_member", models.BooleanField(default=False, verbose_name="Pertenece a Junta de Vecinos")),
                ("neighborhood_group", models.CharField(blank=True, max_length=180, verbose_name="Junta de Vecinos o agrupación")),
                ("organization_role", models.CharField(choices=[("NONE", "Ninguno"), ("PRESIDENT", "Presidente/a"), ("SECRETARY", "Secretario/a"), ("TREASURER", "Tesorero/a"), ("DELEGATE", "Delegado/a")], default="NONE", max_length=12, blank=True, verbose_name="Cargo en la organización")),
                ("is_active", models.BooleanField(default=True, verbose_name="Activo")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="citizens_created", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("full_name", "pk"), "verbose_name": "Ciudadano", "verbose_name_plural": "Ciudadanos"},
        ),
        migrations.CreateModel(
            name="CitizenAudit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(max_length=20)),
                ("changed_at", models.DateTimeField(auto_now_add=True)),
                ("description", models.CharField(blank=True, max_length=200)),
                ("actor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ("citizen", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="audit_events", to="citizen_registry.citizen")),
            ],
            options={"ordering": ("-changed_at", "-pk"), "verbose_name": "Auditoría de ciudadano", "verbose_name_plural": "Auditoría de ciudadanos"},
        ),
    ]
