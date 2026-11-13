from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.views.decorators.http import require_POST
from django.utils.http import url_has_allowed_host_and_scheme
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from accounts.services import sync_employee, sync_position, validate_employee_role_scope
from accounts.permissions import allowed_delegation_ids

from .forms import (
    DelegationForm,
    EmployeeForm,
    OrganizationRoleForm,
    PositionForm,
    mark_invalid_fields,
)
from .models import (
    Delegation,
    EmployeeHistory,
    Employee,
    PositionFunction,
    DelegationResponsibilityLog,
    OrganizationRole,
)
from .exports import workbook_response
from .permission_labels import catalog_permission_queryset
from .employee_history import (
    employee_snapshot, record_employee_change, organization_snapshot,
    record_organization_action,
)

from django.db import IntegrityError

from accounts.forms import AccountCreateForm
from accounts.services import create_user_account, sync_user_groups
from django.db import IntegrityError, transaction

from accounts.forms import AccountCreateForm, AccountEditForm
from accounts.models import UserProfile





ORG_PAGE_SIZE_DEFAULT = 25
ORG_PAGE_SIZE_CHOICES = (10, 25, 50)


def organization_page_size(request):
    size = request.session.get("organization_page_size", ORG_PAGE_SIZE_DEFAULT)
    return size if size in ORG_PAGE_SIZE_CHOICES else ORG_PAGE_SIZE_DEFAULT


@login_required
@require_POST
def set_page_size(request):
    try:
        size = int(request.POST.get("page_size", ""))
    except (TypeError, ValueError):
        size = None
    if size in ORG_PAGE_SIZE_CHOICES:
        request.session["organization_page_size"] = size
        messages.success(request, "Preferencia de visualización actualizada.")
    else:
        messages.error(request, "Selecciona una cantidad válida de registros.")
    next_url = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(
        url=next_url, allowed_hosts={request.get_host()},
        require_https=request.is_secure()
    ):
        next_url = reverse("organization:employee_list")
    else:
        parsed = urlsplit(next_url)
        query = [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key not in {"modal", "id"}
        ]
        next_url = urlunsplit((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urlencode(query),
            "",
        ))
    return redirect(next_url)


def organization_pagination(request, queryset):
    page = Paginator(queryset, organization_page_size(request)).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return page, params.urlencode()


def organization_paging_context(request):
    return {"page_size": organization_page_size(request),
            "page_size_options": ORG_PAGE_SIZE_CHOICES}


def user_filter_delegation(users, value):
    if value and value.isdecimal():
        users = users.filter(
            Q(profile__authorized_delegations__pk=value)
            | Q(profile__authorized_delegations__isnull=True,
                profile__delegation_id=value)
        ).distinct()
    return users


def organization_access(permission):
    def decorator(view):
        view = permission_required(permission, raise_exception=True)(view)
        return login_required(view)

    return decorator


def _delegation_id(user):
    profile = getattr(user, "profile", None)
    if not profile:
        return None
    return profile.delegation_id or profile.authorized_delegations.values_list(
        "pk", flat=True
    ).first()


def _delegation_ids(
    user,
    permission=None,
    *,
    active_only=True,
    respect_role_scope=True,
):
    allowed = allowed_delegation_ids(
        user,
        permission,
        active_only=active_only,
    )
    if respect_role_scope or user.is_superuser or allowed is None:
        return allowed
    created_ids = Delegation.objects.filter(
        created_by_id=user.pk,
        deleted_at__isnull=True,
    ).values_list("pk", flat=True)
    return set(allowed or set()).union(created_ids)


def _scoped_queryset(
    queryset,
    user,
    relation,
    permission=None,
    *,
    active_only=True,
    respect_role_scope=True,
):
    queryset = queryset.filter(deleted_at__isnull=True)
    if user.is_superuser:
        return queryset
    delegation_ids = _delegation_ids(
        user,
        permission,
        active_only=active_only,
        respect_role_scope=respect_role_scope,
    )
    if not delegation_ids:
        return queryset.none()
    if relation == "global_position_catalog":
        # Los cargos son globales y pueden no estar aún asignados a empleados.
        return queryset
    if relation == "pk":
        return queryset.filter(pk__in=delegation_ids)
    return queryset.filter(**{f"{relation}__in": delegation_ids})


def _query(value):
    return value.strip() if value else ""


def _statuses(queryset):
    return queryset.order_by("status").values_list(
        "status", flat=True
    ).distinct()


def _require_permission(user, action, model_name):
    permission = f"organization.{action}_{model_name}"
    if not user.has_perm(permission):
        raise PermissionDenied


