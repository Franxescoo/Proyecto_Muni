# Created for safe attribution of attention entries to the authenticated account.
# Historical entries remain valid with registered_by=NULL.
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("registration_validation", "0008_service"),
    ]

    operations = [
        migrations.AddField(
            model_name="attentionentry",
            name="registered_by",
            field=models.ForeignKey(
                to=settings.AUTH_USER_MODEL,
                on_delete=django.db.models.deletion.PROTECT,
                null=True, blank=True,
                related_name="registered_attention_entries",
                verbose_name="Usuario que registra",
            ),
        ),
    ]
