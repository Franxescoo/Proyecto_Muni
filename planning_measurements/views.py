from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.forms import inlineformset_factory
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from organization.models import PositionFunction

from .forms import GoalForm, GoalInlineForm, PeriodForm
from .models import Goal, Period

PAGE_SIZE = 25
PAGE_SIZE_OPTIONS = (10, 25, 50)


# ---------- Utilidades ----------


def access(permission):
    """Exige sesión iniciada y el permiso indicado (403 si no lo tiene)."""

    def decorator(view):
        view = permission_required(permission, raise_exception=True)(view)
        return login_required(view)  # LOGIN_URL viene de settings

    return decorator


def only_superuser(user):
    """Solo el superusuario puede eliminar registros."""
    if not user.is_superuser:
        raise PermissionDenied("Solo el superusuario puede eliminar.")


def scoped_goals(user):
    """Metas activas visibles para el usuario (scoping por delegación)."""
    goals = Goal.objects.filter(deleted_at__isnull=True).select_related(
        "period", "employee", "position"
    )
    if user.is_superuser:
        return goals
    profile = getattr(user, "profile", None)
    if profile is None or profile.delegation_id is None:
        return goals.none()
    return goals.filter(employee__delegation_id=profile.delegation_id)


def run_bulk_delete(request, queryset):
    """Acción 'Delete': eliminación lógica de los registros seleccionados."""
    only_superuser(request.user)
    ids = [i for i in request.POST.getlist("_selected_action") if i.isdigit()]
    if request.POST.get("action") != "delete_selected" or not ids:
        messages.warning(request, "Seleccione al menos un registro y una acción.")
        return
    now = timezone.now()
    updated = queryset.filter(pk__in=ids).update(deleted_at=now, updated_at=now)
    messages.success(request, f"{updated} Deleted successfully.")


def build_headers(request, columns, order):
    """Encabezados ordenables (clic en la columna para ordenar)."""
    headers = []
    for label, field in columns:
        if field is None:
            headers.append({"label": label})
            continue
        params = request.GET.copy()
        params.pop("page", None)
        params["o"] = "-" + field if order == field else field
        headers.append(
            {
                "label": label,
                "url": "?" + params.urlencode(),
                "asc": order == field,
                "desc": order == "-" + field,
            }
        )
    return headers


def resolve_order(request, columns, default):
    allowed = {field for _, field in columns if field}
    order = request.GET.get("o", default)
    return order if order.lstrip("-") in allowed else default


def paginate(request, queryset):
    # Preferencia guardada en la sesión (ver set_page_size)
    size = request.session.get("planning_page_size", PAGE_SIZE)
    page = Paginator(queryset, size).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return page, params.urlencode()


def after_save(request, redirect_list, redirect_add, redirect_edit):
    """Botones de guardado del Admin: guardar / añadir otro / continuar."""
    if "_addanother" in request.POST:
        return redirect(redirect_add)
    if "_continue" in request.POST:
        return redirect(*redirect_edit)
    return redirect(redirect_list)


# ---------- Inicio (dashboard) ----------


@login_required
def index(request):
    user = request.user
    delegation = None
    if not user.is_superuser:
        profile = getattr(user, "profile", None)
        if profile is None or profile.delegation_id is None:
            raise PermissionDenied("La cuenta no posee una delegación habilitada.")
        delegation = profile.delegation

    # Valor temporal en la sesión: visitas al panel durante esta sesión
    visits = request.session.get("dashboard_visits", 0) + 1
    request.session["dashboard_visits"] = visits

    context = {
        "delegation": delegation,
        "visits": visits,
        "page_size": request.session.get("planning_page_size", PAGE_SIZE),
        "page_size_options": PAGE_SIZE_OPTIONS,
        "periods_count": Period.objects.filter(deleted_at__isnull=True).count(),
        "goals_count": scoped_goals(user).count(),
    }
    return render(request, "planning/index.html", context)


@login_required
@require_POST
def set_page_size(request):
    """Guarda en la sesión la cantidad de registros por página."""
    try:
        size = int(request.POST.get("page_size", ""))
    except ValueError:
        size = None
    if size in PAGE_SIZE_OPTIONS:
        request.session["planning_page_size"] = size
        messages.success(request, "Preferencia de visualización actualizada.")
    else:
        messages.error(request, "Valor no válido para registros por página.")
    return redirect("planning:index")


# ---------- PERÍODOS ----------

