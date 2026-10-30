# Eventos y Campañas municipales — Implementación sobre Proyecto_Muni

## Alcance y funcionamiento

Se agregó la app independiente `municipal_events` para conservar los modelos existentes de `registration_validation`, `citizen_requests` y `organization`.

1. **Eventos recurrentes**: evento principal y ediciones por año, con fecha, lugar, delegación responsable, estado y observaciones. Un evento tiene como máximo una edición por año. Se pueden crear y modificar eventos y ediciones; las ediciones de años anteriores permanecen visibles.
2. **Campañas**: campañas con título, año, tipo de atención relacionado (FK a `registration_validation.AttentionType`), edición de evento opcional, delegación organizadora, fechas y estado Borrador/Abierta/Cerrada. Se pueden crear, consultar, modificar, buscar y paginar. Los registros están relacionados por claves reales, **no por texto ni por IDs fijos**.
3. **Ingreso de Atención → Inscribir en campaña**: botón contextual en cada fila del listado `Registro y Validación → Ingreso de Atención`, solo si el tipo de la atención tiene una campaña abierta dentro de las fechas vigentes y el usuario posee los permisos y alcance territorial requeridos. El botón ofrece elegir una campaña de ese tipo de atención.
4. **Inscripciones**: el usuario registra nombre, RUT con dígito verificador y nacimiento del niño; enlaza la inscripción con la atención y su delegación, sin crear ni duplicar una nueva atención. Una atención admite varios niños. La inscripción inicia Pendiente.
5. **Antiduplicados**: RUT normalizado y único por beneficiario; restricción de base de datos para el par (campaña, beneficiario), comprobación previa y manejo de conflictos concurrentes. Opera entre todas las delegaciones, no solo la activa; la advertencia no revela datos de otras delegaciones.
6. **Revisión y entregas**: un autorizado puede aprobar/rechazar documentando el motivo. Solo una inscripción aprobada permite registrar una entrega; una restricción OneToOne y una transacción impiden entregas repetidas. Cambios, actor y fecha se conservan en el historial.
7. **Permisos territoriales**: se comprueban del lado del servidor con `user.has_perm()` y `allowed_delegation_ids`, que mantienen la configuración actual de roles + delegaciones autorizadas del proyecto. Los datos personales de inscripciones se muestran únicamente a usuarios con permiso de ver inscripciones y en su delegación activa. No se usan superusuarios para la operación.
8. **Integración visual**: tarjetas nuevas en Inicio, pantallas con el encabezado rojo institucional, paginación y búsqueda de campañas y beneficiarios. No se modificó el portal ciudadano, su bandeja, ni el chat.

## Archivos NUEVOS

- `municipal_events/__init__.py`, `apps.py`, `models.py`, `forms.py`, `views.py`, `services.py`, `urls.py`, `tests.py`.
- `municipal_events/migrations/0001_initial.py` y archivos `__init__.py` de migraciones y templatetags.
- `municipal_events/templatetags/municipal_campaigns.py` (botón dinámico contextual).
- `templates/municipal_events/{base,events,campaigns,form,campaign_picker,enroll_form,campaign_detail}.html`.

## Archivos EXISTENTES modificados

- `config/settings.py`: añade `municipal_events` a `INSTALLED_APPS`.
- `config/urls.py`: añade la ruta `/eventos-campanas/`.
- `core/modules.py`: incorpora dos tarjetas al inicio, dependientes de permisos de rol.
- `organization/permission_labels.py`: incorpora los permisos funcionales de la nueva app al catálogo en español de Roles y Permisos.
- `templates/registration_validation/attention_entry_list.html`: añade `load municipal_campaigns` y un enlace contextual. **No se modificaron los modelos, vistas, formularios ni migraciones de `registration_validation`**.

## Instalación local (PowerShell con .venv ya activado)

1. Haz una copia de seguridad de tu base de datos y conserva la carpeta actual del proyecto.
2. Incorpora los archivos entregados a tu proyecto, conservando tu `.env`, `.venv`, `.git`, base de datos y `media`.
3. Ejecuta:
   ```powershell
   python manage.py check
   python manage.py migrate
   python manage.py test municipal_events
   ```
