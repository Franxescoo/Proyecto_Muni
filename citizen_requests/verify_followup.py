"""Confirmación pública con enlace firmado y formulario POST protegido por CSRF."""
from django.core import signing
from django.db import transaction
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from .models import CitizenRequest, RequestEvent
from .email_verification import SALT, MAX_AGE, matches_current_verification, notify_after_verification

@never_cache
@require_http_methods(["GET", "POST"])
def verify_followup_email(request, token):
    valid = False
    try:
        data = signing.loads(token, salt=SALT, max_age=MAX_AGE)
    except (signing.BadSignature, signing.SignatureExpired, ValueError):
        data = None
    if data:
        citizen_request = CitizenRequest.objects.select_related("citizen").filter(pk=data.get("request")).first()
        valid = bool(citizen_request and matches_current_verification(citizen_request,data))
    if request.method == "POST" and valid:
        with transaction.atomic():
            citizen_request = CitizenRequest.objects.select_for_update().select_related("citizen").get(pk=data["request"])
            if matches_current_verification(citizen_request,data):
                citizen_request.verified_followup_email = citizen_request.pending_followup_email
                citizen_request.pending_followup_email = ""
                citizen_request.followup_verification_nonce = None
                citizen_request.followup_email_paused = False
                citizen_request.save(update_fields=["verified_followup_email","pending_followup_email","followup_verification_nonce","followup_email_paused","updated_at"])
                RequestEvent.objects.create(request=citizen_request, actor=None, observation="Nuevo correo de seguimiento verificado por su titular.",previous_status=citizen_request.status,new_status=citizen_request.status)
                notify_after_verification(citizen_request)
                return render(request,"citizen_requests/verify_followup_email.html",{"success":True})
        valid=False
    return render(request,"citizen_requests/verify_followup_email.html",{"valid":valid},status=200 if valid else 400)
