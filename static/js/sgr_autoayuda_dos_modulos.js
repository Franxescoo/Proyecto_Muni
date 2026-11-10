/* Autoayuda de dos módulos: no modifica datos ni envía formularios. */
(() => {
  'use strict';
  function boot() {
    const toolbar = document.querySelector('[data-sgr-autohelp]');
    if (!toolbar) return;
    const page = toolbar.getAttribute('data-sgr-autohelp');
    const moduleName = toolbar.getAttribute('data-sgr-help-module');
    if (!['planning', 'events'].includes(moduleName)) return;
    const layout = toolbar.nextElementSibling;
    if (!layout || !layout.classList.contains('sgr-guide-layout')) return;
    const toggle = toolbar.querySelector('[data-sgr-guide-toggle]');
    const toggleLabel = toolbar.querySelector('[data-sgr-guide-label]');
    const storeKey = 'sgr-ayuda-visible-' + moduleName;
    let collapsed = false;
    try { collapsed = window.localStorage.getItem(storeKey) === '0'; } catch (_) {}
    function applyGuide() {
      layout.classList.toggle('sgr-guide-collapsed', collapsed);
      toggle.setAttribute('aria-pressed', collapsed ? 'true' : 'false');
      toggleLabel.textContent = collapsed ? 'Mostrar guía lateral' : 'Ocultar guía lateral';
    }
    applyGuide();
    toggle.addEventListener('click', () => {
      collapsed = !collapsed;
      applyGuide();
      try { window.localStorage.setItem(storeKey, collapsed ? '0' : '1'); } catch (_) {}
    });

    // Pasos de orientación. Los objetivos inexistentes (por falta de permiso,
    // filtros o registros) se omiten: jamás se desbloquean acciones protegidas.
    const stepsByPage = {
      'planning:periods': [
        ['.monitor-hero', 'Períodos de medición', 'Aquí defines el intervalo de medición. Los días computables consideran días hábiles y feriados chilenos.'],
        ['.sgr-guide-main .section-card.metric', 'Resumen del período', 'Estas tarjetas muestran cuántos períodos existen, están activos o cerrados.'],
        ['#period-search', 'Buscar y filtrar', 'Utiliza la búsqueda y el filtro de estado para ubicar un período.'],
        ['texto:Agregar período', 'Crear un período', 'Si tienes permiso, abre Agregar período e informa las fechas y los parámetros. Puedes usar los signos ? junto a los campos del formulario.'],
        ['.sgr-guide-main table', 'Revisar y cerrar', 'En la tabla puedes consultar cada período. Antes de cerrarlo, deben completarse las metas y ponderadores de sus funcionarios.']
      ],
      'planning:goals': [
        ['.monitor-hero', 'Metas de los funcionarios', 'Cada meta relaciona período, funcionario, cargo e ítem medible.'],
        ['#goal-period', 'Filtrar por período', 'Selecciona un período para revisar solo sus metas y ponderadores.'],
        ['texto:Agregar meta', 'Registrar una meta', 'Para crearla necesitas un período activo y un ítem asociado al cargo del funcionario. Los signos ? explican cada campo.'],
        ['.sgr-guide-main table', 'Consultar resultados', 'La lista permite comprobar valores objetivo, ponderadores y metas asociadas al período.']
      ],
      'planning:items': [
        ['.monitor-hero', 'Catálogo de ítems', 'Los ítems describen qué se mide. Registrar un ítem no crea una meta automáticamente.'],
        ['texto:Nuevo ítem', 'Crear un ítem', 'Si tu rol lo permite, define código, nombre, tipo de medición y unidad de medida.'],
        ['#item-search', 'Localizar un ítem', 'Busca por nombre o código y revisa el estado antes de asociarlo a un cargo.'],
        ['.sgr-guide-main table', 'Consultar y mantener', 'Aquí puedes consultar los ítems disponibles. Para usarlos en metas deben estar activos y asociados al cargo.']
      ],
      'events:events': [
        ['.mec-hero', 'Eventos municipales', 'Un evento representa una actividad que puede repetirse en años distintos.'],
        ['texto:Agregar evento', 'Registrar un evento', 'Con permiso de creación, agrega el evento general antes de registrar ediciones anuales.'],
        ['.mec-panel form[role="search"]', 'Buscar eventos', 'Filtra por nombre o descripción para localizar los eventos registrados.'],
        ['texto:Nueva edición', 'Crear una edición anual', 'Desde un evento existente puedes crear una edición con año, fecha, lugar y responsable.'],
        ['.mec-panel table', 'Consultar ediciones', 'Revisa el evento y despliega Ver ediciones cuando quieras consultar sus distintas realizaciones.']
      ],
      'events:campaigns': [
        ['.mec-hero', 'Campañas municipales', 'Las campañas tienen fechas de inscripción y un tipo de atención asociado.'],
        ['texto:Agregar campaña', 'Crear una campaña', 'Antes de crearla, debe existir un tipo de atención activo. Los signos ? ayudan a completar sus datos.'],
        ['#mec-campaign-search', 'Buscar una campaña', 'Puedes filtrar por campaña o por tipo de atención.'],
        ['.mec-table-wrap', 'Comprobar las inscripciones', 'Para recibir inscripciones, la campaña debe estar abierta y dentro de las fechas permitidas.']
      ],
      'events:enrollments': [
        ['.mec-hero', 'Inscripciones', 'Este listado consulta las inscripciones, pero no crea directamente nuevos beneficiarios.'],
        ['#mec-enroll-status', 'Buscar por estado', 'Filtra las inscripciones pendientes, aprobadas o rechazadas.'],
        ['texto:Evaluar', 'Evaluar una inscripción', 'Cuando tengas permiso, puedes aprobar o rechazar, registrando el motivo correspondiente.'],
        ['.mec-table-wrap', 'Origen de la inscripción', 'La inscripción se inicia desde una atención vinculada a una campaña abierta usando Inscribir en campaña.']
      ],
      'events:deliveries': [
        ['.mec-hero', 'Registro de entregas', 'Una aprobación no equivale a una entrega. La entrega se registra por separado.'],
        ['#mec-deliver-state', 'Filtrar pendientes', 'Consulta los beneficiarios con entrega pendiente o ya realizada.'],
        ['texto:Registrar entrega', 'Confirmar una entrega', 'Solo se puede registrar cuando existe una inscripción aprobada y todavía no tiene entrega.'],
        ['.mec-table-wrap', 'Consultar constancias', 'Usa Ver constancia para revisar una entrega ya registrada.']
      ],
      'events:history': [
        ['.mec-hero', 'Historial de campañas', 'El historial se genera con las inscripciones, evaluaciones y entregas. No se captura manualmente.'],
        ['#mec-history-q', 'Buscar movimientos', 'Filtra por campaña o beneficiario para encontrar cambios registrados.'],
        ['.mec-timeline', 'Revisar trazabilidad', 'Consulta fecha, responsable y motivo de cada movimiento permitido para tu rol.']
      ]
    };
    const textSelector = (needle) => {
      // Busca controles visibles; los que dependen de permisos no están en el HTML.
      const nodes = layout.querySelectorAll('.sgr-guide-main button, .sgr-guide-main a, .mec-panel button, .mec-panel a');
      for (const el of nodes) {
        if (el.textContent && el.textContent.trim().toLowerCase().includes(needle.toLowerCase()) && el.getClientRects().length) return el;
      }
      return null;
    };
    function locate(token) {
      if (token.startsWith('texto:')) return textSelector(token.substring(6));
      const el = document.querySelector(token);
      return el && el.getClientRects().length ? el : null;
    }
    const startButton = toolbar.querySelector('[data-sgr-tour-start]');
    let tour = null, tourSteps = [], position = 0, highlighted = null;
    function clearHighlight() {
      if (highlighted) highlighted.classList.remove('sgr-selfhelp-highlight');
      highlighted = null;
    }
    function endTour() {
      clearHighlight();
      if (tour) tour.remove();
      tour = null;
      startButton.focus({preventScroll:true});
    }
    function updateTour() {
      if (!tour || !tourSteps.length) return;
      clearHighlight();
      const step = tourSteps[position];
      highlighted = step.element;
      highlighted.classList.add('sgr-selfhelp-highlight');
      highlighted.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'center'});
      tour.querySelector('[data-step-count]').textContent = `Paso ${position + 1} de ${tourSteps.length}`;
      tour.querySelector('[data-step-title]').textContent = step.title;
      tour.querySelector('[data-step-description]').textContent = step.description;
      tour.querySelector('[data-step-prev]').disabled = position === 0;
      tour.querySelector('[data-step-next]').textContent = position === tourSteps.length - 1 ? 'Terminar' : 'Siguiente';
    }
    function startTour() {
      if (tour) { endTour(); return; }
      tourSteps = (stepsByPage[page] || []).map(([selector,title,description]) => ({element:locate(selector),title,description})).filter(x => x.element);
      if (!tourSteps.length) return;
      position = 0;
      tour = document.createElement('section');
      tour.className = 'sgr-selfhelp-tour';
      tour.setAttribute('role','dialog');
      tour.setAttribute('aria-label','Tutorial de uso del módulo');
      tour.innerHTML = '<div class="sgr-selfhelp-tour-counter" data-step-count></div>' +
        '<div class="sgr-selfhelp-tour-heading"><strong data-step-title></strong>' +
        '<button type="button" class="sgr-selfhelp-tour-close" aria-label="Cerrar tutorial" data-step-close>&times;</button></div>' +
        '<p data-step-description></p>' +
        '<div class="sgr-selfhelp-tour-actions"><button type="button" class="btn btn-outline-secondary btn-sm" data-step-prev>Anterior</button>' +
        '<button type="button" class="btn btn-danger btn-sm" data-step-next>Siguiente</button></div>';
      document.body.appendChild(tour);
      tour.querySelector('[data-step-close]').addEventListener('click', endTour);
      tour.querySelector('[data-step-prev]').addEventListener('click', () => { if (position > 0) {position--;updateTour();} });
      tour.querySelector('[data-step-next]').addEventListener('click', () => { if (position + 1 < tourSteps.length) {position++;updateTour();} else endTour(); });
      updateTour();
      tour.querySelector('[data-step-next]').focus({preventScroll:true});
    }
    startButton.addEventListener('click', startTour);
    document.addEventListener('keydown', e => { if (tour && e.key === 'Escape') endTour(); });

    // Información breve asociada a los campos de formularios existentes.
    const fieldHelp = {
      start_date: 'Inicio del período. Los días computables se calculan considerando días hábiles y feriados.',
      end_date: 'Término del período. Debe ser coherente con la fecha de inicio.',
      computable_days: 'Cantidad de días computables. El sistema la calcula automáticamente.',
      parameters_version: 'Versión de la configuración de parámetros utilizada para este período.',
      employee: 'Funcionario que tendrá asignada esta meta. Debe pertenecer a tu ámbito autorizado.',
      period: 'Período al que pertenece la meta. Las metas de períodos cerrados son de solo lectura.',
      position: 'Cargo del funcionario. Determina qué ítems medibles se pueden seleccionar.',
      measurement_item: 'Ítem de medición configurado para el cargo; debe estar disponible y activo.',
      objective_value: 'Cantidad o valor que se espera alcanzar al finalizar el período.',
      weight: 'Importancia relativa de la meta. Los ponderadores correspondientes deben sumar 100 %.',
      required_evidence_count: 'Cantidad de evidencias necesarias según la regla de medición.',
      code: 'Identificador del ítem. Procura usar un código único y reconocible.',
      formula: 'Fórmula que define cómo se calcula el cumplimiento de este tipo de medición.',
      unit: 'Unidad en la que se expresa el objetivo: número, porcentaje u otra unidad configurada.',
      is_active: 'Los ítems inactivos permanecen para consulta histórica, pero no deben asignarse a metas nuevas.',
      attention_type: 'Tipo de atención al que se vincula la campaña. Debe coincidir con el tipo de la atención para permitir inscribir.',
      opens_on: 'Primera fecha en que se permiten inscripciones, siempre que la campaña esté abierta.',
      closes_on: 'Última fecha habilitada para inscripciones.',
      organizing_delegation: 'Delegación responsable de organizar la campaña.',
      year: 'Año de la edición o campaña; permite distinguir cada realización anual.',
      place: 'Lugar en el que se realizará esta edición del evento.',
      reason: 'Motivo de la evaluación o del cambio. Quedará asociado al historial cuando corresponda.'
    };
    const norm = (s) => (s || '').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim();
    function helpFor(label, control) {
      if (!control) return null;
      const name = (control.name || '').replace(/^(.*-)?\d+-/,'').replace(/^.*\./,'');
      if (fieldHelp[name]) return fieldHelp[name];
      const labelText = norm(label.textContent);
      if (moduleName === 'planning') {
        if (labelText.includes('ponderador')) return fieldHelp.weight;
        if (labelText.includes('item') && labelText.includes('medic')) return fieldHelp.measurement_item;
        if (labelText.includes('estado') && !label.closest('.modal')) return 'Filtra los períodos por estado. Un período cerrado no permite modificar sus metas.';
      } else {
        if (labelText.includes('tipo de atencion')) return fieldHelp.attention_type;
        if (labelText.includes('apertura') || labelText.includes('inicio inscripcion')) return fieldHelp.opens_on;
        if (labelText.includes('cierre') || labelText.includes('fin inscripcion')) return fieldHelp.closes_on;
        if (labelText.includes('estado') && label.closest('.modal')) return 'El estado determina si la operación está abierta, en curso o finalizada, según sus reglas.';
      }
      return null;
    }
    function enhanceFields() {
      const selectors = moduleName === 'planning'
        ? '.sgr-upgraded-modal .modal-body label[for], .sgr-guide-main label[for]'
        : '#mecAjaxModal .modal-body label[for], .mec .sgr-guide-main label[for]';
      for (const label of document.querySelectorAll(selectors)) {
        if (label.dataset.sgrHelpChecked === '1') continue;
        label.dataset.sgrHelpChecked = '1';
        const fieldId = label.getAttribute('for');
        const control = fieldId ? document.getElementById(fieldId) : null;
        const help = helpFor(label, control);
        if (!help) continue;
        const b = document.createElement('button');
        b.type = 'button'; b.className = 'sgr-help-hint'; b.textContent = '?';
        b.setAttribute('aria-label', 'Ayuda: ' + help);
        b.title = help;
        b.addEventListener('click', evt => evt.stopPropagation());
        label.insertAdjacentElement('afterend', b);
        if (window.bootstrap && window.bootstrap.Tooltip) {
          window.bootstrap.Tooltip.getOrCreateInstance(b, {title:help, container:'body', placement:'top', trigger:'hover focus'});
        }
      }
    }
    enhanceFields();
    // Los formularios de Eventos/Campañas llegan por AJAX al modal existente.
    if (moduleName === 'events') {
      const content = document.getElementById('mecAjaxModalContent');
      if (content && window.MutationObserver) {
        const observer = new MutationObserver(enhanceFields);
        observer.observe(content,{childList:true,subtree:true});
      }
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once:true});
  else boot();
})();
