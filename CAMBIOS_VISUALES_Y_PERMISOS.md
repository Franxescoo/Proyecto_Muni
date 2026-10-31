# Ajustes visuales y revisión de permisos

## Interfaz
- Períodos utiliza ahora el mismo componente de paginación que los seis mantenedores; «Anterior» y «Siguiente» aparecen incluso con una página, deshabilitados cuando corresponde.
- Roles, Delegaciones y Usuarios: las acciones de tabla muestran ícono + texto («Modificar», «Eliminar»).
- Tipos de Atención y Subatenciones: se muestra el texto de los botones en todos los tamaños de pantalla.
- Ítems: botones «Ver», «Modificar» y «Desactivar» con ícono + texto (se conserva la acción de desactivación, no se sustituye por eliminación física).
- Refuerzo de estilos compartidos y versión nueva de CSS para evitar reutilizar el archivo antiguo en caché.
- No cambia la base de datos ni las migraciones.

## Auditoría de visibilidad
**NO se ha implementado todavía una política universal «solo mis registros».** `allowed_delegation_ids` acota por alcance de permisos y delegación, no por propietario.
- Metas: `scoped_goals` filtra por `employee__delegation_id`.
- Actividades: `scoped_activities` filtra por `author__delegation_id`.
- Evidencias: por delegación de la actividad.
- Ingresos de atención: `scoped_attention_entries` filtra por `delegation_id`.
- Períodos: listado global para quienes tengan `view_period`.
- Monitoreo: por delegación, con un mecanismo de compatibilidad para cuentas antiguas sin rol organizacional.
La política para empleado, responsable de delegación y administrador debe confirmarse antes de restringir registros individuales. También deben revisarse endpoints de edición, exportación, URL directa y operaciones masivas.
