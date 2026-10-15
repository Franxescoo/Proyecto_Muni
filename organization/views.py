from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import DelegationForm, EmployeeForm, PositionFunctionForm
from .models import Delegation, Employee, PositionFunction


def permission_required(permission):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(request, *args, **kwargs):
            if not request.user.is_superuser and not request.user.has_perm(permission):
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapped
    return decorator


def _active(queryset):
    return queryset.filter(deleted_at__isnull=True)


@permission_required("organization.view_delegation")
def delegation_list(request):
    items = _active(Delegation.objects.all()).order_by("name")
    return render(request, "organization/delegation_list.html", {"items": items})


@permission_required("organization.view_delegation")
def delegation_detail(request, pk):
    item = get_object_or_404(_active(Delegation.objects.all()), pk=pk)
    employees = _active(Employee.objects.filter(delegation=item)).select_related("position")
    return render(request, "organization/delegation_detail.html", {"item": item, "employees": employees})


@permission_required("organization.add_delegation")
def delegation_create(request):
    return _save_form(request, DelegationForm, "Crear delegación", "organization:delegation_list")


@permission_required("organization.change_delegation")
def delegation_update(request, pk):
    item = get_object_or_404(_active(Delegation.objects.all()), pk=pk)
    return _save_form(request, DelegationForm, "Editar delegación", "organization:delegation_list", item)


@permission_required("organization.delete_delegation")
def delegation_delete(request, pk):
    item = get_object_or_404(_active(Delegation.objects.all()), pk=pk)
    return _soft_delete(request, item, "organization:delegation_list", "delegación")


@permission_required("organization.view_positionfunction")
def position_list(request):
    items = _active(PositionFunction.objects.all()).select_related("group").order_by("position_name")
    return render(request, "organization/position_list.html", {"items": items})


@permission_required("organization.view_positionfunction")
def position_detail(request, pk):
    item = get_object_or_404(_active(PositionFunction.objects.all()), pk=pk)
    return render(request, "organization/position_detail.html", {"item": item})


@permission_required("organization.add_positionfunction")
def position_create(request):
    return _save_form(request, PositionFunctionForm, "Crear cargo y función", "organization:position_list")


@permission_required("organization.change_positionfunction")
def position_update(request, pk):
    item = get_object_or_404(_active(PositionFunction.objects.all()), pk=pk)
    return _save_form(request, PositionFunctionForm, "Editar cargo y función", "organization:position_list", item)


@permission_required("organization.delete_positionfunction")
def position_delete(request, pk):
    item = get_object_or_404(_active(PositionFunction.objects.all()), pk=pk)
    return _soft_delete(request, item, "organization:position_list", "cargo")


@permission_required("organization.view_employee")
def employee_list(request):
    items = _active(Employee.objects.all()).select_related("delegation", "position").order_by("name")
    return render(request, "organization/employee_list.html", {"items": items})


@permission_required("organization.view_employee")
def employee_detail(request, pk):
    item = get_object_or_404(
        _active(Employee.objects.all()).select_related("delegation", "position"), pk=pk
    )
    return render(request, "organization/employee_detail.html", {"item": item})


@permission_required("organization.add_employee")
def employee_create(request):
    return _save_form(request, EmployeeForm, "Crear funcionario", "organization:employee_list")


@permission_required("organization.change_employee")
def employee_update(request, pk):
    item = get_object_or_404(_active(Employee.objects.all()), pk=pk)
    return _save_form(request, EmployeeForm, "Editar funcionario", "organization:employee_list", item)


@permission_required("organization.delete_employee")
def employee_delete(request, pk):
    item = get_object_or_404(_active(Employee.objects.all()), pk=pk)
    return _soft_delete(request, item, "organization:employee_list", "funcionario")


def _save_form(request, form_class, title, destination, instance=None):
    form = form_class(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        item = form.save(commit=False)
        try:
            item.full_clean()
            item.save()
            form.save_m2m()
        except Exception as error:
            form.add_error(None, str(error))
        else:
            messages.success(request, "Los datos se guardaron correctamente.")
            return redirect(destination)
    return render(request, "organization/manage_form.html", {"form": form, "title": title})


def _soft_delete(request, item, destination, label):
    if request.method == "POST":
        item.deleted_at = timezone.now()
        item.save()
        messages.success(request, f"Se eliminó la {label} correctamente.")
        return redirect(destination)
    return render(request, "organization/confirm_delete.html", {"item": item, "label": label})
