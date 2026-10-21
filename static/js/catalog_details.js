/* Vista de consulta: únicamente reutiliza la información YA VISIBLE en el listado.
   No agrega permisos, endpoints ni carga datos ocultos. */
(() => {
  document.addEventListener('DOMContentLoaded', () => {
    if (typeof bootstrap === 'undefined') return;
    const lists = document.querySelectorAll('.sgr-catalog table');
    if (!lists.length) return;
    let detailModal = null;
    let modalTitle = null;
    let detailGrid = null;
    const ensureModal = () => {
      if (detailModal) return detailModal;
      const modal = document.createElement('div');
      modal.className = 'modal fade sgr-upgraded-modal';
      modal.id = 'sgrCatalogDetailModal';
      modal.tabIndex = -1;
      modal.setAttribute('aria-labelledby', 'sgrCatalogDetailTitle');
      modal.setAttribute('aria-hidden', 'true');
      modal.innerHTML = `
        <div class="modal-dialog modal-lg modal-dialog-centered modal-dialog-scrollable">
          <div class="modal-content">
            <div class="modal-header">
              <div><div class="small text-uppercase opacity-75 fw-semibold mb-1"><i class="bi bi-eye me-1"></i> Consulta</div>
                <h2 id="sgrCatalogDetailTitle" class="modal-title fs-5 fw-bold">Detalle del registro</h2>
                <p class="mb-0 small opacity-75">Información disponible en este listado, sin posibilidad de edición.</p>
              </div>
              <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Cerrar"></button>
            </div>
            <div class="modal-body"><dl class="sgr-detail-grid mb-0"></dl></div>
            <div class="modal-footer"><button type="button" data-bs-dismiss="modal" class="btn btn-outline-secondary"><i class="bi bi-x-lg me-1" aria-hidden="true"></i>Cerrar</button></div>
          </div>
        </div>`;
      document.body.appendChild(modal);
      detailGrid = modal.querySelector('.sgr-detail-grid');
      modalTitle = modal.querySelector('.modal-title');
      detailModal = bootstrap.Modal.getOrCreateInstance(modal);
      return detailModal;
    };
    lists.forEach(table => {
      const headers = Array.from(table.querySelectorAll('thead tr:last-child th'));
      const index = headers.findIndex(th => th.textContent.trim().toLowerCase() === 'acciones');
      if (index < 0) return;
      table.querySelectorAll('tbody tr').forEach(row => {
        const cells = Array.from(row.children).filter(el => el.tagName === 'TD');
        if (cells.length !== headers.length || cells.length <= 1) return;
        const actionCell = cells[index];
        if (!actionCell) return;
        const buttons = Array.from(actionCell.querySelectorAll('a, button'));
        if (buttons.some(btn => /^ver(?:\s|$)/i.test(btn.textContent.trim()))) return;
        const actions = actionCell.querySelector('.d-flex') || actionCell;
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn btn-sm btn-outline-info sgr-details-button';
        btn.innerHTML = '<i class="bi bi-eye me-1" aria-hidden="true"></i>Ver';
        btn.addEventListener('click', () => {
          ensureModal();
          detailGrid.replaceChildren();
          const pairs = headers.map((th, idx) => ({
            label: th.textContent.trim(),
            value: cells[idx] ? (cells[idx].innerText || cells[idx].textContent || '').trim().replace(/\s+/g, ' ') : ''
          })).filter(x => x.label && !/^(acciones|seleccionar|foto)$/i.test(x.label));
          modalTitle.textContent = pairs[0]?.value || 'Detalle del registro';
          pairs.forEach(pair => {
            const item = document.createElement('div');
            item.className = 'sgr-detail-item';
            const dt = document.createElement('dt'); dt.textContent = pair.label;
            const dd = document.createElement('dd'); dd.textContent = pair.value || '—';
            item.append(dt, dd);
            detailGrid.append(item);
          });
          detailModal.show();
        });
        actions.prepend(btn);
      });
    });
  });
})();
