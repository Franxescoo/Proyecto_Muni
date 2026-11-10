Sistema de Gestión de Resultados (SGR)
Proyecto Integrado — Municipalidad de La Serena · Segunda entrega

El Sistema de Gestión de Resultados (SGR) es una aplicación web desarrollada con Django para centralizar el registro, seguimiento y validación de información asociada a delegaciones, funcionarios, metas, actividades, evidencias, compromisos e indicadores. Busca mantener trazabilidad, facilitar la gestión municipal y aplicar controles de acceso según los permisos y las delegaciones autorizadas de cada usuario.
Integrantes del equipo
- Sofía Pizarro
- Lucas Rojas
- Lucas Godoy
- Marcos Olivares
Funcionalidades y alcance actual
El sistema incluye mantenedores y módulos para:
- Organización: delegaciones, funcionarios, cargos, roles y permisos.
- Cuentas: usuarios, perfiles, roles y delegaciones autorizadas.
- Ciudadanos y solicitudes ciudadanas.
- Planificación y mediciones: períodos, metas e ítems.
- Registro y validación: actividades, evidencias, validaciones,
  atenciones, servicios y subatenciones.
- Monitoreo y trazabilidad: indicadores, compromisos y auditoría.
- Eventos municipales: eventos, ediciones, campañas, beneficiarios,
  inscripciones, participantes y entregas.
- Mensajería institucional y chat en tiempo real.

Los listados se actualizan automáticamente cuando otro usuario crea, modifica
o elimina información de negocio. El refresco se realiza mediante WebSockets y
se aplaza si la persona está escribiendo, tiene un modal abierto o la pestaña
no está visible.

La aplicación también dispone de inicio y cierre de sesión, identificación de usuario y rol, delegación activa, y un módulo de Ingreso de Atención, que registra información del solicitante, tipo y subatención, delegación, responsable y fecha/hora. El acceso a estas funciones depende de los permisos de la cuenta.

En integración: el flujo de recuperación de contraseña mediante código está a cargo de otro integrante y no se declara terminado hasta que se incorpore y verifique.

El acceso a cada función depende de los permisos de la cuenta y del contexto
de delegación activa. Los cambios de relaciones ManyToMany relevantes también
publican actualizaciones en tiempo real.
Tecnologías utilizadas
- Lenguaje: Python 3.13.
- Framework: Django 6.1.
- Servidor ASGI: Daphne 4.2.1.
- Comunicación en tiempo real: Channels 4.3.2 y WebSockets.
- Interfaz: plantillas de Django, Bootstrap 5, CSS y JavaScript.
- Base de datos: SQLite para el entorno local; configuración disponible para MySQL.
- Channel layer: InMemoryChannelLayer en desarrollo y Redis mediante
  channels-redis en producción.
- Configuración: python-dotenv y variables de entorno.
- Control de versiones: Git y GitHub.
- Dependencias: requirements.txt (entorno de desarrollo) y requirements-aws.txt (servidor).
- Despliegue: flujo de GitHub Actions incluido en .github/workflows/deploy.yml.
Arquitectura y aplicaciones del proyecto
El sistema está organizado en aplicaciones Django según su responsabilidad:
organization — Organización
Gestiona la estructura organizacional, delegaciones, funcionarios, cargos y roles.

Modelos principales: Delegation, DelegationResponsibilityLog, OrganizationRole, PositionFunction y Employee.
planning_measurements — Planificación y mediciones
Gestiona los períodos, las metas y los ítems utilizados en su planificación.

Modelos principales: Period y Goal.
registration_validation — Registro y validación
Gestiona actividades, archivos de evidencia, validaciones y la clasificación y registro de atenciones.

Modelos principales: Activity, Evidence, EvidenceFile, Validation, ActivityType, AttentionType, Service, SubAttention y AttentionEntry.

Un flujo del sistema es:
Actividad → Evidencia → Validación
monitoring_traceability — Monitoreo y trazabilidad
Gestiona indicadores, compromisos, observaciones y auditoría.

Modelos principales: Indicator, Commitment, CommitmentComment y Audit.
municipal_events — Eventos municipales
Gestiona eventos, ediciones, campañas, beneficiarios, participantes,
inscripciones y entregas.

