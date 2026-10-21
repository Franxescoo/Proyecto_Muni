"""Validated per-request delegation context for authenticated users."""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST


def authorized_delegations(user):
    """Never trust ids from the session or a request parameter."""
    if not user.is_authenticated or not user.is_active or user.is_superuser:
        return []
    profile = getattr(user, "profile", None)
    if profile is None or profile.deleted_at is not None:
        return []
    ids = set(profile.authorized_delegations.values_list("pk", flat=True))
    if not ids and profile.delegation_id:
        ids = {profile.delegation_id}
    from organization.models import Delegation
    return list(Delegation.objects.filter(pk__in=ids, deleted_at__isnull=True).order_by("name", "pk"))


class ActiveDelegationMiddleware:
    """Pin non-superuser requests to an authorized delegation.

    If a previously selected delegation is revoked it is replaced immediately.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.sgr_delegations = []
        request.sgr_active_delegation = None
        if request.user.is_authenticated and request.user.is_active and not request.user.is_superuser:
            choices = authorized_delegations(request.user)
            request.sgr_delegations = choices
            ids = {obj.pk for obj in choices}
            selected = request.session.get("sgr_active_delegation")
            if selected not in ids:
                profile = getattr(request.user, "profile", None)
                primary = getattr(profile, "delegation_id", None)
                selected = primary if primary in ids else (choices[0].pk if choices else None)
                if selected is not None:
                    request.session["sgr_active_delegation"] = selected
                else:
                    request.session.pop("sgr_active_delegation", None)
            request.user.sgr_active_delegation_id = selected
            request.sgr_active_delegation = next((obj for obj in choices if obj.pk == selected), None)
        return self.get_response(request)


def session_context(request):
    if not request.user.is_authenticated:
        return {}
    return {
        "sgr_active_delegation": getattr(request, "sgr_active_delegation", None),
        "sgr_delegation_options": getattr(request, "sgr_delegations", []),
        "sgr_display_roles": list(request.user.groups.values_list("name", flat=True)),
    }


@login_required
@require_POST
def change_active_delegation(request):
    if request.user.is_superuser:
        raise PermissionDenied("El administrador usa el contexto global.")
    choices = {str(d.pk) for d in authorized_delegations(request.user)}
    selected = request.POST.get("delegation", "")
    if selected not in choices:
        raise PermissionDenied("No estás autorizado para esa delegación.")
    request.session["sgr_active_delegation"] = int(selected)
    next_url = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        next_url = reverse("home")
    return redirect(next_url)
