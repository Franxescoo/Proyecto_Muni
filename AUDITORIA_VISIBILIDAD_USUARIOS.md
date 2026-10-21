# Auditoría preliminar de visibilidad y propiedad de datos

**Pregunta revisada:** «¿Un usuario solo puede ver sus propias cosas que hace?»

**Respuesta:** No como regla universal. El código implementa en varios módulos límites de **delegaciones autorizadas y permisos**, pero **pertenecer a una delegación no equivale a ser el autor o dueño del registro**.

| Funcionalidad | Comportamiento identificado | ¿Solo propio? |
|---|---|---|
| Organización: Roles y Usuarios | `organization.views.role_list` / `user_list` comprueban superusuario | No aplica: mantenedores administrativos |
| Metas | `planning_measurements.views.scoped_goals`: `employee__delegation_id__in=allowed_ids` | **No**; se muestran metas de otros empleados de la delegación permitida |
| Períodos | `planning_measurements.views.period_list`: lista períodos globales con permiso `view_period`, sin autor/propietario de período | **No**; los períodos son compartidos |
| Actividades | `registration_validation.views.scoped_activities`: `author__delegation_id__in=allowed_ids` | **No**; permite otras actividades de la misma delegación |
| Evidencias/validaciones | `scoped_evidences`/`scoped_validations`: delegación de la actividad asociada | **No**; permite otros autores de la misma delegación |
| Ingresos de atención | `scoped_attention_entries`: `delegation_id__in=allowed_ids` | **No**; el modelo `AttentionEntry` no conserva un `created_by` explícito |
| Monitoreo | `_scoped_queryset`: delegación del responsable/empleado, con una compatibilidad especial de perfiles antiguos | **No**; incluye registros de la unidad con acceso |
| Comentarios de compromisos | La operación de borrar exige `created_by=request.user` | **Sí, en esa operación concreta** |
| Ítems, Tipos de atención y Subatenciones | Catálogos compartidos, protegidos por `view_*`, no por autor individual | No aplica: catálogos globales |

## Aspectos de seguridad para revisar antes de producción

1. **Definir la política de visibilidad por rol.** Propuesta: empleado común ve registros que crea o tiene asignados; responsable ve los de sus delegaciones autorizadas; administrador autorizado ve el ámbito global. Requiere decisión del equipo municipal; no se modificó automáticamente.
2. El campo `Activity.author` referencia un **Empleado** y no siempre acredita qué cuenta realmente creó el registro; para auditoría de autoría conviene conservar un `created_by` a nivel de `User` y migrar de forma segura los datos antiguos.
3. `AttentionEntry` tiene `responsible_employee` (responsable) y `delegation`, pero no registra `created_by`. Si la regla es «ver lo que yo ingresé», habría que incorporar autoría y tratamiento de registros históricos.
4. En `monitoring_traceability.views` se usa una regla de compatibilidad con perfiles antiguos sin roles organizacionales cuando no se hallan delegaciones para un permiso. Debe revisarse si esa excepción de acceso sigue autorizada. Algunas vistas usan `@login_required` sin una comprobación separada del permiso Django de visualización.
5. Verificar en pruebas de seguridad las operaciones **GET, POST, exportar, edición, archivado y acciones masivas**. Ocultar botones no sustituye la autorización del servidor.
6. Los datos compartidos de catálogo y los períodos globales pueden requerir una política diferente de la propiedad individual.

**No se cambió el comportamiento de estas restricciones** para evitar alterar las tareas de supervisores, delegados o evaluadores sin aprobar antes una política concreta.

## Pruebas de aceptación recomendadas para una siguiente fase
- Dos empleados A y B en **Norte**: si la política es «solo lo propio», A no podrá consultar ni editar el trabajo creado por B.
- Responsable de Norte: puede consultar el trabajo de Norte, pero no el de Sur, salvo autorización adicional.
- Usuario con acceso únicamente a Sur: no puede acceder por URL ni por identificador a registros de Norte.
- Catálogos: usuarios sin `view_*` obtienen 403; usuarios con permiso consultan el catálogo sin privilegios de edición.
- Exportaciones y acciones masivas aplican exactamente los mismos límites que el listado correspondiente.
