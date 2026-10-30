"""Acción contextual en Ingreso de Atención, sin modificar sus vistas/modelos."""
from django import template
from django.urls import reverse
from municipal_events.services import can_access_delegation, campaign_active_queryset

register = template.Library()


@register.simple_tag(takes_context=True)
def campaign_link(context, attention):
    user = context["request"].user
    if not can_access_delegation(user, "registration_validation.view_attentionentry", attention.delegation_id):
        return ""
    if not can_access_delegation(user, "municipal_events.add_enrollment", attention.delegation_id):
        return ""
    if not campaign_active_queryset().filter(attention_type_id=attention.attention_type_id).exists():
        return ""
    return reverse("municipal_events:campaigns_for_attention", args=[attention.pk])
