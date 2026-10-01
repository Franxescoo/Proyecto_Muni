# Sistema de Gestión de Resultados (SGR)

El Sistema de Gestión de Resultados (SGR) tiene como objetivo centralizar el registro, seguimiento y validación de información asociada a funcionarios, metas, actividades, evidencias, compromisos e indicadores, manteniendo trazabilidad y control de acceso según el contexto del usuario.

---

## Tecnologías utilizadas

- Python 3.13
- Django 6.1
- SQLite para desarrollo local
- python-dotenv
- Git y GitHub

---

## Arquitectura del proyecto

El sistema está dividido en aplicaciones Django según su responsabilidad.

### `organization`

Gestiona la estructura organizacional.

Modelos principales:

- `Delegation`
- `PositionFunction`
- `Employee`

### `planning_measurements`

Gestiona la planificación y las metas.

Modelos principales:

- `Period`
- `Goal`

### `registration_validation`

Gestiona actividades, evidencias y validaciones.

Modelos principales:

- `Activity`
- `Evidence`
- `Validation`

Flujo principal:

```text
Activity → Evidence → Validation
```

### `monitoring_traceability`

Gestiona seguimiento y trazabilidad.

Modelos principales:

- `Indicator`
- `Commitment`
- `Audit`

### `accounts`

Gestiona información complementaria de los usuarios y su asociación a una delegación.

### `core`

Contiene elementos comunes del proyecto, como `BaseModel`, que incorpora:

- `created_at`
- `updated_at`
- `deleted_at`

---

## Instalación

Clonar el repositorio:

```bash
git clone https://github.com/Franxescoo/Proyecto_Muni.git
cd Proyecto_Muni
```

Crear el entorno virtual:

```bash
python -m venv .venv
```

Activarlo desde Git Bash:

```bash
source .venv/Scripts/activate
```

Instalar las dependencias:

```bash
pip install -r requirements.txt
```

---

## Variables de entorno

Crear un archivo `.env` utilizando como referencia `.env.example`.

Ejemplo para SQLite:

```env
SECRET_KEY=clave_local
DB_ENGINE=sqlite
DB_NAME=db.sqlite3
```

El archivo `.env` contiene la configuración local del proyecto y se encuentra excluido mediante `.gitignore`.

---

## Migraciones

Comprobar el proyecto:

```bash
python manage.py check
```

Aplicar las migraciones:

```bash
python manage.py migrate
```

---

## Carga de datos de prueba

El proyecto dispone de un comando para generar datos de demostración:

```bash
python manage.py seed
```

Este comando permite cargar información relacionada con:

- Delegaciones
- Funcionarios
- Cargos
- Períodos
- Metas
- Actividades
- Evidencias
- Indicadores
- Compromisos
- Auditoría
- Usuario limitado de prueba

El comando utiliza `get_or_create` para evitar la creación innecesaria de registros duplicados al ejecutarse nuevamente.

---

## Usuarios de prueba

El sistema contempla usuarios con distintos niveles de acceso para demostrar el funcionamiento de permisos y restricciones.

### Superadministrador

El superadministrador posee acceso completo a Django Admin y puede consultar y administrar los registros del sistema.

Debe crearse localmente mediante:

```bash
python manage.py createsuperuser
```

Django solicitará los datos necesarios para crear la cuenta administrativa.

### Evaluador

El comando:

```bash
python manage.py seed
```

crea automáticamente un usuario limitado de prueba.

La contraseña del usuario es procesada mediante el sistema de autenticación de Django, por lo que se almacena de forma hasheada en la base de datos y no en texto plano.

Este usuario pertenece al grupo:

```text
Limited User
```

y se encuentra asociado a una delegación determinada.

Esto permite comprobar las restricciones de acceso del sistema, ya que el usuario limitado visualiza únicamente los registros correspondientes a su contexto y permisos.

---

## Ejecución

Iniciar el servidor:

```bash
python manage.py runserver
```

Luego ingresar en el navegador a:

```text
http://127.0.0.1:8000/admin/
```

---

## Pruebas

Para ejecutar las pruebas automatizadas del proyecto:

```bash
python manage.py test
```

Para verificar la configuración general:

```bash
python manage.py check
```

Para comprobar que no existan migraciones pendientes:

```bash
python manage.py makemigrations --check --dry-run
```

---

## Seguridad

El sistema restringe la información según la delegación asociada al usuario.

El superadministrador puede visualizar todos los registros, mientras que un usuario limitado solo puede acceder a información correspondiente a su contexto y permisos.

Las restricciones se aplican tanto a los registros visibles como a las opciones disponibles en relaciones entre modelos.

Las contraseñas de los usuarios son gestionadas mediante el sistema de autenticación de Django y se almacenan de forma hasheada en la base de datos.

También se utiliza borrado lógico mediante el campo:

```text
deleted_at
```

Esto permite conservar los registros históricos en lugar de eliminarlos físicamente de forma inmediata.

Los campos:

```text
created_at
updated_at
deleted_at
```

permiten mantener trazabilidad sobre la creación, modificación y eliminación lógica de los registros.

---

## Trabajo colaborativo

El desarrollo del proyecto se realiza mediante ramas de Git, permitiendo que cada integrante trabaje sobre funcionalidades específicas.

Los cambios se registran mediante commits descriptivos y posteriormente se integran mediante Pull Requests revisados por otro integrante del equipo.

Flujo utilizado:

```text
Rama → Commit → Push → Pull Request → Revisión → Merge
```

Este flujo permite mantener trazabilidad sobre los cambios realizados y diferenciar el aporte de cada integrante del equipo.
