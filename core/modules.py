"""Registro de módulos que se muestran como tarjetas en la página principal.

Cada compañero puede ajustar o agregar tarjetas de su módulo aquí:

- title: texto de la tarjeta.
- icon:  ícono de Bootstrap Icons (https://icons.getbootstrap.com).
- url:   nombre de la ruta (el mismo que se usa en {% url %}).
         Si la ruta todavía no existe, la tarjeta aparece como "Próximamente"
         y se activa sola cuando se defina una ruta con ese nombre.
- perm:  permiso necesario para ver la tarjeta (app.view_modelo).
- perms: permisos adicionales que deben cumplirse simultáneamente.
         Los superusuarios ven todas las tarjetas.
"""

MODULES = [
    
    {
        "title": "Planificación",
        "cards": [
            {
                "title": "Períodos",
                "icon": "bi-calendar-range",
                "url": "planning:period_list",
                "perm": "planning_measurements.view_period",
            },
            {
                "title": "Metas",
                "icon": "bi-bullseye",
                "url": "planning:goal_list",
                "perm": "planning_measurements.view_goal",
            },
            {
                "title": "Catálogo de Ítems",
                "icon": "bi-clipboard-check",
                "url": "planning:item_list",
                "perm": "planning_measurements.view_measurementitem",
            },
        ],
    },

    {
        "title": "Organización",
        "cards": [
            {"title": "Empleados", "icon": "bi-people",
             "url": "organization:employee_list",
             "perm": "organization.view_employee"},
             {
                "title": "Usuarios",
                "icon": "bi-person-gear",
                "url": "organization:user_list",
                "perm": "accounts.view_userprofile",
            },
            {"title": "Delegaciones", "icon": "bi-building",
             "url": "organization:delegation_list",
             "perm": "organization.view_delegation"},
            {"title": "Cargos y funciones", "icon": "bi-person-badge",
             "url": "organization:position_list",
             "perm": "organization.view_positionfunction"},
              {"title": "Roles y Permisos", "icon": "bi-shield-lock",
             "url": "organization:role_list",
               "perm": "organization.view_organizationrole"},
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
            {
                "title": "Servicios",
                "icon": "bi-gear-wide-connected",
                "url": "registration:service_list",
                "perm": "registration_validation.view_service",
            },

            {
                "title": "Tipos de actividad",
                "icon": "bi-list-check",
                "url": "registration:activity_type_list",
                "perm": "registration_validation.view_activitytype",
            },
            {
                "title": "Tipos de atención",
                "icon": "bi-card-checklist",
                "url": "registration:attention_type_list",
                "perm": "registration_validation.view_attentiontype",
            },
            {
                "title": "Sub Atención",
                "icon": "bi-diagram-3",
                "url": "registration:sub_attention_list",
                "perm": "registration_validation.view_subattention",
            },
            {
                "title": "Ingreso de Atención",
                "icon": "bi-journal-check",
                "url": "registration:attention_entry_list",
                "perm": "registration_validation.view_attentionentry",
            },
        ],
    },
    {
        "title": "Eventos y Campañas",
        "cards": [
            {"title": "Eventos", "icon": "bi-calendar-event",
             "url": "municipal_events:event_list",
             "perm": "municipal_events.view_municipalevent"},
            {"title": "Campañas", "icon": "bi-gift",
             "url": "municipal_events:campaign_list",
             "perm": "municipal_events.view_campaign"},
            {"title": "Inscripciones", "icon": "bi-person-vcard",
             "url": "municipal_events:enrollment_list",
             "perm": "municipal_events.view_enrollment"},
            {"title": "Entregas", "icon": "bi-box-seam",
             "url": "municipal_events:delivery_list",
             "perm": "municipal_events.view_enrollment",
             "perms": ["municipal_events.view_giftdelivery"]},
            {"title": "Historial", "icon": "bi-clock-history",
             "url": "municipal_events:history_list",
             "perm": "municipal_events.view_enrollment"},
        ],
    },
    {
        "title": "Monitoreo y trazabilidad",
        "cards": [
            {"title": "Indicadores", "icon": "bi-graph-up",
             "url": "monitoring:indicator_list",
             "perm": "monitoring_traceability.view_indicator"},
            {"title": "Compromisos", "icon": "bi-people-fill",
             "url": "monitoring:commitment_list",
             "perm": "monitoring_traceability.view_commitment"},
            {"title": "Auditoría", "icon": "bi-clipboard-data",
             "url": "monitoring:audit_list",
             "perm": "monitoring_traceability.view_audit"},
            
        ],
    },
]