Modelos principales: MunicipalEvent, EventEdition, Campaign, Beneficiary,
Enrollment, GiftDelivery y EventParticipation.
citizen_registry — Registro de ciudadanos
Gestiona ciudadanos, sus datos de contacto, estado y vínculos con solicitudes.

Modelo principal: Citizen. Los registros de CitizenAudit son históricos y no
disparan refrescos de listados.
citizen_requests — Solicitudes ciudadanas
Gestiona solicitudes, seguimiento, asignación y derivación.
institutional_mail — Mensajería institucional
Gestiona los mensajes internos y sus estados de lectura y notificación.
accounts — Cuentas y perfiles
Gestiona información complementaria de los usuarios, roles asignados, delegaciones autorizadas y el contexto de delegación activa.
core — Elementos comunes
Contiene páginas y componentes compartidos, incluido el modelo base BaseModel que incorpora los campos:
- created_at: fecha de creación.
- updated_at: última actualización.
- deleted_at: fecha de borrado lógico, cuando corresponde.
config — Configuración general
Contiene la configuración de Django y las rutas principales de la aplicación.
Requisitos y puesta en marcha básica
Este apartado permite poner en marcha el proyecto para su revisión. No sustituye al manual detallado de instalación y despliegue, previsto para la tercera entrega.
1. Obtener el código
Repositorio del proyecto:

github.com/Franxescoo/Proyecto_Muni
git clone https://github.com/Franxescoo/Proyecto_Muni.git
cd Proyecto_Muni
2. Preparar el entorno virtual
python -m venv .venv
Activación en PowerShell (Windows):
.\.venv\Scripts\Activate.ps1
O en Git Bash (Windows):
source .venv/Scripts/activate
Instalar las dependencias:
python -m pip install -r requirements.txt
3. Configurar variables de entorno
Crear un archivo .env en la raíz del proyecto. El siguiente ejemplo corresponde únicamente al desarrollo local y no contiene claves reales:
DJANGO_SECRET_KEY=reemplazar-por-una-clave-segura
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
DB_ENGINE=sqlite
DB_NAME=db.sqlite3
El archivo .env está excluido del repositorio mediante .gitignore. No se deben publicar claves, contraseñas ni bases de datos con información privada.

Importante: una versión anterior de .env.example utiliza SECRET_KEY, pero config/settings.py lee la variable DJANGO_SECRET_KEY. Al preparar .env, utilizar este último nombre. La configuración permite también DB_ENGINE=mysql y las variables DB_NAME, DB_USER, DB_PASSWORD, DB_HOST y DB_PORT.
4. Comprobar, migrar y ejecutar
python manage.py check
python manage.py migrate
python manage.py runserver
Abrir http://127.0.0.1:8000/ e iniciar sesión con una cuenta habilitada por el equipo. Las operaciones de administración institucional se realizan desde la interfaz propia del SGR, según el rol y los permisos del usuario; no requieren utilizar una cuenta superusuario de Django.

Con DJANGO_DEBUG=False, runserver no sirve automáticamente todos los archivos estáticos; en el despliegue real estos deben publicarse mediante el servicio de archivos estáticos configurado para producción.

Para probar explícitamente la aplicación ASGI y los WebSockets en desarrollo:

```text
python -m daphne -b 127.0.0.1 -p 8000 config.asgi:application
```

La ruta de actualizaciones en tiempo real es `/ws/updates/` y la del chat es
`/ws/chat/`. En desarrollo se usa `InMemoryChannelLayer`, por lo que todas las
conexiones deben pertenecer al mismo proceso.
Datos de demostración y usuarios de prueba
El repositorio contiene un comando de carga de datos para el entorno de pruebas:
python manage.py seed
El comando prepara datos ficticios relacionados con delegaciones, funcionarios, cargos, períodos, metas, actividades, evidencias, indicadores, compromisos y auditoría; también crea una cuenta de prueba limitada, si no existe.

El comando utiliza operaciones como get_or_create y update_or_create para reutilizar o actualizar parte de los datos de prueba. Se debe ejecutar únicamente en una base de datos destinada a demostración, no en una base que contenga registros importantes o de producción. Para trabajar con cuentas normales autorizadas se utilizan los mantenedores de Roles y Usuarios del sistema.

