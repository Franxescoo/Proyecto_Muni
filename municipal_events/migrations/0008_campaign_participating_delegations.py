
from django.db import migrations, models


def incorporar_delegaciones_existentes(apps, schema_editor):
    Campaign = apps.get_model("municipal_events", "Campaign")
    Enrollment = apps.get_model("municipal_events", "Enrollment")

    conexion = schema_editor.connection.alias
    relacion = Campaign.participating_delegations.through

    pares = set()

    # Conservar las delegaciones organizadoras.
    for campaign_id, delegation_id in (
        Campaign.objects.using(conexion)
        .values_list("pk", "organizing_delegation_id")
    ):
        if delegation_id is not None:
            pares.add((campaign_id, delegation_id))

    # Conservar también las delegaciones que ya tienen inscripciones,
    # incluidas las desactivadas.
    for campaign_id, delegation_id in (
        Enrollment.objects.using(conexion)
        .values_list("campaign_id", "delegation_id")
        .distinct()
    ):
        if delegation_id is not None:
            pares.add((campaign_id, delegation_id))

    relacion.objects.using(conexion).bulk_create(
        [
            relacion(
                campaign_id=campaign_id,
                delegation_id=delegation_id,
            )
            for campaign_id, delegation_id in pares
        ],
        ignore_conflicts=True,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("municipal_events", "0007_campaign_max_age"),
    ]

    operations = [
        migrations.AddField(
            model_name="campaign",
            name="participating_delegations",
            field=models.ManyToManyField(
                blank=True,
                related_name="participating_campaigns",
                to="organization.delegation",
                verbose_name="Delegaciones participantes",
            ),
        ),
        migrations.RunPython(
            incorporar_delegaciones_existentes,
            migrations.RunPython.noop,
        ),
    ]
