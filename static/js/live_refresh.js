(function () {
    "use strict";

    const reconnectLimit = 30000;
    const loadedAt = Date.now();
    let reconnectDelay = 1000;
    let socket;
    let pending = false;
    let pageHadInput = false;

    document.addEventListener("input", function () {
        pageHadInput = true;
    }, true);

    function pageCanReload() {
        const active = document.activeElement;
        return document.visibilityState === "visible"
            && !document.querySelector(".modal.show")
            && (!active || !/^(INPUT|TEXTAREA|SELECT)$/.test(active.tagName))
            && !pageHadInput;
    }

    function tryReload() {
        if (!pending || Date.now() - loadedAt < 2000) return;
        if (pageCanReload()) {
            pending = false;
            window.location.reload();
        }
    }

    function scheduleReload() {
        pending = true;
        window.setTimeout(tryReload, 800);
    }

    function connect() {
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        socket = new WebSocket(protocol + "//" + window.location.host + "/ws/updates/");

        socket.addEventListener("open", function () {
            reconnectDelay = 1000;
        });
        socket.addEventListener("message", function (event) {
            let data;
            try {
                data = JSON.parse(event.data);
            } catch (error) {
                return;
            }
            if (data.type === "data_changed") scheduleReload();
        });
        socket.addEventListener("close", function () {
            window.setTimeout(connect, reconnectDelay);
            reconnectDelay = Math.min(reconnectDelay * 2, reconnectLimit);
        });
        socket.addEventListener("error", function () {
            socket.close();
        });
    }

    document.addEventListener("visibilitychange", tryReload);
    document.addEventListener("hidden.bs.modal", tryReload);
    connect();
}());
