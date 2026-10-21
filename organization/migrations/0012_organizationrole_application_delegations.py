from django.db import migrations, models


def copy_primary_delegations(apps, schema_editor):
    OrganizationRole = apps.get_model("organization", "OrganizationRole")
    through = OrganizationRole.application_delegations.through
    rows = [
        through(
            organizationrole_id=role.pk,
            delegation_id=role.delegation_id,
        )
        for role in OrganizationRole.objects.all().only("pk", "delegation_id")
    ]
    through.objects.bulk_create(rows, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [
        ("organization", "0011_employee_profile_photo"),
    ]

    operations = [
        migrations.AddField(
            model_name="organizationrole",
            name="application_delegations",
            field=models.ManyToManyField(
                blank=True,
                related_name="application_roles",
                to="organization.delegation",
                verbose_name="Delegaciones de aplicación",
            ),
        ),
        migrations.RunPython(
            copy_primary_delegations,
            migrations.RunPython.noop,
        ),
    ]