Las contraseñas gestionadas por Django se almacenan mediante mecanismos de hash, no en texto plano en la base de datos. No se publican credenciales de prueba en este README.
Perfiles, permisos y delegaciones
El sistema considera tres conceptos distintos:
1. Delegación principal del empleado: indica dónde trabaja el funcionario.
2. Delegaciones autorizadas del usuario: define los contextos a los que puede acceder la cuenta.
3. Permisos y alcance del rol: determina qué operaciones puede realizar y en qué delegaciones están autorizadas.
Cuando una cuenta dispone de varias delegaciones autorizadas puede seleccionar una delegación activa desde la cabecera. Los listados presentan normalmente los datos del contexto seleccionado, en lugar de combinar todas las delegaciones en una sola tabla.

Los permisos distinguen consultar, crear, modificar y eliminar o desactivar, según la funcionalidad. La autorización debe comprobarse en el servidor: ocultar un botón no sustituye la validación de acceso. La gestión de Roles, Usuarios y Cargos se realiza con cuentas normales que tengan los permisos apropiados, sin depender de una cuenta superusuario para la operación del sistema.
Seguridad y trazabilidad
- Autenticación de Django con almacenamiento de contraseñas mediante hash.
- Controles de acceso por permiso, operación y delegación autorizada.
- Protección de información histórica mediante borrado lógico cuando el modelo lo contempla (deleted_at).
- Fechas de creación y modificación mediante created_at y updated_at.
- Zona horaria de visualización configurada como America/Santiago, conservando USE_TZ=True.
- Variables sensibles fuera del repositorio mediante .env.
Pruebas y verificaciones
Comprobaciones disponibles en el proyecto:
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
python manage.py test websocket
El proyecto cuenta con pruebas automatizadas y verificaciones manuales de los
mantenedores y módulos principales. El plan de pruebas en Excel, con sus casos,
resultados esperados, resultados obtenidos y evidencias, se entrega por
separado.

Las pruebas que no se hayan ejecutado o las funciones pendientes de integración deben quedar identificadas como tales; no se consideran aprobadas solo por estar documentadas.
Repositorio y trabajo colaborativo
El proyecto utiliza Git para conservar el historial de cambios y facilitar el desarrollo en equipo. El flujo de colaboración documentado es:
Rama → Commit → Push → Pull Request → Revisión → Merge
Esto permite organizar el aporte de los integrantes y vincular los cambios con las tareas y los casos de prueba. La versión evaluada debe corresponder al código efectivamente entregado.
Despliegue y versión de entrega
El repositorio incluye el flujo `.github/workflows/deploy.yml`, configurado
para actualizar el servidor AWS desde la rama `main`. Dicho flujo contempla
instalar dependencias, ejecutar comprobaciones, aplicar migraciones, recopilar
archivos estáticos y reiniciar el servicio configurado en el servidor.

Para que el chat y las actualizaciones globales funcionen en AWS, el servicio
de aplicación debe ejecutarse con la aplicación ASGI
`config.asgi:application`, mediante Daphne o un servidor ASGI equivalente. El
proxy o balanceador debe aceptar WebSockets y Redis debe estar disponible para
`channels-redis`. Con `DJANGO_DEBUG=False`, la configuración actual utiliza
Redis en `redis://127.0.0.1:6379`; si Redis se ejecuta en otro host, esa
configuración debe ajustarse antes del despliegue.

La existencia del flujo no acredita por sí sola que el despliegue final haya sido verificado. Antes de presentar la entrega, el equipo debe confirmar la versión desplegada y conservar la URL de evaluación y la referencia de commit correspondiente, sin incluir credenciales en la documentación pública.

Las migraciones necesarias se mantienen versionadas dentro de las aplicaciones Django.
Estado actual y próximos pasos
- La aplicación cuenta con actualización global de listados mediante WebSockets
  para los modelos de negocio conectados a `websocket/live.py`.
- Las pruebas específicas de esta integración se ejecutan con
  `python manage.py test websocket`.
- Antes de presentar una versión en AWS, verificar que el servicio use ASGI,
  que Redis esté disponible y que el commit desplegado corresponda a la rama 
  evaluada.
- Mantener fuera del repositorio las credenciales, claves, archivos `.env` y
  bases de datos con información privada.

Este README documenta el estado actual del proyecto y no contiene
credenciales ni datos personales reales.