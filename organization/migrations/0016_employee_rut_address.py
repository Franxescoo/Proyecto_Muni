from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("organization", "0015_role_description_delegation_responsible"),
    ]

    operations = [
        migrations.AddField(
            model_name="employee",
            name="address",
            field=models.CharField(
                blank=True,
                max_length=200,
                verbose_name="Dirección",
            ),
        ),
        migrations.AddField(
            model_name="employee",
            name="rut",
            field=models.CharField(
                blank=True,
                max_length=12,
                null=True,
                unique=True,
                verbose_name="RUT",
            ),
        ),
    ]
