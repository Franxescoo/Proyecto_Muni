from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.forms import inlineformset_factory
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.db import transaction
from django.utils.http import url_has_allowed_host_and_scheme

from organization.exports import workbook_response
from organization.models import PositionFunction
from accounts.permissions import allowed_delegation_ids

from .forms import (
    GoalForm,
    GoalInlineForm,
    PeriodForm,
    MeasurementItemForm,
)
from .models import Goal, Period, MeasurementItem, PeriodArchiveLog
from .calculations import (
    InvalidPeriodWeights,
    validate_period_weights,
)

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

def ensure_open_period(period):
    """Impide operaciones sobre períodos archivados o cerrados."""

    if period.deleted_at is not None:
        raise PermissionDenied(
            "No puedes modificar un período archivado."
        )

    if period.status == Period.Status.CLOSED:
        raise PermissionDenied(
            "El período está cerrado. "
            "Debe reabrirse mediante el procedimiento autorizado."
        )


def scoped_goals(user, permission="planning_measurements.view_goal"):
    """Metas activas pertenecientes a períodos no archivados."""

    goals = Goal.objects.filter(
        deleted_at__isnull=True,
        period__deleted_at__isnull=True,
    ).select_related(
        "period",
        "employee",
        "position",
    )

    if user.is_superuser:
        return goals

    delegation_ids = allowed_delegation_ids(user, permission)
    if not delegation_ids:
        return goals.none()
    return goals.filter(employee__delegation_id__in=delegation_ids)



def may_archive_period(user, period):
    """Permiso normal de eliminación y permiso directo adicional si está cerrado."""
    if not (user.is_superuser or user.has_perm("planning_measurements.delete_period")):
        return False
    if period.status == Period.Status.CLOSED and not user.is_superuser:
        return user.user_permissions.filter(
            content_type__app_label="planning_measurements", codename="delete_closed_period"
        ).exists()
    return True


def run_bulk_delete(request, queryset):
    """Archiva registros seleccionados respetando los permisos."""

    if request.POST.get("action") != "delete_selected":
        messages.warning(
            request,
            "Selecciona una acción válida."
        )
        return

    ids = request.POST.getlist("_selected_action")

    if (
        not ids
        or len(ids) != len(set(ids))
        or any(not value.isdecimal() for value in ids)
    ):
        messages.warning(
            request,
            "Selecciona registros válidos."
        )
        return
    
    # o usuarios con el permiso asignado mediante grupos.
    if queryset.model is Period:
        if not (
            request.user.is_superuser
            or request.user.has_perm("planning_measurements.delete_period")
        ):
            raise PermissionDenied(
                "No tienes permiso para eliminar períodos."
            )

    elif queryset.model is Goal:
        if not (
            request.user.is_superuser
            or request.user.has_perm("planning_measurements.delete_goal")
        ):
            raise PermissionDenied(
                "No tienes permiso para eliminar metas."
            )

    else:
        raise PermissionDenied(
            "Esta acción no está disponible."
        )

    if queryset.model is Goal and not request.user.is_superuser:
        queryset = queryset.filter(
            pk__in=scoped_goals(request.user, "planning_measurements.delete_goal").values("pk")
        )

    with transaction.atomic():
        selected = list(
            queryset.filter(pk__in=ids).select_for_update()
        )

        if len(selected) != len(ids):
            raise PermissionDenied(
                "Algún registro no está disponible."
            )

        if queryset.model is Period:
            for period in selected:
                if not may_archive_period(request.user, period):
                    raise PermissionDenied("Falta el permiso individual para archivar un período cerrado.")
                if period.goals.exists():
                    raise PermissionDenied(
                        "No se puede archivar este período: conserva metas o historial asociado."
                    )

        elif queryset.model is Goal:
            for goal in selected:
                if goal.activities.exists() or goal.indicators.exists():
                    if goal.period.status == Period.Status.CLOSED:
                        raise PermissionDenied(
                            "No puedes eliminar metas de períodos cerrados."
                        )
                    raise PermissionDenied(
                        f"No se puede eliminar la meta '{goal.item}' "
                        "porque tiene actividades o indicadores asociados."
                    )

        now = timezone.now()

        updated = queryset.filter(
            pk__in=[obj.pk for obj in selected]
        ).update(
            deleted_at=now,
            updated_at=now
        )
        if queryset.model is Period:
            PeriodArchiveLog.objects.bulk_create([
                PeriodArchiveLog(period=obj, user=request.user,
                                 was_closed=obj.status == Period.Status.CLOSED)
                for obj in selected
            ])

    messages.success(
        request,
        f"{updated} registro(s) archivado(s) correctamente."
    )



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
    """Guarda la cantidad de registros por página."""

    try:
        size = int(request.POST.get("page_size", ""))
    except ValueError:
        size = None

    if size in PAGE_SIZE_OPTIONS:
        request.session["planning_page_size"] = size
        messages.success(
            request,
            "Preferencia de visualización actualizada."
        )
    else:
        messages.error(
            request,
            "Valor no válido para registros por página."
        )

    next_url = request.POST.get("next", "")

    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)

    return redirect("planning:period_list")



