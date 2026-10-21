# Cambios de diseño: formularios municipales

**Base:** Proyecto_Muni_ver_formularios_metas.zip (última copia recibida).

## Implementado
- Modales de Organización, Planificación, Registro y Validación con cabecera rojo institucional, título, descripción, secciones, mejor tipografía, contornos y espaciado.
- Acciones coherentes: Ver = solamente **Cerrar**; Crear/Modificar mantienen sus métodos y botones de guardado ya existentes.
- Formularios de Metas: sección «Medición y resultados», respetando orden, campos y los botones «Guardar», «Guardar y añadir otro» y «Guardar y continuar editando».
- Modales de Períodos, Ítems, Actividades, Evidencias, Tipos de Atención, Tipos de Actividad, Servicios, Validación, Subatenciones e Ingreso de Atención con el mismo estilo.
- Ficha de consulta compartida «Ver» adaptada al mismo diseño; solo Cerrar.
- Hoja de estilos CSS aislada bajo `.sgr-upgraded-modal`; versión de CSS actualizada para evitar caché.

## Cambios que NO se realizaron
- Sin modificaciones en models.py, forms.py, views.py, urls.py ni migraciones.
- Sin modificaciones en validaciones, lógica de guardado ni permisos.
- Las páginas de consulta sin ventana modal no se convirtieron a modales para no alterar navegación.

## Advertencia
- Las modificaciones visuales no otorgan ni restringen permisos; la auditoría de visibilidad por empleado/delegación sigue pendiente.
- Revisar los modales con datos reales y todos los botones específicos en un navegador antes de desplegar a producción.
