Sistema de Gestión de Resultados (SGR)
Proyecto Integrado — Municipalidad de La Serena · Segunda entrega

El Sistema de Gestión de Resultados (SGR) es una aplicación web desarrollada con Django para centralizar el registro, seguimiento y validación de información asociada a delegaciones, funcionarios, metas, actividades, evidencias, compromisos e indicadores. Busca mantener trazabilidad, facilitar la gestión municipal y aplicar controles de acceso según los permisos y las delegaciones autorizadas de cada usuario.
Integrantes del equipo
- Sofía Pizarro
- Lucas Rojas
- Lucas Godoy
- Marcos Olivares
Funcionalidades y alcance de la segunda entrega
Los seis mantenedores principales solicitados para esta entrega son:
Mantenedor	Funcionalidades revisadas
Delegaciones	Crear, consultar, modificar y cambiar estado; búsqueda, filtros y exportación.
Roles y permisos	Crear, consultar y modificar roles; asignar permisos y delegaciones autorizadas.
Usuarios	Gestionar cuentas, perfiles, roles, delegaciones autorizadas y estado.
Ítems	Gestionar los ítems utilizados por la planificación y las metas.
Tipos de Atención	Gestionar el catálogo de tipos de atención y sus estados.
Subatenciones	Gestionar las subatenciones y asociarlas a un tipo de atención.


Los seis mantenedores fueron revisados manualmente durante el desarrollo; las verificaciones abarcan operaciones habituales, búsquedas, filtros y exportación a Excel según cada pantalla. Los resultados y evidencias concretos se registran en el plan de pruebas, que es un entregable separado.

La aplicación también dispone de inicio y cierre de sesión, identificación de usuario y rol, delegación activa, y un módulo de Ingreso de Atención, que registra información del solicitante, tipo y subatención, delegación, responsable y fecha/hora. El acceso a estas funciones depende de los permisos de la cuenta.

En integración: el flujo de recuperación de contraseña mediante código está a cargo de otro integrante y no se declara terminado hasta que se incorpore y verifique.

Existen además funciones de empleados, cargos y funciones, períodos, metas, actividades, evidencias, validaciones, indicadores, compromisos y auditoría. Su presencia en el repositorio no implica que todas las funcionalidades previstas para entregas posteriores estén finalizadas.
Tecnologías utilizadas
- Lenguaje: Python 3.13.
- Framework: Django 6.1.
- Interfaz: plantillas de Django, Bootstrap 5, CSS y JavaScript.
- Base de datos: SQLite para el entorno local; configuración disponible para MySQL.
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
Para la segunda entrega, el equipo ha comprobado manualmente los seis mantenedores y ha ejecutado pruebas automatizadas. El plan de pruebas en Excel, con sus casos, resultados esperados, resultados obtenidos y evidencias, se entrega por separado.

Las pruebas que no se hayan ejecutado o las funciones pendientes de integración deben quedar identificadas como tales; no se consideran aprobadas solo por estar documentadas.
Repositorio y trabajo colaborativo
El proyecto utiliza Git para conservar el historial de cambios y facilitar el desarrollo en equipo. El flujo de colaboración documentado es:
Rama → Commit → Push → Pull Request → Revisión → Merge
Esto permite organizar el aporte de los integrantes y vincular los cambios con las tareas y los casos de prueba. La versión evaluada debe corresponder al código efectivamente entregado.
Despliegue y versión de entrega
El repositorio incluye el flujo .github/workflows/deploy.yml, configurado para actualizar el servidor AWS desde la rama main. Dicho flujo contempla instalar dependencias, ejecutar comprobaciones, aplicar migraciones, recopilar archivos estáticos y reiniciar el servicio.

La existencia del flujo no acredita por sí sola que el despliegue final haya sido verificado. Antes de presentar la entrega, el equipo debe confirmar la versión desplegada y conservar la URL de evaluación y la referencia de commit correspondiente, sin incluir credenciales en la documentación pública.

Las migraciones necesarias se mantienen versionadas dentro de las aplicaciones Django.
Estado actual y próximos pasos
- Revisado para la segunda entrega: seis mantenedores, inicio de sesión, perfiles y permisos, y delegación activa; el plan de pruebas y los diagramas se trabajan como entregables separados.
- Pendiente de integración/verificación: recuperación de contraseña mediante código, a cargo de otro integrante.
- Por verificar antes de presentar: que el código final, los diagramas, el plan de pruebas y la versión disponible en AWS correspondan al mismo incremento.
- Tercera entrega: manual detallado de instalación y despliegue, de acuerdo con la planificación del equipo.
Este README reúne la información del documento original y las actualizaciones de la segunda entrega. No contiene credenciales ni datos personales reales.