4. Desde **Roles y Permisos**, un administrador autorizado distinto del usuario que tiene asignado ese rol debe conceder al grupo correspondiente los permisos necesarios:
   - `Ver eventos municipales`, `Crear/Modificar eventos`, `Crear/Modificar ediciones` (opcional según cargo).
   - `Ver/Crear/Modificar campañas`.
   - `Ver/Crear/Modificar inscripciones a campañas`.
   - `Crear entregas de regalos`.
   - `Ver atenciones` de `registration_validation` para acceder desde una atención.
5. Verifica que el usuario tenga las delegaciones autorizadas y la delegación activa correcta (las restricciones territoriales se siguen aplicando).
6. En el mantenedor existente de Tipos de atención, crea un tipo como **Campañas municipales** (si aún no existe) y una subatención adecuada para registrar atenciones. Después crea la campaña desde el nuevo módulo, seleccionando **ese tipo real**.
7. Para poder inscribir hoy, selecciona estado **Inscripciones abiertas** y un intervalo de fechas que incluya la fecha actual. Al crear una atención con ese tipo, aparecerá `Inscribir en campaña` para usuarios autorizados.

## AWS

- No copies datos SQL ni claves locales; no copies `.env` al ZIP.
- Antes de desplegar, respalda MySQL. En EC2, después de actualizar el código y activar `.venv`, ejecuta `python manage.py migrate` y `python manage.py check`, y reinicia el servicio según tu procedimiento actual.
- La migración crea solamente las tablas nuevas de `municipal_events`. No elimina registros existentes ni crea tipos de atención por su nombre.
- Las **asignaciones de permisos a grupos y los datos de catálogos son distintos entre bases de datos**: configura el rol y crea el tipo y campaña desde la interfaz de AWS, sin `createsuperuser`.
- Para la entrega académica, usa RUT y nombres **ficticios válidos**; evita datos reales de menores en demostraciones.

## Pruebas ejecutadas en el entorno de trabajo

- `python manage.py check`: **OK**.
- `python manage.py makemigrations --check --dry-run`: **sin cambios pendientes**.
- `python manage.py test municipal_events`: **9/9 OK** (permisos, otra delegación, tipos, duplicados transversales, aprobación, entrega única, edición anual, templates).
- `python manage.py test municipal_events organization accounts citizen_requests`: **173/173 OK** (incluye 9 nuevas y 164 preexistentes).
- La suite completa `python manage.py test` excedió el tiempo de ejecución disponible; **no se afirma que esté aprobada**.
- Las pruebas se ejecutaron con una configuración temporal SQLite para verificación en el contenedor, no con la MySQL local ni la MySQL AWS del usuario. Ejecuta nuevamente con tu `.env` y base de datos.

## Reglas aún pendientes de definición por el profesor

- Edad máxima/mínima permitida, custodias, familias con beneficiarios en distintas delegaciones.
- Criterios institucionales de aprobación y documentos requeridos antes de entregar.
- Políticas de conservación de datos personales de menores y, si aplica, cifrado del RUT en reposo; actualmente se almacena normalizado en BD y su visualización queda restringida.
- El Portal Ciudadano sigue registrando solicitudes normalmente y Registro y Validación las convierte a atenciones; la vinculación con campañas comienza **desde la atención**, no desde una solicitud pública automáticamente.
- No existe stock/inventario de regalos, entrega masiva, avisos de regalos por email, ni reglas de cupo por campaña. No fueron implementados para no inventar criterios institucionales.

## Notas de conservación

- No se modificó ni borró el contenido de las demás apps salvo los **cuatro archivos de integración** descritos arriba y el template de Ingreso de Atención.
- No se creó ningún superusuario, no se alteraron permisos de grupos existentes, no se migraron datos privados y no se realizó ningún despliegue real.
- El proyecto se entrega como código fuente de Django para integrarlo con el entorno local que ya tienes; el ZIP omite intencionalmente `.env`, `.venv`, `.git`, archivos de BD y `media`.
