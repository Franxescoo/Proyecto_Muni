"""Registro de módulos que se muestran como tarjetas en la página principal.

Cada compañero puede ajustar o agregar tarjetas de su módulo aquí:

- title: texto de la tarjeta.
- icon:  ícono de Bootstrap Icons (https://icons.getbootstrap.com).
- url:   nombre de la ruta (el mismo que se usa en {% url %}).
         Si la ruta todavía no existe, la tarjeta aparece como "Próximamente"
         y se activa sola cuando se defina una ruta con ese nombre.
- perm:  permiso necesario para ver la tarjeta (app.view_modelo).
         Los superusuarios ven todas las tarjetas.
"""

MODULES = [
    {
        "title": "Planificación",
        "cards": [
            {"title": "Períodos", "icon": "bi-calendar-range",
             "url": "planning:period_list",
             "perm": "planning_measurements.view_period"},
            {"title": "Metas", "icon": "bi-bullseye",
             "url": "planning:goal_list",
             "perm": "planning_measurements.view_goal"},
        ],
    },
    {
        "title": "Organización",
        "cards": [
            {"title": "Funcionarios", "icon": "bi-people",
             "url": "organization:employee_list",
             "perm": "organization.view_employee"},
            {"title": "Delegaciones", "icon": "bi-building",
             "url": "organization:delegation_list",
             "perm": "organization.view_delegation"},
            {"title": "Cargos y funciones", "icon": "bi-person-badge",
             "url": "organization:position_list",
             "perm": "organization.view_positionfunction"},
        ],
    },
    {
        "title": "Registro y validación",
        "cards": [
            {"title": "Actividades", "icon": "bi-journal-text",
             "url": "registration:activity_list",
             "perm": "registration_validation.view_activity"},
            {"title": "Evidencias", "icon": "bi-paperclip",
             "url": "registration:evidence_list",
             "perm": "registration_validation.view_evidence"},
            {"title": "Verificación", "icon": "bi-patch-check",
             "url": "registration:validation_list",
             "perm": "registration_validation.view_validation"},
        ],
    },
    {
        "title": "Monitoreo y trazabilidad",
        "cards": [
            {"title": "Indicadores", "icon": "bi-graph-up",
             "url": "monitoring:indicator_list",
             "perm": "monitoring_traceability.view_indicator"},
            {"title": "Compromisos", "icon": "bi-handshake",
             "url": "monitoring:commitment_list",
             "perm": "monitoring_traceability.view_commitment"},
            {"title": "Auditoría", "icon": "bi-clipboard-data",
             "url": "monitoring:audit_list",
             "perm": "monitoring_traceability.view_audit"},
        ],
    },
]
