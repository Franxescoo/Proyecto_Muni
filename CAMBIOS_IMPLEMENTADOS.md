# Proyecto_Muni — Cambios integrados

**Base:** código de `Proyecto_Muni(9).zip` entregado en la conversación.

## Cambios incorporados

### 1. Interfaz «Empleados»
- El mantenedor de **Funcionarios** ahora se muestra como **Empleados**: navegación, títulos, tarjetas, mensajes y formulario del mantenedor.
- URL principal: `/organization/empleados/`.
- La ruta antigua `/organization/funcionarios/` **se conserva** para no romper vínculos existentes.
- **No se cambiaron** nombres de tablas/modelos, claves externas ni relaciones `Employee` de Django; otros módulos conservan nombres internos históricos.

### 2. Mantenedor de Delegaciones
- Formularios con **Código, Nombre, Dirección, Comuna, Ámbito, Responsable y Estado**.
- Código único y validaciones de campos; se conservan registros antiguos sin completarlos automáticamente.
- Lista con búsqueda parcial, paginación y exportación `.xlsx` filtrada.
- Responsable principal seleccionable entre empleados de esa delegación y registro de cambios de responsable (anterior/nuevo/usuario/fecha).
- Una delegación se crea primero y luego se le asigna un responsable al editarla.
- Protección adicional al archivar delegaciones vinculadas o empleados que son responsables.

### 3. Mantenedor de Roles
- **Descripción** para cada Rol.
- **Múltiples delegaciones de aplicación** para un Rol, preservando `OrganizationRole.delegation` (relación principal existente).
- Selección de permisos `auth.Group`, búsqueda por nombre, descripción y delegaciones; paginación y exportación Excel.
- Bloqueo de eliminación de Roles asignados a Usuarios, Empleados o Cargos.

### 4. Mantenedor de Usuarios
- Crear y editar nombre de cuenta, nombres y apellidos, correo, código, empleado asociado opcional, **varias delegaciones autorizadas**, roles y estado activo/inactivo.
- Contraseña al crear; las modificaciones de contraseña siguen siendo un flujo distinto.
- Protección de la vinculación única `UserProfile.employee`; los perfiles archivados no liberan automáticamente el vínculo.
- Bloqueo de eliminación lógica de un Usuario que continúa vinculado a un Empleado. Las cuentas desvinculadas pueden archivarse.
- Sincronización: los roles se gestionan desde Usuario y se muestran en Empleado como referencia.
- Se eliminó el **buscador duplicado**. Las tres tarjetas de resumen vuelven a mostrarse juntas; búsqueda en el panel de usuarios.
- Paginación visible con contador incluso con una página. Excel para Usuarios.

### 5. Permisos por delegaciones múltiples
- Se conservan las relaciones principales `ForeignKey`; se usan relaciones adicionales `ManyToMany` creadas en las migraciones de la versión base.
- Se incorporó cálculo de delegaciones efectivas: autorización del Usuario **intersección** delegaciones del Rol para el permiso concreto.
- Ajustes de filtrado y validación por delegación en Organización, Planificación, Registro/Validación y Monitoreo.
- La delegación principal de un Empleado permanece independiente.

### 6. Períodos cerrados
- Nuevo permiso `planning_measurements.delete_closed_period`, asignable **directamente al Usuario desde Editar Usuario** (sin otorgarlo a todo un Rol).
- Para archivar un período cerrado se exige permiso normal `delete_period` más el permiso especial directo, o ser superusuario.
- Se impide el archivo de períodos con Metas/historial dependiente, incluso si las Metas fueron archivadas.
- Se registra el usuario y la fecha del archivo mediante `PeriodArchiveLog`.
- La interfaz restringe el botón de eliminación de período cerrado en ausencia del permiso especial.

## Migraciones nuevas incluidas
- `organization/migrations/0015_role_description_delegation_responsible.py`: descripción, responsable y auditoría.
- `planning_measurements/migrations/0006_closed_period_archive_permission_log.py`: permiso especial y auditoría.
- Incluye asimismo las migraciones de delegaciones múltiples y detalles de delegación que ya estaban en el ZIP `(9)`.

## Validaciones efectuadas en el entorno de revisión
- `manage.py check`: correcto.
- `manage.py makemigrations --check --dry-run`: sin diferencias pendientes.
- Pruebas `organization.tests`: **29 aprobadas** (adaptadas a las reglas acordadas).
- Pruebas de integración nuevas y de los módulos Registro/Monitoreo: **23 aprobadas**.
- La suite específica anterior de Planificación también se ejecutó por separado: **53 aprobadas**.
- Las nuevas migraciones se aplicaron en las bases temporales de pruebas Django.
- **No se completó una ejecución conjunta de todas las pruebas**: una ejecución integral alcanzó el límite de tiempo del entorno. Esto no equivale a una validación completa en tu PC ni en AWS.

## Alcance y limitaciones
- No se ha probado contra la base de datos real de AWS ni con datos completos de producción.
- No se asegura que **todos** los flujos antiguos de cada módulo hayan quedado cubiertos por pruebas. Revisar especialmente permisos interdelegación, páginas secundarias, auditoría y operaciones masivas.
- La figura de responsable se implementó como **un responsable principal por delegación**; si necesitan varios, se requiere otro diseño.
- Un período cerrado con historial no se elimina, incluso teniendo permiso especial: se conserva la integridad de la información.
- Se conservaron nombres de modelos internos y algunas referencias históricas a “Funcionario” en pantallas secundarias; el **mantenedor principal** sí se llama “Empleados”.
- El paquete **no incluye** `.env`, `.git`, `.venv`, `db.sqlite3`, respaldos ni archivos de usuarios.

**NO subas esto directamente a `main`**: tu workflow de GitHub Actions despliega a AWS y ejecuta `migrate --noinput`. Primero instala y prueba localmente, revisa los cambios en una rama y haz una copia de seguridad de la base de datos de producción antes de desplegar.
