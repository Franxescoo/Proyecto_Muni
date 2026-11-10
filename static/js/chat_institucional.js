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
            content.textContent = data.message;
            const foot = document.createElement("div");
            foot.className = "sgr-chat-meta";
            const time = shortTime(data.created_at);
            const stateText = mine ? (state === "failed" ? " · No enviado" : state === "pending" ? " · Enviando…" : " · ✓ Enviado") : "";
            foot.textContent = time + stateText;
            item.append(label, content, foot);
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
            return {id:data.id,client_id:data.client_id,user_id:data.user_id,username:data.username,message:data.message,created_at:data.created_at};
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
        async function send(message, existingClientId) {
            const clientId = existingClientId || (window.crypto && crypto.randomUUID ? crypto.randomUUID() : null);
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
