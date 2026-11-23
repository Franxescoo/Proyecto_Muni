# SGR_CIERRE_SEMANAL_V1 — migración aditiva: preserva gestiones históricas.
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def bootstrap_general_admin(apps, schema_editor):
    # Se autoriza el permiso nuevo al rol general existente, SIN superusuario.
    # Los administradores limitados no reciben permisos nuevos.
    alias = schema_editor.connection.alias
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    ct, _ = ContentType.objects.using(alias).get_or_create(
        app_label="citizen_requests", model="citizenrequestactionweek",
    )
    perm, _ = Permission.objects.using(alias).get_or_create(
        content_type_id=ct.pk, codename="manage_citizenrequestaction_week",
        defaults={"name": "Puede cerrar y reabrir semanas de gestiones"},
    )
    group_names = (
        "administrador_general", "Administrador General", "Administrador general",
        "DEMO SGR - Administrador",
    )
    group_ids = Group.objects.using(alias).filter(
        name__in=group_names,
    ).values_list("pk", flat=True)
    through = Group.permissions.through
    for group_id in group_ids:
        through.objects.using(alias).get_or_create(
            group_id=group_id, permission_id=perm.pk,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("citizen_requests", "0009_gestion_ejecutor_seguimiento"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CitizenRequestActionWeek",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("week_start", models.DateField(verbose_name="Lunes de la semana")),
                ("is_closed", models.BooleanField(default=True, verbose_name="Semana cerrada")),
                ("closed_at", models.DateTimeField(blank=True, null=True)),
                ("closed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="closed_request_action_weeks", to=settings.AUTH_USER_MODEL)),
                ("delegation", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="request_action_weeks", to="organization.delegation", verbose_name="Delegación")),
            ],
            options={
                "verbose_name": "Cierre semanal de gestiones",
                "verbose_name_plural": "Cierres semanales de gestiones",
                "ordering": ("-week_start",),
                "default_permissions": (),
                "permissions": [("manage_citizenrequestaction_week", "Puede cerrar y reabrir semanas de gestiones")],
                "constraints": [models.UniqueConstraint(fields=("delegation", "week_start"), name="sgr_actionweek_delegation_date")],
            },
        ),
        migrations.CreateModel(
            name="CitizenRequestActionWeekEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(choices=[("CLOSE", "Cierre"), ("REOPEN", "Reapertura")], max_length=6)),
                ("reason", models.CharField(blank=True, max_length=500)),
                ("occurred_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="request_action_week_events", to=settings.AUTH_USER_MODEL)),
                ("week", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="events", to="citizen_requests.citizenrequestactionweek")),
            ],
            options={
                "default_permissions": (),
                "ordering": ("-occurred_at", "-pk"),
                "verbose_name": "Historial de cierre semanal",
                "verbose_name_plural": "Historial de cierres semanales",
            },
        ),
        migrations.RunPython(bootstrap_general_admin, migrations.RunPython.noop),
    ]