# ---------- PERÍODOS ----------

PERIOD_COLUMNS = [
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

def available_goal_sources(user, period=None):
    """Metas existentes que el usuario puede reutilizar."""

    goals = scoped_goals(user).order_by(
        "-period__start_date",
        "item",
        "pk",
    )

    if period and period.pk:
        goals = goals.exclude(period=period)

    return goals[:300]


def apply_goal_assignments(request, period, *, may_add, may_remove):
    """Copia o archiva metas durante el guardado del período."""

    add_ids = request.POST.getlist("existing_goal_ids")
    remove_ids = request.POST.getlist("remove_goal_ids")

    for ids in (add_ids, remove_ids):
        if (
            len(ids) > 100
            or len(ids) != len(set(ids))
            or any(not value.isdecimal() for value in ids)
        ):
            raise ValidationError(
                "Selecciona hasta 100 metas diferentes y válidas."
            )

    if add_ids and not may_add:
        raise PermissionDenied(
            "No tienes permiso para agregar metas."
        )

    if remove_ids and not may_remove:
        raise PermissionDenied(
            "No tienes permiso para quitar metas."
        )

    if not add_ids and not remove_ids:
        return

    ensure_open_period(period)

    # Quitar metas mediante eliminación lógica.
    if remove_ids:
        targets = list(
            scoped_goals(request.user)
            .filter(period=period, pk__in=remove_ids)
            .select_for_update()
        )

        if len(targets) != len(remove_ids):
            raise ValidationError(
                "Alguna meta seleccionada no pertenece al período."
            )

        for goal in targets:
            if (
                goal.activities.exists()
                or goal.indicators.exists()
            ):
                raise ValidationError(
                    f"No se puede quitar '{goal.item}' porque "
                    "tiene actividades o indicadores asociados."
                )

        now = timezone.now()

        Goal.objects.filter(
            pk__in=[goal.pk for goal in targets]
        ).update(
            deleted_at=now,
            updated_at=now,
        )

    # Copiar metas desde otros períodos.
    if add_ids:
        selected = list(
            scoped_goals(request.user)
            .filter(pk__in=add_ids)
            .exclude(period=period)
            .select_related("employee", "position")
        )

        if len(selected) != len(add_ids):
            raise ValidationError(
                "Alguna meta seleccionada no está disponible."
            )

        
        existing = set(
            Goal.objects.filter(
                period=period,
                deleted_at__isnull=True,
                measurement_item__isnull=False,
            ).values_list(
                "employee_id",
                "position_id",
                "measurement_item_id",
            )
        )

        for source in selected:
            key = (
                source.employee_id,
                source.position_id,
                source.measurement_item_id,
            )

            if source.measurement_item_id and key in existing:
                raise ValidationError(
                    f"La meta '{source.item}' ya existe "
                    "para ese funcionario y cargo."
                )

            if (
                source.employee.deleted_at is not None
                or source.position.deleted_at is not None
            ):
                raise ValidationError(
                    f"La meta '{source.item}' pertenece a un "
                    "funcionario o cargo archivado."
                )

            existing.add(key)

            
            # Utilizar el ítem vinculado a la meta original.
            item = source.measurement_item

            if item is None:
                raise ValidationError(
                    f"La meta '{source.item}' no tiene un ítem "
                    "del catálogo identificado. Debe revisarse "
                    "antes de copiarla."
                )

            if item.deleted_at is not None or not item.is_active:
                raise ValidationError(
                    f"El ítem '{item.code} - {item.name}' "
                    "no está activo y no puede asignarse "
                    "a una nueva meta."
                )

            if item.unit != source.unit:
                raise ValidationError(
                    f"La unidad del ítem '{item.code}' "
                    "no coincide con la meta original."
                )


            copied_goal = Goal(
                period=period,
                employee=source.employee,
                position=source.position,
                measurement_item=item,
                item=source.item,
                objective_value=source.objective_value,
                required_evidence_count=source.required_evidence_count,
                unit=source.unit,
                weight=source.weight,
            )

            copied_goal.full_clean()
            copied_goal.save()

def get_period_list_context(request):
    periods = Period.objects.filter(
        deleted_at__isnull=True
    )

    query = request.GET.get("q", "").strip()

    if query:
        periods = periods.filter(
            Q(status__icontains=query)
            | Q(parameters_version__icontains=query)
        )

    selected_status = request.GET.get("status", "")

    if selected_status:
        periods = periods.filter(
            status=selected_status
        )

    order = resolve_order(
        request,
        PERIOD_COLUMNS,
        "-start_date"
    )

    page, querystring = paginate(
        request,
        periods.order_by(order)
    )
    all_periods = Period.objects.filter(
        deleted_at__isnull=True
    )

    return {
        "page": page,
        "headers": build_headers(
            request,
            PERIOD_COLUMNS,
            order
        ),
        "query": query,
        "selected_status": selected_status,
        "statuses": (
            Period.objects.filter(
                deleted_at__isnull=True
            )
            .order_by("status")
            .values_list("status", flat=True)
            .distinct()
        ),
        "querystring": querystring,
                "total_periods": all_periods.count(),

        "active_periods": all_periods.filter(
            status=Period.Status.ACTIVE
        ).count(),

        "closed_periods": all_periods.filter(
            status=Period.Status.CLOSED
        ).count(),
    }




@access("planning_measurements.view_period")
def period_list(request):
    periods = Period.objects.filter(deleted_at__isnull=True)

    if request.method == "POST":
        run_bulk_delete(request, periods)
        return redirect(request.get_full_path())

    query = request.GET.get("q", "").strip()
    if query:
        periods = periods.filter(
            Q(status__icontains=query) |
            Q(parameters_version__icontains=query)
        )

    selected_status = request.GET.get("status", "")
    if selected_status:
        periods = periods.filter(status=selected_status)

    order = resolve_order(request, PERIOD_COLUMNS, "-start_date")
    page, querystring = paginate(request, periods.order_by(order))

    base_periods = Period.objects.filter(deleted_at__isnull=True)

    context = {
        "page": page,
        "headers": build_headers(request, PERIOD_COLUMNS, order),
        "query": query,
        "selected_status": selected_status,
        "statuses": base_periods.order_by("status")
        .values_list("status", flat=True)
        .distinct(),
        "querystring": querystring,

        # NUEVO
        "total_periods": base_periods.count(),
        "active_periods": base_periods.filter(
            Q(status="Active") | Q(status="Activo")
        ).count(),
        "closed_periods": base_periods.filter(
            Q(status="Closed") | Q(status="Cerrado")
        ).count(),
        "can_archive_closed_period": (
            request.user.is_superuser or request.user.user_permissions.filter(
                content_type__app_label="planning_measurements", codename="delete_closed_period"
            ).exists()
        ),
    }

    return render(request, "planning/period_list.html", context)



def render_period_form(
    request,
    form,
    formset,
    title,
    period,
    readonly,
    can_add_goal,
    can_remove_goal=False,
):
    context = get_period_list_context(request)

    context.update({
        "form": form,
        "formset": formset,
        "title": title,
        "period": period,
        "readonly": readonly,
        "can_add_goal": can_add_goal and not readonly,
        "can_remove_goal": can_remove_goal and not readonly,

        "available_goal_sources": (
            available_goal_sources(request.user, period)
            if can_add_goal and not readonly
            else []
        ),

        "selected_existing_ids": (
            request.POST.getlist("existing_goal_ids")
            if request.method == "POST"
            else []
        ),

        "selected_remove_ids": (
            request.POST.getlist("remove_goal_ids")
            if request.method == "POST"
            else []
        ),
        "can_view_goals": request.user.has_perm(
            "planning_measurements.view_goal"
        ),
        "open_modal": True,
        "modal_action": request.path,
    })

    return render(
        request,
        "planning/period_list.html",
        context,
    )




@access("planning_measurements.add_period")
def period_create(request):
    can_add_goal = (
        request.user.has_perm(
            "planning_measurements.add_goal"
        )
        and request.user.has_perm(
            "planning_measurements.view_goal"
        )
    )

    period = Period()

    form = PeriodForm(
        request.POST or None,
        instance=period,
    )

    formset = goal_formset(can_add_goal, 0)(
        request.POST or None,
        instance=period,
        queryset=Goal.objects.none(),
        form_kwargs={"user": request.user},
    )

    if (
        request.method == "POST"
        and form.is_valid()
        and formset.is_valid()
    ):
        try:
            with transaction.atomic():
                form.save()
                formset.save()
                if (
                    request.POST.getlist("existing_goal_ids")
                    and period.status == Period.Status.CLOSED
                ):
                    raise ValidationError(
                        "Crea el período como Activo antes "
                        "de asignar metas existentes."
                    )

                apply_goal_assignments(
                    request,
                    period,
                    may_add=can_add_goal,
                    may_remove=False,
                )

                if form.cleaned_data["status"] == Period.Status.CLOSED:
                    validate_period_weights(period)

        except InvalidPeriodWeights as exc:
            form.add_error("status", str(exc))
        except ValidationError as exc:
            form.add_error(None, exc)

        else:
            messages.success(
                request,
                "Período creado correctamente."
            )

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
        "Nuevo período",
        None,
        False,
        can_add_goal,
    )




