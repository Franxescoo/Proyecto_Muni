"""SGR: vista transversal de gestiones ya registradas, por delegación.

No crea ni modifica solicitudes, atenciones o gestiones y mantiene la navegación
al flujo existente «Gestiones» de cada atención/solicitud.
"""
from datetime import date

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import CharField, Q
from django.db.models.functions import Cast
from django.shortcuts import render
from django.utils.dateparse import parse_date
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from accounts.permissions import allowed_delegation_ids
from organization.models import Delegation, Employee

from .models import CitizenRequest, CitizenRequestAction


VIEW_PERMISSION = "citizen_requests.view_citizenrequestaction"
PAGE_SIZE = 15


def _selected_delegation(user):
    """Exige delegación global activa y autorizada, igual que el detalle."""
    active_id = getattr(user, "sgr_active_delegation_id", None)
    try:
        active_id = int(active_id)
    except (TypeError, ValueError):
        return None
    ids = allowed_delegation_ids(user, VIEW_PERMISSION)
    if ids is not None and active_id not in ids:
        return None
    return Delegation.objects.filter(pk=active_id, deleted_at__isnull=True).first()


def _parse_filter_date(value):
    """Evita convertir cadenas arbitrarias en filtros o provocar errores SQL."""
    value = (value or "").strip()
    if not value:
        return None, ""
    parsed = parse_date(value)
    if not isinstance(parsed, date):
        return None, "Ingresa una fecha válida para filtrar."
    return parsed, ""


@login_required
@require_GET
@never_cache
def tubo_seguimiento(request):
    """Tubo de consulta sobre CitizenRequestAction, sin duplicar registros."""
    if not request.user.has_perm(VIEW_PERMISSION):
        raise PermissionDenied("No tienes permiso para consultar las gestiones.")

    delegation = _selected_delegation(request.user)
    queryset = CitizenRequestAction.objects.filter(
        deleted_at__isnull=True,
    )
    # Se usa la delegación histórica de la gestión y se valida que la solicitud
    # corresponda a ella. Así no se muestran gestiones de otras delegaciones.
    if delegation is None:
        queryset = queryset.none()
    else:
        queryset = queryset.filter(
            delegation_id=delegation.pk,
            request__delegation_id=delegation.pk,
        )

    total_gestiones = queryset.count()
    total_solicitudes = queryset.values("request_id").distinct().count()

    q = (request.GET.get("q") or "").strip()[:100]
    status = (request.GET.get("status") or "").strip()
    action_type = (request.GET.get("type") or "").strip()
    employee_id = (request.GET.get("employee") or "").strip()
    from_text = (request.GET.get("from") or "").strip()
    until_text = (request.GET.get("until") or "").strip()
    from_date, from_error = _parse_filter_date(from_text)
    until_date, until_error = _parse_filter_date(until_text)
    errors = [x for x in (from_error, until_error) if x]

    employees = Employee.objects.filter(
        pk__in=queryset.order_by().values("responsible_id")
    ).order_by("name", "pk")

    if q:
        queryset = queryset.annotate(
            code_text=Cast("request__tracking_code", output_field=CharField()),
        )
        query_code = q.replace("-", "")
        search = (
            Q(code_text__icontains=q)
            | Q(request__requester_name__icontains=q)
            | Q(request__subject__icontains=q)
            | Q(request__citizen__rut__icontains=q)
            | Q(request__attention_entry__citizen__rut__icontains=q)
            | Q(request__citizen__full_name__icontains=q)
            | Q(request__attention_entry__requester__icontains=q)
            | Q(request__attention_entry__subject__icontains=q)
            | Q(responsible__name__icontains=q)
            | Q(description__icontains=q)
        )
        if query_code != q:
            search |= Q(code_text__icontains=query_code)
        if q.isdigit() and len(q) <= 18:
            search |= Q(request_id=int(q)) | Q(pk=int(q))
        queryset = queryset.filter(search)

    valid_status = {value for value, _ in CitizenRequest.STATUS_CHOICES}
    if status in valid_status:
        queryset = queryset.filter(request__status=status)
    else:
        status = ""

    valid_types = {value for value, _ in CitizenRequestAction.ACTION_TYPE_CHOICES}
    if action_type in valid_types:
        queryset = queryset.filter(action_type=action_type)
    else:
        action_type = ""

    if employee_id.isdigit() and employees.filter(pk=int(employee_id)).exists():
        queryset = queryset.filter(responsible_id=int(employee_id))
    else:
        employee_id = ""

    if from_date:
        queryset = queryset.filter(performed_at__date__gte=from_date)
    if until_date:
        queryset = queryset.filter(performed_at__date__lte=until_date)
    if from_date and until_date and from_date > until_date:
        errors.append("La fecha inicial no puede superar la fecha final.")
        queryset = queryset.none()

    queryset = queryset.select_related(
        "request", "request__citizen", "request__attention_entry",
        "responsible", "delegation", "registered_by",
    ).order_by("-performed_at", "-pk")
    page = Paginator(queryset, PAGE_SIZE).get_page(request.GET.get("page", "1"))

    # Para paginar sin perder búsqueda, filtros ni delegación activa.
    params = request.GET.copy()
    params.pop("page", None)
    querystring = params.urlencode()

    # SGR-ENLACE-ATENCION-20261122: solo ofrecer la atención si el usuario
    # tiene permiso real sobre la delegación activa.
    attention_permission = "registration_validation.view_attentionentry"
    attention_ids = allowed_delegation_ids(request.user, attention_permission)
    can_view_attention = bool(
        delegation is not None
        and request.user.has_perm(attention_permission)
        and (attention_ids is None or delegation.pk in attention_ids)
    )

    return render(request, "citizen_requests/tubo_seguimiento.html", {
        "delegation": delegation,
        "can_view_attention": can_view_attention,
        "page_obj": page,
        "total_gestiones": total_gestiones,
        "total_solicitudes": total_solicitudes,
        "q": q,
        "status_filter": status,
        "type_filter": action_type,
        "employee_filter": employee_id,
        "from_filter": from_text,
        "until_filter": until_text,
        "status_options": CitizenRequest.STATUS_CHOICES,
        "type_options": CitizenRequestAction.ACTION_TYPE_CHOICES,
        "employees": employees,
        "filter_errors": errors,
        "querystring": querystring,
    })
