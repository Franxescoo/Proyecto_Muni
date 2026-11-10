import django.db.models.deletion
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("citizen_registry", "0001_initial"), ("citizen_requests", "0004_citizenrequest_derivar_solicitud")]
    operations = [migrations.AddField(model_name="citizenrequest", name="citizen", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="requests", to="citizen_registry.citizen"))]
