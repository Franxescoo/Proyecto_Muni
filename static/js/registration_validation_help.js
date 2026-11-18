(() => {
  'use strict';

  function boot() {
    const toolbar = document.querySelector('[data-sgr-autohelp]');
    if (!toolbar || toolbar.dataset.sgrTourBound === '1') return;
    toolbar.dataset.sgrTourBound = '1';

    const page = toolbar.dataset.sgrAutohelp;
    const startButton = toolbar.querySelector('[data-sgr-tour-start]');
    const guideButton = toolbar.querySelector('[data-sgr-guide-toggle]');
    const guideLabel = toolbar.querySelector('[data-sgr-guide-label]');
    const guideRail = document.querySelector('[data-sgr-guide-rail]');
    const guideOffcanvas = document.querySelector('[data-sgr-guide-offcanvas]');
    const pageShell = document.querySelector('.registration-shell')
      || document.querySelector('.cr-hero')?.parentElement;
    const pageHeading = pageShell?.querySelector('.registration-hero, .cr-hero');

    if (!startButton || !guideButton || !guideLabel || !guideRail || !guideOffcanvas || !pageShell || !pageHeading) return;

    pageHeading.insertAdjacentElement('afterend', toolbar);
    const layout = document.createElement('div');
    layout.className = 'sgr-guide-layout registration-help-layout';
    const main = document.createElement('div');
    main.className = 'sgr-guide-main registration-help-main';
    const contentNodes = [];
    for (let node = toolbar.nextSibling; node; node = node.nextSibling) {
      contentNodes.push(node);
    }
    contentNodes.forEach((node) => main.appendChild(node));
    layout.append(main, guideRail);
    toolbar.insertAdjacentElement('afterend', layout);
    guideOffcanvas.classList.add('registration-help-offcanvas');
    document.body.appendChild(guideOffcanvas);
    toolbar.classList.add('is-positioned');

    const desktopGuide = window.matchMedia('(min-width: 1500px)');
    const guideStorageKey = 'sgr-ayuda-visible-registration_validation';
    let guideCollapsed = false;
    try {
      guideCollapsed = window.localStorage.getItem(guideStorageKey) === '0';
    } catch (_) {
      guideCollapsed = false;
    }

    function syncGuideButton(mobileOpen) {
      const desktop = desktopGuide.matches;
      const open = typeof mobileOpen === 'boolean'
        ? mobileOpen
        : Boolean(guideOffcanvas.classList.contains('show'));
      layout.classList.toggle('sgr-guide-collapsed', desktop && guideCollapsed);
      const pressed = desktop ? guideCollapsed : open;
      guideButton.setAttribute('aria-pressed', pressed ? 'true' : 'false');
      guideButton.setAttribute('aria-expanded', desktop
        ? (guideCollapsed ? 'false' : 'true')
        : (open ? 'true' : 'false'));
      guideLabel.textContent = desktop
        ? (guideCollapsed ? 'Mostrar guía lateral' : 'Ocultar guía lateral')
        : (open ? 'Ocultar guía lateral' : 'Mostrar guía lateral');
    }

    syncGuideButton(false);
    guideButton.addEventListener('click', () => {
      if (desktopGuide.matches) {
        guideCollapsed = !guideCollapsed;
        try {
          window.localStorage.setItem(guideStorageKey, guideCollapsed ? '0' : '1');
        } catch (_) {}
        syncGuideButton();
      } else if (window.bootstrap && window.bootstrap.Offcanvas) {
        window.bootstrap.Offcanvas.getOrCreateInstance(guideOffcanvas).toggle();
      }
    });
    guideOffcanvas.addEventListener('show.bs.offcanvas', () => {
      document.body.classList.add('registration-help-open');
      syncGuideButton(true);
    });
    guideOffcanvas.addEventListener('hidden.bs.offcanvas', () => {
      document.body.classList.remove('registration-help-open');
      syncGuideButton(false);
    });
    window.addEventListener('resize', () => {
      if (desktopGuide.matches && guideOffcanvas.classList.contains('show')
          && window.bootstrap && window.bootstrap.Offcanvas) {
        window.bootstrap.Offcanvas.getOrCreateInstance(guideOffcanvas).hide();
      }
      syncGuideButton();
    });

    function normalized(text) {
      return (text || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
    }

    function fieldHelp(label, control) {
      if (!control) return null;
      const id = control.id || '';
      const name = (control.name || '').replace(/\[\]$/, '').split('.').pop();
      const labelText = normalized(label.textContent);
      const isFilter = !label.closest('.modal');
      const helpById = {
        citizenSearch: 'Busca ciudadanos por RUT, nombre o correo; la consulta respeta el estado seleccionado.',
        citizenState: 'Limita la lista a ciudadanos activos, inactivos o a todos.',
        searchAttentionEntry: 'Busca ingresos y combina el texto con los filtros de tipo, delegación y estado.',
        filterAttentionType: 'Acota los ingresos al tipo de atención seleccionado.',
        filterAttentionStatus: 'Filtra los ingresos por su estado actual.',
        'activity-search': 'Busca actividades por sus datos y criterios disponibles.',
        'activity-status': 'Filtra las actividades por estado.',
        'evidence-search': 'Busca evidencias por código, actividad, meta o funcionario.',
        'evidence-status': 'Filtra evidencias por estado de revisión.',
        'validation-search': 'Busca validaciones por evidencia, verificador, decisión o resultado.',
        'attention-type-search': 'Busca tipos de atención por los criterios disponibles.',
        'searchSubAttention': 'Busca subatenciones por nombre o tipo asociado.',
        'service-search': 'Busca servicios por los criterios disponibles.'
      };
      if (helpById[id]) return helpById[id];
      if (page === 'citizen_registry:list') {
        if (name === 'rut') return 'El RUT identifica de forma única el registro del ciudadano.';
        if (name === 'phone' || name === 'email') return 'Dato de contacto asociado a la ficha del ciudadano.';
        if (name === 'address') return 'Domicilio registrado para la ficha del ciudadano.';
        return null;
      }
      if (name === 'q' && isFilter) {
        if (page === 'registration:activity_type_list') return 'Busca tipos de actividad por los criterios disponibles.';
        return null;
      }
      if (name === 'attention_type' || labelText.includes('tipo de atencion')) {
        return 'Selecciona la clasificación que corresponda a la atención.';
      }
      if (name === 'sub_attention' || labelText.includes('subatencion')) {
        return 'Elige una subatención compatible con el tipo seleccionado, si corresponde.';
      }
      if (name === 'activity_type' || labelText.includes('tipo de actividad')) {
        return 'Clasifica la actividad con uno de los tipos disponibles.';
      }
      if (name === 'goal' || labelText.includes('meta')) {
        return 'Asocia la actividad a la meta institucional que corresponda.';
      }
      if (name === 'attention') {
        return 'Selecciona la atención relacionada con esta actividad.';
      }
      if (name === 'code' && page === 'registration:evidence_create') {
        return 'El código de evidencia se genera automáticamente al guardar el registro.';
      }
      if (name === 'code' && page === 'registration:evidence_update') {
        return 'El código identifica esta evidencia y no se modifica desde el formulario.';
      }
      if ((name === 'new_files' || labelText.includes('archivos de evidencia'))
          && page.startsWith('registration:evidence_')) {
        return 'Adjunta de 2 a 5 archivos; el tamaño total no debe superar 50 MB.';
      }
      if (name === 'file_link' && page.startsWith('registration:evidence_')) {
        return 'Puedes añadir un enlace como antecedente adicional; también debes mantener entre 2 y 5 archivos.';
      }
      if (name === 'decision' || labelText.includes('decision')) {
        return 'Escribe la decisión de la revisión en este campo.';
      }
      if (name === 'result' || labelText.includes('resultado')) {
        return 'Resume el resultado comunicado por la revisión de la evidencia.';
      }
      if (name === 'verifier' || labelText.includes('verificador')) {
        return 'Identifica a la persona responsable de realizar esta revisión.';
      }
      if ((name === 'requester' || name === 'requester_email' || name === 'requester_phone' || name === 'address')
          && page.startsWith('registration:attention_entry_')) {
        return 'Este dato se carga desde la ficha del ciudadano y se consulta aquí como solo lectura.';
      }
      if (name === 'contact' || name === 'phone') {
        return 'Dato de contacto asociado a la atención; completa solo la información disponible.';
      }
      if (name === 'address' || name === 'subject' || name === 'request_problem') {
        return 'Describe la información necesaria para identificar y dar seguimiento a la atención.';
      }
      if (name === 'responsible_employee') {
        if (control.disabled) return 'El funcionario se asigna automáticamente según el perfil de tu cuenta.';
        return 'Selecciona el funcionario responsable dentro de las opciones autorizadas.';
      }
      if (name === 'status') {
        return isFilter
          ? 'Filtra los registros por estado.'
          : 'El estado refleja la situación actual del registro según las opciones disponibles.';
      }
      if (name === 'date') {
        return 'Indica la fecha relacionada con el registro.';
      }
      if (name === 'action') {
        return 'Describe la acción realizada o planificada para la actividad.';
      }
      if (name === 'observation' || name === 'closing_observation') {
        return 'Registra una observación que aporte contexto al cambio o resultado.';
      }
      if (labelText.includes('buscar') && isFilter && page === 'registration:service_list') {
        return 'Busca servicios por los criterios disponibles en esta pantalla.';
      }
      return null;
    }

    function enhanceFields() {
      const selectors = [
        '.registration-help-main label',
        '.sgr-upgraded-modal .modal-body label',
        '#citizenModal .modal-body label'
      ].join(', ');
      for (const label of document.querySelectorAll(selectors)) {
        if (label.dataset.sgrHelpChecked === '1') continue;
        const fieldId = label.getAttribute('for');
        const control = (fieldId && document.getElementById(fieldId))
          || label.parentElement?.querySelector('input, select, textarea');
        const help = fieldHelp(label, control);
        label.dataset.sgrHelpChecked = '1';
        if (!help) continue;
        const hint = document.createElement('button');
        hint.type = 'button';
        hint.className = 'sgr-help-hint';
        hint.textContent = '?';
        hint.setAttribute('aria-label', `Ayuda: ${help}`);
        hint.title = help;
        hint.addEventListener('click', (event) => event.stopPropagation());
        label.insertAdjacentElement('afterend', hint);
        if (window.bootstrap && window.bootstrap.Tooltip) {
          window.bootstrap.Tooltip.getOrCreateInstance(hint, {
            title: help,
            container: 'body',
            placement: 'top',
            trigger: 'hover focus'
          });
        }
      }
    }

    enhanceFields();

    function restoreToolbar() {
      if (!toolbar.parentElement?.closest('.modal')) return;
      pageHeading.insertAdjacentElement('afterend', toolbar);
      toolbar.insertAdjacentElement('afterend', layout);
    }

    document.querySelectorAll('.sgr-upgraded-modal, #citizenModal').forEach((modal) => {
      modal.addEventListener('show.bs.modal', () => {
        const modalBody = modal.querySelector('.modal-body');
        if (modalBody && toolbar.parentElement !== modalBody) {
          modalBody.insertAdjacentElement('afterbegin', toolbar);
        }
      });
      modal.addEventListener('shown.bs.modal', () => {
        if (tour && tour.parentElement !== modal) modal.appendChild(tour);
        if (tour && page === 'citizen_registry:list' && modal.id === 'citizenModal') {
          const save = modal.querySelector('#citizenSave');
          const selector = save && !save.classList.contains('d-none')
            ? '@citizen-form'
            : '@citizen-view';
          const stepIndex = tourSteps.findIndex((step) => step.selector === selector);
          if (stepIndex >= 0) {
            position = stepIndex;
            updateTour();
          }
        }
      });
      modal.addEventListener('hidden.bs.modal', () => {
        if (tour && tour.parentElement === modal) document.body.appendChild(tour);
        restoreToolbar();
        if (tour) updateTour();
      });
    });

    const stepsByPage = {};

    const catalogTour = (modal, label, fields) => [
      [`${modal} .modal-header`, `Administrar ${label}`, `En este formulario puedes consultar o mantener la información de ${label}.`],
      ...fields.map(([selector, title, description]) => [
        `${modal} ${selector}`, title, description
      ]),
      [`${modal} .modal-footer [type="submit"]`, 'Guardar los cambios', 'Revisa los datos solicitados y utiliza el botón de guardar para confirmar el formulario.']
    ];

    Object.assign(stepsByPage, {
      'citizen_registry:list': [
        ['.cr-hero', 'Gestión de ciudadanos', 'En esta sección puedes consultar las fichas de los ciudadanos registrados. Cada persona se identifica mediante su RUT, lo que permite mantener sus datos organizados.'],
        ['#globalSidebarRegistration', 'Navegar por el módulo', 'Utiliza el menú lateral para acceder a las distintas secciones de Registro y Validación, como atenciones, actividades, evidencias y validaciones.'],
        ['#citizenSearch', 'Buscar ciudadanos', 'Escribe un RUT, nombre o correo para encontrar una ficha.'],
        ['#citizenState', 'Filtrar por estado', 'Utiliza Estado para consultar ciudadanos activos, inactivos o todos los registros.'],
        ['#newCitizen', 'Agregar un ciudadano', 'Selecciona Agregar ciudadano para ingresar una nueva ficha. Completa los datos solicitados y revisa que la información sea correcta antes de guardarla.'],
        ['@citizen-form', 'Completar la ficha', 'Completa o revisa los campos habilitados. El RUT identifica de forma única la ficha y no se puede modificar al editarla. Si corresponde, indica la pertenencia a una organización vecinal.'],
        ['@citizen-view', 'Consultar una ficha', 'Revisa los datos de esta ficha. Para modificarla o administrar su estado, cierra el detalle y utiliza las acciones que tu cuenta tenga habilitadas.'],
        ['.cr-table', 'Consultar y administrar fichas', 'En la lista puedes consultar los ciudadanos registrados. Utiliza las acciones disponibles para ver sus datos o administrarlos según los permisos de tu cuenta.']
      ],
      'registration:attention_entry_list': [
        ['.registration-hero', 'Gestión de atenciones', 'En esta sección puedes registrar y consultar las atenciones realizadas a los ciudadanos, manteniendo organizada la información de cada ingreso.'],
        ['#globalSidebarRegistration', 'Navegar por las secciones', 'Desde el menú lateral puedes acceder a Ciudadanos, Actividades, Evidencias, Validaciones y los catálogos disponibles para tu usuario.'],
        ['#searchAttentionEntry', 'Buscar una atención', 'Utiliza la barra de búsqueda para encontrar una atención por sus datos.'],
        ['#filterAttentionType', 'Filtrar los resultados', 'Combina tipo de atención, delegación y estado para obtener resultados más específicos.'],
        ['a[href*="/registration/attention-entries/new/"]', 'Registrar una atención', 'Selecciona Agregar ingreso para abrir el formulario. Identifica al ciudadano, completa los antecedentes de la atención y revisa los campos solicitados antes de guardar.'],
        ['.sgr-catalog table', 'Consultar una atención', 'En la lista de registros, utiliza Ver para consultar sus antecedentes, el responsable y la información de seguimiento disponible.'],
        ['button[data-bs-target="#solicitudesModal"]', 'Abrir solicitudes ciudadanas', 'Selecciona Solicitudes en la barra superior para acceder a la bandeja donde se consultan las solicitudes recibidas por el municipio.', true],
        ['#solicitudesModal', 'Conocer la bandeja', 'Aquí encontrarás las solicitudes pendientes de derivación y las asignadas a la delegación correspondiente. La información disponible depende de tus permisos.', true],
        ['#solicitudes-search', 'Buscar una solicitud', 'Ingresa un código de seguimiento o un asunto para localizar una solicitud.', true],
        ['#solicitudes-status', 'Filtrar solicitudes', 'Utiliza Estado para precisar la búsqueda en la bandeja.', true],
        ['@requests-loaded', 'Revisar las solicitudes', 'Consulta los registros disponibles en la bandeja. Si no hay solicitudes, el sistema lo indicará y se omitirán los pasos que requieren un detalle.', true],
        ['@request-row', 'Abrir una solicitud', 'Selecciona Ver o Ver solicitud para acceder a sus antecedentes y conocer su situación actual.', true],
        ['@request-history', 'Consultar el historial', 'En el detalle puedes revisar los movimientos administrativos y, cuando corresponda, las gestiones operativas registradas en orden cronológico.', true],
        ['@request-actions', 'Consultar o registrar gestiones', 'Si tu usuario está autorizado para esta solicitud, utiliza el enlace disponible para consultar o registrar las gestiones realizadas.', true],
        ['@request-attachments', 'Revisar los respaldos', 'Cuando una gestión tenga archivos adjuntos disponibles para tu cuenta, podrás abrirlos desde sus enlaces en el historial.', true],
        ['#solicitudesModal', 'Finalizar el recorrido', 'Terminaste la orientación. La bandeja queda disponible para continuar la consulta o cerrar la ventana y seguir navegando.', true]
      ],
      'registration:activity_list': [
        ['.registration-hero', 'Gestión de actividades', 'Aquí puedes consultar las actividades relacionadas con las metas institucionales y revisar sus antecedentes, responsables y estados.'],
        ['#globalSidebarRegistration', 'Navegar por el módulo', 'Utiliza el menú lateral para acceder a otras secciones, como Ingreso de atención, Evidencias y Validaciones.'],
        ['#activity-search', 'Buscar actividades', 'Escribe un problema, acción, funcionario o meta en la búsqueda.'],
        ['#activity-status', 'Filtrar actividades', 'Utiliza el filtro de estado para encontrar las actividades que necesitas revisar.'],
        ['a[href*="/registration/activities/new/"]', 'Registrar una actividad', 'Selecciona Agregar actividad para ingresar una nueva acción. Completa su descripción, clasificación y meta asociada, respetando las opciones disponibles para tu usuario.'],
        ['.sgr-catalog table', 'Consultar actividades', 'En la tabla puedes revisar las actividades registradas y utilizar las acciones disponibles para acceder a sus detalles.']
      ],
      'registration:evidence_list': [
        ['.registration-hero', 'Gestión de evidencias', 'Las evidencias permiten respaldar las actividades registradas mediante archivos y otros antecedentes. En esta sección puedes consultar los respaldos y sus estados de revisión.'],
        ['#globalSidebarRegistration', 'Navegar por el módulo', 'Desde el menú lateral puedes consultar Actividades para identificar el trabajo realizado y Validaciones para revisar los resultados de su evaluación.'],
        ['#evidence-search', 'Buscar evidencias', 'Busca por código, actividad, meta o funcionario.'],
        ['#evidence-status', 'Filtrar evidencias', 'Utiliza el estado de revisión para acotar los respaldos que necesitas consultar.'],
        ['a[href*="/registration/evidences/new/"]', 'Registrar una evidencia', 'Selecciona Agregar evidencia para registrar un respaldo de una actividad. Completa los datos solicitados, adjunta entre 2 y 5 archivos permitidos y revisa que su tamaño total no supere 50 MB. El código se generará automáticamente al guardar.'],
        ['.sgr-catalog table', 'Consultar respaldos', 'En la lista puedes revisar las evidencias registradas y abrir los archivos o enlaces disponibles para tu cuenta. Consulta su estado para conocer si cuentan con una revisión.'],
        ['#globalSidebarRegistration', 'Consultar la validación', 'Para conocer la decisión o el resultado de la revisión de una evidencia, dirígete a Validaciones.']
      ],
      'registration:validation_list': [
        ['.registration-hero', 'Revisión de evidencias', 'Esta sección permite registrar y consultar las revisiones realizadas sobre las evidencias, junto con sus decisiones y resultados.'],
        ['#globalSidebarRegistration', 'Navegar por el módulo', 'Utiliza el menú lateral para consultar Evidencias y revisar los respaldos relacionados con cada validación.'],
        ['#validation-search', 'Buscar validaciones', 'Busca una validación por evidencia, verificador, decisión o resultado para encontrar el registro que necesitas.'],
        ['a[href*="/registration/validations/new/"]', 'Registrar una validación', 'Selecciona Agregar validación para registrar una revisión. Completa la evidencia correspondiente, la decisión y el resultado, junto con los demás antecedentes solicitados.'],
        ['.sgr-catalog table', 'Consultar los resultados', 'En la lista puedes revisar las validaciones registradas, sus verificadores, decisiones, resultados y versiones.']
      ],
      'registration:activity_type_list': [
        ['.registration-hero', 'Tipos de actividad', 'Este catálogo reúne las clasificaciones utilizadas para organizar las actividades registradas en el sistema.'],
        ['#globalSidebarRegistration', 'Navegar por el módulo', 'El menú lateral reúne las secciones disponibles de Registro y Validación para tu cuenta.'],
        ['input[type="search"]', 'Buscar un tipo', 'Utiliza la búsqueda para encontrar una clasificación y revisar su información.'],
        ['select[name="status"]', 'Filtrar por estado', 'Limita la lista a los tipos de actividad según su estado.'],
        ['.sgr-catalog table', 'Administrar el catálogo', 'Consulta los tipos de actividad disponibles y utiliza las acciones habilitadas para tu cuenta.']
      ],
      'registration:attention_type_list': [
        ['.registration-hero', 'Tipos de atención', 'En esta sección se administran las clasificaciones que permiten organizar los ingresos de atención.'],
        ['#globalSidebarRegistration', 'Navegar por el módulo', 'Desde el menú lateral puedes acceder a los registros de atención y a los catálogos relacionados.'],
        ['#attention-type-search', 'Buscar un tipo de atención', 'Utiliza el buscador para localizar la clasificación que necesitas consultar.'],
        ['select[name="status"]', 'Filtrar por estado', 'Limita el catálogo a los tipos de atención según su estado.'],
        ['.sgr-catalog table', 'Consultar el catálogo', 'Revisa los tipos de atención registrados y utiliza las acciones disponibles para tu cuenta.']
      ],
      'registration:sub_attention_list': [
        ['.registration-hero', 'Gestión de subatenciones', 'Las subatenciones permiten especificar con mayor detalle los tipos de atención registrados en el sistema.'],
        ['#globalSidebarRegistration', 'Navegar por el módulo', 'El menú lateral permite consultar Ciudadanos, atenciones, actividades, evidencias y validaciones.'],
        ['#searchSubAttention', 'Buscar subatenciones', 'Utiliza el buscador para encontrar una subatención.'],
        ['#sub-attention-type', 'Consultar el tipo asociado', 'Filtra por tipo de atención para conocer la clasificación a la que pertenece cada subatención.'],
        ['.sgr-catalog table', 'Consultar y administrar', 'Revisa las subatenciones disponibles y utiliza las opciones autorizadas para consultar o mantener sus datos.']
      ],
      'registration:service_list': [
        ['.registration-hero', 'Catálogo de servicios', 'Aquí puedes consultar los servicios disponibles para organizar la información del registro municipal.'],
        ['#globalSidebarRegistration', 'Navegar por el módulo', 'Utiliza el menú lateral para acceder a las secciones disponibles en tu cuenta.'],
        ['#service-search', 'Buscar servicios', 'Utiliza el campo de búsqueda para localizar un servicio según los criterios disponibles en esta pantalla.'],
        ['select[name="status"]', 'Filtrar por estado', 'Limita la lista a los servicios según su estado.'],
        ['.sgr-catalog table', 'Consultar el catálogo', 'Revisa la información de los servicios registrados y utiliza las acciones que estén habilitadas para tu usuario.']
      ]
    });

    Object.assign(stepsByPage, {
      'registration:attention_entry_create': [
        ['#attentionEntryModal .modal-header', 'Registrar una atención', 'Este formulario reúne los antecedentes necesarios para registrar o actualizar un ingreso de atención.'],
        ['#attentionEntryModal #id_citizen_rut', 'Identificar al ciudadano', 'Ingresa el RUT para consultar la ficha existente. Los datos personales se cargan desde Ciudadanos y se mantienen como solo lectura.'],
        ['#attentionEntryModal [name="attention_type"]', 'Clasificar la atención', 'Selecciona el tipo de atención y, si corresponde, una subatención.'],
        ['#attentionEntryModal [name="description"]', 'Describir la atención', 'Registra la descripción y revisa los datos de delegación y responsable que muestra el formulario.'],
        ['#attentionEntryEditForm [type="submit"]', 'Guardar el ingreso', 'Revisa los campos obligatorios y utiliza el botón de guardar para registrar la atención.']
      ],
      'registration:attention_entry_update': [
        ['#attentionEntryModal .modal-header', 'Actualizar una atención', 'En este formulario puedes revisar los antecedentes y el seguimiento de una atención registrada.'],
        ['#attentionEntryModal #id_citizen_rut', 'Consultar al ciudadano', 'Los datos personales se cargan desde Ciudadanos y se mantienen como solo lectura.'],
        ['#attentionEntryModal [name="attention_type"]', 'Revisar la clasificación', 'Comprueba el tipo de atención y, si corresponde, la subatención asociada.'],
        ['#attentionEntryModal [name="description"]', 'Revisar los antecedentes', 'Consulta la descripción y los datos de delegación y responsable del formulario.'],
        ['#attentionEntryModal [name="status"]', 'Revisar el estado', 'Comprueba el estado de la atención y completa la observación cuando el formulario la solicite.'],
        ['#attentionEntryEditForm [type="submit"]', 'Guardar los cambios', 'Revisa los datos y utiliza el botón de guardar para actualizar la atención.']
      ],
      'registration:activity_create': [
        ['#activityModal .modal-header', 'Registrar una actividad', 'La actividad documenta una acción asociada a una meta institucional y a una atención existente.'],
        ['#activityModal [name="goal"]', 'Asociar una meta', 'Selecciona la meta institucional a la que corresponde la actividad.'],
        ['#activityModal [name="attention"]', 'Vincular una atención', 'Selecciona la atención existente relacionada. La atención y el funcionario autor deben corresponder a la misma delegación.'],
        ['#activityModal [name="activity_type"]', 'Clasificar la actividad', 'Para una actividad nueva, selecciona uno de los tipos activos disponibles.'],
        ['#activityModal [name="request_problem"]', 'Describir el problema', 'Resume la solicitud o el problema que da contexto a la actividad.'],
        ['#activityModal [name="action"]', 'Registrar la acción', 'Describe la acción realizada y revisa el funcionario, la fecha y el estado.'],
        ['#activityModal .modal-footer [type="submit"]', 'Guardar la actividad', 'Revisa los datos solicitados y utiliza el botón de guardar para registrar la actividad.']
      ],
      'registration:activity_update': [
        ['#activityModal .modal-header', 'Actualizar una actividad', 'Revisa los antecedentes y el seguimiento de la actividad seleccionada.'],
        ['#activityModal [name="goal"]', 'Revisar la meta', 'Comprueba la meta institucional asociada a esta actividad.'],
        ['#activityModal [name="attention"]', 'Revisar la atención', 'Consulta la atención relacionada y verifica que corresponda a la delegación del funcionario autor.'],
        ['#activityModal [name="activity_type"]', 'Revisar la clasificación', 'Comprueba el tipo de actividad asociado. Los registros históricos conservan su clasificación aunque el tipo deje de estar activo.'],
        ['#activityModal [name="request_problem"]', 'Revisar el problema', 'Consulta la solicitud o el problema que da contexto a la actividad.'],
        ['#activityModal [name="action"]', 'Revisar la acción y el estado', 'Comprueba la acción realizada, el funcionario, la fecha y el estado antes de guardar.'],
        ['#activityModal .modal-footer [type="submit"]', 'Guardar los cambios', 'Revisa los datos solicitados y utiliza el botón de guardar para actualizar la actividad.']
      ],
      'registration:evidence_create': [
        ['#evidenceModal .modal-header', 'Registrar una evidencia', 'La evidencia respalda una actividad con archivos y antecedentes de revisión.'],
        ['#evidenceModal [name="code"]', 'Código automático', 'El código de evidencia se genera automáticamente al guardar; no necesitas completarlo.'],
        ['#evidenceModal [name="activity"]', 'Vincular una actividad', 'Selecciona la actividad a la que pertenecen los respaldos. Solo se ofrecen actividades disponibles para tu cuenta.'],
        ['#evidenceModal [name="author"]', 'Identificar al funcionario', 'Selecciona al funcionario responsable de la evidencia dentro de las opciones autorizadas.'],
        ['#evidenceModal [name="new_files"]', 'Adjuntar archivos', 'Adjunta entre 2 y 5 archivos permitidos. El peso total no debe superar 50 MB; el enlace, si lo agregas, es un antecedente adicional.'],
        ['#evidenceModal [name="file_link"]', 'Agregar un enlace', 'Si existe un enlace de respaldo, puedes incluirlo además de los archivos requeridos.'],
        ['#evidenceModal .modal-footer [type="submit"]', 'Guardar la evidencia', 'Al guardar, el sistema genera el código de evidencia automáticamente.']
      ],
      'registration:evidence_update': [
        ['#evidenceModal .modal-header', 'Actualizar una evidencia', 'Revisa los respaldos y antecedentes de la evidencia seleccionada.'],
        ['#evidenceModal [name="code"]', 'Consultar el código', 'El código identifica esta evidencia y no se modifica desde el formulario.'],
        ['#evidenceModal [name="activity"]', 'Revisar la actividad', 'Comprueba la actividad relacionada con esta evidencia.'],
        ['#evidenceModal [name="new_files"]', 'Agregar archivos', 'Puedes incorporar archivos permitidos, manteniendo entre 2 y 5 en total y un tamaño máximo de 50 MB.'],
        ['#evidenceModal [name="remove_file_ids"]', 'Revisar archivos existentes', 'Marca para quitar únicamente los archivos que deban retirarse. Después de guardar deben permanecer entre 2 y 5 archivos.'],
        ['#evidenceModal [name="file_link"]', 'Revisar el enlace', 'Consulta o actualiza el enlace adicional asociado a la evidencia, si corresponde.'],
        ['#evidenceModal .modal-footer [type="submit"]', 'Guardar los cambios', 'Revisa los respaldos y utiliza el botón de guardar para actualizar la evidencia.']
      ],
      'registration:validation_create': [
        ['#validationModal .modal-header', 'Registrar una validación', 'La validación deja constancia de la revisión realizada sobre una evidencia.'],
        ['#validationModal [name="evidence"]', 'Seleccionar la evidencia', 'Elige la evidencia que se revisó entre las opciones disponibles para tu cuenta.'],
        ['#validationModal [name="verifier"]', 'Identificar al verificador', 'Selecciona al funcionario responsable de realizar la revisión.'],
        ['#validationModal [name="decision"]', 'Registrar la decisión', 'Escribe la decisión de la revisión en este campo de texto.'],
        ['#validationModal [name="date"]', 'Indicar la fecha', 'Registra la fecha y hora relacionadas con esta revisión.'],
        ['#validationModal [name="result"]', 'Registrar el resultado', 'Resume el resultado de la revisión.'],
        ['#validationModal [name="version"]', 'Revisar la versión', 'Indica la versión de la validación. La observación es opcional.'],
        ['#validationModal [name="observation"]', 'Agregar una observación', 'Si aporta contexto a la revisión, puedes escribir una observación.'],
        ['#validationModal [type="submit"]', 'Guardar la validación', 'Revisa los antecedentes y utiliza el botón de guardar para registrar la revisión.']
      ],
      'registration:validation_update': [
        ['#validationModal .modal-header', 'Actualizar una validación', 'Revisa los datos y antecedentes de la validación seleccionada.'],
        ['#validationModal [name="evidence"]', 'Revisar la evidencia', 'Comprueba la evidencia relacionada con esta revisión.'],
        ['#validationModal [name="verifier"]', 'Revisar al verificador', 'Consulta quién es responsable de la revisión.'],
        ['#validationModal [name="decision"]', 'Revisar la decisión', 'Comprueba la decisión registrada; este campo acepta texto.'],
        ['#validationModal [name="date"]', 'Revisar la fecha', 'Comprueba la fecha y hora relacionadas con esta revisión.'],
        ['#validationModal [name="result"]', 'Revisar el resultado', 'Consulta el resultado y la observación, si se registró.'],
        ['#validationModal [name="version"]', 'Revisar la versión', 'Comprueba la versión y la fecha de la validación.'],
        ['#validationModal [type="submit"]', 'Guardar los cambios', 'Revisa los antecedentes y utiliza el botón de guardar para actualizar la validación.']
      ]
    });

    [
      {
        key: 'activity_type',
        label: 'tipos de actividad',
        modal: '#activityTypeModal',
        fields: [
          ['[name="code"]', 'Código', 'Ingresa el código que identifica esta clasificación.'],
          ['[name="name"]', 'Nombre', 'Escribe un nombre claro para el tipo de actividad.'],
          ['[name="description"]', 'Descripción', 'Agrega una descripción cuando el formulario la incluya.'],
          ['[name="status"]', 'Estado', 'Revisa si el tipo queda disponible para nuevas actividades.']
        ]
      },
      {
        key: 'attention_type',
        label: 'tipos de atención',
        modal: '#attentionTypeModal',
        fields: [
          ['[name="code"]', 'Código', 'Ingresa el código que identifica este tipo de atención.'],
          ['[name="name"]', 'Nombre', 'Escribe el nombre de la clasificación.'],
          ['[name="status"]', 'Estado', 'Revisa si el tipo queda disponible para nuevas atenciones.']
        ]
      },
      {
        key: 'sub_attention',
        label: 'subatenciones',
        modal: '#subAttentionModal',
        fields: [
          ['[name="code"]', 'Código', 'Ingresa el código que identifica esta subatención.'],
          ['[name="name"]', 'Nombre', 'Escribe el nombre de la subatención.'],
          ['[name="attention_type"]', 'Tipo de atención', 'Relaciona la subatención con el tipo que corresponda.'],
          ['[name="status"]', 'Estado', 'Revisa si la subatención queda disponible para nuevos ingresos.']
        ]
      },
      {
        key: 'service',
        label: 'servicios',
        modal: '#serviceModal',
        fields: [
          ['[name="code"]', 'Código', 'Ingresa el código que identifica el servicio.'],
          ['[name="name"]', 'Nombre', 'Escribe el nombre del servicio.'],
          ['[name="description"]', 'Descripción', 'Agrega una descripción cuando el formulario la incluya.'],
          ['[name="status"]', 'Estado', 'Revisa si el servicio queda disponible para su consulta.']
        ]
      }
    ].forEach(({key, label, modal, fields}) => {
      for (const action of ['create', 'update']) {
        stepsByPage[`registration:${key}_${action}`] = catalogTour(modal, label, fields);
      }
    });

    const pageSteps = stepsByPage[page] || [
      ['.registration-shell, .cr-panel', 'Registro y Validación', 'Esta pantalla forma parte del módulo Registro y Validación.'],
      ['#globalSidebarRegistration', 'Navegación del módulo', 'El menú lateral reúne las secciones disponibles para tu cuenta.'],
      ['main', 'Fin del recorrido', 'Puedes volver a iniciar la orientación desde el botón visible.']
    ];
    const requestModal = document.getElementById('solicitudesModal');
    const requestLauncher = document.querySelector('button[data-bs-target="#solicitudesModal"]');
    const includeRequestFlow = page === 'registration:attention_entry_list'
      && requestModal && requestLauncher && window.bootstrap && window.bootstrap.Modal;
    let requestDetailReady = Boolean(document.querySelector('#solicitud-detail .card'));
    let requestDetailFailed = false;
    let requestDetailBaseline = document.getElementById('solicitud-detail')?.innerHTML || '';

    function visible(target) {
      return target && target.getClientRects().length ? target : null;
    }

    function requestInboxFailed() {
      const feedback = document.getElementById('solicitudes-feedback');
      return feedback?.classList.contains('alert-danger')
        && normalized(feedback.textContent).includes('no se pudo cargar la bandeja');
    }

    function requestInboxTarget() {
      if (!requestModal?.classList.contains('show')) return null;
      return ['solicitudes-pending', 'solicitudes-delegated']
        .map((id) => document.getElementById(id))
        .find((section) => section?.innerHTML.trim()) || null;
    }

    function requestDetailTarget(selector) {
      if (!requestDetailReady) return null;
      const detail = document.getElementById('solicitud-detail');
      if (!detail) return null;
      if (selector === '@request-history') {
        return Array.from(detail.querySelectorAll('h6'))
          .find((heading) => normalized(heading.textContent).includes('historial de movimientos'));
      }
      if (selector === '@request-actions') {
        return Array.from(detail.querySelectorAll('a'))
          .find((link) => /consultar gestiones operativas|registrar gestion/.test(normalized(link.textContent)));
      }
      if (selector === '@request-attachments') {
        return detail.querySelector('.list-group-item ul a');
      }
      return null;
    }

    function locate(selector) {
      if (selector === '@citizen-form') {
        const modal = document.getElementById('citizenModal');
        const save = document.getElementById('citizenSave');
        return modal?.classList.contains('show') && save && !save.classList.contains('d-none')
          ? visible(modal.querySelector('.modal-body'))
          : null;
      }
      if (selector === '@citizen-view') {
        const modal = document.getElementById('citizenModal');
        const save = document.getElementById('citizenSave');
        return modal?.classList.contains('show') && save?.classList.contains('d-none')
          ? visible(modal.querySelector('.modal-body'))
          : null;
      }
      if (selector === '@requests-loaded') return visible(requestInboxTarget());
      if (selector === '@request-row') {
        if (!requestModal?.classList.contains('show')) return null;
        return visible(requestModal.querySelector('[data-detail-id]'));
      }
      if (selector.startsWith('@request-')) {
        return visible(requestDetailTarget(selector));
      }
      return visible(document.querySelector(selector));
    }

    const tourSteps = pageSteps
      .filter((step) => step[3] ? Boolean(includeRequestFlow) : true)
      .map(([selector, title, description, requestFlow]) => ({
        selector, title, description, requestFlow: Boolean(requestFlow)
      }));
    let position = 0;
    let tour = null;
    let highlighted = null;
    let openedRequestModal = false;

    function clearHighlight() {
      if (highlighted) highlighted.classList.remove('sgr-selfhelp-highlight');
      highlighted = null;
    }

    function endTour() {
      clearHighlight();
      if (tour) tour.remove();
      tour = null;
      const closeRequestModal = openedRequestModal
        && requestModal?.classList.contains('show')
        && window.bootstrap;
      openedRequestModal = false;
      if (closeRequestModal) {
        requestModal.addEventListener('hidden.bs.modal', () => {
          startButton.focus({preventScroll: true});
        }, {once: true});
        window.bootstrap.Modal.getOrCreateInstance(requestModal).hide();
        return;
      }
      startButton.focus({preventScroll: true});
    }

    function updateTour() {
      if (!tour) return;
      clearHighlight();

      while (position < tourSteps.length) {
        const step = tourSteps[position];
        let target = locate(step.selector);
        if (step.selector === '@requests-loaded' && !target && requestModal?.classList.contains('show')) {
          if (requestInboxFailed()) {
            position += 1;
            continue;
          }
          tour.querySelector('[data-step-count]').textContent = `Paso ${position + 1} de ${tourSteps.length}`;
          tour.querySelector('[data-step-title]').textContent = step.title;
          tour.querySelector('[data-step-description]').textContent =
            'La bandeja se está cargando. Este paso estará disponible cuando se muestren los resultados.';
          tour.querySelector('[data-step-prev]').disabled = position === 0;
          tour.querySelector('[data-step-next]').disabled = true;
          return;
        }
        if (!target && step.requestFlow && step.selector === '#solicitudesModal'
            && requestModal && window.bootstrap) {
          openedRequestModal = !requestModal.classList.contains('show');
          if (openedRequestModal) {
            window.bootstrap.Modal.getOrCreateInstance(requestModal).show();
            return;
          }
          target = requestModal;
        }
        if (target) {
          highlighted = target;
          highlighted.classList.add('sgr-selfhelp-highlight');
          highlighted.scrollIntoView({
            behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
            block: 'center'
          });
          tour.querySelector('[data-step-count]').textContent = `Paso ${position + 1} de ${tourSteps.length}`;
          const waitingForRequestDetail = step.selector === '@request-row'
            && !requestDetailReady && !requestDetailFailed;
          tour.querySelector('[data-step-title]').textContent = step.title;
          tour.querySelector('[data-step-description]').textContent = waitingForRequestDetail
            ? 'Selecciona Ver o Ver solicitud en una fila. El siguiente paso se habilitará cuando el detalle termine de cargar.'
            : step.description;
          tour.querySelector('[data-step-prev]').disabled = position === 0;
          tour.querySelector('[data-step-next]').disabled = waitingForRequestDetail;
          tour.querySelector('[data-step-next]').textContent =
            position === tourSteps.length - 1 ? 'Terminar' : 'Siguiente';
          return;
        }
        position += 1;
      }

      endTour();
    }

    function startTour() {
      if (tour) {
        endTour();
        return;
      }
      if (!tourSteps.length) return;
      position = 0;
      if (page === 'citizen_registry:list' && toolbar.closest('#citizenModal.show')) {
        const save = document.getElementById('citizenSave');
        const selector = save && !save.classList.contains('d-none')
          ? '@citizen-form'
          : '@citizen-view';
        const stepIndex = tourSteps.findIndex((step) => step.selector === selector);
        if (stepIndex >= 0) position = stepIndex;
      }
      openedRequestModal = false;
      requestDetailFailed = false;
      tour = document.createElement('section');
      tour.className = 'sgr-selfhelp-tour registration-validation-tour';
      tour.id = 'registrationValidationTour';
      tour.setAttribute('role', 'dialog');
      tour.setAttribute('aria-modal', 'false');
      tour.setAttribute('aria-labelledby', 'registrationValidationTourTitle');
      tour.setAttribute('aria-describedby', 'registrationValidationTourDescription');
      tour.innerHTML =
        '<div class="sgr-selfhelp-tour-counter" data-step-count></div>' +
        '<div class="sgr-selfhelp-tour-heading"><strong id="registrationValidationTourTitle" data-step-title></strong>' +
        '<button type="button" class="sgr-selfhelp-tour-close" aria-label="Cerrar tutorial" data-step-close>&times;</button></div>' +
        '<p id="registrationValidationTourDescription" aria-live="polite" data-step-description></p>' +
        '<div class="sgr-selfhelp-tour-actions"><button type="button" class="btn btn-outline-secondary btn-sm" data-step-prev>Anterior</button>' +
        '<button type="button" class="btn btn-danger btn-sm" data-step-next>Siguiente</button></div>';
      const activeModal = toolbar.closest('.modal.show');
      (activeModal || document.body).appendChild(tour);
      tour.querySelector('[data-step-close]').addEventListener('click', endTour);
      tour.querySelector('[data-step-prev]').addEventListener('click', () => {
        if (position > 0) {
          position -= 1;
          updateTour();
        }
      });
      tour.querySelector('[data-step-next]').addEventListener('click', () => {
        const step = tourSteps[position];
        if (step?.selector === '@request-row' && !requestDetailReady) {
          if (!requestDetailFailed) return;
          position += 1;
          updateTour();
          return;
        }
        if (position + 1 < tourSteps.length) {
          position += 1;
          updateTour();
        } else {
          endTour();
        }
      });
      updateTour();
      tour.querySelector('[data-step-next]').focus({preventScroll: true});
    }

    startButton.addEventListener('click', startTour);
    if (requestModal) {
      requestModal.addEventListener('shown.bs.modal', () => {
        if (tour && openedRequestModal && tour.parentElement !== requestModal) {
          requestModal.appendChild(tour);
          updateTour();
        }
      });
      requestModal.addEventListener('hidden.bs.modal', () => {
        if (tour && openedRequestModal) endTour();
      });
      requestModal.addEventListener('click', (event) => {
        if (!event.target.closest('[data-detail-id]')) return;
        const detail = document.getElementById('solicitud-detail');
        requestDetailBaseline = detail?.innerHTML || '';
        requestDetailReady = false;
        requestDetailFailed = false;
      });
      const requestObserver = new MutationObserver((mutations) => {
        const requestContentChanged = mutations.some((mutation) => {
          const node = mutation.target.nodeType === Node.ELEMENT_NODE
            ? mutation.target
            : mutation.target.parentElement;
          return node?.closest(
            '#solicitudes-pending, #solicitudes-delegated, #solicitud-detail, #solicitudes-feedback'
          );
        });
        if (!requestContentChanged) return;

        const detail = document.getElementById('solicitud-detail');
        const feedback = document.getElementById('solicitudes-feedback');
        const hasDetail = Boolean(detail?.querySelector('.card'));
        if (!hasDetail && !detail?.innerHTML.trim()) {
          requestDetailReady = false;
        } else if (hasDetail && detail.innerHTML !== requestDetailBaseline) {
          requestDetailReady = true;
        }
        requestDetailFailed = Boolean(
          feedback?.classList.contains('alert-danger')
          && normalized(feedback.textContent).includes('no se pudo cargar el detalle')
        );
        if (tour) updateTour();
      });
      requestObserver.observe(requestModal, {childList: true, subtree: true});
    }
    document.addEventListener('keydown', (event) => {
      if (tour && event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        endTour();
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, {once: true});
  } else {
    boot();
  }
})();
