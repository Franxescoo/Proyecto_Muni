"""Gestión de ausencias: sólo la cuenta del responsable de delegación autenticada."""
from datetime import date
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.utils import timezone

from accounts.permissions import allowed_delegation_ids
from organization.models import Delegation, Employee
from planning_measurements.models import Goal
from .absence_rules import absence_intersects_closed_goal
from .models import EmployeeAbsence
from .services import synchronize_indicators_for_goals


VIEW_PERMISSION = 'monitoring_traceability.view_indicator'


def current_delegate_delegation(user):
    """El rol de administrador no sustituye a ser responsable delegado real."""
    if not user.is_authenticated or not user.is_active or not user.has_perm(VIEW_PERMISSION):
        return None
    profile = getattr(user, 'profile', None)
    employee_id = getattr(profile, 'employee_id', None)
    if not employee_id:
        return None
    permitted = allowed_delegation_ids(user, VIEW_PERMISSION)
    scope = Delegation.objects.filter(
        responsible_id=employee_id, deleted_at__isnull=True, status__iexact='Active',
    )
    if permitted is not None:
        scope = scope.filter(pk__in=permitted)
    return scope.order_by('pk').first()


def _recalculate(employee_id, start, end):
    goals = Goal.objects.filter(
        employee_id=employee_id, deleted_at__isnull=True,
        period__deleted_at__isnull=True, period__status__iexact='Active',
        period__start_date__lte=end, period__end_date__gte=start,
    )
    synchronize_indicators_for_goals(goals)


@login_required
@require_POST
def manage_absence(request):
    delegation = current_delegate_delegation(request.user)
    if delegation is None:
        raise PermissionDenied('Solo el delegado responsable autenticado puede informar ausencias.')
    action = (request.POST.get('action') or '').strip()
    if action == 'report':
        try:
            employee = Employee.objects.get(
                pk=request.POST.get('employee_id'), delegation=delegation,
                deleted_at__isnull=True,
            )
            if employee.pk == delegation.responsible_id:
                raise ValidationError('El delegado no puede autorregistrar su propia ausencia.')
            start = date.fromisoformat(request.POST.get('start_date', ''))
            end = date.fromisoformat(request.POST.get('end_date', ''))
            if absence_intersects_closed_goal(employee.pk, start, end):
                raise ValidationError('No es posible cambiar metas de períodos ya cerrados.')
            with transaction.atomic():
                # Lock de empleado para serializar altas concurrentes del mismo funcionario.
                Employee.objects.select_for_update().get(pk=employee.pk)
                absence = EmployeeAbsence(
                    employee=employee, delegation=delegation,
                    reported_by=request.user, start_date=start, end_date=end,
                    absence_type=request.POST.get('absence_type', ''),
                    reason=(request.POST.get('reason') or '').strip(),
                )
                absence.full_clean()
                absence.save()
            _recalculate(employee.pk, start, end)
            messages.success(request, 'Ausencia registrada. Se actualizaron las metas y el semáforo.')
        except (Employee.DoesNotExist, ValueError, TypeError, ValidationError) as err:
            detail = '; '.join(err.messages) if hasattr(err, 'messages') else str(err)
            messages.error(request, f'No se pudo registrar la ausencia: {detail}')
    elif action == 'cancel':
        reason = (request.POST.get('cancel_reason') or '').strip()
        if not reason:
            messages.error(request, 'Indica el motivo de anulación.')
        else:
            with transaction.atomic():
                absence = get_object_or_404(
                    EmployeeAbsence.objects.select_for_update(),
                    pk=request.POST.get('absence_id'), delegation=delegation,
                    cancelled_at__isnull=True,
                )
                if absence_intersects_closed_goal(
                    absence.employee_id, absence.start_date, absence.end_date
                ):
                    messages.error(request, 'No se pueden alterar períodos cerrados.')
                else:
                    absence.cancelled_at = timezone.now()
                    absence.cancelled_by = request.user
                    absence.cancel_reason = reason
                    absence.save(update_fields=['cancelled_at', 'cancelled_by', 'cancel_reason'])
                    pk, start, end = absence.employee_id, absence.start_date, absence.end_date
                    transaction.on_commit(lambda: _recalculate(pk, start, end))
                    messages.success(request, 'Ausencia anulada. Se conservó su historial.')
    else:
        raise PermissionDenied('Operación de ausencia no autorizada.')
    return redirect(reverse('monitoring:indicator_list'))
