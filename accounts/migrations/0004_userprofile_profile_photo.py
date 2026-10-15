from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_userprofile_employee"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="profile_photo",
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to="profile_photos/",
                verbose_name="Foto de perfil",
            ),
        ),
    ]
