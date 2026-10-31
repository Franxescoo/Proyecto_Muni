# Corrección de permisos, Cargos y etiquetas en español

## Cambios

- **Etiquetas**: en Roles y Permisos ahora se muestran nombres de aplicaciones, modelos y operaciones **en español**. Esto es solamente presentación; los `codename`, las tablas, las URLs y los permisos almacenados **NO cambiaron**. Se traduce también el formulario antiguo de grupos si se utiliza.
- **Cargos y Funciones**: los cargos son un catálogo global que puede contener cargos sin empleados asignados. Anteriormente, si el usuario tenía permiso de consulta pero no tenía empleados de su delegación asignados a esos cargos, el listado aparecía vacío. Ahora un Usuario con `organization.view_positionfunction` y ámbito de delegación autorizado puede consultar el catálogo. No se le conceden automáticamente permisos para crear, modificar ni eliminar.
- **Roles y Permisos**: la administración ya no exige `is_superuser`; se controla por `organization.view_organizationrole`, `add_organizationrole`, `change_organizationrole` y `delete_organizationrole`. No se permite delegar permisos ni delegaciones fuera de los que administra la cuenta.
- **Usuarios**: la pantalla de Organización comprueba ahora permisos `accounts.view_userprofile`, `add_userprofile`, `change_userprofile`, `delete_userprofile`, con filtro territorial y protección de URL y formularios.
- **Cargos globales**: la creación, edición y eliminación pueden realizarse con permisos específicos, sin `is_superuser`. Como son compartidos, esos permisos deben asignarse solamente a un rol administrativo autorizado.
- **Cambio de responsable de delegación**: no es otro mantenedor. Es la **bitácora de auditoría** del responsable de una Delegación. Al modificar el campo Responsable del formulario de Delegaciones se registra el responsable anterior, el nuevo, la cuenta que realizó el cambio y la fecha. No se alteró el historial existente.

## Cómo activar al administrador sin superusuario

El cambio de código **no concede permisos a ninguna cuenta automáticamente**. Para gestionar Roles necesitas una cuenta normal que ya tenga los permisos mencionados. Si todavía no existe, se incluye este comando opcional de **provisión inicial**, para ser ejecutado exclusivamente por quien administra la instalación:

```powershell
python manage.py habilitar_administrador_normal --usuario NOMBRE_DE_LA_CUENTA --confirmar
```

El comando **no crea superusuarios**, no cambia `is_superuser` y toma las delegaciones autorizadas que ya posee esa cuenta. Crea un rol «Administración institucional» con permisos administrativos del sistema, salvo el privilegio individual `delete_closed_period`. **No ejecutes** el comando para la cuenta «Consulta Prueba»; debe aplicarse solo a la cuenta destinada a administrar el sistema. Antes de hacerlo, respalda la base de datos. El comando es manual, no se ejecuta por migraciones ni por despliegues.

Luego, cierra la sesión, vuelve a entrar con la cuenta administradora normal y verifica los accesos. El usuario de solo lectura debe conservar exclusivamente sus permisos de lectura.

## Instalación segura

Copia el código actualizado manteniendo intactos `db.sqlite3`, `.env`, `.venv`, `.git` y `media/` de tu proyecto anterior. Las correcciones no requieren migraciones nuevas. Puedes ejecutar:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test organization.test_roles_cargos_espanol
python manage.py runserver --insecure
```

`--insecure` solamente si estás haciendo pruebas **locales** con `DEBUG=False`; no debe usarse en AWS. No se han modificado la configuración de AWS, GitHub Actions ni la recuperación de contraseñas.
