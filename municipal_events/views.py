# SGR_PERMISOS_EVENTOS_V2
"""Vistas con permisos de Django y alcance territorial comprobados en servidor."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.db.models import Count, Q
from django.core.paginator import Paginator
from django.http import HttpResponseNotAllowed, JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from registration_validation.models import AttentionEntry

from .forms import (CampaignForm, DeliveryForm, EditionForm, EnrollmentForm, EventForm, ReviewForm,
                    EventParticipationForm, EventParticipationReviewForm, EventParticipationEditForm)
from .models import (Beneficiary, Campaign, CampaignAudit, Enrollment, EventEdition, GiftDelivery, MunicipalEvent,
                     EventParticipation, EventActionAudit)
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


def _audit_changes(target, actor, relation, action, changes):
    if not changes:
        return
    details = "; ".join(
        f"{label}: «{old}» → «{new}»"
        for label, old, new in changes
    )
    EventActionAudit.objects.create(
        **{relation: target},
        actor=actor,
        action=action,
        reason=details,
    )


def _display_value(value):
    return str(value) if value not in (None, "") else "vacío"


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


def _campaign_options_for_user(user):
    """Solo campañas con inscripciones visibles en la delegación autorizada."""
    visible = _visible_enrollments(user)
    return Campaign.objects.filter(pk__in=visible.values("campaign_id")).order_by("-year", "title", "pk")


def _selected_campaign(request):
    """No aceptar IDs arbitrarios ni filtrar fuera del alcance de inscripciones."""
    raw = request.GET.get("campaign", "").strip()[:12]
    return int(raw) if raw.isdecimal() and int(raw) > 0 else None


@_gate("municipal_events.view_enrollment")
def enrollment_list(request):
    record_state = request.GET.get("record_state", "active")
    if record_state not in ("active", "inactive", "all"):
        record_state = "active"
    campaign_id = _selected_campaign(request)  # SGR_CAMPAIGN_UNIFIED_V1
    campaign_options = _campaign_options_for_user(request.user)
    qs = _visible_enrollments(request.user)
    if campaign_id is not None:
        qs = qs.filter(campaign_id=campaign_id)
    if record_state == "active":
        qs = qs.filter(deleted_at__isnull=True)
    elif record_state == "inactive":
        qs = qs.filter(deleted_at__isnull=False)
    qs = qs.select_related("beneficiary", "campaign", "delegation", "delivery")
    q = request.GET.get("q", "").strip()[:80]
    state = request.GET.get("status", "")
    if q:
        qs = qs.filter(Q(beneficiary__name__icontains=q) | Q(campaign__title__icontains=q))
    if state in dict(Enrollment.STATUS):
        qs = qs.filter(status=state)
    else:
        state = ""
    total = qs.count()
    base = _visible_enrollments(request.user).filter(deleted_at__isnull=True)
    if campaign_id is not None:
        base = base.filter(campaign_id=campaign_id)
    summary = {"all": base.count(), "pending": base.filter(status="PENDING").count(),
               "delivered": GiftDelivery.objects.filter(enrollment__in=base).count()}
    page = Paginator(qs.order_by("-created_at"), 20).get_page(request.GET.get("page"))
    return render(request, "municipal_events/enrollments.html", {
        "section": "enrollments", "enrollments": page, "page_obj": page,
        "q": q, "status": state, "record_state": record_state,
        "campaign_id": campaign_id or "", "campaign_options": campaign_options,
        "total": total, "summary": summary,
    })


@_gate("municipal_events.view_giftdelivery")
@_gate("municipal_events.view_enrollment")
def delivery_list(request):
    campaign_id = _selected_campaign(request)
    campaign_options = _campaign_options_for_user(request.user)
    qs = _visible_enrollments(request.user).filter(status="APPROVED", deleted_at__isnull=True).select_related(
        "beneficiary", "campaign", "delegation", "delivery"
    )
    q = request.GET.get("q", "").strip()[:80]
    state = request.GET.get("state", "")
    if campaign_id is not None:
        qs = qs.filter(campaign_id=campaign_id)
    if q:
        qs = qs.filter(Q(beneficiary__name__icontains=q) | Q(campaign__title__icontains=q))
    if state == "pending":
        qs = qs.filter(delivery__isnull=True)
    elif state == "delivered":
        qs = qs.filter(delivery__isnull=False)
    else:
        state = ""
    base = _visible_enrollments(request.user).filter(status="APPROVED", deleted_at__isnull=True)
    if campaign_id is not None:
        base = base.filter(campaign_id=campaign_id)
    summary = {"approved": base.count(), "delivered": base.filter(delivery__isnull=False).count(),
               "pending": base.filter(delivery__isnull=True).count()}
    page = Paginator(qs.order_by("-created_at"), 20).get_page(request.GET.get("page"))
    return render(request, "municipal_events/deliveries.html", {
        "section": "deliveries", "enrollments": page, "page_obj": page,
        "q": q, "state": state, "summary": summary,
        "campaign_id": campaign_id or "", "campaign_options": campaign_options,
    })


@_gate("municipal_events.view_enrollment")
def history_list(request):
    campaign_id = _selected_campaign(request)
    campaign_options = _campaign_options_for_user(request.user)
    visible = _visible_enrollments(request.user)
    if campaign_id is not None:
        visible = visible.filter(campaign_id=campaign_id)
    qs = CampaignAudit.objects.filter(enrollment__in=visible).select_related(
        "enrollment__campaign", "enrollment__beneficiary", "enrollment__delegation", "actor"
    )
    q = request.GET.get("q", "").strip()[:80]
    if q:
        qs = qs.filter(Q(enrollment__campaign__title__icontains=q) | Q(enrollment__beneficiary__name__icontains=q))
    page = Paginator(qs.order_by("-created_at"), 25).get_page(request.GET.get("page"))
    return render(request, "municipal_events/history.html", {
        "section": "history", "logs": page, "page_obj": page, "q": q,
        "campaign_id": campaign_id or "", "campaign_options": campaign_options,
    })


@_gate("municipal_events.view_municipalevent")
def event_list(request):
    record_state = request.GET.get("record_state", "active")
    if record_state not in ("active", "inactive", "all"):
        record_state = "active"
    all_events = MunicipalEvent.objects.all()
    filtered = all_events
    if record_state == "active":
        filtered = filtered.filter(deleted_at__isnull=True)
    elif record_state == "inactive":
        filtered = filtered.filter(deleted_at__isnull=False)
    q = request.GET.get("q", "").strip()[:80]
    events = filtered.prefetch_related("editions__delegation")
    if q:
        events = events.filter(Q(name__icontains=q) | Q(description__icontains=q))
    page = Paginator(events.order_by("name", "pk"), 20).get_page(request.GET.get("page"))
    return render(request, "municipal_events/events.html", {
        "events": page, "page_obj": page, "q": q, "record_state": record_state, "section": "events",
        "event_total": all_events.filter(deleted_at__isnull=True).count(),
        "edition_total": EventEdition.objects.filter(deleted_at__isnull=True).count(), "year": timezone.localdate().year,
    })


@_gate("municipal_events.add_municipalevent")
def event_create(request):
    form = EventForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            item = form.save(commit=False)
            item.created_by = request.user
            item.full_clean()
            item.save()
            _audit_changes(
                item, request.user, "event", "CREADO",
                [("Registro", "—", item.name)],
            )
        return _saved(request, "Evento municipal creado.", "municipal_events:event_list")
    return _form_response(request, form, "Crear evento municipal", reverse("municipal_events:event_list"), "events")


@_gate("municipal_events.change_municipalevent")
def event_edit(request, pk):
    event = get_object_or_404(MunicipalEvent, pk=pk, deleted_at__isnull=True)
    form = EventForm(request.POST or None, instance=event)
    if request.method == "POST" and form.is_valid():
        original = MunicipalEvent.objects.get(pk=event.pk)
        changes = [
            ("Nombre", original.name, form.cleaned_data["name"]),
            ("Descripción", _display_value(original.description),
             _display_value(form.cleaned_data["description"])),
        ]
        changes = [change for change in changes if change[1] != change[2]]
        with transaction.atomic():
            item = MunicipalEvent.objects.select_for_update().get(pk=event.pk)
            item.name = form.cleaned_data["name"]
            item.description = form.cleaned_data["description"]
            item.full_clean()
            item.save(update_fields=["name", "description"])
            _audit_changes(item, request.user, "event", "MODIFICADO", changes)
        return _saved(request, "Evento municipal actualizado.", "municipal_events:event_list")
    return _form_response(request, form, "Modificar evento municipal", reverse("municipal_events:event_list"), "events")


@_gate("municipal_events.add_eventedition")
def edition_create(request, event_id):
    event = get_object_or_404(MunicipalEvent, pk=event_id, deleted_at__isnull=True)
    form = EditionForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
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
                    _audit_changes(
                        item, request.user, "edition", "CREADO",
                        [("Registro", "—", f"{item.year} · {item.place}")],
                    )
                    return _saved(request, "Edición anual creada.", "municipal_events:event_list")
    return _form_response(request, form, f"Nueva edición de {event.name}", reverse("municipal_events:event_list"), "events")


@_gate("municipal_events.change_eventedition")
def edition_edit(request, pk):
    edition = get_object_or_404(EventEdition.objects.select_related("event"), pk=pk,
                                deleted_at__isnull=True, event__deleted_at__isnull=True)
    require_delegation(request.user, "municipal_events.change_eventedition", edition.delegation_id)
    form = EditionForm(request.POST or None, instance=edition, user=request.user, permission="municipal_events.change_eventedition")
    from accounts.permissions import allowed_delegation_ids
    from organization.models import Delegation
    scope = allowed_delegation_ids(request.user, "municipal_events.change_eventedition")
    form.fields["delegation"].queryset = Delegation.objects.filter(pk__in=scope) if scope is not None else Delegation.objects.all()
    if request.method == "POST" and form.is_valid():
        original = EventEdition.objects.get(pk=edition.pk)
        fields = (
            ("Año", "year", "year"), ("Fecha", "date", "date"),
            ("Lugar", "place", "place"),
            ("Delegación", "delegation_id", "delegation"),
            ("Estado", "status", "status"),
            ("Modalidad", "participation_mode", "participation_mode"),
            ("Cupos", "participation_capacity", "participation_capacity"),
            ("Requisitos", "participation_requirements", "participation_requirements"),
            ("Observaciones", "notes", "notes"),
        )
        changes = [
            (label, _display_value(getattr(original, name)),
             _display_value(
                 form.cleaned_data[key].pk
                 if hasattr(form.cleaned_data[key], "pk")
                 else form.cleaned_data[key]
             ))
            for label, name, key in fields
            if getattr(original, name) != (
                form.cleaned_data[key].pk
                if hasattr(form.cleaned_data[key], "pk")
                else form.cleaned_data[key]
            )
        ]
        with transaction.atomic():
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
                    _audit_changes(item, request.user, "edition", "MODIFICADO", changes)
                    return _saved(request, "Edición actualizada sin perder las anteriores.", "municipal_events:event_list")
    return _form_response(request, form, f"Modificar edición: {edition.event.name}", reverse("municipal_events:event_list"), "events")


@_gate("municipal_events.view_campaign")
def campaign_list(request):
    record_state = request.GET.get("record_state", "active")
    if record_state not in ("active", "inactive", "all"):
        record_state = "active"
    campaigns = Campaign.objects.select_related("attention_type", "organizing_delegation", "edition")
    if record_state == "active":
        campaigns = campaigns.filter(deleted_at__isnull=True)
    elif record_state == "inactive":
        campaigns = campaigns.filter(deleted_at__isnull=False)
    # El contador nunca incluye inscripciones ajenas a la delegación activa.
    can_view_enrollments = request.user.has_perm("municipal_events.view_enrollment")
    if can_view_enrollments:
        scope = allowed_delegation_ids(request.user, "municipal_events.view_enrollment", active_only=True)
        enrollment_filter = Q(enrollments__deleted_at__isnull=True)
        if scope is not None:
            enrollment_filter &= Q(enrollments__delegation_id__in=scope)
        campaigns = campaigns.annotate(n_enrollments=Count("enrollments", filter=enrollment_filter, distinct=True))
    q = request.GET.get("q", "").strip()[:80]
    if q:
        campaigns = campaigns.filter(Q(title__icontains=q) | Q(attention_type__name__icontains=q))
    campaigns = campaigns.order_by("-year", "title", "pk")
    page = Paginator(campaigns, 20).get_page(request.GET.get("page"))
    today = timezone.localdate()
    return render(request, "municipal_events/campaigns.html", {
        "campaigns": page, "page_obj": page, "q": q, "record_state": record_state,
        "section": "campaigns",
        "can_view_enrollments": can_view_enrollments,
        "campaign_total": Campaign.objects.filter(deleted_at__isnull=True).count(),
        "campaign_open": Campaign.objects.filter(deleted_at__isnull=True, status="OPEN",
                           opens_on__lte=today, closes_on__gte=today).count(),
        "campaign_year": Campaign.objects.filter(deleted_at__isnull=True, year=today.year).count(),
    })


@_gate("municipal_events.add_campaign")
def campaign_create(request):
    form = CampaignForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            item = form.save(commit=False)
            require_delegation(request.user, "municipal_events.add_campaign", item.organizing_delegation_id)
            item.created_by = request.user
            item.full_clean()
            item.save()
            _audit_changes(
                item, request.user, "campaign", "CREADO",
                [("Registro", "—", item.title)],
            )
        if _is_modal(request):
            return _saved(request, "Campaña municipal creada.", "municipal_events:campaign_list")
        messages.success(request, "Campaña municipal creada.")
        return redirect("municipal_events:campaign_detail", pk=item.pk)
    return _form_response(request, form, "Crear campaña municipal", reverse("municipal_events:campaign_list"), "campaigns")


@_gate("municipal_events.change_campaign")
def campaign_edit(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk, deleted_at__isnull=True)
    require_delegation(request.user, "municipal_events.change_campaign", campaign.organizing_delegation_id)
    form = CampaignForm(request.POST or None, instance=campaign, user=request.user, permission="municipal_events.change_campaign")
    # El formulario de edición usa el mismo ámbito que el permiso de cambio.
    from accounts.permissions import allowed_delegation_ids
    from organization.models import Delegation
    scope = allowed_delegation_ids(request.user, "municipal_events.change_campaign")
    form.fields["organizing_delegation"].queryset = Delegation.objects.filter(pk__in=scope) if scope is not None else Delegation.objects.all()
    if request.method == "POST" and form.is_valid():
        original = Campaign.objects.get(pk=campaign.pk)
        fields = (
            ("Nombre", "title", "title"), ("Año", "year", "year"),
            ("Descripción", "description", "description"),
            ("Tipo de atención", "attention_type_id", "attention_type"),
            ("Edición", "edition_id", "edition"),
            ("Delegación", "organizing_delegation_id", "organizing_delegation"),
            ("Inicio", "opens_on", "opens_on"), ("Fin", "closes_on", "closes_on"),
            ("Edad máxima", "max_age", "max_age"), ("Estado", "status", "status"),
        )
        changes = [
            (label, _display_value(getattr(original, name)),
             _display_value(
                 form.cleaned_data[key].pk
                 if hasattr(form.cleaned_data[key], "pk")
                 else form.cleaned_data[key]
             ))
            for label, name, key in fields
            if getattr(original, name) != (
                form.cleaned_data[key].pk
                if hasattr(form.cleaned_data[key], "pk")
                else form.cleaned_data[key]
            )
        ]
        with transaction.atomic():
            item = form.save(commit=False)
            require_delegation(request.user, "municipal_events.change_campaign", item.organizing_delegation_id)
            item.full_clean()
            item.save()
            _audit_changes(item, request.user, "campaign", "MODIFICADO", changes)
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
        qs = Enrollment.objects.filter(campaign=campaign, deleted_at__isnull=True).select_related("beneficiary", "attention", "delegation", "reviewed_by", "delivery").prefetch_related("history").order_by("-created_at")
        from accounts.permissions import allowed_delegation_ids
        scope = allowed_delegation_ids(request.user, "municipal_events.view_enrollment", active_only=True)
        if scope is not None:
            qs = qs.filter(delegation_id__in=scope)
        if q:
            qs = qs.filter(beneficiary__name__icontains=q)
        page_obj = Paginator(qs, 25).get_page(request.GET.get("page"))
        enrollments = page_obj
    # Mostrar una sola vez la inscripción recién creada, únicamente si es visible
    # para la delegación y el permiso del funcionario.
    highlight = None  # SGR_CONFIRMACION_INSCRIPCION_UNICA_V1
    recent = request.session.pop("sgr_ultima_inscripcion_creada", None)
    if (can_view_enrollments and page_obj is not None
            and isinstance(recent, dict)
            and recent.get("campaign_id") == campaign.pk
            and isinstance(recent.get("enrollment_id"), int)):
        recent_id = recent["enrollment_id"]
        if any(row.pk == recent_id for row in page_obj.object_list):
            highlight = recent_id
    if _is_modal(request):
        return render(request, "municipal_events/_detail_campaign.html", {
            "campaign": campaign, "section": "campaigns",
            "audit_history": EventActionAudit.objects.filter(campaign=campaign).select_related("actor")[:20],
        })
    return render(request, "municipal_events/campaign_detail.html", {"campaign": campaign, "enrollments": enrollments, "page_obj": page_obj, "q": q, "can_view_enrollments": can_view_enrollments, "section": "campaigns",
        "sgr_recien_inscrito_id": highlight})


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
    campaign = get_object_or_404(
        Campaign.objects.select_related("attention_type", "edition__event"),
        pk=pk, deleted_at__isnull=True,
    )
    attention_id = request.GET.get("attention") if request.method == "GET" else request.POST.get("attention")
    attention = get_object_or_404(AttentionEntry, pk=attention_id, deleted_at__isnull=True)
    if not can_register_from_attention(request.user, attention, campaign):
        raise PermissionDenied("La campaña, el tipo de atención o la delegación no permiten esta inscripción.")
    form = EnrollmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        rut = data["rut"]
        try:
            with transaction.atomic():
                    locked_campaign = Campaign.objects.select_for_update().select_related(
                        "attention_type", "edition__event"
                    ).get(pk=campaign.pk)
                    if not can_register_from_attention(
                        request.user, attention, locked_campaign
                    ):
                        raise PermissionDenied(
                            "La campaña, el tipo de atención o la delegación "
                            "no permiten esta inscripción."
                        )
                    prior = Enrollment.objects.filter(
                        campaign=locked_campaign, beneficiary__rut=rut
                    ).first()
                    if prior:
                        if prior.deleted_at is not None:
                            raise ValueError(
                                "El beneficiario ya está inscrito en esta campaña, "
                                "pero la inscripción está desactivada. Solicita "
                                "su reactivación a personal autorizado."
                            )
                        raise ValueError(
                            "El beneficiario ya está inscrito en esta campaña "
                            "(incluidas otras delegaciones)."
                        )
                    beneficiary, created = Beneficiary.objects.get_or_create(rut=rut, defaults={"name": data["name"], "birth_date": data["birth_date"], "sex": data["sex"]})
                    if not created and beneficiary.birth_date != data["birth_date"]:
                        raise ValueError("Los datos del beneficiario no coinciden con un registro existente. Solicita una revisión autorizada.")
                    if not created:
                        if beneficiary.sex and beneficiary.sex != data["sex"]:
                            raise ValueError("Los datos del beneficiario no coinciden con el registro existente. Solicita revisión autorizada.")
                        if not beneficiary.sex:
                            beneficiary.sex = data["sex"]
                            beneficiary.save(update_fields=["sex"])
                    enrollment = Enrollment(campaign=locked_campaign, beneficiary=beneficiary, attention=attention, delegation=attention.delegation, observation=data["observation"], created_by=request.user)
                    enrollment.full_clean()
                    enrollment.save()
                    CampaignAudit.objects.create(enrollment=enrollment, action="INSCRITA", actor=request.user, reason="Inscripción registrada desde atención")
        except (IntegrityError, ValueError, ValidationError) as exc:
            if isinstance(exc, IntegrityError):
                message = (
                    "El beneficiario ya está inscrito en esta campaña o existe "
                    "un registro concurrente. Revisa la bandeja."
                )
                form.add_error("rut", message)
            elif isinstance(exc, ValidationError):
                for message in exc.messages:
                    form.add_error(None, message)
            else:
                form.add_error("rut", str(exc))
        else:
            request.session["sgr_ultima_inscripcion_creada"] = {
                "campaign_id": campaign.pk, "enrollment_id": enrollment.pk,
            }
            messages.success(
                request,
                f"Inscripción registrada correctamente: {beneficiary.name} en "
                f"{campaign.title} ({campaign.year}). Pendiente de evaluación; "
                "no se ha registrado una entrega.",
            )
            return redirect("municipal_events:campaign_detail", pk=pk)
    return render(request, "municipal_events/enroll_form.html", {"form": form, "campaign": campaign, "attention": attention, "section": "enrollments"})


@_gate("municipal_events.change_enrollment")
def enrollment_deactivate(request, pk):
    enrollment = get_object_or_404(Enrollment.objects.select_related("delegation", "campaign", "beneficiary"), pk=pk)
    require_delegation(request.user, "municipal_events.change_enrollment", enrollment.delegation_id)
    if request.method not in ("GET", "POST"):
        return HttpResponseNotAllowed(["GET", "POST"])
    delivered = GiftDelivery.objects.filter(enrollment_id=pk).exists()
    if request.method == "POST":
        reason = request.POST.get("reason", "").strip()[:500]
        if not reason:
            return HttpResponse("Indica el motivo de la desactivación.", status=400)
        with transaction.atomic():
            item = Enrollment.objects.select_for_update().get(pk=pk)
            if item.deleted_at is not None:
                return _saved(request, "La inscripción ya estaba desactivada.", "municipal_events:enrollment_list")
            if GiftDelivery.objects.filter(enrollment_id=pk).exists():
                raise PermissionDenied("No se puede desactivar una inscripción con regalo entregado.")
            item.deleted_at = timezone.now()
            item.save(update_fields=["deleted_at"])
            CampaignAudit.objects.create(enrollment=item, actor=request.user, action="DESACTIVADA", reason=reason)
        return _saved(request, "Inscripción desactivada sin borrar su historial.", "municipal_events:enrollment_list")
    return _modal_detail(request, "municipal_events/_confirm_enrollment_state.html", {
        "item": enrollment, "action_label": "Desactivar inscripción", "action_icon": "bi-archive",
        "blocked": "No se puede desactivar: el regalo ya fue entregado." if delivered else "",
        "note": "El beneficiario seguirá registrado. Podrás reactivar la misma inscripción después.",
        "section": "enrollments",
    })


@_gate("municipal_events.change_enrollment")
def enrollment_reactivate(request, pk):
    enrollment = get_object_or_404(Enrollment.objects.select_related("delegation", "campaign", "beneficiary"), pk=pk)
    require_delegation(request.user, "municipal_events.change_enrollment", enrollment.delegation_id)
    if enrollment.campaign.deleted_at is not None or (
        enrollment.campaign.edition_id and (
            enrollment.campaign.edition.deleted_at is not None or
            enrollment.campaign.edition.event.deleted_at is not None
        )
    ):
        raise PermissionDenied("Reactiva primero la campaña y su evento para recuperar inscripciones.")
    if request.method not in ("GET", "POST"):
        return HttpResponseNotAllowed(["GET", "POST"])
    if request.method == "POST":
        reason = request.POST.get("reason", "").strip()[:500]
        if not reason:
            return HttpResponse("Indica el motivo de la reactivación.", status=400)
        with transaction.atomic():
            item = Enrollment.objects.select_for_update().get(pk=pk)
            if item.deleted_at is None:
                return _saved(request, "La inscripción ya estaba activa.", "municipal_events:enrollment_list")
            if GiftDelivery.objects.filter(enrollment_id=pk).exists():
                raise PermissionDenied("Inconsistencia histórica: una inscripción desactivada tiene entrega asociada.")
            if item.campaign.deleted_at is not None or (
                item.campaign.edition_id and (
                    item.campaign.edition.deleted_at is not None or
                    item.campaign.edition.event.deleted_at is not None
                )
            ):
                raise PermissionDenied("Reactiva primero la campaña y su edición.")
            # La reactivación preserva campaña, beneficiario, atención, estado e historial.
            item.deleted_at = None
            item.save(update_fields=["deleted_at"])
            CampaignAudit.objects.create(enrollment=item, actor=request.user, action="REACTIVADA", reason=reason)
        return _saved(request, "Inscripción original reactivada, sin duplicar el RUT.", "municipal_events:enrollment_list")
    return _modal_detail(request, "municipal_events/_confirm_enrollment_state.html", {
        "item": enrollment, "action_label": "Reactivar inscripción", "action_icon": "bi-arrow-counterclockwise",
        "blocked": "Esta inscripción ya se encuentra activa." if enrollment.deleted_at is None else "",
        "note": "Se recuperará la inscripción original y todo su historial.",
        "section": "enrollments",
    })


@_gate("municipal_events.change_enrollment")
def enrollment_review(request, pk):
    enrollment = get_object_or_404(Enrollment.objects.select_related("campaign", "delegation"), pk=pk,
                                   deleted_at__isnull=True, campaign__deleted_at__isnull=True)
    require_delegation(request.user, "municipal_events.change_enrollment", enrollment.delegation_id)
    form = ReviewForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            enrollment = Enrollment.objects.select_for_update().get(pk=pk)
            if enrollment.deleted_at is not None:
                raise PermissionDenied("La inscripción está desactivada.")
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
    enrollment = get_object_or_404(Enrollment.objects.select_related("campaign", "delegation"), pk=pk,
                                   deleted_at__isnull=True, campaign__deleted_at__isnull=True)
    require_delegation(request.user, "municipal_events.add_giftdelivery", enrollment.delegation_id)
    if enrollment.status != "APPROVED" or GiftDelivery.objects.filter(enrollment=enrollment).exists():
        raise PermissionDenied("Debe estar aprobada y sin entrega previa.")
    form = DeliveryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                locked = Enrollment.objects.select_for_update().get(pk=pk)
                if locked.deleted_at is not None or locked.status != "APPROVED" or GiftDelivery.objects.filter(enrollment=locked).exists():
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
    return _modal_detail(request, "municipal_events/_detail_event.html", {
        "event": event, "section": "events",
        "audit_history": EventActionAudit.objects.filter(event=event).select_related("actor")[:20],
    })


@_gate("municipal_events.view_eventedition")
def edition_detail(request, pk):
    edition = get_object_or_404(EventEdition.objects.select_related("event", "delegation"), pk=pk)
    require_delegation(request.user, "municipal_events.view_eventedition", edition.delegation_id)
    return _modal_detail(request, "municipal_events/_detail_edition.html", {
        "edition": edition, "section": "events",
        "audit_history": EventActionAudit.objects.filter(edition=edition).select_related("actor")[:20],
    })


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


def _event_record_state(request, obj, permission, *, action, name, return_to, relation):
    """Borrado lógico seguro con permiso normal de modificación y auditoría."""
    if not request.user.has_perm(permission):
        raise PermissionDenied("No tienes permiso para modificar este registro.")
    if request.method not in ("GET", "POST"):
        return HttpResponseNotAllowed(["GET", "POST"])
    activating = action == "reactivate"
    def blocked(item):
        if activating:
            if isinstance(item, EventEdition) and item.event.deleted_at is not None:
                return "Reactiva primero el evento principal."
            if isinstance(item, Campaign) and item.edition_id and (
                item.edition.deleted_at is not None or item.edition.event.deleted_at is not None
            ):
                return "Reactiva primero el evento y su edición."
            return None
        if isinstance(item, MunicipalEvent) and item.editions.filter(deleted_at__isnull=True).exists():
            return "Desactiva primero las ediciones activas de este evento."
        if isinstance(item, EventEdition):
            if item.campaigns.filter(deleted_at__isnull=True).exists():
                return "Desactiva primero las campañas activas vinculadas a esta edición."
            if item.participations.filter(withdrawn_at__isnull=True).exists():
                return "Retira primero las participaciones activas de esta edición."
        if isinstance(item, Campaign):
            if item.status == "OPEN":
                return "Primero cierra las inscripciones de la campaña."
            active = item.enrollments.filter(deleted_at__isnull=True)
            if active.filter(status="PENDING").exists():
                return "La campaña tiene inscripciones pendientes de evaluación."
            if active.filter(status="APPROVED", delivery__isnull=True).exists():
                return "La campaña tiene entregas pendientes. Regístralas antes de desactivar."
            # Inscripciones rechazadas, retiradas y entregas finalizadas conservan su historial.
        return None

    message = blocked(obj)
    if request.method == "POST":
        reason = request.POST.get("reason", "").strip()[:500]
        if not reason:
            message = "Debes indicar el motivo (máximo 500 caracteres)."
        if not message:
            with transaction.atomic():
                item = type(obj).objects.select_for_update().get(pk=obj.pk)
                if bool(item.deleted_at is None) == activating:
                    message = "El estado del registro ya cambió. Actualiza el listado."
                else:
                    message = blocked(item)
                    if not message:
                        item.deleted_at = None if activating else timezone.now()
                        item.full_clean()
                        item.save(update_fields=["deleted_at"])
                        EventActionAudit.objects.create(
                            **{relation: item}, actor=request.user,
                            action="REACTIVADO" if activating else "DESACTIVADO", reason=reason)
            if not message:
                return _saved(request, f"{name} {'reactivado' if activating else 'desactivado'} correctamente.", return_to)
        if not _is_modal(request):
            messages.error(request, message)
            return redirect(return_to)
    title = ("Reactivar " if activating else "Desactivar ") + name.lower()
    context = {"title": title, "object_label": str(obj),
               "blocked": message if request.method == "GET" else None,
               "error": message if request.method == "POST" else None,
               "action_text": "Reactivar" if activating else "Desactivar",
               "action_kind": "reactivate" if activating else "deactivate",
               "request_reason": request.POST.get("reason", "") if request.method == "POST" else "",
               "section": "campaigns" if isinstance(obj, Campaign) else "events"}
    if _is_modal(request):
        return render(request, "municipal_events/_modal_confirm.html", context,
                      status=409 if request.method == "POST" else 200)
    context["cancel_url"] = reverse(return_to)
    return render(request, "municipal_events/delete_confirm.html", context)


@_gate("municipal_events.delete_municipalevent")
def event_delete(request, pk):
    obj = get_object_or_404(MunicipalEvent, pk=pk)
    return _event_record_state(request, obj, "municipal_events.delete_municipalevent",
       action="deactivate", name="Evento municipal", return_to="municipal_events:event_list", relation="event")


@_gate("municipal_events.change_municipalevent")
def event_reactivate(request, pk):
    obj = get_object_or_404(MunicipalEvent, pk=pk)
    return _event_record_state(request, obj, "municipal_events.change_municipalevent",
       action="reactivate", name="Evento municipal", return_to="municipal_events:event_list", relation="event")


@_gate("municipal_events.delete_eventedition")
def edition_delete(request, pk):
    obj = get_object_or_404(EventEdition, pk=pk)
    require_delegation(request.user, "municipal_events.delete_eventedition", obj.delegation_id)
    return _event_record_state(request, obj, "municipal_events.delete_eventedition",
       action="deactivate", name="Edición anual", return_to="municipal_events:event_list", relation="edition")


@_gate("municipal_events.change_eventedition")
def edition_reactivate(request, pk):
    obj = get_object_or_404(EventEdition, pk=pk)
    require_delegation(request.user, "municipal_events.change_eventedition", obj.delegation_id)
    return _event_record_state(request, obj, "municipal_events.change_eventedition",
       action="reactivate", name="Edición anual", return_to="municipal_events:event_list", relation="edition")


@_gate("municipal_events.delete_campaign")
def campaign_delete(request, pk):
    obj = get_object_or_404(Campaign, pk=pk)
    require_delegation(request.user, "municipal_events.delete_campaign", obj.organizing_delegation_id)
    return _event_record_state(request, obj, "municipal_events.delete_campaign",
       action="deactivate", name="Campaña municipal", return_to="municipal_events:campaign_list", relation="campaign")


@_gate("municipal_events.change_campaign")
def campaign_reactivate(request, pk):
    obj = get_object_or_404(Campaign, pk=pk)
    require_delegation(request.user, "municipal_events.change_campaign", obj.organizing_delegation_id)
    return _event_record_state(request, obj, "municipal_events.change_campaign",
       action="reactivate", name="Campaña municipal", return_to="municipal_events:campaign_list", relation="campaign")


@_gate("municipal_events.view_eventparticipation")
def participation_list(request, pk):
    edition = get_object_or_404(EventEdition.objects.select_related("event", "delegation"), pk=pk)
    require_delegation(request.user, "municipal_events.view_eventparticipation", edition.delegation_id)
    state = request.GET.get("state", "active")
    if state not in ("active", "withdrawn", "all"):
        state = "active"
    qs = edition.participations.select_related("reviewed_by", "created_by")
    if state == "active":
        qs = qs.filter(withdrawn_at__isnull=True)
    elif state == "withdrawn":
        qs = qs.filter(withdrawn_at__isnull=False)
    can_register = can_access_delegation(request.user, "municipal_events.add_eventparticipation", edition.delegation_id)
    can_edit = can_access_delegation(request.user, "municipal_events.change_eventparticipation", edition.delegation_id)
    can_evaluate = can_access_delegation(request.user, "municipal_events.evaluate_eventparticipation", edition.delegation_id)
    can_withdraw = can_access_delegation(request.user, "municipal_events.withdraw_eventparticipation", edition.delegation_id)
    can_reactivate = can_access_delegation(request.user, "municipal_events.reactivate_eventparticipation", edition.delegation_id)
    return _modal_detail(request, "municipal_events/_participation_list.html", {
        "edition": edition, "items": qs,
        "can_register": can_register, "can_edit": can_edit, "can_evaluate": can_evaluate,
        "can_withdraw": can_withdraw, "can_reactivate": can_reactivate,
        "record_state": state, "total_active": edition.participations.filter(withdrawn_at__isnull=True).count(),
        "section": "events",
    })


@_gate("municipal_events.view_eventparticipation")
def participation_detail(request, pk):
    item = get_object_or_404(EventParticipation.objects.select_related(
        "edition__event", "created_by", "reviewed_by"), pk=pk)
    require_delegation(request.user, "municipal_events.view_eventparticipation", item.edition.delegation_id)
    return _modal_detail(request, "municipal_events/_detail_participation.html", {
        "item": item, "section": "events",
        "audit_history": EventActionAudit.objects.filter(participation=item).select_related("actor")[:40],
    })


@_gate("municipal_events.change_eventparticipation")
def participation_edit(request, pk):
    item = get_object_or_404(EventParticipation.objects.select_related("edition__event"), pk=pk)
    require_delegation(request.user, "municipal_events.change_eventparticipation", item.edition.delegation_id)
    if item.withdrawn_at or item.edition.status == "FINISHED" or item.edition.deleted_at or item.edition.event.deleted_at:
        raise PermissionDenied("No se pueden modificar registros retirados ni ediciones finalizadas o desactivadas.")
    form = EventParticipationEditForm(request.POST or None, instance=item)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            locked = EventParticipation.objects.select_for_update().select_related("edition__event").get(pk=pk)
            if locked.withdrawn_at or locked.edition.status == "FINISHED" or locked.edition.deleted_at or locked.edition.event.deleted_at:
                raise PermissionDenied("La participación ya no se puede modificar.")
            changed = [name for name in ("full_name", "email", "description")
                       if getattr(locked, name) != form.cleaned_data[name]]
            if changed:
                for name in changed:
                    setattr(locked, name, form.cleaned_data[name])
                locked.full_clean()
                locked.save(update_fields=changed)
                EventActionAudit.objects.create(participation=locked, actor=request.user,
                                                action="MODIFICADO", reason="Campos modificados: " + ", ".join(changed))
        return _saved(request, "Datos del participante actualizados.", "municipal_events:event_list")
    return _form_response(request, form, "Modificar participante — " + item.full_name,
                          reverse("municipal_events:event_list"), "events",
                          note="El RUT y la edición no pueden modificarse. RUT: " + item.rut)


def _participation_state(request, item, *, reactivate):
    if request.method not in ("GET", "POST"):
        return HttpResponseNotAllowed(["GET", "POST"])

    def blocked(participant, edition):
        if edition.deleted_at or edition.event.deleted_at or edition.status == "FINISHED":
            return "La edición está desactivada o finalizada. No se permite cambiar participantes."
        if reactivate and participant.withdrawn_at is None:
            return "El participante ya se encuentra activo."
        if not reactivate and participant.withdrawn_at is not None:
            return "El participante ya fue retirado."
        if reactivate and participant.status in ("ACCEPTED", "REGISTERED") and edition.participation_capacity is not None:
            occupied = edition.participations.filter(
                withdrawn_at__isnull=True, status__in=("ACCEPTED", "REGISTERED")
            ).count()
            if occupied >= edition.participation_capacity:
                return "No quedan cupos disponibles para reactivar a este participante."
        return None

    blocked_message = blocked(item, item.edition)
    if request.method == "POST":
        reason = request.POST.get("reason", "").strip()
        if not 1 <= len(reason) <= 500:
            blocked_message = "Indica el motivo obligatorio (máximo 500 caracteres)."
        if not blocked_message:
            with transaction.atomic():
                edition = EventEdition.objects.select_for_update().select_related("event").get(pk=item.edition_id)
                locked = EventParticipation.objects.select_for_update().get(pk=item.pk)
                blocked_message = blocked(locked, edition)
                if not blocked_message:
                    locked.withdrawn_at = None if reactivate else timezone.now()
                    locked.save(update_fields=["withdrawn_at"])
                    EventActionAudit.objects.create(participation=locked, actor=request.user,
                        action="REACTIVADO" if reactivate else "RETIRADO", reason=reason)
            if not blocked_message:
                return _saved(request, "Participante reactivado correctamente." if reactivate
                              else "Participante retirado sin perder su historial.", "municipal_events:event_list")
        if not _is_modal(request):
            messages.error(request, blocked_message)
            return redirect("municipal_events:event_list")
    context = {
        "title": "Reactivar participante" if reactivate else "Retirar participante",
        "object_label": item.full_name, "action_text": "Reactivar" if reactivate else "Retirar",
        "action_kind": "reactivate_participation" if reactivate else "withdraw",
        "blocked": blocked_message if request.method == "GET" else None,
        "error": blocked_message if request.method == "POST" else None,
        "request_reason": request.POST.get("reason", "") if request.method == "POST" else "",
        "section": "events",
    }
    if _is_modal(request):
        return render(request, "municipal_events/_modal_confirm.html", context,
                      status=409 if request.method == "POST" else 200)
    context["cancel_url"] = reverse("municipal_events:event_list")
    return render(request, "municipal_events/delete_confirm.html", context)


@_gate("municipal_events.withdraw_eventparticipation")
def participation_withdraw(request, pk):
    item = get_object_or_404(EventParticipation.objects.select_related("edition__event"), pk=pk)
    require_delegation(request.user, "municipal_events.withdraw_eventparticipation", item.edition.delegation_id)
    return _participation_state(request, item, reactivate=False)


@_gate("municipal_events.reactivate_eventparticipation")
def participation_reactivate(request, pk):
    item = get_object_or_404(EventParticipation.objects.select_related("edition__event"), pk=pk)
    require_delegation(request.user, "municipal_events.reactivate_eventparticipation", item.edition.delegation_id)
    return _participation_state(request, item, reactivate=True)

@_gate("municipal_events.add_eventparticipation")
def participation_create(request, pk):
    edition = get_object_or_404(EventEdition.objects.select_related("event"), pk=pk,
        deleted_at__isnull=True, event__deleted_at__isnull=True)
    require_delegation(request.user, "municipal_events.add_eventparticipation", edition.delegation_id)
    if edition.participation_mode == "OPEN" or edition.status == "FINISHED":
        raise PermissionDenied("La edición no admite inscripciones o postulaciones actualmente.")
    form = EventParticipationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            with transaction.atomic():
                edition = EventEdition.objects.select_for_update().get(pk=pk)
                if edition.deleted_at or edition.event.deleted_at or edition.status == "FINISHED":
                    raise ValueError("La edición ya no recibe participantes.")
                duplicate = EventParticipation.objects.filter(edition=edition, rut=data["rut"]).first()
                if duplicate:
                    form.add_error("rut", "Este RUT ya pertenece a esta edición. Si está retirado, reactiva su registro anterior.")
                else:
                    status = "PENDING" if edition.participation_mode == "APPLICATION" else "REGISTERED"
                    if status == "REGISTERED" and edition.participation_capacity is not None and (
                        edition.participations.filter(status__in=("ACCEPTED", "REGISTERED"), withdrawn_at__isnull=True).count()
                        >= edition.participation_capacity
                    ):
                        raise ValueError("La edición ya completó sus cupos.")
                    item = form.save(commit=False)
                    item.edition = edition
                    item.status = status
                    item.created_by = request.user
                    item.full_clean()
                    item.save()
                    EventActionAudit.objects.create(participation=item, actor=request.user, action="REGISTRADO",
                                                    reason="Alta desde gestión municipal")
        except IntegrityError:
            form.add_error("rut", "El RUT ya se encuentra registrado en esta edición.")
        except ValueError as exc:
            form.add_error(None, str(exc))
        else:
            if not form.errors:
                return _saved(request, "Participante registrado en la edición.", "municipal_events:event_list")
    return _form_response(request, form, "Registrar participante — " + str(edition),
                          reverse("municipal_events:event_list"), "events",
                          note="Postulación pendiente de evaluación" if edition.participation_mode == "APPLICATION" else "Inscripción directa")


@_gate("municipal_events.evaluate_eventparticipation")
def participation_review(request, pk):
    item = get_object_or_404(EventParticipation.objects.select_related("edition__event"), pk=pk)
    require_delegation(request.user, "municipal_events.evaluate_eventparticipation", item.edition.delegation_id)
    if item.withdrawn_at or item.edition.participation_mode != "APPLICATION" or item.status != "PENDING":
        raise PermissionDenied("Solo pueden evaluarse postulaciones activas y pendientes.")
    form = EventParticipationReviewForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            edition = EventEdition.objects.select_for_update().get(pk=item.edition_id)
            locked = EventParticipation.objects.select_for_update().get(pk=pk)
            if edition.deleted_at or edition.event.deleted_at or edition.status == "FINISHED" or locked.withdrawn_at or locked.status != "PENDING":
                raise PermissionDenied("La postulación ya no puede ser evaluada.")
            decision = form.cleaned_data["decision"]
            if decision == "ACCEPTED" and edition.participation_capacity is not None and (
                edition.participations.filter(status__in=("ACCEPTED", "REGISTERED"), withdrawn_at__isnull=True).count()
                >= edition.participation_capacity
            ):
                form.add_error("decision", "No quedan cupos disponibles para aceptar la postulación.")
            else:
                locked.status = decision
                locked.review_reason = form.cleaned_data["reason"]
                locked.reviewed_by = request.user
                locked.reviewed_at = timezone.now()
                locked.save(update_fields=["status", "review_reason", "reviewed_by", "reviewed_at"])
                EventActionAudit.objects.create(participation=locked, actor=request.user,
                                                action=decision, reason=locked.review_reason)
        if not form.errors:
            return _saved(request, "Postulación evaluada y registrada en el historial.", "municipal_events:event_list")
    return _form_response(request, form, "Evaluar postulación — " + item.full_name,
                          reverse("municipal_events:event_list"), "events")
