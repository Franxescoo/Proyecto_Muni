# Eventos y Campañas · Diseño funcional integrado (V2)

**Proyecto_Muni · 30 de octubre de 2026**

## Qué se implementó

Se adaptaron las pantallas reales de Django al diseño del simulador aprobado. El contenido usa **consultas reales** y las mismas operaciones del módulo `municipal_events` instalado previamente. No se usan datos ficticios, JavaScript para simular cambios ni formularios que no guarden.

- Panel `/eventos-campanas/` con indicadores reales: eventos, campañas, inscripciones pendientes y entregas registradas. Los indicadores de beneficiarios y entregas respetan permisos y delegación activa.
- Barra lateral del módulo: Resumen, Eventos, Campañas, Inscripciones, Entregas e Historial. Cada enlace aparece según los permisos del usuario.
- Eventos: edición anual y acciones existentes de alta y modificación.
- Campañas: listado con búsqueda/paginación, ficha y opciones de gestión.
- Inscripciones: listado real con búsqueda, estado y paginación, botón de evaluación y opción de entrega cuando corresponde. La inscripción nueva **continúa iniciándose desde Ingreso de Atención**, con la coincidencia del Tipo de atención y campaña abierta.
- Entregas: lista de inscripciones aprobadas, estado de entrega, funcionario y fecha. Botón para registrar entrega real cuando está pendiente.
- Historial: listado de eventos `CampaignAudit` de inscripciones, decisiones y entregas. **No incluye un registro de creación/edición de eventos municipales**, porque el modelo anterior no almacena esa auditoría.
- Estilos institucionales, responsive y aislados en `static/css/municipal_events.css`, para no cambiar otras pantallas.

## Archivos cambiados

- `municipal_events/views.py`: cuatro vistas nuevas (panel, inscripción, entrega, historial), más indicadores, filtros de permisos y contexto de navegación. Se mantienen intactas las reglas de negocio existentes.
- `municipal_events/urls.py`: cuatro rutas nuevas.
- `municipal_events/tests.py`: tres pruebas nuevas para navegación, aislamiento territorial y permisos.
- `core/modules.py`: la tarjeta «Campañas e inscripciones» del inicio pasa a abrir el panel «Panel Eventos y Campañas». La tarjeta de «Eventos municipales» se mantiene.
- `static/css/municipal_events.css`: estilos del módulo.
- `templates/municipal_events/`: se rediseñaron las siete plantillas previas y se agregaron cuatro nuevas (`dashboard.html`, `enrollments.html`, `deliveries.html`, `history.html`).

**No se modificaron** `registration_validation`, los modelos de ningún módulo, migraciones, `config/settings.py`, `config/urls.py`, `.env`, `.git`, bases de datos, ni otras aplicaciones.

## Instalación en tu proyecto actual

1. Conserva un respaldo de tu carpeta y, si procede, respalda tu base de datos.
2. **Detén `runserver`** antes de copiar.
3. Extrae `Proyecto_Muni_Eventos_Campanas_Diseno_Funcional_Solo_Cambios.zip` en la carpeta *que contiene* tu directorio `Proyecto_Muni`. Autoriza reemplazar los archivos existentes incluidos en el ZIP. No borres la carpeta ni reemplaces todos los archivos del proyecto.
4. Activa tu entorno Python habitual y ejecuta:

   ```bash
   python manage.py check
   python manage.py test municipal_events
   python manage.py runserver
   ```

5. Entra a **Inicio → Panel Eventos y Campañas** o directamente a `/eventos-campanas/`. Recarga con `Ctrl+F5` si conserva el CSS antiguo.
6. Para ver **Inscripciones** y **Historial**, el rol necesita `municipal_events.view_enrollment`; para **Entregas**, además necesita `municipal_events.view_giftdelivery`. Las operaciones de evaluar y entregar siguen dependiendo de `change_enrollment` y `add_giftdelivery`. Asígnalos desde el mantenedor Roles y Permisos usando un administrador normal distinto del usuario cuyo rol se edita.

**No hace falta `migrate`** para este paquete: no crea ni modifica tablas. Para desplegar los CSS en AWS bajo `DEBUG=False`, debe realizarse el procedimiento de estáticos ya establecido, incluido `collectstatic` si lo utiliza tu despliegue.

## Resultados de la validación de esta entrega

- `compileall` de la app: correcto.
- Compilación de 11 plantillas con el motor Django: correcta.
- `python manage.py check` con ajustes temporales para pruebas (excluyendo Daphne y WebSocket del proceso de prueba en Linux): correcto.
- `python manage.py test municipal_events` con esos ajustes: **12/12 OK**.
- `python manage.py test accounts organization citizen_requests municipal_events` con esos ajustes: **176/176 OK**.

Los ajustes temporales de entorno **no se incluyen en el ZIP**. Las pruebas no sustituyen abrir el módulo en tu Windows con tus datos reales y permisos. No se ha ejecutado un despliegue AWS ni probado allí el CSS.

## Consideraciones

- El prototipo tenía controles con identificadores de demostración. El módulo real requiere RUT validado, una atención existente y una campaña abierta.
- El total de campañas y eventos es información de gestión municipal; las filas, los indicadores de beneficiarios, entregas e historial se limitan al ámbito territorial autorizado para esos permisos.
- Los usuarios con solo lectura de eventos/campañas no verán botones ni datos de beneficiarios para los cuales no tengan permisos.
- Si durante la instalación cambiaste manualmente `municipal_events/views.py`, `municipal_events/urls.py`, `municipal_events/tests.py` o `core/modules.py`, compara esos archivos antes de reemplazarlos. Esta versión se construyó sobre el **ZIP completo que te entregué previamente**, no sobre cambios posteriores que hayas podido hacer en local.
