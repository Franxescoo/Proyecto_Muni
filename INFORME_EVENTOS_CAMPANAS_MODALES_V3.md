# Eventos y Campañas — V3 (CRUD con modales)

## Qué cambia

Se conservan los datos y operaciones del módulo `municipal_events`, pero la presentación se integra visualmente al SGR, con navegación lateral, una única barra institucional original, encabezado rojo del contenido, indicadores reales, filtros y tablas compactas.

**Modales dentro del módulo:**
- Eventos municipales: crear, ver, modificar, eliminar con confirmación.
- Ediciones anuales: crear, ver, modificar, eliminar con confirmación.
- Campañas: crear, ver, modificar, eliminar con confirmación.
- Inscripciones: ver detalles y evaluar (aprobar/rechazar); el historial de cada registro sigue disponible.
- Entregas: registrar una entrega y consultar su constancia.

Los formularios y detalles se cargan dentro de **un modal Bootstrap reutilizable** mediante solicitudes AJAX. Un guardado correcto recarga los datos de la misma sección y muestra confirmación. Los errores del formulario aparecen dentro del modal sin navegar a una nueva página. El servidor vuelve a validar permisos, ámbitos territoriales y reglas de negocio en cada operación.

**Excepción conservada:** desde `registration_validation` / Ingreso de Atención se puede navegar al selector de campaña y al formulario de inscripción del beneficiario en Eventos y Campañas; no se modifica ese flujo entre módulos.

## Seguridad e integridad

- Los registros de niños visibles, sus detalles, sus constancias y sus indicadores respetan `view_enrollment`, `view_giftdelivery` y el ámbito territorial de la delegación activa.
- Se evita mostrar contadores de inscritos globales a usuarios que no tienen permiso de consulta; cuando sí lo tienen, solo se cuentan los inscritos visibles de su ámbito.
- Eliminar requiere permiso específico (`delete_municipalevent`, `delete_eventedition`, `delete_campaign`) por servidor y una confirmación POST/CSRF. No se borran eventos con ediciones, ediciones con campañas ni campañas con inscripciones. El modelo conserva sus protecciones `PROTECT`.
- No se elimina ni modifica la inscripción de un niño ni una entrega registrada mediante el rediseño: conservar esa trazabilidad es intencional. Los estados se administran mediante evaluación y entrega con auditoría.
- No se modifican `registration_validation`, modelos ni migraciones.

## Archivos incluidos

**Modificados:**
- `municipal_events/views.py`
- `municipal_events/urls.py`
- `municipal_events/forms.py` (filtro de delegaciones según permiso de modificar)
- `municipal_events/tests.py`
- `organization/permission_labels.py` (visibilidad de permisos de eliminación; conserva consulta de entregas)
- `templates/municipal_events/base.html`, `dashboard.html`, `events.html`, `campaigns.html`, `campaign_detail.html`, `enrollments.html`, `deliveries.html`, `history.html`
- `static/css/municipal_events.css`

**Nuevos:**
- `static/js/municipal_events_modals.js`
- `templates/municipal_events/_modal_form.html`
- `templates/municipal_events/_modal_confirm.html`
- `templates/municipal_events/_detail_event.html`
- `templates/municipal_events/_detail_edition.html`
- `templates/municipal_events/_detail_campaign.html`
- `templates/municipal_events/_detail_enrollment.html`
- `templates/municipal_events/_detail_delivery.html`
- `templates/municipal_events/detail.html` (compatibilidad para apertura directa)
- `templates/municipal_events/delete_confirm.html` (compatibilidad para apertura directa)

**No incluye** `.env`, `.git`, `.venv`, `db.sqlite3`, respaldos de base de datos ni archivos de usuarios.

## Instalación en local

1. Respalda tu proyecto actual. Mantén tu base de datos, configuraciones y entorno virtual.
2. Descomprime `Proyecto_Muni_Eventos_Campanas_CRUD_Modales_V3_Solo_Cambios.zip` **en la carpeta que contiene `Proyecto_Muni`**. Acepta reemplazar únicamente los archivos incluidos.
3. Verifica en Git Bash dentro del proyecto:

```bash
python manage.py check
python manage.py test municipal_events
python manage.py runserver
```

No se requieren nuevas migraciones: no cambian los modelos.

4. Entra como Marcos y prueba crear/ver/modificar un evento, una edición y una campaña sin salir del listado; evaluar una inscripción y registrar una entrega mediante modales.
5. Solo si deseas probar **eliminar**: otro administrador normal autorizado (no Marcos editando su propio rol) puede otorgar los permisos de eliminación de Eventos, Ediciones y Campañas desde Roles y Permisos. Los objetos con datos vinculados continuarán protegidos.

## Validaciones realizadas en el entorno de entrega

- `python -m compileall`: sintaxis Python correcta.
- `node --check static/js/municipal_events_modals.js`: JavaScript sin errores de sintaxis.
- `django check`: sin observaciones.
- **17 de 17 pruebas del módulo** completadas correctamente, incluidas pruebas AJAX de modales, validaciones de formulario, bloqueo de eliminación y control territorial de detalles.
- La ejecución conjunta de Cuentas, Organización, Solicitudes Ciudadanas y Eventos y Campañas imprimió **181 pruebas aprobadas (OK)**. El comando del entorno fue interrumpido por límite de tiempo después de imprimir el resultado, por lo que es recomendable repetir la batería en tu computador.

## Límites funcionales

Esta entrega cambia principalmente la interfaz. Mantiene la inscripción de niños como formulario en página independiente **solo cuando se llega desde otro módulo**, según lo acordado. No se implementan todavía reglas especiales de edad o custodia que el profesor debe definir; no cambia el envío de correos de atenciones internas.
