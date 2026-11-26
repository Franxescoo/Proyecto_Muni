"""Fixtures para probar las metas que avanzan con atenciones resueltas.

La atención se relaciona por la FK nueva AttentionEntry.activity. Cada llamada
crea una atención independiente (no reutiliza una entre actividades).
"""
from uuid import uuid4

from registration_validation.models import AttentionEntry, AttentionType, SubAttention


def link_resolved_attention(activity, *, status="RESOLVED"):
    token = uuid4().hex[:12].upper()
    kind = AttentionType.objects.create(
        code=f"TST-{token}", name="Tipo de atención para regresiones"
    )
    subtype = SubAttention.objects.create(
        code=f"SUB-{token}", name="Subatención para regresiones",
        attention_type=kind,
    )
    return AttentionEntry.objects.create(
        requester=activity.contact or "",
        requester_phone=activity.phone or "",
        attention_type=kind,
        sub_attention=subtype,
        description="Atención resuelta de prueba",
        delegation=activity.author.delegation,
        responsible_employee=activity.author,
        activity=activity,
        status=status,
    )
