import logging
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q, Min, Subquery
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .forms import ComposeMessageForm
from .models import InstitutionalMessage

logger = logging.getLogger(__name__)


def _is_employee(user):
    if not user.is_authenticated or not user.is_active:
        return False
    profile = getattr(user, 'profile', None)
    return bool(profile and profile.employee_id and not profile.employee.deleted_at)


def _no_access():
    return JsonResponse({'ok': False, 'error': 'Solo los funcionarios vinculados pueden utilizar el correo institucional.'}, status=403)


def _display_name(user):
    full = user.get_full_name().strip()
    if full:
        return full
    profile = getattr(user, 'profile', None)
    if profile and profile.employee_id:
        return profile.employee.name
    return user.username


def _get_message(user, pk):
    return get_object_or_404(
        InstitutionalMessage.objects.select_related(
            'sender', 'recipient', 'sender__profile__employee',
            'recipient__profile__employee',
        ).filter(Q(sender=user) | Q(recipient=user)),
        pk=pk,
    )


def _batch_members(item, user):
    if item.sender_id != user.pk:
        return [item]
    return list(InstitutionalMessage.objects.select_related(
        'recipient', 'recipient__profile__employee',
    ).filter(sender=user, batch_id=item.batch_id).order_by('id'))


def _summary(item, user):
    is_recipient = item.recipient_id == user.pk
    members = _batch_members(item, user)
    to_names = [_display_name(m.recipient) for m in members]
    return {
        'id': item.pk,
        'from': _display_name(item.sender),
        'to': ', '.join(to_names),
        'recipient_count': len(members),
        'subject': item.subject,
        'snippet': item.body.replace('\n', ' ')[:125],
        'when': timezone.localtime(item.created_at).strftime('%d/%m/%Y %H:%M'),
        'unread': bool(is_recipient and not item.read_at),
        'archived': bool(item.recipient_archived_at if is_recipient else item.sender_archived_at),
        'mine': item.sender_id == user.pk,
    }


@login_required
@require_GET
def unread_count(request):
    if not _is_employee(request.user):
        return _no_access()
    count = InstitutionalMessage.objects.filter(
        recipient=request.user, read_at__isnull=True,
        recipient_archived_at__isnull=True,
    ).count()
    return JsonResponse({'ok': True, 'unread': count})


@login_required
@require_GET
def recipients(request):
    if not _is_employee(request.user):
        return _no_access()
    q = request.GET.get('q', '').strip()[:80]
    users = get_user_model().objects.filter(
        is_active=True,
        profile__employee__isnull=False,
        profile__employee__deleted_at__isnull=True,
    ).exclude(pk=request.user.pk).exclude(email='')
    if q:
        users = users.filter(
            Q(username__icontains=q) | Q(first_name__icontains=q) |
            Q(last_name__icontains=q) | Q(email__icontains=q) |
            Q(profile__employee__name__icontains=q)
        )
    users = users.select_related('profile__employee__delegation').order_by('username')[:100]
    return JsonResponse({'ok': True, 'recipients': [
        {
            'id': user.pk,
            'name': _display_name(user),
            'email': user.email,
            'delegation': user.profile.employee.delegation.name,
        }
        for user in users
    ]})


@login_required
@require_GET
def messages(request):
    if not _is_employee(request.user):
        return _no_access()
    folder = request.GET.get('folder', 'inbox')
    if folder not in {'inbox', 'sent', 'archive'}:
        return JsonResponse({'ok': False, 'error': 'Carpeta inválida.'}, status=400)
    qs = InstitutionalMessage.objects.select_related(
        'sender', 'recipient', 'sender__profile__employee',
        'recipient__profile__employee',
    )
    if folder == 'inbox':
        qs = qs.filter(recipient=request.user, recipient_archived_at__isnull=True)
    elif folder == 'sent':
        qs = qs.filter(sender=request.user, sender_archived_at__isnull=True)
    else:
        qs = qs.filter(
            Q(sender=request.user, sender_archived_at__isnull=False) |
            Q(recipient=request.user, recipient_archived_at__isnull=False)
        ).distinct()
    q = request.GET.get('q', '').strip()[:100]
    if q:
        qs = qs.filter(
            Q(subject__icontains=q) | Q(body__icontains=q) |
            Q(sender__username__icontains=q) | Q(recipient__username__icontains=q) |
            Q(sender__profile__employee__name__icontains=q) |
            Q(recipient__profile__employee__name__icontains=q)
        )
    if folder in {'sent', 'archive'}:
        # Una fila por envío agrupado para el remitente; el destinatario solo ve su copia.
        sent_groups = qs.filter(sender=request.user).order_by().values('batch_id').annotate(
            representative=Min('pk')
        ).values('representative')
        qs = qs.filter(Q(recipient=request.user) | Q(pk__in=Subquery(sent_groups)))
    try:
        page = max(1, int(request.GET.get('page', '1')))
    except ValueError:
        page = 1
    page_size = 30
    total = qs.count()
    items = list(qs[(page - 1) * page_size:page * page_size])
    return JsonResponse({
        'ok': True, 'folder': folder, 'total': total, 'page': page,
        'has_more': page * page_size < total,
        'messages': [_summary(item, request.user) for item in items],
    })


