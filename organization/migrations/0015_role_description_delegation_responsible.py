from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [("organization", "0014_merge_delegation_and_catalogs")]
    operations = [
        migrations.AddField(model_name="organizationrole", name="description", field=models.TextField(blank=True, verbose_name="Descripción")),
        migrations.AddField(model_name="delegation", name="responsible", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="responsible_for_delegations", to="organization.employee", verbose_name="Responsable de delegación")),
        migrations.CreateModel(name="DelegationResponsibilityLog", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("changed_at", models.DateTimeField(auto_now_add=True)),
            ("delegation", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="responsibility_history", to="organization.delegation")),
            ("previous_responsible", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="previous_responsibility_changes", to="organization.employee")),
            ("new_responsible", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="new_responsibility_changes", to="organization.employee")),
            ("changed_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="auth.user")),
        ], options={"verbose_name": "Cambio de responsable de delegación", "verbose_name_plural": "Cambios de responsable de delegación"}),
    ]
