import secrets
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
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
    message = EmailMultiAlternatives(
        subject,
        text_body,
        None,
        [user.email],
        headers={"X-Recovery-Request": "password"},
    )
    message.attach_alternative(html_body, "text/html")
    message.send()


def valid_recovery_code(recovery, code):
    return (
        recovery.used_at is None
        and recovery.expires_at > timezone.now()
        and check_password(code, recovery.code_hash)
    )
