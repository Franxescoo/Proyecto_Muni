from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("citizen_requests", "0003_alter_citizenrequest_delegation"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="citizenrequest",
            options={
                "ordering": ["-created_at"],
                "permissions": [
                    (
                        "derivar_solicitud",
                        "Puede derivar solicitudes ciudadanas",
                    ),
                ],
                "verbose_name": "Solicitud ciudadana",
                "verbose_name_plural": "Solicitudes ciudadanas",
            },
        ),
    ]
