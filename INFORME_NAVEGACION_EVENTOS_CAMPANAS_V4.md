# Eventos y Campañas — V4: navegación integrada al SGR

## Cambios implementados

1. **Sin Resumen:** se retiró la sección del menú lateral y del inicio del SGR. La antigua URL base del módulo (`municipal_events:dashboard`) ahora **redirige al inicio general del SGR** para que los enlaces históricos no queden rotos; la plantilla antigua del panel queda sin uso.
2. **Un único Inicio:** el enlace «Inicio» del menú lateral de Eventos y Campañas lleva a la ruta `home` del SGR. Se eliminó «Inicio del SGR» porque duplicaba la misma acción.
3. **Cinco tarjetas independientes en el inicio general del SGR** dentro de «Eventos y Campañas»: Eventos, Campañas, Inscripciones, Entregas, Historial. Cada una abre directamente su sección existente, no el panel anterior.
4. **Visibilidad según permisos:** Eventos requiere `municipal_events.view_municipalevent`; Campañas requiere `municipal_events.view_campaign`; Inscripciones e Historial requieren `municipal_events.view_enrollment`; Entregas requiere **ambos** `municipal_events.view_enrollment` y `municipal_events.view_giftdelivery` (consistente con la vista). La interfaz oculta accesos para los que no hay permiso; el servidor sigue protegiendo las vistas.
5. **Pruebas actualizadas** para enlaces del inicio, permisos dobles y redirección del antiguo Resumen.

## Archivos incluidos / modificados

- `core/modules.py`: reemplaza 2 tarjetas por 5 tarjetas y agrega permiso adicional a Entregas.
- `core/views.py`: permite comprobar permisos adicionales de cada tarjeta sin alterar el comportamiento de las tarjetas anteriores.
- `templates/municipal_events/base.html`: modifica y simplifica el menú lateral; elimina la referencia visual al Resumen.
- `municipal_events/views.py`: conserva la URL antigua del Resumen pero redirige a `home`.
- `municipal_events/tests.py`: adapta las pruebas y agrega controles de navegación y permisos.

**Sin cambios** en `registration_validation`, `citizen_requests`, modelos, migraciones, bases de datos, usuarios, roles, correos, evaluaciones, entregas, formularios CRUD ni ventanas modales.

## Instalación

1. Respalda tu proyecto antes de copiar archivos.
2. Extrae el ZIP **en la carpeta que contiene `Proyecto_Muni`** (no dentro de una segunda carpeta `Proyecto_Muni/Proyecto_Muni`). Reemplaza solo los cinco archivos indicados.
3. En Git Bash, dentro de la carpeta de tu proyecto:

```bash
python manage.py check
python manage.py test municipal_events
python manage.py runserver
```

4. Recarga el navegador con Ctrl+F5 y entra al **Inicio** general. En «Eventos y Campañas» verás las cinco tarjetas **si el usuario tiene los permisos correspondientes**. Si alguna no aparece, revisa Roles y Permisos desde otra cuenta administrativa autorizada.
5. Dentro del módulo, «Inicio» regresará al inicio general. Los CRUD siguen abriéndose en modales.

No hace falta `makemigrations` ni `migrate` porque no se modificaron los modelos.

## Validaciones de esta entrega

- `python -m compileall`: sin errores de sintaxis en los archivos Python modificados.
- `python manage.py check` con configuración temporal de verificación: correcto.
- `municipal_events`: **19/19 pruebas aprobadas**.
- `municipal_events`, `accounts.test`, `organization`, `citizen_requests`: **183/183 pruebas aprobadas** con configuración temporal de verificación basada en las bibliotecas de la instalación suministrada. No equivale a una prueba de navegador ni a un despliegue AWS.

