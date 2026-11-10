# Entrega — Ver, formularios, logo y acciones de Metas

## Aplicado

- **Metas** (`templates/planning/goal_list.html`): acciones Ver, Modificar y Eliminar en la **misma fila**. Eliminado el `flex-wrap: wrap` de `.goal-actions` y reservada anchura para la columna de acciones; la tabla mantiene desplazamiento horizontal en pantallas pequeñas. Se añadieron íconos junto a los nombres.
- **Organización**: enlaces `Ver` en las tablas de **Delegaciones, Empleados, Cargos y funciones, Roles y Usuarios**. `?modal=view&id=<id>` abre el formulario del registro con campos deshabilitados y sin botón Guardar. Las consultas respetan las restricciones de lectura de cada vista; Roles/Usuarios siguen siendo exclusivos de superusuarios.
- **Otros catálogos** (`static/js/catalog_details.js`): donde haya tabla dentro de `.sgr-catalog` con columna Acciones y sin un botón Ver existente, se agrega un botón **Ver** que despliega una ficha de solo lectura **con los campos ya visibles en esa tabla**. No solicita información nueva al backend ni amplía permisos. Para consultar campos no incluidos en la tabla se necesitaría una vista de detalle específica.
- **Estética de formularios**: `static/css/municipal_forms.css`, cargado desde `templates/base.html`. Encabezados rojos institucionales, estructura clara, foco y ayudas uniformes, footer y botones mejorados; afecta los modales existentes de Crear/Editar/Ver sin cambiar su procesamiento.
- **Inicio de sesión**: logo de La Serena validado en `static/img/logotamarindo.png`; se conserva la referencia con `{% static %}` y se incluye una imagen de respaldo local embebida para cuando la URL del estático no cargue en el navegador.
- **Alineación de acciones**: `.sgr-catalog` mantiene Ver, Modificar y Eliminar juntos incluso con tablas anchas. El contenedor horizontal de la tabla permite desplazamiento cuando haga falta.

## Qué NO se modificó

- Modelos y migraciones, datos reales, lógica de autorización o filtros, ni rutas de producción.
- Los permisos por propietario o asignación siguen sujetos a la auditoría previa; esta entrega es principalmente de interfaz.

## Pruebas

- `python manage.py check`: correcto.
- `python manage.py makemigrations --check --dry-run`: `No changes detected`.
- `python manage.py findstatic img/logotamarindo.png`: archivo encontrado.
- `node --check static/js/catalog_details.js`: sintaxis válida.
- 2 pruebas específicas para modales Ver de Organización: aprobadas.
- 4 pruebas acotadas para Ver y mantenedores: aprobadas.
- 38 pruebas de Organización (ejecución inicial): aprobadas.
- La batería ampliada de Organización y Registro no completó dentro del tiempo disponible. **No** se considera aprobada la batería integral.

## Instalación segura

1. Conserva un respaldo completo de la carpeta de proyecto y de los datos.
2. Incorpora el código actualizado en una rama de Git, **sin reemplazar** `.git`, `.env`, `.venv`, `db.sqlite3` o `media/`.
3. Ejecuta `python -m pip install -r requirements.txt`, `python manage.py check`, `python manage.py makemigrations --check --dry-run` y `python manage.py test` localmente.
4. No se introducen migraciones nuevas en esta entrega. Inicia `runserver` y comprueba el login, los modales Ver/Crear/Editar y la tabla de Metas.
5. No subas directamente a `main` hasta verificar los cambios; tu GitHub Actions despliega a AWS al recibir un push a esa rama.
