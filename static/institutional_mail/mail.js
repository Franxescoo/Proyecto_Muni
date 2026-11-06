/* Mensajería institucional SGR. Solo usa endpoints internos con sesión y CSRF. */
(() => {
  'use strict';
  const modal = document.getElementById('sgrInstitutionalMailModal');
  if (!modal) return;
  const $ = id => document.getElementById(id);
  const routes = {
    unread: '/correo/api/unread/',
    list: '/correo/api/messages/',
    recipients: '/correo/api/recipients/',
    send: '/correo/api/messages/send/'
  };
  const escape = str => String(str ?? '').replace(/[&<>"']/g, c =>
    ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
  let folder = 'inbox', selected = null, selectedData = null, page = 1, more = false;
  let composing = false, replyTo = null;
  let chosenRecipients = [], matches = [], activeMatch = -1, lookupSequence = 0;
  let recipientsLocked = false;
  const csrf = $('sgr-mail-csrf')?.value || '';

  async function call(url, options={}) {
    const result = await fetch(url, {
      credentials: 'same-origin',
      headers: {'X-Requested-With':'XMLHttpRequest', ...(options.method === 'POST' ? {'X-CSRFToken':csrf} : {}), ...options.headers},
      ...options
    });
    let data;
    try { data = await result.json(); }
    catch (_) { throw new Error('No se pudo interpretar la respuesta del servidor.'); }
    if (!result.ok || !data.ok) throw new Error(data.error || 'No se pudo completar la operación.');
    return data;
  }
  const payload = obj => new URLSearchParams(Object.entries(obj).filter(([,v]) => v !== undefined && v !== null));
  function feedback(msg, error=false) {
    const el = $('sgr-mail-feedback');
    el.textContent = msg;
    el.hidden = false;
    el.classList.toggle('error', error);
  }
  function clearFeedback() { $('sgr-mail-feedback').hidden = true; }

  async function unread() {
    try {
      const {unread: count} = await call(routes.unread);
      const badge = $('sgr-mail-badge');
      badge.textContent = count > 99 ? '99+' : count;
      badge.classList.toggle('d-none', count === 0);
      $('sgr-mail-inbox-count').textContent = count || '';
    } catch (_) {
      // La barra superior no debe interrumpirse si falla una petición.
    }
  }
  function empty(icon, label, hint) {
    return `<div class="sgr-mail-empty"><i class="bi ${icon}" aria-hidden="true"></i><h4>${escape(label)}</h4><p>${escape(hint)}</p></div>`;
  }
  function showNothing() {
    $('sgr-mail-detail').innerHTML = empty('bi-envelope-open','Selecciona un mensaje','Elige un mensaje para leerlo.');
    $('sgr-mail-detail-actions').hidden = true;
    $('sgr-mail-detail').hidden = false;
    $('sgr-mail-compose').hidden = true;
    selectedData = null;
  }
  function title(folder) { return ({inbox:'Recibidos', sent:'Enviados', archive:'Archivados'})[folder]; }
  async function loadList({autoselect=false}={}) {
    const list = $('sgr-mail-list');
    list.innerHTML = empty('bi-hourglass-split', 'Cargando...', 'Consultando los mensajes.');
    try {
      const url = routes.list + '?' + new URLSearchParams({folder, q:$('sgr-mail-search').value.trim(), page});
      const data = await call(url);
      $('sgr-mail-folder-title').textContent = title(folder);
      $('sgr-mail-total').textContent = `${data.total} ${data.total===1?'mensaje':'mensajes'}`;
      $('sgr-mail-page').textContent = `Página ${page}`;
      more = data.has_more;
      $('sgr-mail-next').disabled = !more;
      $('sgr-mail-prev').disabled = page <= 1;
      list.innerHTML = data.messages.map(m => `
        <button type="button" class="sgr-mail-row ${m.unread?'unread':''} ${selected===m.id&&!composing?'selected':''}" data-mail-id="${m.id}">
          <span class="row-title"><span>${m.unread?'<i class="sgr-mail-dot" aria-label="No leído"></i>':''}${escape(folder === 'sent' ? m.to : m.from)}</span><time>${escape(m.when)}</time></span>
          <span class="row-subject">${escape(m.subject)}</span>
          <span class="row-preview">${escape(m.snippet)}</span>
        </button>`).join('') || empty('bi-inbox','Sin mensajes','Esta carpeta no contiene mensajes.');
      if (autoselect && data.messages.length) await selectMessage(data.messages[0].id);
      else if (!data.messages.length && !composing) showNothing();
    } catch (err) { list.innerHTML = empty('bi-exclamation-triangle','No se pudo cargar',err.message); }
  }
  async function selectMessage(id) {
    clearFeedback();
    composing = false; replyTo = null; selected = id;
    $('sgr-mail-compose').hidden = true;
    $('sgr-mail-detail').hidden = false;
    $('sgr-mail-detail').innerHTML = empty('bi-hourglass-split','Cargando...','Leyendo el mensaje.');
    try {
      const {message:m} = await call(`${routes.list}${id}/`);
      selectedData = m;
      const own = m.mine;
      $('sgr-mail-detail').innerHTML = `
        <h3 class="sgr-mail-subject">${escape(m.subject)}</h3>
        <div class="sgr-mail-party">
          <div><div><strong>De:</strong> ${escape(m.from)}</div><small class="text-secondary">${escape(m.sender_email)}</small>
          <div class="mt-2"><strong>Para:</strong> ${escape(m.to)}</div><small class="text-secondary">${escape(m.recipient_email)}</small></div>
          <small class="text-secondary">${escape(m.when)}</small>
        </div>
        <div class="sgr-mail-letter">${escape(m.body)}</div>
        ${own && m.notifications?.includes('FAILED') ? '<p class="alert alert-warning small mt-3">Mensaje guardado. Algunas copias externas no se pudieron enviar.</p>' : ''}
        ${own && m.notifications?.every(s => s === 'SENT') ? '<p class="small text-success mt-3"><i class="bi bi-check-circle me-1"></i>Copias enviadas a los correos de los destinatarios.</p>' : ''}`;
      $('sgr-mail-detail-actions').hidden = false;
      $('sgr-mail-archive').innerHTML = m.archived ? '<i class="bi bi-arrow-counterclockwise me-1"></i>Restaurar' : '<i class="bi bi-archive me-1"></i>Archivar';
      document.querySelectorAll('.sgr-mail-row').forEach(el => el.classList.toggle('selected', Number(el.dataset.mailId) === id));
      if (m.unread && !m.mine) {
        await call(`${routes.list}${id}/read/`, {method:'POST', body:payload({})});
        const row = document.querySelector(`[data-mail-id="${id}"]`);
        row?.classList.remove('unread');
        row?.querySelector('.sgr-mail-dot')?.remove();
        await unread();
      }
    } catch (err) { feedback(err.message, true); showNothing(); }
  }
  const toInput = $('sgr-mail-to-input');
  const suggestionBox = $('sgr-mail-suggestions');
  function closeSuggestions() {
    suggestionBox.hidden = true;
    suggestionBox.innerHTML = '';
    toInput.setAttribute('aria-expanded', 'false');
    matches = []; activeMatch = -1;
  }
  function renderChips() {
    const zone = $('sgr-mail-chips');
    zone.innerHTML = chosenRecipients.map(u => `
      <span class="sgr-mail-chip"><span>${escape(u.email)}</span>
      ${recipientsLocked ? '' : `<button type="button" data-mail-remove="${u.id}" aria-label="Quitar ${escape(u.email)}">&times;</button>`}
      </span>`).join('');
  }
  function chooseRecipient(u) {
    if (recipientsLocked || chosenRecipients.some(existing => existing.id === u.id)) {
      toInput.value = ''; closeSuggestions(); return;
    }
    if (chosenRecipients.length >= 20) {
      feedback('Puedes seleccionar hasta 20 destinatarios.', true); return;
    }
    chosenRecipients.push(u);
    toInput.value = '';
    closeSuggestions(); renderChips();
    toInput.focus();
  }
  function highlightMatch(index) {
    activeMatch = index;
    suggestionBox.querySelectorAll('[data-mail-contact-id]').forEach((el, i) => {
      const active = i === index;
      el.classList.toggle('active', active);
      el.setAttribute('aria-selected', String(active));
    });
  }
  function showSuggestions() {
    if (!matches.length) {
      suggestionBox.hidden = false;
      suggestionBox.innerHTML = '<div class="sgr-mail-no-match">Sin funcionarios coincidentes.</div>';
      toInput.setAttribute('aria-expanded','true');
      return;
    }
    suggestionBox.innerHTML = matches.map(u => `
      <button type="button" role="option" class="sgr-mail-suggestion" data-mail-contact-id="${u.id}" aria-selected="false">
        <strong>${escape(u.name)}</strong>
        <small>${escape(u.email)} · ${escape(u.delegation)}</small>
      </button>`).join('');
    suggestionBox.hidden = false;
    toInput.setAttribute('aria-expanded','true');
    highlightMatch(-1);
  }
  async function lookupRecipients() {
    const query = toInput.value.trim();
    const seq = ++lookupSequence;
    if (recipientsLocked || !composing || !query) { closeSuggestions(); return; }
    try {
      const url = routes.recipients + '?' + new URLSearchParams({q:query});
      const {recipients:users} = await call(url);
      if (seq !== lookupSequence || toInput.value.trim() !== query || !composing) return;
      matches = users.filter(u => !chosenRecipients.some(c => c.id === u.id));
      showSuggestions();
    } catch (err) { if(seq===lookupSequence) feedback(err.message,true); }
  }
  function setRecipients(users, locked=false) {
    chosenRecipients = users;
    recipientsLocked = locked;
    toInput.value = '';
    toInput.disabled = locked;
    toInput.placeholder = locked ? 'Respuesta a un único destinatario' : 'Escribe nombre o correo…';
    lookupSequence++;
    closeSuggestions(); renderChips();
  }
  async function compose(reply=false) {
    clearFeedback();
    composing = true;
    replyTo = reply && selectedData ? selectedData.id : null;
    $('sgr-mail-detail-actions').hidden = true;
    $('sgr-mail-detail').hidden = true;
    $('sgr-mail-compose').hidden = false;
    $('sgr-mail-compose-title').textContent = reply ? 'Responder mensaje' : 'Nuevo mensaje';
    const target = reply && selectedData ? (selectedData.mine ? {
      id:selectedData.recipient_id,
      name:selectedData.recipients?.[0]?.name || selectedData.to.split(',')[0],
      email:selectedData.recipients?.[0]?.email || selectedData.recipient_email.split(',')[0]
    } : {
      id:selectedData.sender_id, name:selectedData.from, email:selectedData.sender_email
    }) : null;
    setRecipients(target ? [target] : [], reply);
    $('sgr-mail-subject').value = reply && selectedData ? (/^Re:/i.test(selectedData.subject) ? selectedData.subject : 'Re: ' + selectedData.subject) : '';
    $('sgr-mail-message').value = '';
    if (reply) $('sgr-mail-message').focus(); else toInput.focus();
  }
  async function send(event) {
    event.preventDefault(); clearFeedback(); closeSuggestions();
    const subject = $('sgr-mail-subject').value.trim(),
          body = $('sgr-mail-message').value.trim();
    if (toInput.value.trim()) {
      return feedback('Selecciona el destinatario sugerido antes de enviar.', true);
    }
    if (!chosenRecipients.length || !subject || !body) {
      return feedback('Completa Para, asunto y mensaje.', true);
    }
    const button = $('sgr-mail-send');
    button.disabled = true;
    try {
      const recipients = chosenRecipients.map(u => u.id).join(',');
      const result = await call(routes.send, {method:'POST',body:payload({recipients, subject, body, reply_to:replyTo||''})});
      composing = false; replyTo = null;
      selected = result.id;
      folder = 'sent'; page = 1;
      document.querySelectorAll('[data-mail-folder]').forEach(el=>el.classList.toggle('active',el.dataset.mailFolder===folder));
      await loadList(); await selectMessage(result.id);
      feedback(result.notice);
      await unread();
    } catch (err) { feedback(err.message, true); }
    finally { button.disabled = false; }
  }
  async function archive() {
    if (!selectedData) return;
    clearFeedback();
    const archived = selectedData.archived;
    try {
      await call(`${routes.list}${selectedData.id}/archive/`, {method:'POST',body:payload({archive:archived?'0':'1'})});
      selected = null; selectedData = null;
      await loadList(); showNothing(); await unread();
      feedback(archived ? 'Mensaje restaurado.' : 'Mensaje archivado.');
    } catch (err) { feedback(err.message, true); }
  }
  async function switchFolder(f) {
    folder=f; selected=null; selectedData=null; page=1; composing=false; replyTo=null;
    $('sgr-mail-search').value='';
    document.querySelectorAll('[data-mail-folder]').forEach(el=>el.classList.toggle('active',el.dataset.mailFolder===f));
    showNothing(); clearFeedback(); await loadList({autoselect:true});
  }
  let debounce;
  let contactsDebounce;
  toInput.addEventListener('input', () => {
    clearTimeout(contactsDebounce);
    contactsDebounce = setTimeout(lookupRecipients, 220);
  });
  toInput.addEventListener('keydown', ev => {
    if (ev.key === 'Escape') return closeSuggestions();
    if (ev.key === 'Backspace' && !toInput.value && chosenRecipients.length && !recipientsLocked) {
      chosenRecipients.pop(); renderChips();
    }
    if (!suggestionBox.hidden && matches.length && ['ArrowDown','ArrowUp','Enter'].includes(ev.key)) {
      ev.preventDefault();
      if (ev.key === 'ArrowDown') highlightMatch((activeMatch+1)%matches.length);
      else if (ev.key === 'ArrowUp') highlightMatch((activeMatch+matches.length-1)%matches.length);
      else chooseRecipient(matches[activeMatch >= 0 ? activeMatch : 0]);
    } else if (ev.key === 'Enter') {
      ev.preventDefault();
      if(toInput.value.trim()) feedback('Selecciona un correo de las sugerencias.', true);
    }
  });
  toInput.addEventListener('blur', () => setTimeout(closeSuggestions, 130));
  suggestionBox.addEventListener('mousedown', ev => ev.preventDefault());
  suggestionBox.addEventListener('click', ev => {
    const entry = ev.target.closest('[data-mail-contact-id]');
    const user = entry && matches.find(u => u.id === Number(entry.dataset.mailContactId));
    if (user) chooseRecipient(user);
  });
  $('sgr-mail-chips').addEventListener('click', ev => {
    const button = ev.target.closest('[data-mail-remove]');
    if (!button || recipientsLocked) return;
    chosenRecipients = chosenRecipients.filter(u => u.id !== Number(button.dataset.mailRemove));
    renderChips(); toInput.focus();
  });
  $('sgr-mail-new').addEventListener('click',()=>compose());
  $('sgr-mail-reply').addEventListener('click',()=>compose(true));
  $('sgr-mail-archive').addEventListener('click',archive);
  $('sgr-mail-cancel').addEventListener('click',()=>{composing=false;selectedData ? selectMessage(selectedData.id) : showNothing();});
  $('sgr-mail-compose').addEventListener('submit',send);
  document.querySelectorAll('[data-mail-folder]').forEach(el=>el.addEventListener('click',()=>switchFolder(el.dataset.mailFolder)));
  $('sgr-mail-list').addEventListener('click',ev=>{
    const row=ev.target.closest('[data-mail-id]');
    if (row) selectMessage(Number(row.dataset.mailId));
  });
  $('sgr-mail-search').addEventListener('input',()=>{
    clearTimeout(debounce);
    debounce=setTimeout(()=>{page=1;selected=null;loadList();},300);
  });
  $('sgr-mail-prev').addEventListener('click',()=>{if(page>1){page--;selected=null;loadList();}});
  $('sgr-mail-next').addEventListener('click',()=>{if(more){page++;selected=null;loadList();}});
  modal.addEventListener('show.bs.modal',()=>switchFolder('inbox'));
  unread();
  setInterval(()=>{if(!document.hidden) unread();},60000);
})();
