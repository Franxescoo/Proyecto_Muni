# Se ajusta la dependencia a la última migración de tu instalación.
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('municipal_events', '0004_eventos_participacion_borrado_logico')]

    operations = [
        migrations.AddField(
            model_name='eventparticipation', name='withdrawn_at',
            field=models.DateTimeField('Retirado el', null=True, blank=True, db_index=True),
        ),
    ]
