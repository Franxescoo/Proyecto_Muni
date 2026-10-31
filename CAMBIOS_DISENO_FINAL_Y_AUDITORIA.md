# Cambios de presentación y análisis de permisos

## Cambios de interfaz
- Botones Crear/Agregar y Exportar Excel (donde existe esa exportación) agrupados a la derecha, sin crear rutas de exportación inexistentes.
- Los seis mantenedores obligatorios (Delegaciones, Roles, Usuarios, Ítems, Tipos de Atención y Subatenciones) conservan sus filtros, botones y guardado de preferencia. La paginación ahora tiene contador a la izquierda y controles **centrados** `Anterior | 1 / 1 | Siguiente`, incluso con una sola página.
- Empleados y Cargos/Funciones: mismo estilo de cabecera, botón Crear a la derecha, filtro Limpiar, selector de registros por página, paginación real de 10/25/50 registros y acciones `Modificar` / `Eliminar` con icono + texto.
- Períodos y Metas: paginación compartida y siempre visible; se conserva el funcionamiento y diseño general de sus filtros, botones y reglas del módulo.
- Actividades, tipos de actividad, Servicios, Evidencias, Validaciones e Ingresos de atención: paginación con el mismo componente, controles y etiquetas de acciones visibles también en pantallas pequeñas donde correspondía.
- Se mantiene la verificación actual de permisos de la aplicación. Sin cambios en modelos ni migraciones.

## Resultado de auditoría de autorización
**La norma «un usuario ordinario solo puede consultar lo propio/asignado» NO está implementada universalmente.** Los permisos estándar de Django no implican propiedad del registro.
- Organización: Empleados se filtra por delegaciones del usuario para `view_employee`; cargos por las delegaciones de los empleados asociados. Dos empleados autorizados en la misma delegación pueden ver registros del otro.
- Metas: `scoped_goals` filtra por la delegación del empleado asignado, no por identidad del usuario autenticado.
- Actividades: `scoped_activities` por delegación del autor, no necesariamente por `author=user`.
- Evidencias: por la delegación de la actividad asociada.
- Atención: entradas por delegación autorizada.
- Períodos: listado de ámbito general para usuarios con permiso de consulta, no por propietario.
- Monitoreo: por delegación; existe compatibilidad de acceso para cuentas anteriores sin roles organizacionales.
- **Revisión adicional de Cargos/Funciones:** `_handle_mutations` usa el conjunto filtrado para lectura y comprueba el permiso de cambio/borrado, pero no vuelve a limitar su alcance por delegación para `positionfunction`. Debe revisarse como caso potencial de autorización demasiado amplia antes del despliegue.
- `accounts.permissions.allowed_delegation_ids` calcula el alcance autorizado según perfil, permisos y roles, pero **no** aplica una restricción por creador/titular en cada queryset.

### Pendiente antes de cambiar permisos
Definir la política por operación y módulo: (a) empleado normal ve lo suyo y lo asignado, (b) responsable ve registros de sus delegaciones, (c) administrador accede a su alcance autorizado. Después hay que adaptar tanto listados como vistas de detalle, edición, borrado, exportaciones y acciones masivas, con pruebas de acceso cruzado y URL directa. La modificación de permisos no se ha implementado para no bloquear flujos municipales legítimos sin esa definición.