PERIOD_COLUMNS = [
    ("ID", "period_id"),
    ("Inicio", "start_date"),
    ("Término", "end_date"),
    ("Días computables", "computable_days"),
    ("Estado", "status"),
    ("Versión de parámetros", "parameters_version"),
    ("Creado", "created_at"),
    ("Acciones", None),
]


def goal_formset(can_add, existing_count):
    """Formset de metas dentro del período (sin borrado, como el Inline)."""
    return inlineformset_factory(
        Period,
        Goal,
        form=GoalInlineForm,
        extra=0,
        can_delete=False,
        max_num=None if can_add else existing_count,
        validate_max=True,
    )


def disable_formset(formset, only_existing=False):
    forms = formset.forms
    if only_existing:
        forms = forms[: formset.initial_form_count()]
    for form in forms:
        for field in form.fields.values():
            field.disabled = True


@access("planning_measurements.view_period")
def period_list(request):
    periods = Period.objects.filter(deleted_at__isnull=True)

    if request.method == "POST":
        run_bulk_delete(request, periods)
        return redirect(request.get_full_path())

    query = request.GET.get("q", "").strip()
    if query:
        periods = periods.filter(
            Q(status__icontains=query) | Q(parameters_version__icontains=query)
        )
    selected_status = request.GET.get("status", "")
    if selected_status:
        periods = periods.filter(status=selected_status)

    order = resolve_order(request, PERIOD_COLUMNS, "-start_date")
    page, querystring = paginate(request, periods.order_by(order))

    context = {
        "page": page,
        "headers": build_headers(request, PERIOD_COLUMNS, order),
        "query": query,
        "selected_status": selected_status,
        "statuses": Period.objects.filter(deleted_at__isnull=True)
        .order_by("status")
        .values_list("status", flat=True)
        .distinct(),
        "querystring": querystring,
    }
    return render(request, "planning/period_list.html", context)


def render_period_form(request, form, formset, title, period, readonly, can_add_goal):
    return render(
        request,
        "planning/period_form.html",
        {
            "form": form,
            "formset": formset,
            "title": title,
            "period": period,
            "readonly": readonly,
            "can_add_goal": can_add_goal and not readonly,
        },
    )


@access("planning_measurements.add_period")
def period_create(request):
    can_add_goal = request.user.has_perm("planning_measurements.add_goal")
    period = Period()
    form = PeriodForm(request.POST or None, instance=period)
    formset = goal_formset(can_add_goal, 0)(
        request.POST or None,
        instance=period,
        queryset=Goal.objects.none(),
        form_kwargs={"user": request.user},
    )
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        form.save()
        formset.save()
        messages.success(request, "Período creado correctamente.")
        return after_save(
            request,
            "planning:period_list",
            "planning:period_create",
            ("planning:period_edit", period.pk),
        )
    return render_period_form(
        request, form, formset, "Nuevo período", None, False, can_add_goal
    )


@access("planning_measurements.view_period")
def period_edit(request, period_id):
    period = get_object_or_404(Period, pk=period_id, deleted_at__isnull=True)
    user = request.user
    can_change = user.has_perm("planning_measurements.change_period")
    can_change_goal = user.has_perm("planning_measurements.change_goal")
    can_add_goal = user.has_perm("planning_measurements.add_goal")

    if request.method == "POST" and not can_change:
        raise PermissionDenied

    goals = scoped_goals(user).filter(period=period)
    form = PeriodForm(request.POST or None, instance=period)
    formset = goal_formset(can_add_goal, goals.count())(
        request.POST or None,
        instance=period,
        queryset=goals,
        form_kwargs={"user": user},
    )

    # Sin permiso de modificación se muestra en modo solo lectura
    readonly = not can_change
    if readonly:
        for field in form.fields.values():
            field.disabled = True
    if readonly:
        disable_formset(formset)
    elif not can_change_goal:
        disable_formset(formset, only_existing=True)

    if request.method == "POST" and form.is_valid() and formset.is_valid():
        form.save()
        if can_change_goal or can_add_goal:
            formset.save()
        messages.success(request, "Período modificado correctamente.")
        return after_save(
            request,
            "planning:period_list",
            "planning:period_create",
            ("planning:period_edit", period.pk),
        )
    return render_period_form(
        request,
        form,
        formset,
        "Detalle del período" if readonly else "Modificar período",
        period,
        readonly,
        can_add_goal,
    )


