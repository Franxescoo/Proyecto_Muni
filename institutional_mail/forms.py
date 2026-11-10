from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import validate_email


MAX_RECIPIENTS = 20


class ComposeMessageForm(forms.Form):
    # `recipient` mantiene compatibilidad con el envío unitario de la versión anterior.
    recipient = forms.IntegerField(min_value=1, required=False)
    recipients = forms.CharField(required=False, max_length=512)
    subject = forms.CharField(max_length=200, strip=True)
    body = forms.CharField(max_length=10000, strip=True)
    reply_to = forms.IntegerField(min_value=1, required=False)

    def __init__(self, *args, sender=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.sender = sender

    def clean(self):
        cleaned = super().clean()
        raw = (cleaned.get('recipients') or '').strip()
        if not raw and cleaned.get('recipient'):
            raw = str(cleaned['recipient'])
        if not raw:
            raise ValidationError('Selecciona al menos un funcionario en Para.')
        parts = [p.strip() for p in raw.replace(';', ',').split(',')]
        if not all(parts) or any(not p.isdecimal() for p in parts):
            raise ValidationError('Selecciona funcionarios desde las sugerencias de Para.')
        ids = [int(p) for p in parts]
        if len(ids) > MAX_RECIPIENTS:
            raise ValidationError(f'Se permiten como máximo {MAX_RECIPIENTS} destinatarios por mensaje.')
        if len(set(ids)) != len(ids):
            raise ValidationError('No puedes agregar el mismo destinatario dos veces.')
        if self.sender and self.sender.pk in ids:
            raise ValidationError('No puedes enviarte un mensaje a ti mismo.')
        users = get_user_model().objects.filter(
            pk__in=ids, is_active=True,
            profile__employee__isnull=False,
            profile__employee__deleted_at__isnull=True,
        ).exclude(email='')
        by_id = {u.pk: u for u in users}
        if len(by_id) != len(ids):
            raise ValidationError('Uno de los destinatarios no es un funcionario habilitado.')
        for user in by_id.values():
            try:
                validate_email(user.email)
            except ValidationError:
                raise ValidationError('Uno de los funcionarios no tiene correo válido.')
        cleaned['recipient_users'] = [by_id[pk] for pk in ids]
        return cleaned

    def clean_body(self):
        body = self.cleaned_data['body'].strip()
        if not body:
            raise ValidationError('Escribe el contenido del mensaje.')
        return body
