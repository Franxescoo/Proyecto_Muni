/* CRUD de Eventos y Campañas en modales Bootstrap, sin navegación a formularios internos. */
(function () {
  'use strict';
  document.addEventListener('DOMContentLoaded', function () {
    const dialog = document.getElementById('mecAjaxModal');
    const content = document.getElementById('mecAjaxModalContent');
    if (!dialog || !content || !window.bootstrap) return;
    const modal = bootstrap.Modal.getOrCreateInstance(dialog);
    try {
      const flash = sessionStorage.getItem('mec-success');
      if (flash) {
        sessionStorage.removeItem('mec-success');
        const banner = document.createElement('div');
        banner.className = 'alert alert-success alert-dismissible fade show';
        banner.role = 'status';
        banner.textContent = flash;
        const close = document.createElement('button');
        close.type = 'button';
        close.className = 'btn-close';
        close.dataset.bsDismiss = 'alert';
        close.setAttribute('aria-label', 'Cerrar');
        banner.appendChild(close);
        const hero = document.querySelector('.mec-hero');
        if (hero) hero.insertAdjacentElement('afterend', banner);
      }
    } catch (ignored) { /* El modo privado no debe impedir guardar. */ }
    let loading = false;

    function errorMessage(message) {
      content.innerHTML = '';
      const alert = document.createElement('div');
      alert.className = 'alert alert-danger';
      alert.role = 'alert';
      alert.textContent = message;
      content.appendChild(alert);
      const footer = document.createElement('div');
      footer.className = 'modal-footer';
      const close = document.createElement('button');
      close.type = 'button';
      close.className = 'btn btn-outline-secondary';
      close.dataset.bsDismiss = 'modal';
      close.textContent = 'Cerrar';
      footer.appendChild(close);
      content.appendChild(footer);
    }
    function busy(on) {
      loading = on;
      content.setAttribute('aria-busy', String(on));
      content.querySelectorAll('button[type="submit"]').forEach(button => {
        button.disabled = on;
      });
    }
    async function open(url) {
      if (loading) return;
      content.innerHTML = '<div class="py-4 text-center text-muted">Cargando formulario…</div>';
      modal.show();
      loading = true;
      try {
        const response = await fetch(url, {
          credentials: 'same-origin',
          headers: { 'X-Requested-With': 'XMLHttpRequest' }
        });
        if (response.redirected && response.url.includes('/login')) {
          window.location.assign(response.url);
          return;
        }
        if (!response.ok) throw new Error(response.status === 403 ? 'No tienes permiso para esta operación.' : 'No se pudo cargar el contenido.');
        content.innerHTML = await response.text();
      } catch (error) {
        errorMessage(error.message);
      } finally {
        loading = false;
      }
    }
    document.addEventListener('click', function (event) {
      const link = event.target.closest('a[data-mec-modal-url]');
      if (!link) return;
      event.preventDefault();
      open(link.getAttribute('href'));
    });
    dialog.addEventListener('submit', async function (event) {
      const form = event.target.closest('form[data-mec-ajax-form]');
      if (!form || loading) return;
      event.preventDefault();
      busy(true);
      try {
        const response = await fetch(form.action, {
          method: 'POST', credentials: 'same-origin',
          headers: { 'X-Requested-With': 'XMLHttpRequest' },
          body: new FormData(form)
        });
        if (response.ok) {
          const data = await response.json();
          if (data.ok) {
            try { sessionStorage.setItem('mec-success', data.message || 'Cambios guardados correctamente.'); } catch (ignored) { }
            // Se mantiene la misma página y se recuperan cifras y filas reales.
            window.location.reload();
            return;
          }
        }
        if (response.status === 422 || response.status === 409) {
          content.innerHTML = await response.text();
          return;
        }
        throw new Error(response.status === 403 ? 'Operación no autorizada.' : 'No se pudo guardar. Comprueba tu conexión.');
      } catch (error) {
        errorMessage(error.message);
      } finally {
        busy(false);
      }
    });
    dialog.addEventListener('hidden.bs.modal', function () { content.innerHTML = ''; });
  });
}());