@login_required
@require_GET
def message_detail(request, pk):
    if not _is_employee(request.user):
        return _no_access()
    item = _get_message(request.user, pk)
    members = _batch_members(item, request.user)
    return JsonResponse({'ok': True, 'message': {
        **_summary(item, request.user),
        'body': item.body,
        'sender_id': item.sender_id,
        'sender_email': item.sender.email,
        'recipient_id': item.recipient_id,
        'recipient_email': ', '.join(m.recipient.email for m in members),
        'recipients': [{'id': m.recipient_id, 'name': _display_name(m.recipient),
                        'email': m.recipient.email} for m in members],
        'reply_to': item.reply_to_id,
        'notification': item.notice_status if item.sender_id == request.user.pk else None,
        'notifications': [m.notice_status for m in members] if item.sender_id == request.user.pk else [],
    }})


@login_required
@require_POST
def mark_read(request, pk):
    if not _is_employee(request.user):
        return _no_access()
    item = get_object_or_404(InstitutionalMessage, pk=pk, recipient=request.user)
    if not item.read_at:
        item.read_at = timezone.now()
        item.save(update_fields=['read_at'])
    return JsonResponse({'ok': True})


@login_required
@require_POST
def set_archive(request, pk):
    if not _is_employee(request.user):
        return _no_access()
    item = _get_message(request.user, pk)
    desired = request.POST.get('archive')
    if desired not in {'0', '1'}:
        return JsonResponse({'ok': False, 'error': 'Acción inválida.'}, status=400)
    date = timezone.now() if desired == '1' else None
    if item.sender_id == request.user.pk:
        InstitutionalMessage.objects.filter(
            sender=request.user, batch_id=item.batch_id,
        ).update(sender_archived_at=date)
    else:
        item.recipient_archived_at = date
        item.save(update_fields=['recipient_archived_at'])
    return JsonResponse({'ok': True})


@login_required
@require_POST
def send_message(request):
    if not _is_employee(request.user):
        return _no_access()
    form = ComposeMessageForm(request.POST, sender=request.user)
    if not form.is_valid():
        first_error = next(iter(form.errors.values()))[0]
        return JsonResponse({'ok': False, 'error': str(first_error)}, status=400)

    recipients = form.cleaned_data['recipient_users']
    reply_id = form.cleaned_data.get('reply_to')
    reply = None
    if reply_id:
        reply = _get_message(request.user, reply_id)
        expected = reply.sender_id if reply.recipient_id == request.user.pk else reply.recipient_id
        if len(recipients) != 1 or expected != recipients[0].pk:
            return JsonResponse({'ok': False, 'error': 'La respuesta debe dirigirse al otro participante.'}, status=400)

    # Limitar envíos individuales por hora; 1 mensaje a N personas cuenta N envíos.
    past_hour = timezone.now() - timedelta(hours=1)
    recent = InstitutionalMessage.objects.filter(sender=request.user, created_at__gte=past_hour).count()
    if recent + len(recipients) > 30:
        return JsonResponse({
            'ok': False, 'error': 'Máximo 30 entregas por hora, contando cada destinatario.'
        }, status=429)

    batch_id = uuid.uuid4()
    with transaction.atomic():
        items = [InstitutionalMessage.objects.create(
            batch_id=batch_id, sender=request.user, recipient=user,
            subject=form.cleaned_data['subject'], body=form.cleaned_data['body'],
            reply_to=reply,
        ) for user in recipients]

    delivered = 0
    failed = 0
    for item in items:
        try:
            sent = send_mail(
                subject=f'[SGR] {item.subject}',
                message=(
                    f'Mensaje institucional de {_display_name(request.user)}\n\n'
                    f'{item.body}\n\n'
                    'Para responder dentro del SGR, entra a Correo institucional.\n'
                    'Este mensaje también queda guardado en tu bandeja interna.'
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[item.recipient.email],
                fail_silently=False,
            )
            status = (InstitutionalMessage.NoticeStatus.SENT if sent else
                      InstitutionalMessage.NoticeStatus.FAILED)
        except Exception as exc:
            status = InstitutionalMessage.NoticeStatus.FAILED
            logger.warning('No se pudo avisar por correo (mensaje %s, error %s).',
                           item.pk, type(exc).__name__)
        item.notice_status = status
        item.save(update_fields=['notice_status'])
        delivered += status == InstitutionalMessage.NoticeStatus.SENT
        failed += status == InstitutionalMessage.NoticeStatus.FAILED

    count = len(items)
    notice = (f'Mensaje guardado para {count} destinatario(s). '
              f'Copias externas enviadas: {delivered}; no enviadas: {failed}.')
    return JsonResponse({
        'ok': True, 'id': items[0].pk, 'recipient_count': count,
        'notification': items[0].notice_status, 'sent_emails': delivered,
        'failed_emails': failed, 'notice': notice,
    }, status=201)
