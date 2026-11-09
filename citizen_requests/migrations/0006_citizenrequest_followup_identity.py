from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [
        ("citizen_requests", "0005_citizenrequest_citizen"),
        ("citizen_registry", "0001_initial"),
    ]
    operations = [
        migrations.AddField(model_name="citizenrequest",name="original_citizen",field=models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.PROTECT,related_name="requests_originally_linked",to="citizen_registry.citizen")),
        migrations.AddField(model_name="citizenrequest",name="followup_email_paused",field=models.BooleanField(default=False)),
        migrations.AddField(model_name="citizenrequest",name="verified_followup_email",field=models.EmailField(blank=True,max_length=254)),
        migrations.AddField(model_name="citizenrequest",name="pending_followup_email",field=models.EmailField(blank=True,max_length=254)),
        migrations.AddField(model_name="citizenrequest",name="followup_verification_nonce",field=models.UUIDField(blank=True,null=True)),
    ]
