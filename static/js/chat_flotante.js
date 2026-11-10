/* SGR | Ventana de chat movible, sin backdrop y persistente entre páginas. */
(function () {
    "use strict";
    document.addEventListener("DOMContentLoaded", function () {
        const panel = document.getElementById("chatInstitucionalModal");
        const toggle = document.querySelector("[data-sgr-chat-toggle]");
        if (!panel || !toggle || panel.dataset.chatEnabled !== "1") return;

        // Mover la ventana al nivel raíz del documento. De esta forma no queda
        // recortada por overflow/transform ni debajo de la barra de base.html.
        if (panel.parentElement !== document.body) {
            document.body.appendChild(panel);
        }

        const header = panel.querySelector(".sgr-chat-header");
        const input = panel.querySelector("#message");
        const minimizeButton = panel.querySelector("[data-sgr-chat-minimize]");
        const closeButton = panel.querySelector("[data-sgr-chat-close]");
        const username = panel.dataset.chatUserId || "0";
        const delegation = panel.dataset.chatDelegationId || "sin-delegacion";
        const storageKey = "sgr_chat_float_" + username + "_" + delegation;
        let saved = {};
        let drag = null;
        let savePending = false;
        let isOpen = false;

        try { saved = JSON.parse(sessionStorage.getItem(storageKey) || "{}"); }
        catch (_) { saved = {}; }

        function store() {
            try {
                sessionStorage.setItem(storageKey, JSON.stringify({
                    open: isOpen,
                    minimized: panel.classList.contains("is-minimized"),
                    x: Number.isFinite(saved.x) ? saved.x : null,
                    y: Number.isFinite(saved.y) ? saved.y : null,
                    draft: input ? input.value.slice(0, 300) : ""
                }));
            } catch (_) { /* Puede estar bloqueado en navegación privada. */ }
        }
        function announce(eventName) {
            panel.dispatchEvent(new Event(eventName)); // Compatibilidad con chat_institucional.js.
        }
        function setOpen(value, opts) {
            const next = Boolean(value);
            if (isOpen === next) return;
            isOpen = next;
            panel.classList.toggle("is-open", next);
            panel.setAttribute("aria-hidden", next ? "false" : "true");
            toggle.setAttribute("aria-expanded", next ? "true" : "false");
            if (next) {
                restorePosition();
                if (!panel.classList.contains("is-minimized")) announce("shown.bs.modal");
                if (!(opts && opts.restoring) && input && !panel.classList.contains("is-minimized")) input.focus();
            } else {
                announce("hidden.bs.modal");
            }
            store();
        }
        function setMinimized(value) {
            panel.classList.toggle("is-minimized", Boolean(value));
            minimizeButton.setAttribute("aria-label", value ? "Restaurar chat" : "Minimizar chat");
            minimizeButton.setAttribute("title", value ? "Restaurar" : "Minimizar");
            minimizeButton.innerHTML = value ? '<i class="bi bi-arrows-angle-expand" aria-hidden="true"></i>' : '<i class="bi bi-dash-lg" aria-hidden="true"></i>';
            if (isOpen) {
                restorePosition();
                announce(value ? "hidden.bs.modal" : "shown.bs.modal");
            }
            store();
            if (!value && isOpen && input) input.focus();
        }
        function clamp(n, lo, hi) { return Math.min(Math.max(n, lo), Math.max(lo, hi)); }
        function restorePosition() {
            if (!Number.isFinite(saved.x) || !Number.isFinite(saved.y)) return;
            const width = panel.offsetWidth;
            const height = panel.offsetHeight;
            const x = clamp(saved.x, 8, window.innerWidth - width - 8);
            const y = clamp(saved.y, 8, window.innerHeight - height - 8);
            panel.style.left = x + "px";
            panel.style.top = y + "px";
            panel.style.right = "auto";
            panel.style.bottom = "auto";
        }
        function updatePosition(x, y) {
            const left = clamp(x, 8, window.innerWidth - panel.offsetWidth - 8);
            const top = clamp(y, 8, window.innerHeight - panel.offsetHeight - 8);
            panel.style.left = left + "px";
            panel.style.top = top + "px";
            panel.style.right = "auto";
            panel.style.bottom = "auto";
            saved.x = left;
            saved.y = top;
        }
        toggle.addEventListener("click", function () {
            if (!isOpen) setOpen(true);
            else if (panel.classList.contains("is-minimized")) setMinimized(false);
            else if (input) input.focus();
        });
        closeButton.addEventListener("click", function () {
            setOpen(false);
            toggle.focus();
        });
        minimizeButton.addEventListener("click", function () {
            setMinimized(!panel.classList.contains("is-minimized"));
        });
        header.addEventListener("pointerdown", function (event) {
            if (event.button !== 0 || event.target.closest("button, a, input")) return;
            const rect = panel.getBoundingClientRect();
            drag = {id: event.pointerId, x: event.clientX, y: event.clientY, left: rect.left, top: rect.top};
            header.setPointerCapture(event.pointerId);
            panel.classList.add("is-dragging");
            event.preventDefault();
        });
        header.addEventListener("pointermove", function (event) {
            if (!drag || drag.id !== event.pointerId) return;
            updatePosition(drag.left + event.clientX - drag.x, drag.top + event.clientY - drag.y);
            event.preventDefault();
        });
        function stopDrag(event) {
            if (!drag || drag.id !== event.pointerId) return;
            drag = null;
            panel.classList.remove("is-dragging");
            store();
        }
        header.addEventListener("pointerup", stopDrag);
        header.addEventListener("pointercancel", stopDrag);
        header.addEventListener("lostpointercapture", stopDrag);
        header.addEventListener("keydown", function (event) {
            if (!event.altKey || !["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key) ) return;
            event.preventDefault();
            const rect = panel.getBoundingClientRect();
            const step = event.shiftKey ? 40 : 16;
            updatePosition(rect.left + (event.key === "ArrowRight" ? step : event.key === "ArrowLeft" ? -step : 0),
                rect.top + (event.key === "ArrowDown" ? step : event.key === "ArrowUp" ? -step : 0));
            store();
        });
        panel.addEventListener("keydown", function (event) {
            if (event.key === "Escape") {
                event.stopPropagation();
                setOpen(false);
                toggle.focus();
            }
        });
        window.addEventListener("resize", function () {
            if (isOpen) restorePosition();
        });
        const form = panel.querySelector("#chat-form");
        if (form) form.addEventListener("submit", function () {
            // El chat original limpia el campo: evita restaurar un texto ya enviado.
            queueMicrotask(store);
        });
        if (input) input.addEventListener("input", function () {
            if (savePending) return;
            savePending = true;
            requestAnimationFrame(function () { savePending = false; store(); });
        });
        // Se ejecuta después de que chat_institucional.js instale sus listeners.
        if (input && typeof saved.draft === "string") input.value = saved.draft.slice(0, 300);
        if (saved.minimized) setMinimized(true);
        if (saved.open === true) setOpen(true, {restoring:true});
        else store();
    });
})();
