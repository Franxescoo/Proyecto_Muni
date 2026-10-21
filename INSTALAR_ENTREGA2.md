# Incorporar esta versión de Entrega 2 sin afectar el despliegue

1. **No la subas a main**. Mantén el proyecto actual y trabaja con una copia o rama local.
2. Con el servidor detenido, crea un respaldo de `db.sqlite3` (o del motor de BD que uses), `.env` y `media/`. Conserva `.git` y `.venv` de tu proyecto local.
3. Descomprime el ZIP en una carpeta nueva. Copia exclusivamente código, plantillas, migraciones y pruebas; no reemplaces tus datos ni tu entorno.
4. En Windows Git Bash, activa `source .venv/Scripts/activate`, luego ejecuta `python -m pip install -r requirements.txt`.
5. Ejecuta por este orden:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --plan
python manage.py migrate
python manage.py test registration_validation.test_entrega2_security organization.test_catalog_uniform accounts.test
python manage.py runserver
```

6. Revisa primero **Usuarios, Roles, Delegaciones e Ingreso de Atención** con cuentas de prueba. Para los demás módulos, revisa GET, POST y URLs directas sin permisos.
7. Solo después de validación local se debe planificar la integración con la rama de entrega; los archivos de AWS/GitHub quedaron intactos.

Nueva migración: `registration_validation/migrations/0009_attentionentry_registered_by.py`. Agrega columna opcional sin borrar registros existentes. Registros antiguos sin usuario permanecen sin atribución histórica; no debe rellenarse automáticamente con datos inventados.
