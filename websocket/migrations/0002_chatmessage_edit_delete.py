from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("websocket", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatmessage",
            name="edited_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="chatmessage",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
