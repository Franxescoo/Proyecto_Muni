import json
import os
import secrets
import subprocess
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

from .models import PasswordRecoveryCode


CODE_LIFETIME = timedelta(minutes=5)


def create_recovery_code(user):
    code = f"{secrets.randbelow(1_000_000):06d}"
    now = timezone.now()
    PasswordRecoveryCode.objects.filter(
        user=user,
        used_at__isnull=True,
    ).update(used_at=now)
    recovery = PasswordRecoveryCode.objects.create(
        user=user,
        code_hash=make_password(code),
        expires_at=now + CODE_LIFETIME,
    )
    return recovery, code


def send_recovery_code(request, user, code):
    context = {
        "user": user,
        "code": code,
        "site_name": "Municipalidad de La Serena",
    }
    subject = "Municipalidad de La Serena - Código de recuperación"
    text_body = render_to_string(
        "registration/password_recovery_code.txt",
        context,
    )
    html_body = render_to_string(
        "registration/password_recovery_code.html",
        context,
    )
    if settings.MAILER_BACKEND == "phpmailer":
        _send_with_phpmailer(
            user.email,
            subject,
            text_body,
            html_body,
        )
        return

    message = EmailMultiAlternatives(
        subject,
        text_body,
        None,
        [user.email],
        headers={"X-Recovery-Request": "password"},
    )
    message.attach_alternative(html_body, "text/html")
    message.send()


def _send_with_phpmailer(recipient, subject, text_body, html_body):
    payload = json.dumps({
        "to": recipient,
        "subject": subject,
        "text": text_body,
        "html": html_body,
    })
    environment = os.environ.copy()
    result = subprocess.run(
        [settings.PHPMAILER_PHP, settings.PHPMAILER_SCRIPT],
        input=payload,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
        env=environment,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "No se recibió detalle del error."
        raise RuntimeError(f"No se pudo enviar el correo con PHPMailer: {detail}")


def valid_recovery_code(recovery, code):
    return (
        recovery.used_at is None
        and recovery.expires_at > timezone.now()
        and check_password(code, recovery.code_hash)
    )
