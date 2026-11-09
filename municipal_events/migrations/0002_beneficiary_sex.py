from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("municipal_events", "0001_initial")]
    operations = [migrations.AddField(model_name="beneficiary", name="sex", field=models.CharField(blank=True, choices=[("M", "Masculino"), ("F", "Femenino")], default="", max_length=1, verbose_name="Sexo del niño o niña"))]
