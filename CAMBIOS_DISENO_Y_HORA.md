# Corrección de diseño y hora — 21 de octubre de 2026

## Cambios incluidos

1. Los estilos institucionales de formularios y listados ahora están insertados en `templates/base.html` dentro del bloque `<style>`. Ya no dependen de peticiones a `/static/css/municipal_forms.css` ni `/static/css/catalog_uniform.css`, que daban error en el navegador del usuario. Se conservan los CSS fuente para referencia.
2. Los botones de Crear/Agregar y Exportar se alinean a la derecha en los listados administrativos, incluidos los que no tienen una envoltura `catalog-toolbar-actions`.
3. «Agregar período» en `templates/planning/period_list.html` y «Agregar meta» en `templates/planning/goal_list.html` usan `btn btn-success` sin `btn-sm`, como los demás botones de creación.
4. En `config/settings.py`, `TIME_ZONE = 'America/Santiago'` y se conserva `USE_TZ = True`. Django guarda instantes conscientes en UTC y los presenta en horario chileno (incluyendo cambios estacionales) al usar filtros de plantilla como `date`. Esto NO reescribe horas antiguas en la base de datos.
5. `STATIC_URL = '/static/'` establece rutas absolutas para los archivos estáticos existentes. Los CSS institucionales ya están en la plantilla y no requieren servicio de archivos estáticos para funcionar.

## Qué no se modificó

No se modificaron modelos, vistas, formularios, permisos, rutas, migraciones ni la base de datos. Las acciones Ver/Crear/Modificar conservan sus envíos originales.

## Instalación

- Mantener la base de datos `db.sqlite3`, el archivo `.env`, la carpeta `.venv`, `.git` y los archivos de `media/` de la instalación anterior.
- Incorporar el código de este ZIP en una rama de desarrollo y verificar `python manage.py check` antes de desplegar.
- No hace falta ejecutar `makemigrations` para estos cambios; `python manage.py migrate` no debería agregar tablas por esta entrega.
- Reiniciar el servidor y forzar recarga del navegador con Ctrl+F5.
- En local, si `DJANGO_DEBUG=False`, Django `runserver` no sirve archivos estáticos por defecto (por ejemplo, logos); use configuración de desarrollo apropiada solo en local, o configure el servidor estático para producción.
- En AWS, verificar que `collectstatic` y el servidor web sigan sirviendo `/static/`.

## Comprobaciones visuales sugeridas

1. Abrir Crear meta: cabecera roja institucional y secciones diferenciadas.
2. Abrir Crear rol/usuario: mismo estilo.
3. Comprobar Crear/Exportar a la derecha en Ítems y Organización.
4. Comprobar botón verde «Agregar período».
5. Comprobar hora de una creación nueva con la hora local de Chile. Las horas existentes que fueron registradas con valores incorrectos por alguna otra causa requerirán análisis independiente.
