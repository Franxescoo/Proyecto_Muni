# Cambio obligatorio de contraseña temporal en el primer ingreso SGR.
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0006_passwordrecoverycode'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='must_change_password',
            field=models.BooleanField(
                default=False, verbose_name='Debe cambiar contraseña inicial',
            ),
        ),
    ]