@access("planning_measurements.view_period")
def period_edit(request, period_id):
    period = get_object_or_404(
        Period,
        pk=period_id,
        deleted_at__isnull=True,
    )

    user = request.user

    
    # Reapertura autorizada del período
    if request.method == "POST" and request.POST.get("_action") == "reopen":
        from monitoring_traceability.models import Audit

        if not user.has_perm("planning_measurements.change_period"):
            raise PermissionDenied

        motivo = request.POST.get("reason", "").strip()

        if not motivo or len(motivo) > 500:
            messages.error(request, "Indica un motivo válido.")
            return redirect("planning:period_list")

        empleado = getattr(
            getattr(user, "profile", None), "employee", None
        )
        if empleado is None:
            raise PermissionDenied("La cuenta necesita un funcionario asociado.")

        with transaction.atomic():
            periodo = get_object_or_404(
                Period.objects.select_for_update(),
                pk=period_id,
                deleted_at__isnull=True,
            )

            if periodo.status != Period.Status.CLOSED:
                messages.warning(request, "El período no está cerrado.")
                return redirect("planning:period_list")

            periodo.status = Period.Status.ACTIVE
            periodo.save(update_fields=["status", "updated_at"])

            Audit.objects.create(
                user=empleado,
                event="Reopened Period",
                entity="Period",
                object_identifier=str(periodo.pk),
                previous_value={"status": "Closed"},
                new_value={
                    "status": "Active",
                    "motivo": motivo,
                    "editado_por": user.get_username(),
                },
            )

        messages.success(request, "Período reabierto correctamente.")
        return redirect("planning:period_list")


    can_change = (
        user.has_perm(
            "planning_measurements.change_period"
        )
        and period.status != Period.Status.CLOSED
    )

    can_view_goals = user.has_perm(
        "planning_measurements.view_goal"
    )

    can_change_goal = (
        can_view_goals
        and user.has_perm(
            "planning_measurements.change_goal"
        )
    )

    can_add_goal = (
        can_view_goals
        and user.has_perm(
            "planning_measurements.add_goal"
        )
    )

    if request.method == "POST" and (
        not can_change
        or request.GET.get("view") == "1"
    ):
        raise PermissionDenied

    goals = (
        scoped_goals(user).filter(period=period)
        if can_view_goals
        else Goal.objects.none()
    )

    form = PeriodForm(
        request.POST or None,
        instance=period,
    )

    formset = goal_formset(
        can_add_goal,
        goals.count(),
    )(
        request.POST or None,
        instance=period,
        queryset=goals,
        form_kwargs={"user": user},
    )

    readonly = (
        not can_change
        or request.GET.get("view") == "1"
    )

    if readonly:
        for field in form.fields.values():
            field.disabled = True

        disable_formset(formset)

    elif not can_change_goal:
        disable_formset(
            formset,
            only_existing=True,
        )

    if (
        request.method == "POST"
        and formset.is_valid()
        and form.is_valid()
    ):
        try:
            with transaction.atomic():

                # Guardar las metas mientras el período
                # todavía se encuentra abierto.
                if can_change_goal or can_add_goal:
                    formset.save()
                    apply_goal_assignments(
                        request,
                        period,
                        may_add=can_add_goal,
                        may_remove=can_change_goal,
                    )

                # Comprobar ponderadores antes del cierre.
                if form.cleaned_data["status"] == Period.Status.CLOSED:
                    validate_period_weights(period)

                # Guardar los cambios del período.
                form.save()

        except InvalidPeriodWeights as exc:
            form.add_error("status", str(exc))
        except ValidationError as exc:
            form.add_error(None, exc)

        else:
            messages.success(
                request,
                "Período modificado correctamente."
            )

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
        can_change_goal,
    )

