import uuid

from django.db import migrations, models


def fill_batches(apps, schema_editor):
    Message = apps.get_model('institutional_mail', 'InstitutionalMessage')
    for pk in Message.objects.using(schema_editor.connection.alias).values_list('pk', flat=True).iterator():
        Message.objects.using(schema_editor.connection.alias).filter(pk=pk).update(batch_id=uuid.uuid4())


class Migration(migrations.Migration):
    dependencies = [('institutional_mail', '0001_initial')]
    operations = [
        migrations.AddField(
            model_name='institutionalmessage', name='batch_id',
            field=models.UUIDField(null=True, editable=False, db_index=True),
        ),
        migrations.RunPython(fill_batches, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='institutionalmessage', name='batch_id',
            field=models.UUIDField(default=uuid.uuid4, editable=False, db_index=True),
        ),
    ]
