"""API HTTP del chat, con autorización servidor y persistencia."""

import uuid

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Max
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from .access import chat_delegation_id
from .models import ChatMessage, ChatReadState
from .services import publish_chat_message, serialize_message, unread_count


def _delegation_for_request(request):
    current = getattr(request, "sgr_active_delegation", None)
    # Nunca usar la delegación principal si el middleware ha seleccionado otra.
    if current is None:
        return None
    return chat_delegation_id(request.user, current.pk)


@login_required
@require_GET
def chat_room(request):
    return render(request, "websocket/chat.html")


@login_required
@require_GET
def message_history(request):
    delegation_id = _delegation_for_request(request)
    if delegation_id is None:
        return JsonResponse({"error": "Sin delegación autorizada"}, status=403)
    raw_after = request.GET.get("after", "")
    if raw_after:
        try:
            after = int(raw_after)
            if after < 0:
                raise ValueError
        except (ValueError, TypeError):
            return JsonResponse({"error": "Cursor inválido"}, status=400)
        rows = list(ChatMessage.objects.filter(
            delegation_id=delegation_id, pk__gt=after,
        ).select_related("sender").order_by("pk")[:100])
    else:
        # Últimos 100 mensajes de la delegación; se muestran en orden cronológico.
        rows = list(reversed(list(ChatMessage.objects.filter(
            delegation_id=delegation_id,
        ).select_related("sender").order_by("-pk")[:100])))
    return JsonResponse({
        "messages": [serialize_message(row) for row in rows],
        "unread_count": unread_count(request.user, delegation_id),
    })


@login_required
@require_POST
def mark_messages_read(request):
    delegation_id = _delegation_for_request(request)
    if delegation_id is None:
        return JsonResponse({"error": "Sin delegación autorizada"}, status=403)
    try:
        last_id = int(request.POST.get("last_message_id", "0"))
        if last_id < 0:
            raise ValueError
    except (ValueError, TypeError):
        return JsonResponse({"error": "ID inválido"}, status=400)
    latest = ChatMessage.objects.filter(
        delegation_id=delegation_id,
    ).aggregate(last_id=Max("pk"))["last_id"] or 0
    last_id = min(last_id, latest)
    with transaction.atomic():
        state, _ = ChatReadState.objects.select_for_update().get_or_create(
            user=request.user, delegation_id=delegation_id,
            defaults={"last_read_id": 0},
        )
        if last_id > state.last_read_id:
            state.last_read_id = last_id
            state.save(update_fields=["last_read_id"])
    return JsonResponse({"ok": True, "unread_count": unread_count(request.user, delegation_id)})


@login_required
@require_POST
def send_message(request):
    delegation_id = _delegation_for_request(request)
    if delegation_id is None:
        return JsonResponse({"error": "Sin delegación autorizada"}, status=403)
    text = request.POST.get("message", "")
    if not isinstance(text, str):
        return JsonResponse({"error": "Mensaje inválido"}, status=400)
    text = text.strip()
    if not 1 <= len(text) <= 300:
        return JsonResponse({"error": "Mensaje inválido (1 a 300 caracteres)"}, status=400)
    client_id = request.POST.get("client_id")
    if client_id:
        try:
            client_id = uuid.UUID(client_id)
        except (ValueError, AttributeError, TypeError):
            return JsonResponse({"error": "Identificador inválido"}, status=400)
    else:
        client_id = uuid.uuid4()  # Compatibilidad con clientes antiguos.

    with transaction.atomic():
        message, created = ChatMessage.objects.get_or_create(
            sender=request.user, client_id=client_id,
            defaults={"delegation_id": delegation_id, "message": text},
        )
        if message.delegation_id != delegation_id or message.message != text:
            return JsonResponse({"error": "Identificador de envío ya utilizado"}, status=409)
    if created:
        publish_chat_message(message)
    message = ChatMessage.objects.select_related("sender").get(pk=message.pk)
    return JsonResponse({"ok": True, "message": serialize_message(message)})
