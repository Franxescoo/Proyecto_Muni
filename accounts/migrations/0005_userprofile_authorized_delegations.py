from django.db import migrations, models


def copy_primary_delegations(apps, schema_editor):
    UserProfile = apps.get_model("accounts", "UserProfile")
    through = UserProfile.authorized_delegations.through
    rows = [
        through(
            userprofile_id=profile.pk,
            delegation_id=profile.delegation_id,
        )
        for profile in UserProfile.objects.exclude(
            delegation_id__isnull=True
        ).only("pk", "delegation_id")
    ]
    through.objects.bulk_create(rows, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [
        ("organization", "0011_employee_profile_photo"),
        ("accounts", "0004_userprofile_profile_photo"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="authorized_delegations",
            field=models.ManyToManyField(
                blank=True,
                related_name="authorized_user_profiles",
                to="organization.delegation",
                verbose_name="Delegaciones autorizadas",
            ),
        ),
        migrations.RunPython(
            copy_primary_delegations,
            migrations.RunPython.noop,
        ),
    ]
