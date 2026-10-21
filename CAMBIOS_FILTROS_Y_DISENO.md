# Proyecto_Muni — Unificación de los seis mantenedores

**Base:** `Proyecto_Muni_actualizado_empleados.zip` (versión integrada anterior, no una copia del equipo ni de AWS).

## Implementado

### Interfaz común (solo los seis mantenedores obligatorios)
- Tarjetas de resumen **fuera** del panel principal.
- Cabecera del panel con título y acciones `Crear/Nuevo` y `Exportar Excel`.
- Formulario de filtros **dentro** del panel, con los botones **Filtrar** y **Limpiar**.
- Selector **Registros por página** (10, 25 o 50) y botón **Guardar preferencia**, persistido en la sesión Django.
- Contador de registros y controles **Anterior / Página N de M / Siguiente**, visibles también con una sola página.
- Al paginar se conservan todos los parámetros de búsqueda y filtros.
- Estilos reutilizables en `static/css/catalog_uniform.css` y componentes de plantilla en `templates/shared/`.
- Los botones y tablas comparten clases/estilos, sin modificar las páginas de edición ni cambiar rutas existentes.

### Filtros específicos
| Mantenedor | Filtros |
|---|---|
| Delegaciones | Texto, **comuna**, estado |
| Roles | Texto, **delegación de aplicación** (múltiple en el modelo) |
| Usuarios | Texto, **delegación autorizada, rol, estado** |
| Ítems | Texto, tipo (cuantitativo/porcentual), estado (ya existían, se uniformó diseño) |
| Tipos de atención | Texto y estado (ya existían, se uniformó diseño) |
| Subatenciones | Texto, **tipo de atención**, estado |

### Exportaciones `.xlsx`
- Se conservaron las existentes en Delegaciones, Roles y Usuarios y se les aplican también los filtros desplegables nuevos.
- Se agregaron exportaciones en **Ítems, Tipos de atención y Subatenciones**, usando los filtros del listado y sus respectivos permisos `view_*`.
- No se añadió ninguna migración de esquema, tabla ni campo a la base de datos.

### Archivos principales
- `organization/views.py`, `organization/urls.py`, `templates/organization/{roles,delegations,users}.html`
- `planning_measurements/views.py`, `planning_measurements/urls.py`, `templates/planning/item_list.html`
- `registration_validation/views.py`, `registration_validation/urls.py`, `templates/registration_validation/{attention_type_list,sub_attention_list}.html`
- `templates/shared/catalog_page_size.html`, `templates/shared/catalog_pagination.html`
- `templates/base.html`, `static/css/catalog_uniform.css`
- `organization/test_catalog_uniform.py`: pruebas nuevas de visualización, filtros, opciones por página, enlaces de paginación y Excel.

## Pruebas efectuadas
- `manage.py check`: correcto.
- `manage.py makemigrations --check --dry-run`: ninguna migración pendiente.
- `organization.tests organization.test_integrated_changes registration_validation.tests`: **39 aprobadas**.
- `organization.test_catalog_uniform`: **9 aprobadas**.
- `planning_measurements.test_closed_periods monitoring_traceability.tests`: **13 aprobadas**.
- `planning_measurements.tests`: **53 aprobadas**.
- En total, **114 pruebas aprobadas en ejecuciones separadas**. Una ejecución combinada se interrumpió por tiempo, por lo que no se considera aprobada.

## Alcance y límites
- La **uniformidad visual** se aplicó a los **seis mantenedores obligatorios**. Otras pantallas operativas (Metas, Períodos, Indicadores, Compromisos, etc.) conservan sus componentes y flujos específicos. No se ha reescrito el sitio completo.
- No se hicieron cambios sobre las reglas de autorización o propiedad de registros. **Ver `AUDITORIA_VISIBILIDAD_USUARIOS.md`.**
- No se ha ejecutado contra la base de datos real del usuario ni AWS. Las pruebas usan bases temporales.
- No se incorporan archivos de entorno, bases SQLite, medios ni secretos.

## Instalación segura
1. Respaldar la versión actual y `db.sqlite3` por separado (y `media/` si aplica).
2. Descomprimir el ZIP en **otro directorio**, comparar los cambios y preservar `.git`, `.env`, `.venv`, `media/` y `db.sqlite3` del entorno local.
3. Integrar solo el código y los templates sobre una rama Git de trabajo.
4. Ejecutar `python -m pip install -r requirements.txt`, `python manage.py check`, `python manage.py makemigrations --check --dry-run` y las pruebas listadas arriba.
5. **No deberían existir migraciones nuevas**; si se solicitan, detenerse y revisar las diferencias antes de ejecutarlas.
6. Probar manualmente los seis listados y los permisos con cuentas reales representativas.
7. **No subir sin revisión a `main`**. El GitHub Actions del proyecto despliega en AWS automáticamente.
