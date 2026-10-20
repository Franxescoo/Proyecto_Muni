from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.contrib.auth import get_user_model

from accounts.services import sync_employee

from .forms import (
	DelegationForm,
	EmployeeForm,
	OrganizationRoleForm,
	PositionForm,
	mark_invalid_fields,
)
from .models import Delegation, Employee, PositionFunction

from django.db import IntegrityError

from accounts.forms import AccountCreateForm
from accounts.services import create_user_account, sync_user_groups
from django.db import IntegrityError, transaction

from accounts.forms import AccountCreateForm, AccountEditForm
from accounts.models import UserProfile




def organization_access(permission):
	def decorator(view):
		view = permission_required(permission, raise_exception=True)(view)
		return login_required(view)

	return decorator


def _delegation_id(user):
	profile = getattr(user, "profile", None)
	return profile.delegation_id if profile else None


def _scoped_queryset(queryset, user, relation):
	queryset = queryset.filter(deleted_at__isnull=True)
	if user.is_superuser:
		return queryset

	delegation_id = _delegation_id(user)
	if delegation_id is None:
		return queryset.none()
	if relation == "pk":
		return queryset.filter(pk=delegation_id)
	return queryset.filter(**{relation: delegation_id})


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


def _limit_form_choices(form, user):
	if isinstance(form, EmployeeForm) and not user.is_superuser:
		form.fields["delegation"].queryset = Delegation.objects.filter(
			pk=_delegation_id(user),
			deleted_at__isnull=True,
		)
		form.fields["assigned_groups"].disabled = True
		form.fields["assigned_groups"].queryset = (
			form.instance.assigned_groups.all()
			if form.instance.pk
			else Group.objects.none()
		)


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
			record = get_object_or_404(records, pk=instance_id)
			record.deleted_at = timezone.now()
			record.save(update_fields=["deleted_at", "updated_at"])
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
		instance = None
		if modal_action == "edit":
			instance = get_object_or_404(records, pk=instance_id)
		form = form_class(request.POST, request.FILES, instance=instance)
		_limit_form_choices(form, request.user)
		if form.is_valid():
			saved = form.save()
			if isinstance(form, EmployeeForm):
				sync_employee(saved)
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
		elif modal_action == "edit":
			_require_permission(request.user, "change", model_name)
			instance = get_object_or_404(records, pk=instance_id)
			form = form_class(instance=instance)
		else:
			return {"form": None, "modal_open": False}
		_limit_form_choices(form, request.user)

	return {
		"form": form,
		"modal_open": True,
		"modal_action": modal_action,
		"modal_title": (
			f"Crear {object_label}"
			if modal_action == "create"
			else f"Modificar {object_label}"
		),
		"edit_confirmation": {
			"funcionario": "¿Desea modificar el Funcionario?",
			"delegación": "¿Desea modificar la Delegación?",
			"cargo": "¿Desea modificar el Cargo?",
		}[object_label],
		"object_id": instance_id if modal_action == "edit" else "",
	}


@login_required
def role_list(request):
	if not request.user.is_superuser:
		raise PermissionDenied(
			"Solo el administrador puede gestionar roles y permisos."
		)

	groups = Group.objects.select_related(
		"organization_role__delegation"
	).annotate(
		permission_count=Count("permissions", distinct=True),
		account_count=Count("user", distinct=True),
		employee_count=Count("assigned_employees", distinct=True),
	).order_by("name")
	form = None
	modal_action = ""
	object_id = ""
	modal_open = False

	if request.method == "POST":
		modal_action = request.POST.get("action", "")
		object_id = request.POST.get("object_id", "")
		if modal_action == "delete":
			group = get_object_or_404(Group, pk=object_id)
			if group.positions.exists():
				messages.error(
					request,
					"No se puede eliminar este rol mientras esté asignado a un cargo.",
				)
				return redirect("organization:role_list")
			group.delete()
			messages.success(
				request,
				"Rol eliminado y desasignado de cuentas y funcionarios.",
			)
			return redirect("organization:role_list")

		if modal_action not in ("create", "edit"):
			messages.error(request, "La operación solicitada no es válida.")
			return redirect("organization:role_list")

		instance = None
		if modal_action == "edit":
			instance = get_object_or_404(Group, pk=object_id)
		form = OrganizationRoleForm(request.POST, group=instance)
		if form.is_valid():
			form.save()
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
			form = OrganizationRoleForm()
			modal_open = True
		elif modal_action == "edit":
			group = get_object_or_404(Group, pk=object_id)
			form = OrganizationRoleForm(group=group)
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
		"modal_title": "Crear rol" if modal_action == "create" else "Modificar rol",
		"edit_confirmation": "¿Desea modificar el rol y sus permisos?",
		"object_id": object_id if modal_action == "edit" else "",
		"active_page": "roles",
		"page_title": "Roles y Permisos",
		"page_description": "Crea roles y define los permisos que se asignarán a funcionarios y cuentas.",
		"page_icon": "bi-shield-lock",
	}
	return render(request, "organization/roles.html", context)


