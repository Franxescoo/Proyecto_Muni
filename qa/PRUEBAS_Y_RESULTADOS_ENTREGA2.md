# Revisión de la segunda entrega — código local

## Alcance

Versión integrada basada en `Proyecto_Muni_diseno_hora_corregidos.zip` / copia de trabajo previa `Proyecto_Muni_diseno_hora_chile`.
Se excluyeron deliberadamente **AWS, GitHub Actions, push/merge a main y recuperación de contraseñas**.

## Cambios implementados

1. **Acceso por delegación activa:** middleware valida delegaciones de `UserProfile` en cada solicitud, selector en la cabecera y cambio con `POST` protegido por CSRF. La selección no amplía el alcance de ningún rol; `allowed_delegation_ids` intersecta perfil + rol/permiso + delegación activa.
2. **Autorización de escritura:** editar o eliminar Actividades, Evidencias, Validaciones e Ingresos de Atención usa permisos y alcances de la operación correspondiente, no solamente el alcance de lectura. En Metas se comprueba `change_goal`/`delete_goal` para la delegación objetivo, incluida eliminación masiva.
3. **Organización:** se refuerza el bloqueo de modificaciones a Cargos compartidos y la creación global de Delegaciones para cuentas no superusuario. Empleados y Delegaciones aplican la intersección del permiso y ámbito para editar/archivar. Los accesos directos al formulario también se protegen.
4. **Monitoreo:** requiere permiso explícito de visualización para Indicadores, Compromisos y Auditoría. Los comentarios requieren permisos de agregar/eliminar y, para borrar, pertenecer al creador. Los botones también respetan esos permisos.
5. **Ingreso de Atención:** campo `registered_by` guarda automáticamente la cuenta que registra una atención, con migración no destructiva. La fecha/hora continúa automática. Para empleados vinculados que operan en su delegación principal, el empleado responsable se preselecciona y bloquea; la delegación se obtiene del contexto activo y es de solo lectura. En cuentas sin empleado vinculado se conserva el campo de empleado asignado como requisito del modelo original, pero la cuenta registradora siempre queda almacenada.
6. **Vista de Ingreso de Atención:** se muestra quién registró el ingreso, cuando esté disponible. Los antiguos registros mantienen `registered_by=NULL`, sin pérdida de sus otros datos.
7. **Pruebas y QA:** pruebas específicas para permisos, contexto, suplantación de formularios, Excel/filtros, cuentas y períodos, además de script acotado de carga local que se ejecuta solo con autorización del usuario.

## Comprobaciones realmente ejecutadas en una base SQLite temporal

| Ejecución | Resultado |
| --- | --- |
| `python manage.py check` | **OK**: sin problemas de configuración |
| `python manage.py makemigrations --check --dry-run` | **OK**: no faltan migraciones de modelos |
| `python manage.py migrate --noinput` | **OK** en base SQLite nueva, incluida migración `0009_attentionentry_registered_by` |
| Seguridad + catálogos + cuentas + comentarios + períodos (`29 tests`) | **OK: 29/29** |
| Integración, navegación, paginación y Registro (`13 tests`) | **OK: 13/13** |
| Vista Ver de organización y período cerrado (`2 tests`, controles adicionales) | **OK** |

**Total:** 42 pruebas distintas aprobadas en dos ejecuciones agrupadas, además de dos controles individuales. Las pruebas de las dos ejecuciones no son una ejecución unificada completa de todo el repositorio.

La batería completa de pruebas del proyecto **no quedó aprobada como conjunto**: algunas ejecuciones prolongadas excedieron el tiempo; pruebas antiguas esperaban versiones obsoletas del formulario de Usuarios o el texto del botón «Cerrar detalle». Se actualizaron esas pruebas para reflejar el comportamiento vigente; los detalles están en `accounts/test.py` y `organization/tests.py`. Las pruebas funcionales manuales del navegador, los escenarios de carga real y AWS todavía están **pendientes**.

## Verificación manual pendiente antes de liberar

| ID | Qué probar en navegador / base local | Esperado | Estado |
| --- | --- | --- | --- |
| QA-01 | Iniciar sesión con lectura Norte e intentar editar registro Norte | 403 | Pendiente |
| QA-02 | Abrir `?modal=view&id=<ID Sur>` desde cuenta Norte | 404 sin datos Sur | Pendiente |
| QA-03 | Cambiar a delegación autorizada sin rol operativo | Listas vacías o 403, sin datos ajenos | Pendiente |
| QA-04 | Manipular el campo delegación en Ingreso de Atención | Guardar solo delegación activa validada | Automatizada; UI pendiente |
| QA-05 | Crear ingreso de atención y revisar usuario/hora | `registered_by` corresponde a la sesión; hora America/Santiago | Automatizada parcial; UI pendiente |
| QA-06 | Excel Delegaciones, Roles, Usuarios, Ítems, Tipos, Subatenciones | Respeta filtros/alcance, sin campos sensibles | Automatizada parcial; UI pendiente |
| QA-07 | Validaciones, duplicados, desactivación y SweetAlert2 de seis CRUD | Error y confirmación correctos, sin pérdida histórica | Pendiente |
| QA-08 | Pantalla de usuario con dos delegaciones y navegación/cabecera | Selector muestra solo delegaciones autorizadas; contexto persistente | Automatizada parcial; UI pendiente |
| QA-09 | Intentar comentario sin permisos por POST directo | 403 y sin escritura | Automatizada parcial; UI pendiente |
| QA-10 | Carga local usando `python qa/carga_local.py --requests 30 --workers 3` | Registrar latencia media/p95 y errores | **No ejecutada** |

La guía también solicita evidencia sobre carga a escala mayor en un entorno de QA autorizado. No se simularon ni inventaron resultados de carga.

## Importante: registros propios frente a delegación

Esta versión endurece **operaciones** y **delegaciones autorizadas**. No impone automáticamente la regla universal «solo lo creado por mí» a los registros dentro de una misma delegación, porque la guía de Entrega 2 exige alcance por rol/delegación, y el modelo permite supervisión por responsable. Para aislar todos los registros por propietario se requiere una política específica por módulo y permiso de supervisión. Esto queda fuera del alcance ya acordado y no debe confundirse con una validación aprobada.

## Cambios no incluidos

- Recuperación de contraseña mediante código: trabajo del compañero.
- GitHub, workflows, scripts AWS, configuración del servidor remoto y despliegue: **sin modificar**.
- Credenciales, base de datos de producción, `db.sqlite3`, `.env`, `.venv`, `.git`, archivos de `media/`: **no incluidos en el ZIP**.