@access("planning_measurements.view_period")
def period_assign_existing_goals(request, period_id):
    """Copia metas existentes a un período, conservando las originales."""

    if not request.user.has_perm("planning_measurements.add_goal"):
        raise PermissionDenied

    period = get_object_or_404(
        Period,
        pk=period_id,
        deleted_at__isnull=True
    )

    ensure_open_period(period)

    # Metas que el usuario puede consultar según su delegación.
    sources = scoped_goals(request.user).exclude(period=period)

    already_assigned = set(
        scoped_goals(request.user)
        .filter(
            period=period,
            measurement_item__isnull=False,
        )
        .values_list(
            "employee_id",
            "position_id",
            "measurement_item_id",
        )
    )

    available = [
        goal
        for goal in sources.order_by(
            "-period__start_date", "item", "pk"
        )
        if (
            goal.measurement_item_id is not None
            and (
                goal.employee_id,
                goal.position_id,
                goal.measurement_item_id,
            ) not in already_assigned
        )
    ]

    if request.method == "POST":
        selected_ids = request.POST.getlist("goal_ids")

        if (
            not selected_ids
            or len(selected_ids) > 100
            or len(set(selected_ids)) != len(selected_ids)
        ):
            messages.error(
                request,
                "Selecciona entre 1 y 100 metas distintas."
            )

        elif not all(value.isdecimal() for value in selected_ids):
            messages.error(
                request,
                "La selección contiene identificadores inválidos."
            )

        else:
            with transaction.atomic():

                locked_period = (
                    Period.objects
                    .select_for_update()
                    .get(pk=period.pk)
                )

                ensure_open_period(locked_period)

                selected = list(
                    sources.filter(pk__in=selected_ids)
                )

                if len(selected) != len(selected_ids):
                    messages.error(
                        request,
                        "Alguna meta seleccionada no está disponible."
                    )

                else:
                    errors = []

                                        
                    current = set(
                        Goal.objects.filter(
                            period=locked_period,
                            deleted_at__isnull=True,
                            measurement_item__isnull=False,
                        ).values_list(
                            "employee_id",
                            "position_id",
                            "measurement_item_id",
                        )
                    )


                    new_goals = []

                    for source in selected:                   
                        key = (
                            source.employee_id,
                            source.position_id,
                            source.measurement_item_id,
                        )

                        if key in current:
                            errors.append(
                                f"La meta '{source.item}' ya existe "
                                "para ese funcionario."
                            )
                            continue

                        current.add(key)

                        
                        # Identifica el ítem por su relación, no por el nombre.
                        item = source.measurement_item

                        if item is None:
                            errors.append(
                                f"La meta '{source.item}' no tiene un ítem "
                                "del catálogo identificado. Debe revisarse "
                                "antes de copiarla."
                            )
                            continue

                        if item.deleted_at is not None or not item.is_active:
                            errors.append(
                                f"El ítem '{item.code} - {item.name}' "
                                "no está activo y no puede copiarse."
                            )
                            continue

                        if item.unit != source.unit:
                            errors.append(
                                f"La unidad del ítem '{item.code}' "
                                "no coincide con la meta original."
                            )
                            continue


                        copy = Goal(
                            period=locked_period,
                            employee=source.employee,
                            position=source.position,
                            measurement_item=item,
                            item=source.item,
                            objective_value=source.objective_value,
                            required_evidence_count=source.required_evidence_count,
                            unit=source.unit,
                            weight=source.weight
                        )

                        try:
                            copy.full_clean()

                        except ValidationError as exc:
                            errors.append(
                                f"{source.item}: "
                                f"{', '.join(exc.messages)}"
                            )

                        else:
                            new_goals.append(copy)

                    if errors:
                        for error in errors[:5]:
                            messages.error(request, error)

                        messages.error(
                            request,
                            "No se copió ninguna meta; "
                            "revisa la selección."
                        )

                    else:
                        for copy in new_goals:
                            copy.save()

                        messages.success(
                            request,
                            f"{len(new_goals)} meta(s) "
                            "asignada(s) correctamente."
                        )

                        return redirect(
                            "planning:period_edit",
                            period_id=period.pk
                        )

    return render(
        request,
        "planning/period_assign_goals.html",
        {
            "period": period,
            "available_goals": available,
        }
    )



