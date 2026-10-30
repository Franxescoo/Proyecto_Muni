"""Vistas con permisos de Django y alcance territorial comprobados en servidor."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.db.models import Count, Q
from django.core.paginator import Paginator
from django.http import HttpResponseNotAllowed, JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from registration_validation.models import AttentionEntry

from .forms import CampaignForm, DeliveryForm, EditionForm, EnrollmentForm, EventForm, ReviewForm
from .models import Beneficiary, Campaign, CampaignAudit, Enrollment, EventEdition, GiftDelivery, MunicipalEvent
from .services import can_access_delegation, can_register_from_attention, campaign_active_queryset, require_delegation
from accounts.permissions import allowed_delegation_ids


def _gate(perm):
    return lambda view: login_required(permission_required(perm, raise_exception=True)(view))


def _is_modal(request):
    """La interfaz usa AJAX solo para los CRUD dentro del módulo."""
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _form_response(request, form, title, cancel, section, *, note=""):
    context = {"form": form, "title": title, "cancel_url": cancel,
               "section": section, "note": note}
    if _is_modal(request):
        response = render(request, "municipal_events/_modal_form.html", context)
        if request.method == "POST":
            response.status_code = 422
        return response
    return render(request, "municipal_events/form.html", context)


def _saved(request, message, url):
    if _is_modal(request):
        return JsonResponse({"ok": True, "message": message})
    messages.success(request, message)
    return redirect(url)


def _modal_detail(request, template, context):
    if not _is_modal(request):
        # Uso directo de enlaces históricos: mostrar la misma ficha con el marco del SGR.
        return render(request, "municipal_events/detail.html", {
            **context, "detail_template": template,
        })
    return render(request, template, context)


def _visible_enrollments(user):
    """Solo inscripciones de la delegación activa y autorizada para consulta."""
    scope = allowed_delegation_ids(user, "municipal_events.view_enrollment", active_only=True)
    queryset = Enrollment.objects.all()
    return queryset if scope is None else queryset.filter(delegation_id__in=scope)


@login_required
def dashboard(request):
    """Compatibilidad con antiguos enlaces al resumen: ahora se usa el inicio del SGR."""
    return redirect("home")


@_gate("municipal_events.view_enrollment")
def enrollment_list(request):
    qs = _visible_enrollments(request.user).select_related("beneficiary", "campaign", "delegation", "delivery")
    q = request.GET.get("q", "").strip()[:80]
    state = request.GET.get("status", "")
    if q:
        qs = qs.filter(Q(beneficiary__name__icontains=q) | Q(campaign__title__icontains=q))
    if state in dict(Enrollment.STATUS):
        qs = qs.filter(status=state)
    else:
        state = ""
    total = qs.count()
    base = _visible_enrollments(request.user)
    summary = {"all": base.count(), "pending": base.filter(status="PENDING").count(),
               "delivered": GiftDelivery.objects.filter(enrollment__in=base).count()}
    page = Paginator(qs.order_by("-created_at"), 20).get_page(request.GET.get("page"))
    return render(request, "municipal_events/enrollments.html", {
        "section": "enrollments", "enrollments": page, "page_obj": page,
        "q": q, "status": state, "total": total, "summary": summary,
    })


@_gate("municipal_events.view_giftdelivery")
@_gate("municipal_events.view_enrollment")
def delivery_list(request):
    qs = _visible_enrollments(request.user).filter(status="APPROVED").select_related(
        "beneficiary", "campaign", "delegation", "delivery"
    )
    q = request.GET.get("q", "").strip()[:80]
    state = request.GET.get("state", "")
    if q:
        qs = qs.filter(Q(beneficiary__name__icontains=q) | Q(campaign__title__icontains=q))
    if state == "pending":
        qs = qs.filter(delivery__isnull=True)
    elif state == "delivered":
        qs = qs.filter(delivery__isnull=False)
    else:
        state = ""
    base = _visible_enrollments(request.user).filter(status="APPROVED")
    summary = {"approved": base.count(), "delivered": base.filter(delivery__isnull=False).count(),
               "pending": base.filter(delivery__isnull=True).count()}
    page = Paginator(qs.order_by("-created_at"), 20).get_page(request.GET.get("page"))
    return render(request, "municipal_events/deliveries.html", {
        "section": "deliveries", "enrollments": page, "page_obj": page,
        "q": q, "state": state, "summary": summary,
    })


@_gate("municipal_events.view_enrollment")
def history_list(request):
    visible = _visible_enrollments(request.user)
    qs = CampaignAudit.objects.filter(enrollment__in=visible).select_related(
        "enrollment__campaign", "enrollment__beneficiary", "enrollment__delegation", "actor"
    )
    q = request.GET.get("q", "").strip()[:80]
    if q:
        qs = qs.filter(Q(enrollment__campaign__title__icontains=q) | Q(enrollment__beneficiary__name__icontains=q))
    page = Paginator(qs.order_by("-created_at"), 25).get_page(request.GET.get("page"))
    return render(request, "municipal_events/history.html", {
        "section": "history", "logs": page, "page_obj": page, "q": q,
    })


@_gate("municipal_events.view_municipalevent")
def event_list(request):
    all_events = MunicipalEvent.objects.all()
    q = request.GET.get("q", "").strip()[:80]
    events = all_events.prefetch_related("editions__delegation")
    if q:
        events = events.filter(Q(name__icontains=q) | Q(description__icontains=q))
    page = Paginator(events.order_by("name", "pk"), 20).get_page(request.GET.get("page"))
    return render(request, "municipal_events/events.html", {
        "events": page, "page_obj": page, "q": q, "section": "events",
        "event_total": all_events.count(),
        "edition_total": EventEdition.objects.count(), "year": timezone.localdate().year,
    })


@_gate("municipal_events.add_municipalevent")
def event_create(request):
    form = EventForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        item = form.save(commit=False)
        item.created_by = request.user
        item.save()
        return _saved(request, "Evento municipal creado.", "municipal_events:event_list")
    return _form_response(request, form, "Crear evento municipal", reverse("municipal_events:event_list"), "events")


@_gate("municipal_events.change_municipalevent")
def event_edit(request, pk):
    event = get_object_or_404(MunicipalEvent, pk=pk)
    form = EventForm(request.POST or None, instance=event)
    if request.method == "POST" and form.is_valid():
        form.save()
        return _saved(request, "Evento municipal actualizado.", "municipal_events:event_list")
    return _form_response(request, form, "Modificar evento municipal", reverse("municipal_events:event_list"), "events")


@_gate("municipal_events.add_eventedition")
def edition_create(request, event_id):
    event = get_object_or_404(MunicipalEvent, pk=event_id)
    form = EditionForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        item = form.save(commit=False)
        require_delegation(request.user, "municipal_events.add_eventedition", item.delegation_id)
        item.event = event
        item.responsible = request.user
        if EventEdition.objects.filter(event=event, year=item.year).exists():
            form.add_error("year", "Ya existe una edición de ese evento para el año seleccionado.")
        else:
            item.full_clean()
            try:
                item.save()
            except IntegrityError:
                form.add_error("year", "Ya existe una edición de ese evento para el año seleccionado.")
            else:
                return _saved(request, "Edición anual creada.", "municipal_events:event_list")
    return _form_response(request, form, f"Nueva edición de {event.name}", reverse("municipal_events:event_list"), "events")


@_gate("municipal_events.change_eventedition")
def edition_edit(request, pk):
    edition = get_object_or_404(EventEdition.objects.select_related("event"), pk=pk)
    require_delegation(request.user, "municipal_events.change_eventedition", edition.delegation_id)
    form = EditionForm(request.POST or None, instance=edition, user=request.user, permission="municipal_events.change_eventedition")
    from accounts.permissions import allowed_delegation_ids
    from organization.models import Delegation
    scope = allowed_delegation_ids(request.user, "municipal_events.change_eventedition")
    form.fields["delegation"].queryset = Delegation.objects.filter(pk__in=scope) if scope is not None else Delegation.objects.all()
    if request.method == "POST" and form.is_valid():
        item = form.save(commit=False)
        require_delegation(request.user, "municipal_events.change_eventedition", item.delegation_id)
        if EventEdition.objects.filter(event=edition.event, year=item.year).exclude(pk=item.pk).exists():
            form.add_error("year", "El evento ya tiene una edición para este año.")
        else:
            item.full_clean()
            try:
                item.save()
            except IntegrityError:
                form.add_error("year", "El evento ya tiene una edición para este año.")
            else:
                return _saved(request, "Edición actualizada sin perder las anteriores.", "municipal_events:event_list")
    return _form_response(request, form, f"Modificar edición: {edition.event.name}", reverse("municipal_events:event_list"), "events")


@_gate("municipal_events.view_campaign")
def campaign_list(request):
    campaigns = Campaign.objects.select_related("attention_type", "organizing_delegation", "edition")
    # El contador nunca incluye inscripciones ajenas a la delegación activa.
    can_view_enrollments = request.user.has_perm("municipal_events.view_enrollment")
    if can_view_enrollments:
        scope = allowed_delegation_ids(request.user, "municipal_events.view_enrollment", active_only=True)
        enrollment_filter = Q(enrollments__delegation_id__in=scope) if scope is not None else Q()
        campaigns = campaigns.annotate(n_enrollments=Count("enrollments", filter=enrollment_filter, distinct=True))
    q = request.GET.get("q", "").strip()[:80]
    if q:
        campaigns = campaigns.filter(Q(title__icontains=q) | Q(attention_type__name__icontains=q))
    campaigns = campaigns.order_by("-year", "title", "pk")
    page = Paginator(campaigns, 20).get_page(request.GET.get("page"))
    today = timezone.localdate()
    return render(request, "municipal_events/campaigns.html", {
        "campaigns": page, "page_obj": page, "q": q, "section": "campaigns",
        "can_view_enrollments": can_view_enrollments,
        "campaign_total": Campaign.objects.count(),
        "campaign_open": Campaign.objects.filter(status="OPEN", opens_on__lte=today, closes_on__gte=today).count(),
        "campaign_year": Campaign.objects.filter(year=today.year).count(),
    })


@_gate("municipal_events.add_campaign")
def campaign_create(request):
    form = CampaignForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        item = form.save(commit=False)
        require_delegation(request.user, "municipal_events.add_campaign", item.organizing_delegation_id)
        item.created_by = request.user
        item.full_clean()
        item.save()
        if _is_modal(request):
            return _saved(request, "Campaña municipal creada.", "municipal_events:campaign_list")
        messages.success(request, "Campaña municipal creada.")
        return redirect("municipal_events:campaign_detail", pk=item.pk)
    return _form_response(request, form, "Crear campaña municipal", reverse("municipal_events:campaign_list"), "campaigns")


@_gate("municipal_events.change_campaign")
def campaign_edit(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    require_delegation(request.user, "municipal_events.change_campaign", campaign.organizing_delegation_id)
    form = CampaignForm(request.POST or None, instance=campaign, user=request.user, permission="municipal_events.change_campaign")
    # El formulario de edición usa el mismo ámbito que el permiso de cambio.
    from accounts.permissions import allowed_delegation_ids
    from organization.models import Delegation
    scope = allowed_delegation_ids(request.user, "municipal_events.change_campaign")
    form.fields["organizing_delegation"].queryset = Delegation.objects.filter(pk__in=scope) if scope is not None else Delegation.objects.all()
    if request.method == "POST" and form.is_valid():
        item = form.save(commit=False)
        require_delegation(request.user, "municipal_events.change_campaign", item.organizing_delegation_id)
        item.full_clean()
        item.save()
        if _is_modal(request):
            return _saved(request, "Campaña actualizada.", "municipal_events:campaign_list")
        messages.success(request, "Campaña actualizada.")
        return redirect("municipal_events:campaign_detail", pk=pk)
    return _form_response(request, form, "Modificar campaña", reverse("municipal_events:campaign_list"), "campaigns")


@_gate("municipal_events.view_campaign")
def campaign_detail(request, pk):
    campaign = get_object_or_404(Campaign.objects.select_related("attention_type", "edition", "organizing_delegation"), pk=pk)
    # Los datos personales solo pueden consultarlos los roles que administran inscripciones.
    can_view_enrollments = request.user.has_perm("municipal_events.view_enrollment")
    enrollments = []
    page_obj = None
    q = request.GET.get("q", "").strip()[:80]
    if can_view_enrollments:
        qs = Enrollment.objects.filter(campaign=campaign).select_related("beneficiary", "attention", "delegation", "reviewed_by", "delivery").prefetch_related("history").order_by("-created_at")
        from accounts.permissions import allowed_delegation_ids
        scope = allowed_delegation_ids(request.user, "municipal_events.view_enrollment", active_only=True)
        if scope is not None:
            qs = qs.filter(delegation_id__in=scope)
        if q:
            qs = qs.filter(beneficiary__name__icontains=q)
        page_obj = Paginator(qs, 25).get_page(request.GET.get("page"))
        enrollments = page_obj
    if _is_modal(request):
        return render(request, "municipal_events/_detail_campaign.html", {"campaign": campaign, "section": "campaigns"})
    return render(request, "municipal_events/campaign_detail.html", {"campaign": campaign, "enrollments": enrollments, "page_obj": page_obj, "q": q, "can_view_enrollments": can_view_enrollments, "section": "campaigns"})


@_gate("registration_validation.view_attentionentry")
def campaigns_for_attention(request, attention_id):
    attention = get_object_or_404(AttentionEntry.objects.select_related("attention_type", "delegation"), pk=attention_id, deleted_at__isnull=True)
    require_delegation(request.user, "registration_validation.view_attentionentry", attention.delegation_id)
    campaigns = [c for c in campaign_active_queryset().filter(attention_type_id=attention.attention_type_id).order_by("title") if can_register_from_attention(request.user, attention, c)]
    if not campaigns:
        messages.info(request, "No hay campañas abiertas o autorizadas para este tipo de atención.")
        return redirect("registration:attention_entry_list")
    return render(request, "municipal_events/campaign_picker.html", {"attention": attention, "campaigns": campaigns, "section": "enrollments"})


@_gate("municipal_events.add_enrollment")
def enrollment_create(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    attention_id = request.GET.get("attention") if request.method == "GET" else request.POST.get("attention")
    attention = get_object_or_404(AttentionEntry, pk=attention_id, deleted_at__isnull=True)
    if not can_register_from_attention(request.user, attention, campaign):
        raise PermissionDenied("La campaña, el tipo de atención o la delegación no permiten esta inscripción.")
    form = EnrollmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        rut = data["rut"]
        if Enrollment.objects.filter(campaign=campaign, beneficiary__rut=rut).exists():
            form.add_error("rut", "El beneficiario ya está inscrito en esta campaña (incluidas otras delegaciones).")
        else:
            try:
                with transaction.atomic():
                    beneficiary, created = Beneficiary.objects.get_or_create(rut=rut, defaults={"name": data["name"], "birth_date": data["birth_date"]})
                    if not created and beneficiary.birth_date != data["birth_date"]:
                        raise ValueError("Los datos del beneficiario no coinciden con un registro existente. Solicita una revisión autorizada.")
                    enrollment = Enrollment(campaign=campaign, beneficiary=beneficiary, attention=attention, delegation=attention.delegation, observation=data["observation"], created_by=request.user)
                    enrollment.full_clean()
                    enrollment.save()
                    CampaignAudit.objects.create(enrollment=enrollment, action="INSCRITA", actor=request.user, reason="Inscripción registrada desde atención")
            except (IntegrityError, ValueError) as exc:
                # El conflicto puede ser concurrente: no revelar datos de otras delegaciones.
                if isinstance(exc, IntegrityError):
                    form.add_error("rut", "El beneficiario ya está inscrito en esta campaña o existe un registro concurrente. Revisa la bandeja.")
                else:
                    form.add_error("rut", str(exc))
            else:
                messages.success(request, "Beneficiario inscrito. La entrega requiere aprobación posterior.")
                return redirect("municipal_events:campaign_detail", pk=pk)
    return render(request, "municipal_events/enroll_form.html", {"form": form, "campaign": campaign, "attention": attention, "section": "enrollments"})


@_gate("municipal_events.change_enrollment")
def enrollment_review(request, pk):
    enrollment = get_object_or_404(Enrollment.objects.select_related("campaign", "delegation"), pk=pk)
    require_delegation(request.user, "municipal_events.change_enrollment", enrollment.delegation_id)
    form = ReviewForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            enrollment = Enrollment.objects.select_for_update().get(pk=pk)
            if GiftDelivery.objects.filter(enrollment=enrollment).exists():
                raise PermissionDenied("No se puede cambiar una inscripción con entrega registrada.")
            enrollment.status = form.cleaned_data["status"]
            enrollment.reviewed_by = request.user
            enrollment.reviewed_at = timezone.now()
            enrollment.save(update_fields=["status", "reviewed_by", "reviewed_at"])
            CampaignAudit.objects.create(enrollment=enrollment, action=enrollment.status, actor=request.user, reason=form.cleaned_data["reason"])
        if _is_modal(request):
            return _saved(request, "Decisión registrada en el historial.", "municipal_events:enrollment_list")
        messages.success(request, "Decisión registrada en el historial.")
        return redirect("municipal_events:campaign_detail", pk=enrollment.campaign_id)
    return _form_response(request, form, "Evaluar inscripción", reverse("municipal_events:enrollment_list"), "enrollments", note=f"Inscripción #{enrollment.pk} · {enrollment.campaign.title}")


@_gate("municipal_events.add_giftdelivery")
def delivery_create(request, pk):
    enrollment = get_object_or_404(Enrollment.objects.select_related("campaign", "delegation"), pk=pk)
    require_delegation(request.user, "municipal_events.add_giftdelivery", enrollment.delegation_id)
    if enrollment.status != "APPROVED" or GiftDelivery.objects.filter(enrollment=enrollment).exists():
        raise PermissionDenied("Debe estar aprobada y sin entrega previa.")
    form = DeliveryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                locked = Enrollment.objects.select_for_update().get(pk=pk)
                if locked.status != "APPROVED" or GiftDelivery.objects.filter(enrollment=locked).exists():
                    raise PermissionDenied("La inscripción no está disponible para una nueva entrega.")
                delivery = form.save(commit=False)
                delivery.enrollment = locked
                delivery.delivered_by = request.user
                delivery.full_clean()
                delivery.save()
                CampaignAudit.objects.create(enrollment=locked, action="ENTREGADO", actor=request.user, reason=delivery.notes)
        except IntegrityError:
            messages.error(request, "Ya existe una entrega para esta inscripción.")
            return redirect("municipal_events:campaign_detail", pk=enrollment.campaign_id)
        if _is_modal(request):
            return _saved(request, "Entrega registrada con fecha, funcionario e historial.", "municipal_events:delivery_list")
        messages.success(request, "Entrega registrada con fecha, funcionario e historial.")
        return redirect("municipal_events:campaign_detail", pk=enrollment.campaign_id)
    return _form_response(request, form, "Registrar entrega de regalo", reverse("municipal_events:delivery_list"), "deliveries", note=f"Beneficiario: {enrollment.beneficiary.name} · Campaña: {enrollment.campaign.title}")


@_gate("municipal_events.view_municipalevent")
def event_detail(request, pk):
    event = get_object_or_404(MunicipalEvent, pk=pk)
    return _modal_detail(request, "municipal_events/_detail_event.html", {"event": event, "section": "events"})


@_gate("municipal_events.view_municipalevent")
def edition_detail(request, pk):
    edition = get_object_or_404(EventEdition.objects.select_related("event", "delegation"), pk=pk)
    return _modal_detail(request, "municipal_events/_detail_edition.html", {"edition": edition, "section": "events"})


@_gate("municipal_events.view_enrollment")
def enrollment_detail(request, pk):
    enrollment = get_object_or_404(_visible_enrollments(request.user).select_related(
        "beneficiary", "campaign", "delegation", "attention", "reviewed_by", "delivery"), pk=pk)
    history = enrollment.history.select_related("actor").order_by("created_at")
    return _modal_detail(request, "municipal_events/_detail_enrollment.html", {
        "item": enrollment, "history": history, "section": "enrollments",
    })


@_gate("municipal_events.view_giftdelivery")
@_gate("municipal_events.view_enrollment")
def delivery_detail(request, pk):
    enrollment = get_object_or_404(_visible_enrollments(request.user).select_related(
        "beneficiary", "campaign", "delegation", "delivery__delivered_by"), pk=pk,
        delivery__isnull=False)
    return _modal_detail(request, "municipal_events/_detail_delivery.html", {
        "item": enrollment, "section": "deliveries",
    })


def _delete_request(request, obj, permission, *, used, name, return_to):
    # La autorización no depende de que el botón esté visible.
    if not request.user.has_perm(permission):
        raise PermissionDenied("No tienes permiso para eliminar este registro.")
    if request.method not in ("GET", "POST"):
        return HttpResponseNotAllowed(["GET", "POST"])
    if request.method == "POST":
        if used():
            error = "No se puede eliminar: tiene registros vinculados que deben conservarse."
        else:
            try:
                obj.delete()
            except ProtectedError:
                error = "No se puede eliminar: existen registros protegidos."
            else:
                return _saved(request, f"{name} eliminado correctamente.", return_to)
        if _is_modal(request):
            return render(request, "municipal_events/_modal_confirm.html", {
                "title": f"Eliminar {name.lower()}", "object_label": str(obj),
                "error": error,
            }, status=409)
        messages.error(request, error)
        return redirect(return_to)
    if used():
        message = "Este registro tiene información vinculada y no se puede eliminar."
    else:
        message = None
    if _is_modal(request):
        return render(request, "municipal_events/_modal_confirm.html", {
            "title": f"Eliminar {name.lower()}", "object_label": str(obj),
            "blocked": message,
        })
    return render(request, "municipal_events/delete_confirm.html", {
        "title": f"Eliminar {name.lower()}", "object_label": str(obj),
        "blocked": message, "cancel_url": reverse(return_to), "section": "campaigns" if isinstance(obj, Campaign) else "events",
    })


@_gate("municipal_events.delete_municipalevent")
def event_delete(request, pk):
    obj = get_object_or_404(MunicipalEvent, pk=pk)
    return _delete_request(request, obj, "municipal_events.delete_municipalevent",
                           used=lambda: obj.editions.exists(), name="Evento municipal",
                           return_to="municipal_events:event_list")


@_gate("municipal_events.delete_eventedition")
def edition_delete(request, pk):
    obj = get_object_or_404(EventEdition, pk=pk)
    require_delegation(request.user, "municipal_events.delete_eventedition", obj.delegation_id)
    return _delete_request(request, obj, "municipal_events.delete_eventedition",
                           used=lambda: obj.campaigns.exists(), name="Edición anual",
                           return_to="municipal_events:event_list")


@_gate("municipal_events.delete_campaign")
def campaign_delete(request, pk):
    obj = get_object_or_404(Campaign, pk=pk)
    require_delegation(request.user, "municipal_events.delete_campaign", obj.organizing_delegation_id)
    return _delete_request(request, obj, "municipal_events.delete_campaign",
                           used=lambda: obj.enrollments.exists(), name="Campaña municipal",
                           return_to="municipal_events:campaign_list")
