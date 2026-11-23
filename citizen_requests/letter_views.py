"""Tubo de cartas: vista transversal y alta mínima ligada a CitizenRequest.

No crea una segunda solicitud ni una atención sin solicitud. La consulta es
por delegación activa con los mismos permisos de la gestión existente.
"""
from datetime import date
from uuid import UUID

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import CharField, Q
from django.db.models.functions import Cast
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.dateparse import parse_date
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from accounts.permissions import allowed_delegation_ids
from citizen_registry.models import Citizen
from citizen_registry.rut import normalize_rut
from organization.models import Delegation

from .letter_models import CitizenRequestLetter
from .models import CitizenRequest, RequestEvent

VIEW_PERMISSION = "citizen_requests.view_citizenrequestaction"
ADD_PERMISSIONS = (
    "registration_validation.add_attentionentry",
    "citizen_requests.add_citizenrequestaction",
)
PAGE_SIZE = 15


class NewLetterForm(forms.Form):
    # SGR-INTEGRACION-CARTAS-20261122: vincular a solicitud previa sin duplicarla.
    existing_request_code = forms.CharField(
        label="Código de seguimiento de solicitud existente (opcional)",
        max_length=36, required=False,
        help_text=(
            "Si la carta ya fue registrada como solicitud, introduce su código; "
            "se reutilizarán el solicitante y su atención, si existe."
        ),
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "UUID de la solicitud"}),
    )
    kind = forms.ChoiceField(
        label="Tipo de correspondencia", choices=CitizenRequestLetter.Kind.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    external_folio = forms.CharField(
        label="Folio o número de la carta", max_length=80, required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    sender_institution = forms.CharField(
        label="Institución remitente (si corresponde)", max_length=160,
        required=False, widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    rut = forms.CharField(
        label="RUT del solicitante (opcional)", max_length=16, required=False,
        help_text="Si se ingresa, debe existir previamente en Ciudadanos.",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    requester_name = forms.CharField(
        label="Nombre de quien presenta la carta", max_length=120, required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    requester_phone = forms.CharField(
        label="Teléfono", max_length=25, required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    requester_email = forms.EmailField(
        label="Correo electrónico (opcional para carta presencial)", required=False,
        widget=forms.EmailInput(attrs={"class": "form-control"}),
    )
    address = forms.CharField(
        label="Dirección", max_length=250, required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    subject = forms.CharField(
        label="Asunto", max_length=160, required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    description = forms.CharField(
        label="Contenido o resumen de la carta", required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )

    def clean(self):
        data = super().clean()
        data["citizen"] = None
        existing_code = (data.get("existing_request_code") or "").strip()
        if existing_code:
            try:
                data["existing_request_uuid"] = UUID(existing_code)
            except (ValueError, AttributeError):
                self.add_error("existing_request_code", "El código de la solicitud no es válido.")
            # No se vuelven a solicitar datos personales de una solicitud ya existente.
            return data
        # Si ya existe el ciudadano, el registro central es la fuente de verdad.
        rut = (data.get("rut") or "").strip()
        if rut:
            try:
                normalized = normalize_rut(rut)
            except ValidationError:
                self.add_error("rut", "Ingresa un RUT válido.")
                return data
            citizen = Citizen.objects.filter(rut__iexact=normalized, is_active=True).first()
            if citizen is None:
                self.add_error(
                    "rut", "El ciudadano no existe o está inactivo. Regístralo primero en Ciudadanos."
                )
            else:
                data["citizen"] = citizen
                data["requester_name"] = citizen.full_name
                data["requester_phone"] = citizen.phone
                data["requester_email"] = citizen.email
                data["address"] = citizen.address
        for key in ("requester_name", "address", "subject", "description"):
            if not (data.get(key) or "").strip():
                self.add_error(key, "Este campo es obligatorio al crear una solicitud nueva.")
        return data


def _delegation(user):
    active_id = getattr(user, "sgr_active_delegation_id", None)
    try:
        active_id = int(active_id)
    except (ValueError, TypeError):
        return None
    ids = allowed_delegation_ids(user, VIEW_PERMISSION)
    if ids is not None and active_id not in ids:
        return None
    return Delegation.objects.filter(
        pk=active_id, deleted_at__isnull=True, status__iexact="Active"
    ).first()


def _can_create(user, delegation):
    if delegation is None:
        return False
    for permission in ADD_PERMISSIONS:
        ids = allowed_delegation_ids(user, permission)
        if ids is None or delegation.pk in ids:
            return True
    return False


def _filter_date(value):
    value = (value or "").strip()
    if not value:
        return None, None
    parsed = parse_date(value)
    if not isinstance(parsed, date):
        return None, "Ingresa una fecha válida."
    return parsed, None


@login_required
@require_http_methods(["GET", "POST"])
@never_cache
def tubo_cartas(request):
    if not request.user.has_perm(VIEW_PERMISSION):
        raise PermissionDenied("No tienes autorización para consultar el Tubo de cartas.")
    delegation = _delegation(request.user)
    can_create = _can_create(request.user, delegation)
    form = NewLetterForm(request.POST if request.method == "POST" else None)
    if request.method == "POST":
        if not can_create:
            raise PermissionDenied("No tienes autorización para registrar cartas en esta delegación.")
        if form.is_valid():
            c = form.cleaned_data
            try:
                with transaction.atomic():
                    if c.get("existing_request_uuid"):
                        # Vincular a una solicitud del mismo ámbito sin crear otra.
                        citizen_request = CitizenRequest.objects.select_for_update().filter(
                            tracking_code=c["existing_request_uuid"],
                            delegation_id=delegation.pk,
                        ).first()
                        if citizen_request is None:
                            raise ValidationError({
                                "existing_request_code": "No existe esa solicitud en tu delegación activa."
                            })
                        if CitizenRequestLetter.objects.filter(request=citizen_request).exists():
                            raise ValidationError({
                                "existing_request_code": "Esta solicitud ya tiene una carta u oficio vinculado."
                            })
                    else:
                        # Solicitud nueva; nunca se crea una atención automáticamente.
                        citizen_request = CitizenRequest.objects.create(
                            citizen=c["citizen"],
                            delegation=delegation,
                            origin="INTERNAL",
                            requester_name=c["requester_name"].strip(),
                            requester_email=(c.get("requester_email") or "").strip(),
                            requester_phone=c["requester_phone"].strip(),
                            address=c["address"].strip(),
                            subject=c["subject"].strip(),
                            description=c["description"].strip(),
                            status="NEW",
                        )
                    CitizenRequestLetter.objects.create(
                        request=citizen_request,
                        kind=c["kind"],
                        external_folio=c["external_folio"].strip(),
                        sender_institution=c["sender_institution"].strip(),
                        registered_by=request.user,
                    )
                    RequestEvent.objects.create(
                        request=citizen_request,
                        actor=request.user,
                        observation=(
                            "Correspondencia registrada: "
                            f"{dict(CitizenRequestLetter.Kind.choices)[c['kind']]}"
                            + (f". Folio externo: {c['external_folio'].strip()}" if c["external_folio"].strip() else "")
                        ),
                        previous_status=citizen_request.status,
                        new_status=citizen_request.status,
                    )
            except ValidationError as exc:
                if hasattr(exc, "message_dict") and "existing_request_code" in exc.message_dict:
                    form.add_error("existing_request_code", exc.message_dict["existing_request_code"])
                else:
                    form.add_error(None, "No se pudo registrar la carta. Revisa los datos.")
            except (ValueError, IntegrityError):
                form.add_error(None, "No se pudo vincular la carta. Verifica si ya fue registrada.")
            else:
                messages.success(request, "Carta vinculada a una única solicitud, sin generar atenciones adicionales.")
                return redirect("citizen_requests:carta_detalle", request_id=citizen_request.pk)

    queryset = CitizenRequestLetter.objects.select_related(
        "request", "request__delegation", "request__citizen",
        "request__assigned_to", "registered_by",
    )
    if delegation is None:
        queryset = queryset.none()
    else:
        queryset = queryset.filter(request__delegation_id=delegation.pk)
    total = queryset.count()

    q = (request.GET.get("q") or "").strip()[:100]
    status = (request.GET.get("status") or "").strip()
    kind = (request.GET.get("kind") or "").strip()
    since_text = (request.GET.get("from") or "").strip()
    until_text = (request.GET.get("until") or "").strip()
    since, since_error = _filter_date(since_text)
    until, until_error = _filter_date(until_text)
    errors = [error for error in (since_error, until_error) if error]
    if q:
        queryset = queryset.annotate(
            tracking_code_text=Cast("request__tracking_code", output_field=CharField()),
        ).filter(
            Q(request__requester_name__icontains=q)
            | Q(request__citizen__rut__icontains=q)
            | Q(request__subject__icontains=q)
            | Q(tracking_code_text__icontains=q)
            | Q(external_folio__icontains=q)
            | Q(sender_institution__icontains=q)
        )
    if status in {key for key, _ in CitizenRequest.STATUS_CHOICES}:
        queryset = queryset.filter(request__status=status)
    else:
        status = ""
    if kind in {key for key, _ in CitizenRequestLetter.Kind.choices}:
        queryset = queryset.filter(kind=kind)
    else:
        kind = ""
    if since:
        queryset = queryset.filter(received_at__date__gte=since)
    if until:
        queryset = queryset.filter(received_at__date__lte=until)
    if since and until and since > until:
        errors.append("La fecha inicial no puede superar la fecha final.")
        queryset = queryset.none()

    queryset = queryset.order_by("-received_at", "-pk")
    page = Paginator(queryset, PAGE_SIZE).get_page(request.GET.get("page", "1"))
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "citizen_requests/tubo_cartas.html", {
        "delegation": delegation,
        "can_create": can_create,
        "form": form,
        "open_create": request.method == "POST" and form.errors,
        "total": total,
        "page_obj": page,
        "search": q,
        "status_filter": status,
        "kind_filter": kind,
        "from_filter": since_text,
        "until_filter": until_text,
        "status_options": CitizenRequest.STATUS_CHOICES,
        "kind_options": CitizenRequestLetter.Kind.choices,
        "filter_errors": errors,
        "querystring": params.urlencode(),
    })


@login_required
@never_cache
def carta_detalle(request, request_id):
    """Detalle HTML del expediente. La ruta histórica request_detail devuelve JSON."""
    if not request.user.has_perm(VIEW_PERMISSION):
        raise PermissionDenied("No tienes autorización para consultar cartas.")
    delegation = _delegation(request.user)
    if delegation is None:
        raise PermissionDenied("Selecciona una delegación activa y autorizada.")
    letter = get_object_or_404(
        CitizenRequestLetter.objects.select_related(
            "request", "request__citizen", "request__attention_entry",
            "request__delegation", "registered_by",
        ),
        request_id=request_id,
        request__delegation_id=delegation.pk,
    )
    citizen_request = letter.request

    def _allowed(permission):
        if not request.user.has_perm(permission):
            return False
        ids = allowed_delegation_ids(request.user, permission)
        return ids is None or delegation.pk in ids

    return render(request, "citizen_requests/carta_detalle.html", {
        "letter": letter,
        "citizen_request": citizen_request,
        "events": citizen_request.events.select_related("actor").order_by("created_at", "pk"),
        "can_view_attention": bool(
            citizen_request.attention_entry_id
            and _allowed("registration_validation.view_attentionentry")
        ),
        "can_create_attention": bool(
            not citizen_request.attention_entry_id
            and citizen_request.status != "CLOSED"
            and _allowed("registration_validation.add_attentionentry")
        ),
    })
