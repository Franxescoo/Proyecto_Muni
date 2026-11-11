/* Chat del SGR: WebSocket permanente + recuperación HTTP + confirmación de envíos. */
(function () {
    "use strict";
    document.addEventListener("DOMContentLoaded", function () {
        const modal = document.getElementById("chatInstitucionalModal");
        if (!modal || modal.dataset.chatEnabled !== "1") return;

        const form = document.getElementById("chat-form");
        const messages = document.getElementById("messages");
        const input = document.getElementById("message");
        const button = document.getElementById("send");
        const status = document.getElementById("chat-status");
        const badge = document.getElementById("chat-unread-badge");
        const myId = Number(modal.dataset.chatUserId);
        const historyUrl = form.dataset.historyUrl;
        const readUrl = form.dataset.readUrl;
        const editUrlTemplate = form.dataset.editUrlTemplate;
        const deleteUrlTemplate = form.dataset.deleteUrlTemplate;
        const csrfToken = form.querySelector("[name=csrfmiddlewaretoken]").value;
        let socket = null;
        let socketRetryTimer = null;
        let retryDelay = 1500;
        let lastMessageId = 0;
        let loaded = false;
        let busy = false;
        let readBusy = false;
        let modalVisible = false;

        function connectionStatus(text, klass) {
            status.textContent = text;
            status.className = "badge " + klass;
        }
        function updateBadge(count) {
            const number = Math.max(0, Number(count) || 0);
            badge.textContent = number > 99 ? "99+" : String(number);
            badge.classList.toggle("d-none", number === 0 || modalVisible);
        }
        function isOwn(data) { return Number(data.user_id) === myId; }
        function findBubble(clientId, serverId) {
            return Array.from(messages.children).find(item =>
                (serverId && item.dataset.messageId === String(serverId)) ||
                (clientId && item.dataset.clientId === String(clientId))
            );
        }
        function shortTime(isoTime) {
            if (!isoTime) return "";
            const date = new Date(isoTime);
            return Number.isNaN(date.valueOf()) ? "" : date.toLocaleTimeString("es-CL", {hour:"2-digit",minute:"2-digit"});
        }
        function upsertMessage(data, state) {
            const mine = isOwn(data);
            let item = findBubble(data.client_id, data.id);
            const shouldScroll = messages.scrollTop + messages.clientHeight >= messages.scrollHeight - 100;
            if (!item) {
                item = document.createElement("li");
                messages.appendChild(item);
            }
            if (data.id) {
                item.dataset.messageId = String(data.id);
                lastMessageId = Math.max(lastMessageId, Number(data.id));
                // Ordenar mensajes recibidos por WS antes de recuperar el historial.
                const following = Array.from(messages.children).find(child =>
                    child !== item && child.dataset.messageId &&
                    Number(child.dataset.messageId) > Number(data.id)
                );
                if (following) messages.insertBefore(item, following);
            }
            if (data.client_id) item.dataset.clientId = String(data.client_id);
            item.className = "sgr-chat-item " + (mine ? "sgr-chat-own" : "sgr-chat-other");
            if (mine) item.classList.add(state === "failed" ? "sgr-chat-failed" : state === "pending" ? "sgr-chat-pending" : "sgr-chat-sent");
            item.replaceChildren();
            const label = document.createElement("div");
            label.className = "sgr-chat-author";
            label.textContent = mine ? "Tú" : data.username || "Funcionario";
            const content = document.createElement("div");
            content.className = "sgr-chat-text";
            content.textContent = data.is_deleted ? "Este mensaje fue eliminado" : data.message;
            if (data.is_deleted) content.classList.add("sgr-chat-deleted");
            const foot = document.createElement("div");
            foot.className = "sgr-chat-meta";
            const time = shortTime(data.created_at);
            const stateText = data.is_deleted ? "" : mine ? (state === "failed" ? " · No enviado" : state === "pending" ? " · Enviando…" : " · ✓ Enviado") : "";
            const editText = data.is_edited && !data.is_deleted ? " · editado" : "";
            foot.textContent = time + editText + stateText;
            item.append(label, content, foot);
            if (mine && data.id && !data.is_deleted && state !== "pending" && state !== "failed") {
                const actions = document.createElement("div");
                actions.className = "sgr-chat-actions";
                const menuButton = document.createElement("button");
                menuButton.type = "button";
                menuButton.className = "sgr-chat-menu-button";
                menuButton.title = "Opciones del mensaje";
                menuButton.setAttribute("aria-label", "Opciones del mensaje");
                menuButton.innerHTML = '<i class="bi bi-three-dots-vertical" aria-hidden="true"></i>';
                const menu = document.createElement("div");
                menu.className = "sgr-chat-menu";
                const edit = document.createElement("button");
                edit.type = "button";
                edit.className = "sgr-chat-menu-option";
                edit.innerHTML = '<i class="bi bi-pencil me-2" aria-hidden="true"></i>Editar';
                edit.appendChild(document.createTextNode("Editar"));
                edit.addEventListener("click", (event) => {
                    event.stopPropagation();
                    menu.hidden = true;
                    editMessage(data, item);
                });
                const remove = document.createElement("button");
                remove.type = "button";
                remove.className = "sgr-chat-menu-option sgr-chat-menu-danger";
                remove.innerHTML = '<i class="bi bi-trash me-2" aria-hidden="true"></i>Eliminar';
                remove.addEventListener("click", (event) => {
                    event.stopPropagation();
                    menu.hidden = true;
                    askDeleteMessage(data.id);
                });
                menu.append(edit, remove);
                menu.hidden = true;
                menuButton.addEventListener("click", (event) => {
                    event.stopPropagation();
                    document.querySelectorAll(".sgr-chat-menu").forEach(other => {
                        if (other !== menu) other.hidden = true;
                    });
                    menu.hidden = !menu.hidden;
                });
                actions.append(menuButton, menu);
                item.appendChild(actions);
            }
            if (mine && state === "failed") {
                const retry = document.createElement("button");
                retry.type = "button";
                retry.className = "btn btn-sm btn-light mt-2";
                retry.textContent = "Reintentar";
                retry.addEventListener("click", () => send(data.message, data.client_id));
                item.appendChild(retry);
            }
            while (messages.children.length > 200) messages.firstElementChild.remove();
            if (shouldScroll || mine) messages.scrollTop = messages.scrollHeight;
        }
        function normalize(data) {
            return {id:data.id,client_id:data.client_id,user_id:data.user_id,username:data.username,message:data.message,created_at:data.created_at,is_edited:Boolean(data.is_edited),is_deleted:Boolean(data.is_deleted)};
        }
        async function refreshMessages() {
            if (busy) return;
            busy = true;
            try {
                const url = historyUrl + (loaded ? "?after=" + lastMessageId : "");
                const response = await fetch(url, {headers:{"X-Requested-With":"XMLHttpRequest"}, cache:"no-store"});
                if (!response.ok) throw new Error("No fue posible recuperar mensajes.");
                const data = await response.json();
                data.messages.forEach(msg => upsertMessage(normalize(msg), "sent"));
                loaded = true;
                updateBadge(data.unread_count);
                if (modalVisible) markRead();
            } catch (error) {
                // Se reintentará mediante el siguiente sondeo o al reconectar.
            } finally {
                busy = false;
            }
        }
        async function markRead() {
            if (!modalVisible || readBusy) return;
            readBusy = true;
            try {
                const response = await fetch(readUrl, {
                    method:"POST",
                    headers:{"X-CSRFToken":csrfToken,"X-Requested-With":"XMLHttpRequest"},
                    body:new URLSearchParams({last_message_id:String(lastMessageId)})
                });
                if (response.ok) {
                    const data = await response.json();
                    updateBadge(data.unread_count);
                }
            } catch (error) {
                // La próxima sincronización puede volver a marcar leído.
            } finally {
                readBusy = false;
            }
        }
        function scheduleReconnect() {
            if (socketRetryTimer) return;
            socketRetryTimer = window.setTimeout(() => {
                socketRetryTimer = null;
                connect();
            }, retryDelay);
            retryDelay = Math.min(retryDelay * 2, 30000);
        }
        function connect() {
            const scheme = location.protocol === "https:" ? "wss:" : "ws:";
            try { 
                socket = new WebSocket(scheme + "//" + location.host + "/ws/chat/"); 
                window.chatSocket = socket; // <--- Expone el socket globalmente
            }
            catch (error) {
                connectionStatus("Sin conexión en tiempo real", "bg-danger");
                scheduleReconnect();
                return;
            }
            connectionStatus("Conectando...", "bg-secondary");
            socket.addEventListener("open", function () {
                retryDelay = 1500;
                connectionStatus("Conectado", "bg-success");
                refreshMessages();
            });
            socket.addEventListener("message", function (event) {
                try {
                    const data = JSON.parse(event.data);
                    if (data.type !== "chat_message") return;
                    upsertMessage(normalize(data), "sent");
                    if (modalVisible) markRead();
                    else refreshMessages();
                } catch (error) { /* Ignorar mensajes malformados. */ }
            });
            socket.addEventListener("close", function () {
                connectionStatus("Sin conexión en tiempo real", "bg-danger");
                scheduleReconnect();
            });
            socket.addEventListener("error", function () {
                connectionStatus("Sin conexión en tiempo real", "bg-danger");
                // La señal de close programará el reintento.
            });
        }

        function newClientId() {
            if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
            const bytes = new Uint8Array(16);
            if (window.crypto && crypto.getRandomValues) {
                crypto.getRandomValues(bytes);
            } else {
                for (let i = 0; i < 16; i++) bytes[i] = Math.floor(Math.random() * 256);
            }
            bytes[6] = (bytes[6] & 0x0f) | 0x40;
            bytes[8] = (bytes[8] & 0x3f) | 0x80;
            const h = Array.from(bytes, b => b.toString(16).padStart(2, "0")).join("");
            return h.slice(0, 8) + "-" + h.slice(8, 12) + "-" + h.slice(12, 16) + "-" + h.slice(16, 20) + "-" + h.slice(20);
        }
        
        function endpoint(template, id) { return template.replace(/\/0\//, "/" + String(id) + "/"); }
        function editMessage(data, item) {
            if (item.querySelector(".sgr-chat-inline-editor")) return;
            const text = item.querySelector(".sgr-chat-text");
            if (!text) return;
            const editor = document.createElement("div");
            editor.className = "sgr-chat-inline-editor";
            const inputEditor = document.createElement("input");
            inputEditor.type = "text";
            inputEditor.className = "sgr-chat-inline-input";
            inputEditor.maxLength = 300;
            inputEditor.value = data.message;
            const controls = document.createElement("div");
            controls.className = "sgr-chat-inline-controls";
            const cancel = document.createElement("button");
            cancel.type = "button";
            cancel.className = "sgr-chat-inline-cancel";
            cancel.textContent = "Cancelar";
            const save = document.createElement("button");
            save.type = "button";
            save.className = "sgr-chat-inline-save";
            save.textContent = "Guardar";
            cancel.addEventListener("click", () => upsertMessage(data, "sent"));
            save.addEventListener("click", () => saveEditedMessage(data, item, inputEditor.value));
            inputEditor.addEventListener("keydown", (event) => {
                if (event.key === "Enter") save.click();
                if (event.key === "Escape") cancel.click();
            });
            controls.append(cancel, save);
            editor.append(inputEditor, controls);
            text.replaceWith(editor);
            inputEditor.focus();
            inputEditor.select();
        }
        async function saveEditedMessage(data, item, value) {
            const text = value.trim();
            if (!text || text === data.message || text.length > 300) return;
            try {
                const response = await fetch(endpoint(editUrlTemplate, data.id), {
                    method:"POST",
                    headers:{"X-CSRFToken":csrfToken,"X-Requested-With":"XMLHttpRequest"},
                    body:new URLSearchParams({message:text})
                });
                const result = await response.json();
                if (!response.ok || !result.ok) throw new Error(result.error || "No fue posible editar el mensaje.");
                upsertMessage(normalize(result.message), "sent");
            } catch (error) {
                connectionStatus(error.message, "bg-danger");
            }
        }
        function askDeleteMessage(id) {
            const existing = modal.querySelector(".sgr-chat-confirmation");
            if (existing) existing.remove();
            const confirmation = document.createElement("div");
            confirmation.className = "sgr-chat-confirmation";
            confirmation.innerHTML = "<span>¿Eliminar este mensaje?</span>";
            const cancel = document.createElement("button");
            cancel.type = "button";
            cancel.className = "btn btn-sm btn-light";
            cancel.textContent = "Cancelar";
            const confirm = document.createElement("button");
            confirm.type = "button";
            confirm.className = "btn btn-sm btn-danger";
            confirm.textContent = "Eliminar";
            cancel.addEventListener("click", () => confirmation.remove());
            confirm.addEventListener("click", () => {
                confirmation.remove();
                deleteMessage(id);
            });
            confirmation.append(cancel, confirm);
            modal.querySelector(".sgr-chat-body").prepend(confirmation);
        }
        async function deleteMessage(id) {
            try {
                const response = await fetch(endpoint(deleteUrlTemplate, id), {
                    method:"POST",
                    headers:{"X-CSRFToken":csrfToken,"X-Requested-With":"XMLHttpRequest"}
                });
                const result = await response.json();
                if (!response.ok || !result.ok) throw new Error(result.error || "No fue posible eliminar el mensaje.");
                upsertMessage(normalize(result.message), "sent");
            } catch (error) {
                connectionStatus(error.message, "bg-danger");
            }
        }
        async function send(message, existingClientId) {
            const clientId = existingClientId || newClientId();
            if (!clientId) { connectionStatus("No se puede generar el envío", "bg-danger"); return; }
            const draft = {client_id:clientId,user_id:myId,username:"Tú",message:message,created_at:new Date().toISOString()};
            upsertMessage(draft, "pending");
            button.disabled = true;
            try {
                const response = await fetch(form.action, {
                    method:"POST",
                    headers:{"X-CSRFToken":csrfToken,"X-Requested-With":"XMLHttpRequest"},
                    body:new URLSearchParams({message:message,client_id:clientId})
                });
                const result = await response.json();
                if (!response.ok || !result.ok || !result.message) throw new Error(result.error || "Error de envío");
                upsertMessage(normalize(result.message), "sent");
                if (modalVisible) markRead();
            } catch (error) {
                upsertMessage(draft, "failed");
            } finally {
                button.disabled = false;
                input.focus();
            }
        }
        form.addEventListener("submit", function (event) {
            event.preventDefault();
            const message = input.value.trim();
            if (!message || message.length > 300 || button.disabled) return;
            input.value = "";
            send(message);
        });
        modal.addEventListener("shown.bs.modal", function () {
            modalVisible = true;
            updateBadge(0);
            messages.scrollTop = messages.scrollHeight;
            refreshMessages();
            markRead();
            input.focus();
        });
        modal.addEventListener("hidden.bs.modal", function () {
            modalVisible = false;
            refreshMessages();
        });
        document.addEventListener("visibilitychange", function () {
            if (!document.hidden) refreshMessages();
        });
        window.addEventListener("online", function () { refreshMessages(); });
        // El envío HTTP funciona incluso si el WebSocket no está disponible.
        button.disabled = false;
        // No cerrar el socket al cerrar el modal: así llegan avisos desde cualquier página.
        refreshMessages();
        connect();
        window.setInterval(refreshMessages, 10000);
    });
})();
