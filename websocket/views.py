from django.shortcuts import render

# Create your views here.
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST
from .services import publish_chat_message

@login_required
def chat_room(request):
    return render(request, "websocket/chat.html")

@login_required
@require_POST
def send_message(request):
    try:
        delegation_id = request.user.profile.delegation_id
    except ObjectDoesNotExist:
        delegation_id = None

    if delegation_id is None:
        return JsonResponse(
            {"error": "Sin delegación asignada"},
            status=403
        )

    message = request.POST.get("message", "").strip()

    if not 1 <= len(message) <= 300:
        return JsonResponse(
            {"error": "Mensaje inválido"},
            status=400
        )

    publish_chat_message(
        request.user,
        delegation_id,
        message
    )

    return JsonResponse({"ok": True})
