# Entrega: interfaz unificada y revisión de permisos

## Qué cambia
- Paginación uniforme: contador a la izquierda y controles centrados `Anterior | 1 / 1 | Siguiente` en 16 listados, visibles incluso con una sola página.
- Botones Crear/Agregar y Exportar Excel (cuando esta función existe) en la zona superior derecha de cada panel actualizado.
- Acciones de tabla con ícono + texto en las pantallas ajustadas.
- Empleados y Cargos/Funciones ahora incorporan Limpiar, selector 10/25/50 y paginación real sin cambiar la estructura de datos.
- Conserva filtros, rutas y confirmaciones existentes.

## Autorización
No se cambia ningún permiso. La regla "solo registros propios/asignados" NO está garantizada: varios módulos filtran por delegación, no por persona creadora. Ver `CAMBIOS_DISENO_FINAL_Y_AUDITORIA.md` para hallazgos por módulo y caso potencial de alcance indebido en Cargos/Funciones. No desplegar en producción suponiendo que la autorización individual ya está resuelta.

## Verificaciones
- `python manage.py check`: correcto.
- `python manage.py makemigrations --check --dry-run`: sin migraciones pendientes.
- 58 pruebas de Organización y Registro/Validación: correctas.
- 2 pruebas nuevas de paginación en Empleados/Cargos: correctas.
- 1 prueba de renderizado de los 16 listados: correcta.
- 13 pruebas de períodos cerrados y Monitoreo: correctas.
- Se observaron 6 fallos en pruebas heredadas de `accounts/test.py` que todavía esperan el formulario antiguo de creación de cuentas, no atribuidos a esta modificación visual. La ejecución más extensa de Planificación y Monitoreo alcanzó su tiempo límite y no se da por aprobada.

## Instalación
Revisar `INSTALACION_SEGURA.md`. No sobreescribir `.git`, `.venv`, `.env`, `db.sqlite3` ni `media/`, y no hacer merge en `main` antes de probar con tus datos y respaldar AWS.