@access("planning_measurements.delete_period")
def period_delete(request, period_id):
    """Archiva un período abierto o cerrado si no tiene metas activas."""

    period = get_object_or_404(
        Period,
        pk=period_id,
        deleted_at__isnull=True,
    )

    if not may_archive_period(request.user, period):
        raise PermissionDenied("No tienes el permiso individual necesario para un período cerrado.")

    if request.method == "POST":
        with transaction.atomic():
            period = get_object_or_404(
                Period.objects.select_for_update(),
                pk=period_id,
                deleted_at__isnull=True,
            )
            if not may_archive_period(request.user, period):
                raise PermissionDenied("No puedes archivar este período cerrado.")

            if period.goals.exists():
                raise PermissionDenied(
                    "No se puede eliminar este período porque "
                    "tiene metas asociadas. Debes conservar "
                    "el historial de esas metas."
                )

            now = timezone.now()
            period.deleted_at = now
            period.save(
                update_fields=["deleted_at", "updated_at"]
            )
            PeriodArchiveLog.objects.create(
                period=period, user=request.user,
                was_closed=period.status == Period.Status.CLOSED,
            )

        messages.success(
            request,
            "Período archivado correctamente."
        )
        return redirect("planning:period_list")

    return render(
        request,
        "planning/period_confirm_delete.html",
        {
            "period": period,
            "goals_count": period.goals.filter(
                deleted_at__isnull=True
            ).count(),
        },
    )



