from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("organization", "0016_employee_rut_address"),
    ]

    operations = [
        migrations.AlterField(
            model_name="employee",
            name="roles",
            field=models.TextField(max_length=1000),
        ),
    ]