def _limit_form_choices(
    form,
    user,
    permission=None,
    *,
    respect_role_scope=True,
):
    if isinstance(form, EmployeeForm) and not user.is_superuser:
        permitted = _delegation_ids(
            user,
            permission,
            active_only=False,
            respect_role_scope=respect_role_scope,
        )
        form.fields["delegation"].queryset = Delegation.objects.filter(
            pk__in=permitted, deleted_at__isnull=True,
        )
        form.fields["user_account"].queryset = (
            form.fields["user_account"].queryset.filter(
                Q(authorized_delegations__pk__in=permitted)
                | Q(delegation_id__in=permitted)
            ).distinct()
        )
        form.fields["authorized_delegations"].queryset = (
            form.fields["authorized_delegations"].queryset.filter(
                pk__in=permitted
            )
        )
        # Los roles del cargo no se filtran por delegación del rol.
        # Su ámbito de ejecución se limita en accounts.permissions a las
        # delegaciones autorizadas del usuario.



def _sync_employee_account(employee, form):
    """Crea o actualiza el acceso que pertenece al empleado."""
    username = form.cleaned_data.get("username", "").strip()
    if not username:
        return

    User = get_user_model()
    profile = UserProfile.objects.filter(
        employee=employee,
        deleted_at__isnull=True,
    ).select_related("user").first()
    if profile:
        user = profile.user
    else:
        user = User()

    user.username = username
    user.email = form.cleaned_data["email"].strip()
    user.first_name = employee.name
    user.last_name = ""
    user.is_staff = False
    user.is_superuser = False
    password = form.cleaned_data.get("password1")
    if password:
        user.set_password(password)
    user.save()

    delegations = form.cleaned_data.get("authorized_delegations")
    primary = employee.delegation
    profile, _ = UserProfile.objects.update_or_create(
        user=user,
        defaults={
            "employee": employee,
            "employee_code": form.cleaned_data["employee_code"].strip(),
            "delegation": primary,
            "deleted_at": None,
        },
    )
    profile.authorized_delegations.set(delegations or [primary])
    # El formulario de Empleados es el origen principal de la fotografía.
    # Los dos campos ImageField apuntan al mismo archivo (sin duplicarlo).
    # Recuperar una foto histórica de la cuenta si el empleado aún no tiene.
    if employee.profile_photo:
        if profile.profile_photo.name != employee.profile_photo.name:
            profile.profile_photo = employee.profile_photo.name
            profile.save(update_fields=["profile_photo", "updated_at"])
    elif profile.profile_photo:
        employee.profile_photo = profile.profile_photo.name
        employee.save(update_fields=["profile_photo", "updated_at"])
    # El cargo es la única fuente de roles para una cuenta vinculada.
    sync_user_groups(user)


