from django.contrib import messages
from django.core.exceptions import ValidationError
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST
from .forms import CitizenForm, CitizenRutForm
from .models import Citizen, CitizenAudit


def _safe_public_fields(citizen):
    """No exponer RSH / agrupación a consultas automáticas de atención."""
    return {"id": citizen.pk, "rut": citizen.rut, "name": citizen.full_name, "email": citizen.email, "phone": citizen.phone, "address": citizen.address}


@login_required
@permission_required("citizen_registry.view_citizen", raise_exception=True)
@require_GET
def citizen_list(request):
    q = request.GET.get("q", "").strip()[:120]
    state = request.GET.get("state", "active")
    if state not in ("active", "inactive", "all"):
        state = "active"
    citizens = Citizen.objects.all()
    if state == "active":
        citizens = citizens.filter(is_active=True)
    elif state == "inactive":
        citizens = citizens.filter(is_active=False)
    if q:
        citizens = citizens.filter(Q(rut__icontains=q.replace(".", "").replace("-", "")) | Q(full_name__icontains=q) | Q(email__icontains=q))
    page = Paginator(citizens, 15).get_page(request.GET.get("page"))
    return render(request, "citizen_registry/list.html", {
        "page_obj": page, "q": q, "state": state,
        "citizen_form": CitizenForm(),
        "groups": Citizen.objects.exclude(neighborhood_group="").values_list("neighborhood_group", flat=True).distinct().order_by("neighborhood_group"),
    })


@login_required
@permission_required("citizen_registry.view_citizen", raise_exception=True)
@require_GET
def citizen_lookup(request):
    form = CitizenRutForm(request.GET)
    if not form.is_valid():
        return JsonResponse({"found": False, "error": "RUT inválido"}, status=400)
    citizen = Citizen.objects.filter(rut=form.cleaned_data["rut"]).first()
    # No se revelan datos personales del ciudadano desactivado por el buscador.
    if citizen and not citizen.is_active:
        return JsonResponse({"found": False, "inactive": True,
                             "message": "Existe un registro inactivo con este RUT. Solicita su reactivación desde Ciudadanos."})
    return JsonResponse({"found": bool(citizen), "inactive": False,
                         "citizen": _safe_public_fields(citizen) if citizen else None})


@login_required
@permission_required("citizen_registry.add_citizen", raise_exception=True)
@require_POST
def citizen_create(request):
    form = CitizenForm(request.POST)
    if not form.is_valid():
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"ok": False, "errors": form.errors.get_json_data()}, status=400)
        messages.error(request, "Revisa los campos del ciudadano.")
        return redirect("citizen_registry:list")
    try:
        with transaction.atomic():
            citizen = form.save(commit=False)
            citizen.created_by = request.user
            citizen.save()
            CitizenAudit.objects.create(citizen=citizen, actor=request.user, action="CREATED")
    except (IntegrityError, ValueError, ValidationError):
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"ok": False, "errors": {"rut": [{"message": "El RUT ya existe. Búscalo antes de registrar nuevamente."}]}}, status=409)
        messages.error(request, "El RUT ya existe.")
        return redirect("citizen_registry:list")
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"ok": True, "citizen": _safe_public_fields(citizen)}, status=201)
    messages.success(request, "Ciudadano registrado.")
    return redirect("citizen_registry:list")


@login_required
@permission_required("citizen_registry.view_citizen", raise_exception=True)
@require_GET
def citizen_detail(request, pk):
    citizen = get_object_or_404(Citizen, pk=pk)
    return JsonResponse({"citizen": {
        "id": citizen.pk, "rut": citizen.rut, "full_name": citizen.full_name,
        "birth_date": citizen.birth_date.isoformat() if citizen.birth_date else "",
        "phone": citizen.phone, "email": citizen.email, "address": citizen.address,
        "rsh_folio": citizen.rsh_folio, "rsh_bracket": citizen.rsh_bracket,
        "is_neighborhood_member": citizen.is_neighborhood_member,
        "neighborhood_group": citizen.neighborhood_group,
        "organization_role": citizen.organization_role, "is_active": citizen.is_active,
    }})


@login_required
@permission_required("citizen_registry.change_citizen", raise_exception=True)
@require_POST
def citizen_edit(request, pk):
    citizen = get_object_or_404(Citizen, pk=pk)
    form = CitizenForm(request.POST, instance=citizen)
    if not form.is_valid():
        return JsonResponse({"ok": False, "errors": form.errors.get_json_data()}, status=400)
    try:
        with transaction.atomic():
            form.save()
            CitizenAudit.objects.create(citizen=citizen, actor=request.user, action="UPDATED")
    except IntegrityError:
        return JsonResponse({"ok": False, "error": "Conflicto al guardar el ciudadano."}, status=409)
    return JsonResponse({"ok": True})


@login_required
@permission_required("citizen_registry.change_citizen", raise_exception=True)
@require_POST
def citizen_deactivate(request, pk):
    citizen = get_object_or_404(Citizen, pk=pk)
    if citizen.is_active:
        citizen.is_active = False
        citizen.save(update_fields=["is_active", "updated_at"])
        CitizenAudit.objects.create(citizen=citizen, actor=request.user, action="DEACTIVATED")
    return JsonResponse({"ok": True})


@login_required
@permission_required("citizen_registry.change_citizen", raise_exception=True)
@require_POST
def citizen_reactivate(request, pk):
    """Restituye el mismo registro y su historial; nunca duplica el RUT."""
    with transaction.atomic():
        citizen = get_object_or_404(Citizen.objects.select_for_update(), pk=pk)
        if not citizen.is_active:
            citizen.is_active = True
            citizen.save(update_fields=["is_active", "updated_at"])
            CitizenAudit.objects.create(citizen=citizen, actor=request.user, action="REACTIVATED",
                                        description="Ciudadano reactivado desde el mantenedor")
    return JsonResponse({"ok": True})


@login_required
@permission_required("citizen_registry.view_citizen", raise_exception=True)
@permission_required("registration_validation.add_attentionentry", raise_exception=True)
@require_POST
def citizen_link_request(request, pk):
    """Vincula un ciudadano existente con una solicitud accesible al funcionario.

    Mantiene los datos originales de la solicitud tal como fueron ingresados.
    """
    from citizen_requests.models import RequestEvent
    from citizen_requests.views import _request_queryset_for_user
    from django.db import transaction
    form = CitizenRutForm(request.POST)
    if not form.is_valid():
        return JsonResponse({"ok": False, "error": "RUT inválido."}, status=400)
    rut = form.cleaned_data["rut"]
    citizen = Citizen.objects.filter(rut=rut, is_active=True).first()
    if citizen is None:
        return JsonResponse({"ok": False, "error": "Primero registra al ciudadano en el mantenedor."}, status=404)
    with transaction.atomic():
        obj = get_object_or_404(_request_queryset_for_user(request).select_for_update(), pk=pk)
        if obj.attention_entry_id:
            return JsonResponse({"ok": False, "error": "La solicitud ya tiene una atención; no se puede cambiar su ciudadano desde aquí."}, status=409)
        if obj.citizen_id and obj.citizen_id != citizen.pk:
            return JsonResponse({"ok": False, "error": "La solicitud ya está vinculada a otro ciudadano."}, status=409)
        if not obj.citizen_id:
            obj.citizen = citizen
            obj.save(update_fields=["citizen", "updated_at"])
            RequestEvent.objects.create(request=obj, actor=request.user, observation="Ciudadano vinculado por funcionario autorizado.", previous_status=obj.status, new_status=obj.status)
    return JsonResponse({"ok": True, "name": citizen.full_name})
