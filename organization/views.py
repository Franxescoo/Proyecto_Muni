from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from .forms import DelegationForm, EmployeeForm, PositionFunctionForm
from .models import Delegation, Employee, PositionFunction
from accounts.access import allowed_delegation_ids, is_general_administrator


def _active(model):
    return model.objects.filter(deleted_at__isnull=True)


def _save_form(
    request,
    form_class,
    template_name,
    title,
    redirect_name,
    instance=None,
    **form_kwargs,
):
    form = form_class(
        request.POST if request.method == "POST" else None,
        instance=instance,
        **form_kwargs,
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Los datos se guardaron correctamente.")
        return redirect(redirect_name)
    return render(request, template_name, {"form": form, "title": title})


@permission_required("organization.view_employee", raise_exception=True)
def employee_list(request):
    query = request.GET.get("q", "").strip()
    employees = _active(Employee).select_related("delegation", "position")
    delegation_ids = allowed_delegation_ids(request.user)
    if delegation_ids is not None:
        employees = employees.filter(delegation_id__in=delegation_ids)
    if query:
        employees = employees.filter(
            Q(name__icontains=query)
            | Q(delegation__name__icontains=query)
            | Q(position__position_name__icontains=query)
        )
    return render(
        request,
        "organization/employee_list.html",
        {"employees": employees.order_by("name"), "query": query},
    )


@permission_required("organization.add_employee", raise_exception=True)
def employee_create(request):
    delegation_ids = allowed_delegation_ids(request.user)
    return _save_form(
        request, EmployeeForm, "organization/employee_form.html",
        "Agregar funcionario", "organization:employee_list",
        delegation_ids=delegation_ids,
    )


@permission_required("organization.change_employee", raise_exception=True)
def employee_edit(request, pk):
    employees = _active(Employee)
    delegation_ids = allowed_delegation_ids(request.user)
    if delegation_ids is not None:
        employees = employees.filter(delegation_id__in=delegation_ids)
    employee = get_object_or_404(employees, pk=pk)
    return _save_form(
        request, EmployeeForm, "organization/employee_form.html",
        "Editar funcionario", "organization:employee_list", employee,
        delegation_ids=delegation_ids,
    )


@permission_required("organization.view_delegation", raise_exception=True)
def delegation_list(request):
    query = request.GET.get("q", "").strip()
    delegations = _active(Delegation)
    delegation_ids = allowed_delegation_ids(request.user)
    if delegation_ids is not None:
        delegations = delegations.filter(pk__in=delegation_ids)
    if query:
        delegations = delegations.filter(
            Q(name__icontains=query)
            | Q(scope__icontains=query)
            | Q(status__icontains=query)
        )
    return render(
        request,
        "organization/delegation_list.html",
        {"delegations": delegations.order_by("name"), "query": query},
    )


@permission_required("organization.add_delegation", raise_exception=True)
def delegation_create(request):
    if not is_general_administrator(request.user):
        raise PermissionDenied("Solo Administración General puede crear delegaciones.")
    return _save_form(
        request, DelegationForm, "organization/delegation_form.html",
        "Agregar delegación", "organization:delegation_list",
    )


@permission_required("organization.change_delegation", raise_exception=True)
def delegation_edit(request, pk):
    delegations = _active(Delegation)
    delegation_ids = allowed_delegation_ids(request.user)
    if delegation_ids is not None:
        delegations = delegations.filter(pk__in=delegation_ids)
    delegation = get_object_or_404(delegations, pk=pk)
    return _save_form(
        request, DelegationForm, "organization/delegation_form.html",
        "Editar delegación", "organization:delegation_list", delegation,
    )


@permission_required("organization.view_positionfunction", raise_exception=True)
def position_list(request):
    query = request.GET.get("q", "").strip()
    positions = _active(PositionFunction)
    if query:
        positions = positions.filter(
            Q(position_name__icontains=query)
            | Q(services__icontains=query)
            | Q(measurable_items__icontains=query)
        )
    return render(
        request,
        "organization/position_list.html",
        {"positions": positions.order_by("position_name"), "query": query},
    )


@permission_required("organization.add_positionfunction", raise_exception=True)
def position_create(request):
    return _save_form(
        request, PositionFunctionForm, "organization/position_form.html",
        "Agregar cargo y función", "organization:position_list",
    )


@permission_required("organization.change_positionfunction", raise_exception=True)
def position_edit(request, pk):
    position = get_object_or_404(_active(PositionFunction), pk=pk)
    return _save_form(
        request, PositionFunctionForm, "organization/position_form.html",
        "Editar cargo y función", "organization:position_list", position,
    )