def _handle_mutations(
    request,
    records,
    form_class,
    model_name,
    object_label,
):
    form = None
    modal_action = ""
    instance_id = None

    if request.method == "POST":
        modal_action = request.POST.get("action", "")
        instance_id = request.POST.get("object_id")
        if modal_action == "delete":
            _require_permission(request.user, "delete", model_name)
            allowed = _delegation_ids(
                request.user,
                f"organization.delete_{model_name}",
                active_only=False,
                respect_role_scope=model_name not in ("employee", "delegation"),
            )
            if not request.user.is_superuser:
                if model_name == "positionfunction":
                    # Catálogo global: su permiso explícito de eliminación autoriza la operación.
                    record = get_object_or_404(records, pk=instance_id)
                else:
                    relation = "delegation_id" if model_name == "employee" else "pk"
                    record = get_object_or_404(records.filter(**{f"{relation}__in": allowed}), pk=instance_id)
            else:
                record = get_object_or_404(records, pk=instance_id)
            if isinstance(record, Employee) and record.responsible_for_delegations.exists():
                messages.error(request, "Cambia antes el responsable de la delegación.")
                return None
            if isinstance(record, Delegation) and (
                record.employees.exists() or record.user_profiles.exists() or record.organization_roles.exists()
            ):
                messages.error(request, "No se puede archivar esta delegación mientras tenga empleados, usuarios o roles vinculados.")
                return None
            previous_employee = employee_snapshot(record) if isinstance(record, Employee) else None
            previous_action = organization_snapshot(record)
            with transaction.atomic():
                record.deleted_at = timezone.now()
                record.save(update_fields=["deleted_at", "updated_at"])
                if isinstance(record, Employee):
                    # Archivar no puede dejar una cuenta con permisos heredados.
                    sync_employee(record)
                    record_employee_change(record, request.user, "Desactivación", previous_employee)
                elif isinstance(record, PositionFunction):
                    sync_position(record)
                record_organization_action(
                    request.user,
                    {"employee": "Empleados", "delegation": "Delegaciones",
                     "positionfunction": "Cargos y Funciones"}[model_name],
                    "Desactivó", record, previous_action,
                )
            messages.success(
                request,
                f"{object_label.capitalize()} archivado correctamente.",
            )
            return None

        if modal_action not in ("create", "edit"):
            messages.error(request, "La operación solicitada no es válida.")
            return None

        permission_action = "add" if modal_action == "create" else "change"
        _require_permission(request.user, permission_action, model_name)
        # Los permisos add/change del cargo son explícitos. No usar is_superuser.
        # Al crear una delegación, exigir igualmente el permiso específico add_delegation.
        instance = None
        if modal_action == "edit":
            targets = records
            if not request.user.is_superuser and model_name in (
                "employee", "delegation"
            ):
                relation = "delegation_id" if model_name == "employee" else "pk"
                targets = targets.filter(
                    **{
                        f"{relation}__in": _delegation_ids(
                            request.user,
                            f"organization.change_{model_name}",
                            active_only=False,
                        respect_role_scope=False,
                    )
                    }
                )
            instance = get_object_or_404(targets, pk=instance_id)
        previous_employee = employee_snapshot(instance) if isinstance(instance, Employee) else {}
        previous_action = organization_snapshot(instance) if instance is not None else {}
        form = form_class(request.POST, request.FILES, instance=instance)
        _limit_form_choices(
            form,
            request.user,
            f"organization.{permission_action}_{model_name}",
            respect_role_scope=model_name not in ("employee", "delegation"),
        )
        if form.is_valid():

            if isinstance(form, DelegationForm):
                with transaction.atomic():
                    previous_id = (Delegation.objects.select_for_update().filter(pk=instance.pk).values_list("responsible_id", flat=True).first() if instance else None)
                    if instance is None:
                        form.instance.created_by = request.user
                    saved = form.save()
                    if instance is None and not request.user.is_superuser:
                        profile = UserProfile.objects.filter(
                            user=request.user,
                            deleted_at__isnull=True,
                        ).first()
                        if profile is None:
                            raise PermissionDenied(
                                "El usuario creador no tiene un perfil activo."
                            )
                        profile.authorized_delegations.add(saved)
                    if saved.responsible_id != previous_id:
                        DelegationResponsibilityLog.objects.create(
                            delegation=saved,
                            previous_responsible_id=previous_id,
                            new_responsible_id=saved.responsible_id,
                            changed_by=request.user,
                        )

            elif isinstance(form, EmployeeForm):
                # Nadie puede elevar sus propios roles cambiándose de cargo.
                actor_employee_id = getattr(getattr(request.user, "profile", None), "employee_id", None)
                if actor_employee_id and instance and actor_employee_id == instance.pk:
                    old_role_ids = set(request.user.groups.values_list("pk", flat=True))
                    new_position = form.cleaned_data.get("position")
                    new_role_ids = (set(new_position.role_groups.values_list("pk", flat=True))
                                    if new_position else set())
                    if old_role_ids != new_role_ids:
                        raise PermissionDenied("No puedes modificar tus propios roles cambiando de cargo.")

                # No permitir otorgar mediante el cargo permisos que el actor no posee.
                selected_position = form.cleaned_data.get("position")
                if selected_position and not request.user.is_superuser:
                    granted = request.user.get_all_permissions()
                    for group in selected_position.role_groups.prefetch_related("permissions__content_type"):
                        if any(f"{permission.content_type.app_label}.{permission.codename}" not in granted
                               for permission in group.permissions.all()):
                            raise PermissionDenied("No puedes asignar un cargo con permisos superiores a los tuyos.")

                with transaction.atomic():

                    saved = form.save()

                    # Cuenta seleccionada para el funcionario.
                    profile = form.cleaned_data.get("user_account")

                    if profile:

                        # Vincular la cuenta si aún está disponible.
                        if profile.employee_id is None:
                            profile.employee = saved

                            profile.save(
                                update_fields=["employee", "updated_at"]
                            )

                    _sync_employee_account(saved, form)
                    # Reemplazar los grupos antiguos por los del cargo actual.
                    sync_employee(saved)
                    record_employee_change(
                        saved, request.user,
                        "Creación" if modal_action == "create" else "Modificación",
                        previous_employee,
                    )

            elif isinstance(form, PositionForm):
                # Impedir modificar los roles del cargo propio.
                actor_employee = getattr(getattr(request.user, "profile", None), "employee", None)
                if (instance is not None and actor_employee is not None
                    and actor_employee.position_id == instance.pk):
                    old_ids = set(instance.role_groups.values_list("pk", flat=True))
                    new_ids = set(form.cleaned_data["role_groups"].values_list("pk", flat=True))
                    if old_ids != new_ids:
                        raise PermissionDenied("No puedes modificar los roles de tu propio cargo.")
                if not request.user.is_superuser:
                    granted = request.user.get_all_permissions()
                    for group in form.cleaned_data["role_groups"].prefetch_related("permissions__content_type"):
                        if any(f"{permission.content_type.app_label}.{permission.codename}" not in granted
                               for permission in group.permissions.all()):
                            raise PermissionDenied("No puedes asignar a un cargo permisos superiores a los tuyos.")
                with transaction.atomic():
                    saved = form.save()
                    # Cambiar roles del cargo actualiza a todos sus empleados.
                    sync_position(saved)

            else:
                saved = form.save()
            record_organization_action(
                request.user,
                {"employee": "Empleados", "delegation": "Delegaciones",
                 "positionfunction": "Cargos y Funciones"}[model_name],
                "Creó" if modal_action == "create" else "Modificó", saved, previous_action,
            )
            verb = "creado" if modal_action == "create" else "actualizado"
            messages.success(
                request,
                f"{object_label.capitalize()} {verb} correctamente.",
            )
            return None
        mark_invalid_fields(form)
    else:
        modal_action = request.GET.get("modal", "")
        instance_id = request.GET.get("id")
        if modal_action == "create":
            _require_permission(request.user, "add", model_name)
            form = form_class()
        elif modal_action in ("edit", "view"):
            _require_permission(request.user, "view" if modal_action == "view" else "change", model_name)
            targets = records
            if (
                not request.user.is_superuser
                and model_name == "employee"
            ) or (
                not request.user.is_superuser
                and model_name == "delegation"
                and modal_action == "edit"
            ):
                relation = "delegation_id" if model_name == "employee" else "pk"
                targets = targets.filter(
                    **{
                        f"{relation}__in": _delegation_ids(
                            request.user,
                            f"organization.{('view' if modal_action == 'view' else 'change')}_{model_name}",
                            active_only=False,
                            respect_role_scope=model_name not in ("employee", "delegation"),
                        )
                    }
                )
            instance = get_object_or_404(targets, pk=instance_id)
            form = form_class(instance=instance)
            if modal_action == "view":
                for field in form.fields.values():
                    field.disabled = True
        else:
            return {"form": None, "modal_open": False}
        _limit_form_choices(
            form,
            request.user,
            "organization." + (
                "add" if modal_action == "create"
                else "view" if modal_action == "view"
                else "change"
            ) + "_" + model_name,
            respect_role_scope=model_name not in ("employee", "delegation"),
        )

    return {
        "form": form,
        "modal_open": True,
        "modal_action": modal_action,
        "modal_title": (
            f"Crear {object_label}" if modal_action == "create"
            else f"Ver {object_label}" if modal_action == "view"
            else f"Modificar {object_label}"
        ),
        "edit_confirmation": {
            "empleado": "¿Desea modificar el Empleado?",
            "delegación": "¿Desea modificar la Delegación?",
            "cargo": "¿Desea modificar el Cargo?",
        }[object_label],
        "object_id": instance_id if modal_action == "edit" else "",
    }


