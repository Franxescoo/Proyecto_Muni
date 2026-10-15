from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("organization", "0008_positionfunction_group"),
    ]

    operations = [
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
        migrations.AddField(
            model_name="employee",
            name="photo",
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to="employees/",
                verbose_name="Foto de perfil",
            ),
        ),
    ]
