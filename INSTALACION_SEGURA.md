# Cómo incorporar esta versión de Proyecto_Muni sin perder datos

El archivo ZIP contiene un directorio `Proyecto_Muni/` con el **código del proyecto**, no con tus datos reales.

## Método seguro recomendado en Windows / VS Code

1. Cierra el servidor Django y **respáldate** la carpeta de proyecto original y su base `db.sqlite3` (si usas SQLite local). Conserva una copia separada de `media/`.
2. **No borres ni reemplaces** tus carpetas `.git/`, `.venv/`, `media/`, tu archivo `.env`, `db.sqlite3`, `db_backup.sqlite3` ni cualquier otro secreto o fichero de entorno.
3. Descomprime el ZIP en **otra carpeta temporal**. Revisa `CAMBIOS_IMPLEMENTADOS.md` y compara archivos.
4. Usa tu rama de desarrollo (por ejemplo `feature/planning_measurements`) y copia/integra **los archivos de código, plantillas y migraciones** desde el directorio `Proyecto_Muni/` descomprimido hacia tu proyecto actual, sin reemplazar los datos protegidos.
5. Confirma que tus dependencias están instaladas usando el Python del entorno: `python -m pip install -r requirements.txt`.
6. Ejecuta en el proyecto original, con el entorno virtual activo:
   ```bash
   python manage.py check
   python manage.py makemigrations --check --dry-run
   python manage.py migrate
   python manage.py test organization.tests organization.test_integrated_changes
   python manage.py test planning_measurements.tests planning_measurements.test_closed_periods
   python manage.py test registration_validation.tests monitoring_traceability.tests
   python manage.py runserver
   ```
7. Verifica manualmente: Usuarios, Empleados, Delegaciones, Roles, permisos por delegación, archivos Excel, Responsable y restricciones de Períodos cerrados.
8. **Antes de fusionar a `main`**, revisa el diff de Git, los resultados y **haz respaldo de la base AWS**. GitHub Actions aplicará las migraciones automáticamente al desplegar.

## Precauciones

- No ejecutes `makemigrations` para crear migraciones nuevas sin revisar primero las incluidas.
- Si fallan `migrate` o los tests, **detente**. No borres tablas ni reinicies la base de datos para “arreglar” el error.
- Una migración contra una base de datos real ya poblada puede revelar restricciones que las pruebas con bases temporales no muestran. En ese caso prepara y prueba una migración de datos específica, sin hacer cambios destructivos.
- `requirements-aws.txt` ya contempla `openpyxl` para la exportación Excel.
- La ruta de Empleados es `/organization/empleados/`; la ruta antigua de Funcionarios sigue disponible por compatibilidad.