def _role_groups_for(user, action="view"):
    """Roles del catálogo, sin delegaciones por rol; requiere permiso funcional."""
    _require_permission(user, action, "organizationrole")
    if not user.is_superuser:
        authorized = allowed_delegation_ids(
            user, f"organization.{action}_organizationrole", active_only=False
        )
        if not authorized:
            return Group.objects.none()
    return Group.objects.filter(organization_role__isnull=False)


def _role_target(user, pk, action):
    group = get_object_or_404(_role_groups_for(user, action), pk=pk)
    if not user.is_superuser and action in ("change", "delete"):
        if action == "change" and user.groups.filter(pk=group.pk).exists():
            raise PermissionDenied(
                "No puedes modificar un rol que tienes asignado."
            )
        if action == "delete":
            own = user.get_all_permissions()
            if any(
                f"{p.content_type.app_label}.{p.codename}" not in own
                for p in group.permissions.select_related("content_type")
            ):
                raise PermissionDenied(
                    "El rol contiene permisos fuera de tu autorización."
                )

    return group


@login_required
def role_list(request):
    catalog_permission_ids = catalog_permission_queryset(
        Permission.objects.all()
    ).values("pk")
    groups = _role_groups_for(request.user).select_related(
        "organization_role__delegation"
    ).annotate(
        permission_count=Count(
            "permissions",
            filter=Q(permissions__pk__in=catalog_permission_ids),
            distinct=True,
        ),
        account_count=Count("user", distinct=True),
        employee_count=Count("assigned_employees", distinct=True),
    ).order_by("name")
    own_role_ids = set(
        request.user.groups.values_list("pk", flat=True)
    )
    search = _query(request.GET.get("q"))
    if search:
        groups = groups.filter(
            Q(name__icontains=search)
            | Q(organization_role__description__icontains=search)
        ).distinct()
    form = None
    modal_action = ""
    object_id = ""
    modal_open = False

    if request.method == "POST":
        modal_action = request.POST.get("action", "")
        object_id = request.POST.get("object_id", "")
        if modal_action == "delete":
            group = _role_target(request.user, object_id, "delete")
            if (
                group.positions.exists()
                or group.role_positions.exists()
                or group.user_set.exists()
                or group.assigned_employees.exists()
            ):
                messages.error(
                    request,
                    "No se puede eliminar el rol mientras esté asignado a un cargo, empleado o usuario.",
                )
                return redirect("organization:role_list")
            previous_action = organization_snapshot(group)
            with transaction.atomic():
                record_organization_action(request.user, "Roles y Permisos", "Eliminó", group, previous_action)
                group.delete()
            messages.success(
                request,
                "Rol eliminado correctamente.",
            )
            return redirect("organization:role_list")

        if modal_action not in ("create", "edit"):
            messages.error(request, "La operación solicitada no es válida.")
            return redirect("organization:role_list")

        _require_permission(request.user, "add" if modal_action == "create" else "change", "organizationrole")
        instance = None
        if modal_action == "edit":
            instance = _role_target(request.user, object_id, "change")
        previous_action = organization_snapshot(instance) if instance is not None else {}
        form = OrganizationRoleForm(request.POST, group=instance, actor=request.user)
        if form.is_valid():
            with transaction.atomic():
                saved_role = form.save()
                record_organization_action(
                    request.user, "Roles y Permisos",
                    "Creó" if modal_action == "create" else "Modificó",
                    saved_role, previous_action,
                )
            messages.success(
                request,
                "Rol y permisos guardados correctamente.",
            )
            return redirect("organization:role_list")
        mark_invalid_fields(form)
        modal_open = True
    else:
        modal_action = request.GET.get("modal", "")
        object_id = request.GET.get("id", "")
        if modal_action == "create":
            _require_permission(request.user, "add", "organizationrole")
            form = OrganizationRoleForm(actor=request.user)
            modal_open = True
        elif modal_action in ("edit", "view"):
            if modal_action == "edit":
                group = _role_target(request.user, object_id, "change")
            else:
                group = _role_target(request.user, object_id, "view")
            form = OrganizationRoleForm(group=group, actor=request.user if modal_action == "edit" else None)
            if modal_action == "view":
                for field in form.fields.values():
                    field.disabled = True
            modal_open = True

    context = {
        "roles": groups,
        "total_roles": groups.count(),
        "total_role_permissions": sum(
            role.permission_count for role in groups
        ),
        "form": form,
        "modal_open": modal_open,
        "modal_action": modal_action,
        "modal_title": "Crear rol" if modal_action == "create" else "Ver rol" if modal_action == "view" else "Modificar rol",
        "edit_confirmation": "¿Desea modificar el rol y sus permisos?",
        "object_id": object_id if modal_action == "edit" else "",
        "active_page": "roles",
        "page_title": "Roles y Permisos",
        "page_description": "Crea roles y define los permisos que se asignarán a empleados y cuentas.",
        "page_icon": "bi-shield-lock",
        "search": search,
        "own_role_ids": own_role_ids,
    }
    page, querystring = organization_pagination(request, groups)
    context["roles"] = page
    context["querystring"] = querystring
    context.update(organization_paging_context(request))
    return render(request, "organization/roles.html", context)