@access("planning_measurements.view_period")
def period_delete(request, period_id):
    only_superuser(request.user)
    period = get_object_or_404(Period, pk=period_id, deleted_at__isnull=True)
    if request.method == "POST":
        now = timezone.now()
        period.deleted_at = now  # eliminación lógica
        period.save(update_fields=["deleted_at", "updated_at"])
        messages.success(request, "Período eliminado correctamente.")
        return redirect("planning:period_list")
    return render(
        request,
        "planning/period_confirm_delete.html",
        {
            "period": period,
            "goals_count": period.goals.filter(deleted_at__isnull=True).count(),
        },
    )


# ---------- METAS ----------

GOAL_COLUMNS = [
    ("ID", "goal_id"),
    ("Ítem", "item"),
    ("Período", "period__start_date"),
    ("Funcionario", "employee__name"),
    ("Cargo", "position__position_name"),
    ("Valor objetivo", "objective_value"),
    ("Unidad", "unit"),
    ("Ponderador", "weight"),
    ("Creado", "created_at"),
    ("Acciones", None),
]


@access("planning_measurements.view_goal")
def goal_list(request):
    goals = scoped_goals(request.user)

    if request.method == "POST":
        run_bulk_delete(request, goals)
        return redirect(request.get_full_path())

    base_goals = goals  # para armar las opciones de los filtros

    query = request.GET.get("q", "").strip()
    if query:
        goals = goals.filter(
            Q(item__icontains=query) | Q(employee__name__icontains=query)
        )
    selected_period = request.GET.get("period", "")
    if selected_period.isdigit():
        goals = goals.filter(period_id=selected_period)
    selected_position = request.GET.get("position", "")
    if selected_position.isdigit():
        goals = goals.filter(position_id=selected_position)
    selected_unit = request.GET.get("unit", "")
    if selected_unit:
        goals = goals.filter(unit=selected_unit)

    order = resolve_order(request, GOAL_COLUMNS, "period__start_date")
    page, querystring = paginate(request, goals.order_by(order, "item"))

    context = {
        "page": page,
        "headers": build_headers(request, GOAL_COLUMNS, order),
        "query": query,
        "periods": Period.objects.filter(deleted_at__isnull=True).order_by("-start_date"),
        "positions": PositionFunction.objects.filter(deleted_at__isnull=True),
        "units": base_goals.order_by("unit").values_list("unit", flat=True).distinct(),
        "selected_period": selected_period,
        "selected_position": selected_position,
        "selected_unit": selected_unit,
        "querystring": querystring,
    }
    return render(request, "planning/goal_list.html", context)


@access("planning_measurements.add_goal")
def goal_create(request):
    form = GoalForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        goal = form.save()
        messages.success(request, "Meta creada correctamente.")
        return after_save(
            request,
            "planning:goal_list",
            "planning:goal_create",
            ("planning:goal_edit", goal.pk),
        )
    return render(
        request,
        "planning/goal_form.html",
        {"form": form, "title": "Nueva meta", "goal": None, "readonly": False},
    )


@access("planning_measurements.view_goal")
def goal_edit(request, goal_id):
    # Una meta de otra delegación no está en el queryset: responde 404
    goal = get_object_or_404(scoped_goals(request.user), pk=goal_id)
    can_change = request.user.has_perm("planning_measurements.change_goal")
    if request.method == "POST" and not can_change:
        raise PermissionDenied

    form = GoalForm(request.POST or None, instance=goal, user=request.user)
    readonly = not can_change
    if readonly:
        for field in form.fields.values():
            field.disabled = True

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Meta modificada correctamente.")
        return after_save(
            request,
            "planning:goal_list",
            "planning:goal_create",
            ("planning:goal_edit", goal.pk),
        )
    return render(
        request,
        "planning/goal_form.html",
        {
            "form": form,
            "title": "Detalle de la meta" if readonly else "Modificar meta",
            "goal": goal,
            "readonly": readonly,
        },
    )


@access("planning_measurements.view_goal")
def goal_delete(request, goal_id):
    only_superuser(request.user)
    goal = get_object_or_404(scoped_goals(request.user), pk=goal_id)
    if request.method == "POST":
        goal.deleted_at = timezone.now()  # eliminación lógica
        goal.save(update_fields=["deleted_at", "updated_at"])
        messages.success(request, "Meta eliminada correctamente.")
        return redirect("planning:goal_list")
    return render(
        request,
        "planning/goal_confirm_delete.html",
        {"goal": goal},
    )
