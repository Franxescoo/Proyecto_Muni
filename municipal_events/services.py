"""Reglas territoriales del nuevo módulo, sin cambiar las de Organización."""
from django.core.exceptions import PermissionDenied
from django.utils import timezone

from accounts.permissions import allowed_delegation_ids


def can_access_delegation(user, permission, delegation_id):
    if not user.is_authenticated or not user.is_active or not user.has_perm(permission):
        return False
    scope = allowed_delegation_ids(user, permission)
    return scope is None or (bool(scope) and delegation_id in scope)


def require_delegation(user, permission, delegation_id):
    if not can_access_delegation(user, permission, delegation_id):
        raise PermissionDenied("No tienes autorización sobre esta delegación y operación.")


def can_register_from_attention(user, attention, campaign):
    return (
        campaign.attention_type_id == attention.attention_type_id
        and campaign.accepts_enrollments
        and can_access_delegation(user, "municipal_events.add_enrollment", attention.delegation_id)
        and can_access_delegation(user, "registration_validation.view_attentionentry", attention.delegation_id)
    )


def campaign_active_queryset():
    from .models import Campaign
    today = timezone.localdate()
    return Campaign.objects.filter(status="OPEN", opens_on__lte=today, closes_on__gte=today)
