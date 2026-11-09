from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("organization", "0017_employee_roles_max_length"),
    ]

    operations = [
        migrations.AlterField(
            model_name="organizationrole",
            name="delegation",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.PROTECT,
                related_name="organization_roles",
                to="organization.delegation",
            ),
        ),
    ]