@login_required
def role_export(request):
    groups = _role_groups_for(request.user).select_related(
        "organization_role__delegation"
    ).order_by("name")
    search = _query(request.GET.get("q"))
    if search:
        groups = groups.filter(
            Q(name__icontains=search)
            | Q(organization_role__description__icontains=search)
        ).distinct()
    # Los roles son globales; el alcance de acceso se controla en cada cuenta.
    return workbook_response(
        "roles.xlsx",
        ["Rol", "Descripción", "Permisos"],
        [
            (
                group.name,
                getattr(getattr(group, "organization_role", None), "description", ""),
                group.permissions.count(),
            )
            for group in groups
        ],
    )


@organization_access("organization.view_employee")
def employee_list(request):
    records = _scoped_queryset(
        Employee.objects.select_related("delegation", "position").prefetch_related(
            "assigned_groups"
        ),
        request.user,
        "delegation_id",
        "organization.view_employee",
        active_only=False,
        respect_role_scope=False,
    )
    history_employee = None
    history_events = []
    performed_events = []
    if request.method == "GET" and request.GET.get("history"):
        history_employee = get_object_or_404(
            records, pk=request.GET["history"]
        )
        history_events = list(
            EmployeeHistory.objects.filter(employee=history_employee)
            .exclude(event__startswith="Acción: ")
            .select_related("actor")[:100]
        )
        performed_events = list(
            EmployeeHistory.objects.filter(employee=history_employee, event__startswith="Acción: ")
            .select_related("actor")[:100]
        )
    mutation_context = _handle_mutations(
        request,
        records,
        EmployeeForm,
        "employee",
        "empleado",
    )
    if mutation_context is None:
        return redirect("organization:employee_list")
    employees = records
    search = _query(request.GET.get("q"))
    status = _query(request.GET.get("status"))
    if search:
        employees = employees.filter(
            Q(name__icontains=search)
            | Q(rut__icontains=search)
            | Q(address__icontains=search)
            | Q(roles__icontains=search)
            | Q(delegation__name__icontains=search)
            | Q(position__position_name__icontains=search)
        )
    if status:
        employees = employees.filter(status__iexact=status)

    context = {
        "employees": employees,
        "total_employees": employees.count(),
        "active_employees": employees.filter(
            Q(status__iexact="active") | Q(status__iexact="activo")
        ).count(),
        "history_employee": history_employee,
        "history_events": history_events,
        "performed_events": performed_events,
        "statuses": _statuses(
            _scoped_queryset(
                Employee.objects.all(),
                request.user,
                "delegation_id",
                active_only=False,
                respect_role_scope=False,
            )
        ),
        "active_page": "employees",
        "page_title": "Empleados",
        "page_description": "Consulta empleados, cargos y funciones por delegación.",
        "page_icon": "bi-people",
    }
    page, querystring = organization_pagination(request, employees.order_by("name", "pk"))
    context["employees"] = page
    context["querystring"] = querystring
    context.update(organization_paging_context(request))
    context.update(mutation_context)
    return render(
        request,
        "organization/employees.html",
        context,
    )