# ---------- METAS ----------

GOAL_COLUMNS = [
    ("Ítem", "item"),
    ("Período", "period__start_date"),
    ("Funcionario", "employee__name"),
    ("Cargo", "position__position_name"),
    ("Valor objetivo", "objective_value"),
    ("Evidencias requeridas", "required_evidence_count"),
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
    total_goals = base_goals.count()

    active_goals = base_goals.filter(
        period__status=Period.Status.ACTIVE
    ).count()

    closed_goals = base_goals.filter(
        period__status=Period.Status.CLOSED
    ).count()

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
        "total_goals": total_goals,
        "active_goals": active_goals,
        "closed_goals": closed_goals,
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
    editable_scope = scoped_goals(request.user, "planning_measurements.change_goal").filter(pk=goal_id).exists()
    can_change = (
        request.user.has_perm(
            "planning_measurements.change_goal"
        )
        and goal.period.status != Period.Status.CLOSED
        and editable_scope
    )
    if request.method == "POST" and (
        not can_change
        or request.GET.get("view") == "1"
    ):
        raise PermissionDenied

    form = GoalForm(request.POST or None, instance=goal, user=request.user)
    readonly = (
        not can_change
        or request.GET.get("view") == "1"
    )
    if readonly:
        for field in form.fields.values():
            field.disabled = True

    if request.method == "POST" and form.is_valid():
        campos = (
            "period_id",
            "employee_id",
            "position_id",
            "measurement_item_id",
            "item",
            "objective_value",
            "required_evidence_count",
            "unit",
            "weight",
        )

        # Obtener los valores guardados antes de modificar la meta.
        anterior = Goal.objects.get(pk=goal.pk)

        form.instance._audit_before = {
            campo: str(getattr(anterior, campo))
            for campo in campos
        }

        form.instance._audit_actor = request.user.get_username()

        with transaction.atomic():
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
    # Permite eliminar al superusuario o a quienes tengan
    # el permiso delete_goal asignado directamente o mediante un grupo.
    if not (
        request.user.is_superuser
        or request.user.has_perm("planning_measurements.delete_goal")
    ):
        raise PermissionDenied(
            "No tienes permiso para eliminar metas."
        )

    # Respeta la delegación del usuario y excluye metas archivadas.
    goal = get_object_or_404(
        scoped_goals(request.user, "planning_measurements.delete_goal"),
        pk=goal_id
    )

    if goal.period.status == Period.Status.CLOSED:
        raise PermissionDenied(
            "No puedes eliminar metas de un período cerrado. "
            "Primero debe realizarse una reapertura autorizada."
        )


    # No bloqueamos por estado cerrado: ese es el cambio solicitado.
    # Protegemos las referencias de otros módulos.
    if goal.activities.exists() or goal.indicators.exists():
        raise PermissionDenied(
            "No se puede eliminar esta meta porque tiene "
            "actividades o indicadores asociados."
        )

    if request.method == "POST":
        goal.deleted_at = timezone.now()
        goal.save(update_fields=["deleted_at", "updated_at"])

        messages.success(
            request,
            "Meta eliminada correctamente."
        )
        return redirect("planning:goal_list")

    return render(
        request,
        "planning/goal_confirm_delete.html",
        {"goal": goal},
    )



# ---------- CATÁLOGO DE ÍTEMS ----------



def get_item_list_context(request):
    """Prepara filtros, contadores y paginación del catálogo."""

    all_items = MeasurementItem.objects.filter(
        deleted_at__isnull=True
    )

    # Contadores generales de ítems visibles.
    total_items = all_items.count()

    active_items = all_items.filter(
        is_active=True
    ).count()

    inactive_items = all_items.filter(
        is_active=False
    ).count()

    # Filtros.
    query = request.GET.get("q", "").strip()
    selected_type = request.GET.get("item_type", "")
    selected_status = request.GET.get("status", "")

    items = all_items

    if query:
        items = items.filter(
            Q(code__icontains=query)
            | Q(name__icontains=query)
            | Q(description__icontains=query)
        )

    if selected_type in ("quantitative", "percentage"):
        items = items.filter(
            item_type=selected_type
        )

    if selected_status == "active":
        items = items.filter(
            is_active=True
        )

    elif selected_status == "inactive":
        items = items.filter(
            is_active=False
        )

    items = items.order_by("code")

    page, querystring = paginate(request, items)

    return {
        "page_size": request.session.get("planning_page_size", PAGE_SIZE),
        "page_size_options": PAGE_SIZE_OPTIONS,
        "page": page,
        "query": query,
        "querystring": querystring,

        "selected_type": selected_type,
        "selected_status": selected_status,

        "total_items": total_items,
        "active_items": active_items,
        "inactive_items": inactive_items,
    }




@access("planning_measurements.view_measurementitem")
def item_export(request):
    """Mismo alcance y filtros que el listado de ítems."""
    items = MeasurementItem.objects.filter(deleted_at__isnull=True)
    query = request.GET.get("q", "").strip()
    if query:
        items = items.filter(Q(code__icontains=query) | Q(name__icontains=query) | Q(description__icontains=query))
    selected_type = request.GET.get("item_type", "")
    if selected_type in ("quantitative", "percentage"):
        items = items.filter(item_type=selected_type)
    selected_status = request.GET.get("status", "")
    if selected_status == "active":
        items = items.filter(is_active=True)
    elif selected_status == "inactive":
        items = items.filter(is_active=False)
    return workbook_response("items_medicion.xlsx", ["Código", "Nombre", "Descripción", "Tipo", "Unidad", "Estado"], [
        (obj.code, obj.name, obj.description, obj.get_item_type_display(), obj.unit, "Activo" if obj.is_active else "Inactivo")
        for obj in items.order_by("code")
    ])


@access("planning_measurements.view_measurementitem")
def item_list(request):
    context = get_item_list_context(request)

    return render(
        request,
        "planning/item_list.html",
        context,
    )




@access("planning_measurements.add_measurementitem")
def item_create(request):
    """Crear ítems mediante una ventana modal."""

    form = MeasurementItemForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        form.save()

        messages.success(
            request,
            "Ítem creado correctamente."
        )

        return redirect("planning:item_list")

    context = get_item_list_context(request)

    context.update({
        "form": form,
        "title": "Nuevo ítem",
        "readonly": False,
        "open_modal": True,
        "modal_action": request.path,
    })

    return render(
        request,
        "planning/item_list.html",
        context,
    )




@access("planning_measurements.view_measurementitem")
def item_detail(request, item_id):
    """Mostrar un ítem en un modal de solo lectura."""

    item = get_object_or_404(
        MeasurementItem,
        pk=item_id,
        deleted_at__isnull=True,
    )

    form = MeasurementItemForm(instance=item)

    for field in form.fields.values():
        field.disabled = True

    context = get_item_list_context(request)

    context.update({
        "form": form,
        "title": "Detalle del ítem",
        "readonly": True,
        "open_modal": True,
        "modal_action": request.path,
    })

    return render(
        request,
        "planning/item_list.html",
        context,
    )




@access("planning_measurements.change_measurementitem")
def item_edit(request, item_id):
    """Modificar un ítem desde una ventana modal."""

    item = get_object_or_404(
        MeasurementItem,
        pk=item_id,
        deleted_at__isnull=True,
    )

    form = MeasurementItemForm(
        request.POST or None,
        instance=item,
    )

    if request.method == "POST" and form.is_valid():
        form.save()

        messages.success(
            request,
            "Ítem actualizado correctamente."
        )

        return redirect("planning:item_list")

    context = get_item_list_context(request)

    context.update({
        "form": form,
        "title": "Modificar ítem",
        "readonly": False,
        "open_modal": True,
        "modal_action": request.path,
    })

    return render(
        request,
        "planning/item_list.html",
        context,
    )



@access("planning_measurements.delete_measurementitem")
@require_POST
def item_delete(request, item_id):
    """Desactiva un ítem sin eliminarlo físicamente."""

    item = get_object_or_404(
        MeasurementItem,
        pk=item_id,
        deleted_at__isnull=True,
    )

    item.is_active = False
    item.deleted_at = timezone.now()

    item.save(
        update_fields=[
            "is_active",
            "deleted_at",
            "updated_at",
        ]
    )

    messages.success(
        request,
        "Ítem desactivado correctamente."
    )

    return redirect("planning:item_list")
