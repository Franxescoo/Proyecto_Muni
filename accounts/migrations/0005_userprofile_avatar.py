from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_rolescope"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="avatar",
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to="profiles/",
                verbose_name="Foto de perfil",
            ),
        ),
    ]
