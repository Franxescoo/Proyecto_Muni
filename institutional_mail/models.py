import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class InstitutionalMessage(models.Model):
    class NoticeStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pendiente'
        SENT = 'SENT', 'Correo enviado'
        FAILED = 'FAILED', 'No se pudo enviar aviso'
        SKIPPED = 'SKIPPED', 'Sin correo externo'

    batch_id = models.UUIDField(default=uuid.uuid4, db_index=True, editable=False)

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='institutional_messages_sent', verbose_name='Remitente',
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='institutional_messages_received', verbose_name='Destinatario',
    )
    reply_to = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='replies', verbose_name='Respuesta a',
    )
    subject = models.CharField(max_length=200, verbose_name='Asunto')
    body = models.TextField(verbose_name='Mensaje')
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    recipient_archived_at = models.DateTimeField(null=True, blank=True)
    sender_archived_at = models.DateTimeField(null=True, blank=True)
    notice_status = models.CharField(
        max_length=10, choices=NoticeStatus.choices,
        default=NoticeStatus.PENDING,
    )

    class Meta:
        ordering = ('-created_at', '-id')
        indexes = [
            models.Index(fields=['recipient', 'recipient_archived_at', '-created_at'], name='mail_inbox_idx'),
            models.Index(fields=['sender', 'sender_archived_at', '-created_at'], name='mail_sent_idx'),
        ]
        verbose_name = 'Mensaje institucional'
        verbose_name_plural = 'Mensajes institucionales'

    def __str__(self):
        return f'{self.subject} ({self.sender_id} -> {self.recipient_id})'
