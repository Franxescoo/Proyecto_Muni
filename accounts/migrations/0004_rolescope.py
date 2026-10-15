# Generated manually to keep the role scope schema explicit in version control.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_userprofile_employee"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("organization", "0008_positionfunction_group"),
    ]

    operations = [
        migrations.CreateModel(
            name="RoleScope",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                (
                    "all_delegations",
                    models.BooleanField(
                        default=False,
                        verbose_name="Acceso a todas las delegaciones",
                    ),
                ),
                (
                    "delegations",
                    models.ManyToManyField(
                        blank=True,
                        related_name="role_scopes",
                        to="organization.delegation",
                        verbose_name="Delegaciones autorizadas",
                    ),
                ),
                (
                    "group",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="role_scope",
                        to="auth.group",
                        verbose_name="Rol",
                    ),
                ),
            ],
            options={
                "verbose_name": "Alcance de rol",
                "verbose_name_plural": "Alcances de roles",
            },
        ),
    ]
