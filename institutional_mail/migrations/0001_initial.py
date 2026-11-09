from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name='InstitutionalMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('subject', models.CharField(max_length=200, verbose_name='Asunto')),
                ('body', models.TextField(verbose_name='Mensaje')),
                ('created_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('read_at', models.DateTimeField(blank=True, null=True)),
                ('recipient_archived_at', models.DateTimeField(blank=True, null=True)),
                ('sender_archived_at', models.DateTimeField(blank=True, null=True)),
                ('notice_status', models.CharField(choices=[('PENDING', 'Pendiente'), ('SENT', 'Correo enviado'), ('FAILED', 'No se pudo enviar aviso'), ('SKIPPED', 'Sin correo externo')], default='PENDING', max_length=10)),
                ('recipient', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='institutional_messages_received', to=settings.AUTH_USER_MODEL, verbose_name='Destinatario')),
                ('sender', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='institutional_messages_sent', to=settings.AUTH_USER_MODEL, verbose_name='Remitente')),
                ('reply_to', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='replies', to='institutional_mail.institutionalmessage', verbose_name='Respuesta a')),
            ],
            options={'verbose_name': 'Mensaje institucional', 'verbose_name_plural': 'Mensajes institucionales', 'ordering': ('-created_at', '-id')},
        ),
        migrations.AddIndex(model_name='institutionalmessage', index=models.Index(fields=['recipient', 'recipient_archived_at', '-created_at'], name='mail_inbox_idx')),
        migrations.AddIndex(model_name='institutionalmessage', index=models.Index(fields=['sender', 'sender_archived_at', '-created_at'], name='mail_sent_idx')),
    ]