@organization_access("organization.view_employee")
def employee_list(request):
	records = _scoped_queryset(
		Employee.objects.select_related("delegation", "position").prefetch_related(
			"assigned_groups"
		),
		request.user,
		"delegation_id",
	)
	mutation_context = _handle_mutations(
		request,
		records,
		EmployeeForm,
		"employee",
		"funcionario",
	)
	if mutation_context is None:
		return redirect("organization:employee_list")
	employees = records
	search = _query(request.GET.get("q"))
	status = _query(request.GET.get("status"))
	if search:
		employees = employees.filter(
			Q(name__icontains=search)
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
		"statuses": _statuses(
			_scoped_queryset(Employee.objects.all(), request.user, "delegation_id")
		),
		"active_page": "employees",
		"page_title": "Funcionarios",
		"page_description": "Consulta funcionarios, cargos y funciones por delegación.",
		"page_icon": "bi-people",
	}
	context.update(mutation_context)
	return render(
		request,
		"organization/employees.html",
		context,
	)


@organization_access("organization.view_delegation")
def delegation_list(request):
	records = _scoped_queryset(
		Delegation.objects.annotate(
			employee_count=Count(
				"employees",
				filter=Q(employees__deleted_at__isnull=True),
			)
		),
		request.user,
		"pk",
	)
	mutation_context = _handle_mutations(
		request,
		records,
		DelegationForm,
		"delegation",
		"delegación",
	)
	if mutation_context is None:
		return redirect("organization:delegation_list")
	delegations = records
	search = _query(request.GET.get("q"))
	status = _query(request.GET.get("status"))
	if search:
		delegations = delegations.filter(
			Q(name__icontains=search) | Q(scope__icontains=search)
		)
	if status:
		delegations = delegations.filter(status__iexact=status)

	context = {
		"delegations": delegations,
		"total_delegations": delegations.count(),
		"active_delegations": delegations.filter(
			Q(status__iexact="active") | Q(status__iexact="activo")
		).count(),
		"statuses": _statuses(
			_scoped_queryset(Delegation.objects.all(), request.user, "pk")
		),
		"active_page": "delegations",
		"page_title": "Delegaciones",
		"page_description": "Consulta las unidades territoriales y sus funcionarios.",
		"page_icon": "bi-building",
	}
	context.update(mutation_context)
	return render(
		request,
		"organization/delegations.html",
		context,
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
		"employees__delegation_id",
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
	context.update(mutation_context)
	return render(
		request,
		"organization/positions.html",
		context,
	)


@login_required
def user_list(request):
    """Mantenedor de usuarios con modales de creación y edición."""

    if not request.user.is_superuser:
        raise PermissionDenied(
            "No tienes permiso para administrar usuarios."
        )

    form = None
    modal_open = False
    modal_action = ""
    object_id = ""

    if request.method == "POST":
        modal_action = request.POST.get("action", "")
        object_id = request.POST.get("object_id", "")
		
        if modal_action == "delete":
            if not object_id.isdecimal():
                raise PermissionDenied("Usuario no válido.")

            with transaction.atomic():
                account = get_object_or_404(
                    get_user_model().objects.select_for_update(),
                    pk=object_id,
                    is_superuser=False,
                    profile__deleted_at__isnull=True,
                )

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

                # El usuario pierde acceso al sistema.
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


        if modal_action == "create":
            form = AccountCreateForm(request.POST)

        elif modal_action == "edit":
            account = get_object_or_404(
                get_user_model(),
                pk=object_id,
                is_superuser=False,
                profile__deleted_at__isnull=True,
            )
            form = AccountEditForm(
                request.POST,
                instance=account,
            )

        else:
            raise PermissionDenied(
                "La operación solicitada no es válida."
            )

        modal_open = True

        if form.is_valid():
            try:
                if modal_action == "create":
                    create_user_account(form)
                else:
                    with transaction.atomic():
                        form.save()

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

    else:
        modal_action = request.GET.get("modal", "")
        object_id = request.GET.get("id", "")

        if modal_action == "create":
            form = AccountCreateForm()
            modal_open = True

        elif modal_action == "edit":
            account = get_object_or_404(
                get_user_model(),
                pk=object_id,
                is_superuser=False,
                profile__deleted_at__isnull=True,
            )
            form = AccountEditForm(instance=account)
            modal_open = True

    users = (
        get_user_model().objects
        .filter(
			is_superuser=False,
			profile__deleted_at__isnull=True,
		)
        .select_related(
            "profile",
            "profile__employee",
            "profile__delegation",
        )
        .prefetch_related("groups")
        .order_by("username")
    )

    context = {
        "users": users,
        "total_users": users.count(),
        "active_users": users.filter(is_active=True).count(),
        "inactive_users": users.filter(is_active=False).count(),
        "form": form,
        "modal_open": modal_open,
        "modal_action": modal_action,
        "modal_title": (
            "Crear usuario"
            if modal_action == "create"
            else "Modificar usuario"
        ),
        "edit_confirmation": "¿Desea modificar este usuario?",
        "object_id": (
            object_id if modal_action == "edit" else ""
        ),
        "active_page": "users",
        "page_title": "Usuarios",
        "page_description": (
            "Administra las cuentas de los funcionarios."
        ),
        "page_icon": "bi-person-gear",
    }

    return render(
        request,
        "organization/users.html",
        context,
    )



