from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("organization", "0012_organizationrole_application_delegations"),
    ]

    operations = [
        migrations.AddField(
            model_name="delegation",
            name="address",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="delegation",
            name="code",
            field=models.CharField(
                blank=True,
                max_length=30,
                null=True,
                unique=True,
            ),
        ),
        migrations.AddField(
            model_name="delegation",
            name="commune",
            field=models.CharField(blank=True, max_length=100),
        ),
    ]