@organization_access("organization.view_delegation")
def delegation_list(request):
    all_records = _scoped_queryset(
        Delegation.objects.select_related("responsible").annotate(
            employee_count=Count(
                "employees",
                filter=Q(employees__deleted_at__isnull=True),
            )
        ),
        request.user,
        "pk",
        "organization.view_delegation",
        active_only=False,
        respect_role_scope=False,
    )
    mutation_context = _handle_mutations(
        request,
        all_records,
        DelegationForm,
        "delegation",
        "delegación",
    )
    if mutation_context is None:
        return redirect("organization:delegation_list")
    delegations = all_records
    search = _query(request.GET.get("q"))
    status = _query(request.GET.get("status"))
    if search:
        delegations = delegations.filter(
            Q(code__icontains=search)
            | Q(name__icontains=search)
            | Q(address__icontains=search)
            | Q(commune__icontains=search)
            | Q(scope__icontains=search)
        )
    if status:
        delegations = delegations.filter(status__iexact=status)
    selected_commune = _query(request.GET.get("commune"))
    if selected_commune:
        delegations = delegations.filter(commune__iexact=selected_commune)
    page, querystring = organization_pagination(request, delegations.order_by("name"))

    context = {
        "delegations": page,
        "total_delegations": delegations.count(),
        "active_delegations": delegations.filter(
            Q(status__iexact="active") | Q(status__iexact="activo")
        ).count(),
        "selected_commune": selected_commune,
        "commune_options": (
            all_records.exclude(commune="")
            .order_by("commune")
            .values_list("commune", flat=True)
            .distinct()
        ),
        "statuses": _statuses(all_records),
        "active_page": "delegations",
        "page_title": "Delegaciones",
        "page_description": "Consulta las unidades territoriales y sus empleados.",
        "page_icon": "bi-building",
    }
    context["querystring"] = querystring
    context.update(organization_paging_context(request))
    context.update(mutation_context)
    return render(
        request,
        "organization/delegations.html",
        context,
    )


@organization_access("organization.view_delegation")
def delegation_export(request):
    delegations = _scoped_queryset(
        Delegation.objects.select_related("responsible"),
        request.user,
        "pk",
        "organization.view_delegation",
        active_only=False,
        respect_role_scope=False,
    ).order_by("name")
    search = _query(request.GET.get("q"))
    status = _query(request.GET.get("status"))
    if search:
        delegations = delegations.filter(
            Q(code__icontains=search)
            | Q(name__icontains=search)
            | Q(address__icontains=search)
            | Q(commune__icontains=search)
            | Q(scope__icontains=search)
        )
    if status:
        delegations = delegations.filter(status__iexact=status)
    commune = _query(request.GET.get("commune"))
    if commune:
        delegations = delegations.filter(commune__iexact=commune)
    return workbook_response(
        "delegaciones.xlsx",
        ["Código", "Nombre", "Dirección", "Comuna", "Ámbito", "Responsable", "Estado"],
        [
            (
                delegation.code or "",
                delegation.name,
                delegation.address,
                delegation.commune,
                delegation.scope,
                delegation.responsible.name if delegation.responsible else "",
                delegation.status,
            )
            for delegation in delegations
        ],
    )


@organization_access("organization.view_positionfunction")
def position_list(request):
    delegation_id = _delegation_id(request.user)
    employee_filter = Q(employees__deleted_at__isnull=True)
    if not request.user.is_superuser and delegation_id is not None:
        employee_filter &= Q(employees__delegation_id=delegation_id)

    records = _scoped_queryset(
        PositionFunction.objects.annotate(
            employee_count=Count(
                "employees",
                filter=employee_filter,
            )
        ).select_related("group"),
        request.user,
        "global_position_catalog", "organization.view_positionfunction",
    ).distinct()
    mutation_context = _handle_mutations(
        request,
        records,
        PositionForm,
        "positionfunction",
        "cargo",
    )
    if mutation_context is None:
        return redirect("organization:position_list")
    positions = records
    search = _query(request.GET.get("q"))
    validity = _query(request.GET.get("validity"))
    today = timezone.localdate()
    if search:
        positions = positions.filter(
            Q(position_name__icontains=search)
            | Q(measurable_items__icontains=search)
            | Q(services__icontains=search)
        )
    if validity == "current":
        positions = positions.filter(
            validity_start__lte=today,
            validity_end__gte=today,
        )
    elif validity == "expired":
        positions = positions.filter(validity_end__lt=today)
    elif validity == "upcoming":
        positions = positions.filter(validity_start__gt=today)

    positions = positions.order_by("position_name")
    context = {
        "positions": positions,
        "total_positions": positions.count(),
        "current_positions": positions.filter(
            validity_start__lte=today,
            validity_end__gte=today,
        ).count(),
        "active_page": "positions",
        "page_title": "Cargos y funciones",
        "page_description": "Consulta responsabilidades, servicios y vigencia de los cargos.",
        "page_icon": "bi-person-badge",
    }
    page, querystring = organization_pagination(request, positions)
    context["position_page"] = page
    context["querystring"] = querystring
    context.update(organization_paging_context(request))
    context.update(mutation_context)
    return render(
        request,
        "organization/positions.html",
        context,
    )



