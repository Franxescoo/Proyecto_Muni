import django.db.models.deletion
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("citizen_registry", "0001_initial"), ("registration_validation", "0010_attentionentry_address_attentionentry_closed_at_and_more")]
    operations = [migrations.AddField(model_name="attentionentry", name="citizen", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="attention_entries", to="citizen_registry.citizen"))]
