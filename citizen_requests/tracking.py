"""Etapas públicas del seguimiento; conserva las transiciones históricas reales."""


def tracking_stages(citizen_request):
    stages = [{"label": "Solicitud recibida", "complete": True}]
    if citizen_request.delegation_id:
        stages.append({"label": "Derivada para revisión", "complete": True})
    if citizen_request.attention_entry_id:
        stages.append({"label": "En gestión", "complete": True})

    # El estado actual no reemplaza la historia: una reapertura inicia un nuevo ciclo.
    # No inferir "Resuelta" solo por existir un cierre: debe estar auditado.
    for event in citizen_request.events.all().order_by("created_at", "pk"):
        if event.previous_status == "CLOSED" and event.new_status == "IN_PROGRESS":
            stages.append({"label": "Reabierta — En gestión", "complete": True})
        elif event.new_status == "RESOLVED":
            stages.append({"label": "Resuelta", "complete": True})
        elif event.new_status == "REJECTED":
            stages.append({"label": "No procede", "complete": True})
        elif event.new_status == "CLOSED":
            stages.append({"label": "Cerrada", "complete": True})

    # Compatibilidad con registros antiguos que tenían estado pero no evento.
    attention_status = (
        citizen_request.attention_entry.status
        if citizen_request.attention_entry_id else None
    )
    if attention_status in ("RESOLVED", "REJECTED"):
        expected_label = "Resuelta" if attention_status == "RESOLVED" else "No procede"
        if not any(s["label"] == expected_label for s in stages):
            stages.append({"label": expected_label, "complete": True})
    if citizen_request.status == "CLOSED" and (not stages or stages[-1]["label"] != "Cerrada"):
        stages.append({"label": "Cerrada", "complete": True})
    return stages