def _user_queryset(user, action="view"):
    """Limitar cuentas a la delegación donde tiene permiso el solicitante."""
    permission = f"accounts.{action}_userprofile"
    if not user.has_perm(permission):
        raise PermissionDenied("Operación sin permiso de usuario.")
    users = get_user_model().objects.filter(
        is_superuser=False, profile__deleted_at__isnull=True
    )
    if user.is_superuser:
        return users
    scoped = allowed_delegation_ids(user, permission)
    return users.filter(
        Q(profile__authorized_delegations__pk__in=scoped)
        | Q(profile__authorized_delegations__isnull=True,
            profile__delegation_id__in=scoped)
    ).distinct()


def _user_target(user, pk, action):
    target = get_object_or_404(_user_queryset(user, action), pk=pk)
    if not user.is_superuser and action in ("change", "delete"):
        permitted = allowed_delegation_ids(
            user, f"accounts.{action}_userprofile", active_only=False
        )
        scope = set(target.profile.authorized_delegations.values_list("pk", flat=True))
        if not scope and target.profile.delegation_id:
            scope = {target.profile.delegation_id}
        if not scope.issubset(permitted):
            raise PermissionDenied("La cuenta tiene delegaciones que no administras.")
        own = user.get_all_permissions()
        for group in target.groups.prefetch_related("permissions__content_type"):
            if any(f"{p.content_type.app_label}.{p.codename}" not in own
                   for p in group.permissions.all()):
                raise PermissionDenied("La cuenta tiene roles que no administras.")
    return target


@login_required
def user_list(request):
    """Mantenedor de usuarios con modales de creación y edición."""

    _require_permission(request.user, "view", "userprofile") if False else None
    if not request.user.has_perm("accounts.view_userprofile"):
        raise PermissionDenied("No tienes permiso para consultar usuarios.")

    form = None
    modal_open = False
    modal_action = ""
    object_id = ""

    if request.method == "POST":
        modal_action = request.POST.get("action", "")
        object_id = request.POST.get("object_id", "")

        # ELIMINAR USUARIO
        if modal_action == "delete":
            _user_queryset(request.user, "delete")
            if not object_id.isdecimal():
                raise PermissionDenied("Usuario no válido.")

            with transaction.atomic():
                account = _user_target(request.user, object_id, "delete")

                profile = UserProfile.objects.filter(
                    user=account,
                    deleted_at__isnull=True,
                ).first()

                if profile is None:
                    messages.error(
                        request,
                        "No se puede eliminar una cuenta sin perfil activo."
                    )
                    return redirect("organization:user_list")

                # Impedir eliminar usuarios vinculados a funcionarios.
                if profile.employee_id is not None:
                    messages.error(
                        request,
                        "No puedes eliminar este usuario porque está "
                        "vinculado a un empleado. "
                        "Primero debes desvincularlo."
                    )
                    return redirect("organization:user_list")

                # Desactivar la cuenta.
                account.is_active = False
                account.save(update_fields=["is_active"])

                # Eliminación lógica del perfil.
                profile.deleted_at = timezone.now()
                profile.save(
                    update_fields=["deleted_at", "updated_at"]
                )

            messages.success(
                request,
                "Usuario eliminado correctamente."
            )
            return redirect("organization:user_list")

        # CREAR USUARIO
        if modal_action == "create":
            _user_queryset(request.user, "add")
            form = AccountCreateForm(request.POST, actor=request.user)

        # EDITAR USUARIO
        elif modal_action == "edit":
            account = _user_target(request.user, object_id, "change")
            linked_employee = (getattr(account.profile, "employee", None)
                               if hasattr(account, "profile") else None)
            previous_account_employee = employee_snapshot(linked_employee)

            form = AccountEditForm(
                request.POST,
                instance=account, actor=request.user,
            )

        else:
            raise PermissionDenied(
                "La operación solicitada no es válida."
            )

        modal_open = True

        # VALIDAR Y GUARDAR
        if form.is_valid():
            try:
                if modal_action == "create":
                    new_account = create_user_account(form)
                    linked = getattr(new_account.profile, "employee", None)
                    if linked:
                        record_employee_change(linked, request.user, "Vinculación de cuenta", {})

                else:
                    with transaction.atomic():
                        form.save()
                        if linked_employee:
                            record_employee_change(
                                linked_employee, request.user, "Cambio de cuenta",
                                previous_account_employee,
                            )
                        updated_profile = UserProfile.objects.filter(
                            user=account, deleted_at__isnull=True
                        ).first()
                        updated_employee = (updated_profile.employee
                                            if updated_profile else None)
                        if updated_employee and (
                            linked_employee is None
                            or linked_employee.pk != updated_employee.pk
                        ):
                            record_employee_change(
                                updated_employee, request.user,
                                "Vinculación de cuenta", {},
                            )

            except IntegrityError:
                form.add_error(
                    None,
                    "No se pudo guardar la cuenta. "
                    "Revisa que los datos no estén duplicados."
                )

            else:
                messages.success(
                    request,
                    (
                        "Usuario creado correctamente."
                        if modal_action == "create"
                        else "Usuario modificado correctamente."
                    ),
                )

                return redirect("organization:user_list")

        mark_invalid_fields(form)

    # ABRIR MODALES DESDE GET
    else:
        modal_action = request.GET.get("modal", "")
        object_id = request.GET.get("id", "")

        if modal_action == "create":
            _user_queryset(request.user, "add")
            form = AccountCreateForm(actor=request.user)
            modal_open = True

        elif modal_action in ("edit", "view"):
            account = _user_target(
                request.user, object_id,
                "change" if modal_action == "edit" else "view",
            )
            form = AccountEditForm(instance=account, actor=request.user if modal_action == "edit" else None)
            if modal_action == "view":
                for field in form.fields.values():
                    field.disabled = True
            modal_open = True

    # LISTADO DE USUARIOS ACTIVOS Y INACTIVOS
    users = (
        _user_queryset(request.user)
        .select_related(
            "profile",
            "profile__employee",
            "profile__delegation",
        )
        .prefetch_related(
            "groups",
            "profile__authorized_delegations",
        )
        .order_by("username")
    )
    search = _query(request.GET.get("q"))
    if search:
        users = users.filter(
            Q(username__icontains=search)
            | Q(email__icontains=search)
            | Q(profile__employee__name__icontains=search)
            | Q(profile__employee_code__icontains=search)
            | Q(
                profile__authorized_delegations__name__icontains=search
            )
        ).distinct()
    selected_delegation = _query(request.GET.get("delegation"))
    selected_role = _query(request.GET.get("role"))
    selected_status = _query(request.GET.get("status"))
    users = user_filter_delegation(users, selected_delegation)
    if selected_role.isdecimal():
        users = users.filter(groups__pk=selected_role).distinct()
    if selected_status == "active":
        users = users.filter(is_active=True)
    elif selected_status == "inactive":
        users = users.filter(is_active=False)
    page, querystring = organization_pagination(request, users)


    # CONTEXTO DE LA PLANTILLA
    context = {
        "users": page,
        "total_users": users.count(),
        "active_users": users.filter(is_active=True).count(),
        "inactive_users": users.filter(is_active=False).count(),
        "form": form,
        "modal_open": modal_open,
        "modal_action": modal_action,
        "modal_title": (
            "Crear usuario"
            if modal_action == "create"
            else "Ver usuario" if modal_action == "view"
            else "Modificar usuario"
        ),
        "edit_confirmation": "¿Desea modificar este usuario?",
        "object_id": (
            object_id if modal_action == "edit" else ""
        ),
        "active_page": "users",
        "page_title": "Usuarios",
        "page_description": (
            "Administra las cuentas de los empleados."
        ),
        "page_icon": "bi-person-gear",
        "search": search,
        "selected_delegation": selected_delegation,
        "selected_role": selected_role,
        "selected_status": selected_status,
        "delegation_options": Delegation.objects.filter(
            pk__in=allowed_delegation_ids(request.user, "accounts.view_userprofile", active_only=False),
            deleted_at__isnull=True,
        ).order_by("name") if not request.user.is_superuser else Delegation.objects.filter(deleted_at__isnull=True).order_by("name"),
        "role_options": Group.objects.filter(organization_role__isnull=False).order_by("name"),
    }
    context["querystring"] = querystring
    context.update(organization_paging_context(request))

    return render(
        request,
        "organization/users.html",
        context,
    )


@login_required
def user_export(request):
    users = _user_queryset(request.user).select_related("profile").prefetch_related(
        "profile__authorized_delegations", "groups"
    ).order_by("username")
    search = _query(request.GET.get("q"))
    if search:
        users = users.filter(
            Q(username__icontains=search)
            | Q(email__icontains=search)
            | Q(profile__employee__name__icontains=search)
            | Q(profile__employee_code__icontains=search)
            | Q(profile__authorized_delegations__name__icontains=search)
        ).distinct()
    users = user_filter_delegation(users, _query(request.GET.get("delegation")))
    selected_role = _query(request.GET.get("role"))
    if selected_role.isdecimal():
        users = users.filter(groups__pk=selected_role).distinct()
    selected_status = _query(request.GET.get("status"))
    if selected_status == "active":
        users = users.filter(is_active=True)
    elif selected_status == "inactive":
        users = users.filter(is_active=False)
    return workbook_response(
        "usuarios.xlsx",
        ["Usuario", "Correo", "Código", "Delegaciones", "Roles", "Estado"],
        [
            (
                user.username,
                user.email,
                user.profile.employee_code,
                ", ".join(
                    delegation.name
                    for delegation in user.profile.authorized_delegations.all()
                ),
                ", ".join(group.name for group in user.groups.all()),
                "Activo" if user.is_active else "Inactivo",
            )
            for user in users
        ],
    )
