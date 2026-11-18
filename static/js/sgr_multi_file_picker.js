/* SGR · Selección acumulativa de adjuntos. Solo mejora la interfaz.
   Las validaciones y la cantidad final de archivos se comprueban en Django. */
(function () {
    "use strict";

    function initMultiFileUploader(root) {
        if (root.dataset.sgrReady === "1") return;
        var original = root.querySelector('input[type="file"][multiple]');
        var addButton = root.querySelector('[data-sgr-add-files]');
        var summary = root.querySelector('[data-sgr-file-summary]');
        var list = root.querySelector('[data-sgr-file-list]');
        var message = root.querySelector('[data-sgr-file-message]');
        var inputContainer = root.querySelector('[data-sgr-original-input]');
        if (!original || !addButton || !summary || !list || !message || !inputContainer) return;

        // Si el navegador no admite FileList asignable, se conserva el input nativo.
        if (typeof DataTransfer !== "function") return;
        try {
            var probe = new DataTransfer();
            original.files = probe.files;
        } catch (error) {
            return;
        }

        var maxFiles = parseInt(root.dataset.maxFiles || "5", 10);
        var minFiles = parseInt(root.dataset.minFiles || "0", 10);
        var maxBytes = parseInt(root.dataset.maxBytes || "52428800", 10);
        var selected = [];
        var picker = document.createElement("input");
        picker.type = "file";
        picker.multiple = true;
        picker.accept = original.accept;
        picker.className = "d-none";
        picker.tabIndex = -1;
        picker.setAttribute("aria-hidden", "true");
        // Sin name: el servidor recibe solamente los archivos del input original.
        root.appendChild(picker);

        function checkedRemovals() {
            var form = root.closest("form");
            if (!form) return 0;
            return Array.from(form.querySelectorAll('input[name="remove_file_ids"]'))
                .filter(function (box) { return box.checked; }).length;
        }
        function existingCount() {
            var base = parseInt(root.dataset.existingFiles || "0", 10);
            return Math.max(0, base - checkedRemovals());
        }
        function selectedBytes() {
            return selected.reduce(function (acc, file) { return acc + file.size; }, 0);
        }
        function fileKey(file) {
            return [file.name, file.size, file.lastModified].join("::");
        }
        function formatSize(bytes) {
            if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + " KB";
            return (bytes / (1024 * 1024)).toFixed(2) + " MB";
        }
        function showMessage(text) {
            message.textContent = text || "";
            message.classList.toggle("d-none", !text);
        }
        function syncInput() {
            var transfer = new DataTransfer();
            selected.forEach(function (file) { transfer.items.add(file); });
            original.files = transfer.files;
        }
        function render() {
            var existing = existingCount();
            var total = existing + selected.length;
            var minimum = minFiles && total < minFiles
                ? " · faltan " + (minFiles - total) + " para el mínimo"
                : "";
            summary.textContent = selected.length +
                (selected.length === 1 ? " archivo nuevo" : " archivos nuevos") +
                " · " + total + " en total · " +
                formatSize(selectedBytes()) + " nuevos" + minimum;
            list.replaceChildren();
            list.classList.toggle("d-none", selected.length === 0);
            selected.forEach(function (file, index) {
                var item = document.createElement("li");
                item.className = "list-group-item d-flex flex-wrap align-items-center justify-content-between gap-2 px-2 py-2";
                var name = document.createElement("span");
                name.className = "small text-break";
                name.textContent = file.name + " (" + formatSize(file.size) + ")";
                var remove = document.createElement("button");
                remove.type = "button";
                remove.className = "btn btn-outline-danger btn-sm";
                remove.textContent = "Quitar";
                remove.setAttribute("aria-label", "Quitar " + file.name);
                remove.addEventListener("click", function () {
                    selected.splice(index, 1);
                    syncInput();
                    showMessage("");
                    render();
                });
                item.appendChild(name);
                item.appendChild(remove);
                list.appendChild(item);
            });
        }

        addButton.addEventListener("click", function () {
            picker.value = "";
            picker.click();
        });
        picker.addEventListener("change", function () {
            var incoming = Array.from(picker.files || []);
            var existing = existingCount();
            var keys = new Set(selected.map(fileKey));
            var added = 0;
            var rejected = [];
            incoming.forEach(function (file) {
                var key = fileKey(file);
                if (keys.has(key)) {
                    rejected.push("El archivo «" + file.name + "» ya estaba seleccionado.");
                } else if (existing + selected.length >= maxFiles) {
                    rejected.push("Se permite un máximo de " + maxFiles + " archivos por registro.");
                } else if (selectedBytes() + file.size > maxBytes) {
                    rejected.push("Los archivos nuevos no pueden superar 50 MB en conjunto.");
                } else {
                    selected.push(file);
                    keys.add(key);
                    added++;
                }
            });
            syncInput();
            render();
            // El selector temporal se limpia, pero los archivos reales quedan guardados.
            picker.value = "";
            showMessage(rejected.length ? Array.from(new Set(rejected)).join(" ") : "");
        });

        // Si se elimina un archivo ya guardado, se libera su cupo al momento.
        var form = root.closest("form");
        if (form) {
            form.addEventListener("change", function (event) {
                if (event.target.matches('input[name="remove_file_ids"]')) {
                    render();
                }
            });
        }
        inputContainer.classList.add("d-none");
        addButton.classList.remove("d-none");
        root.dataset.sgrReady = "1";
        render();
    }

    function initAll() {
        document.querySelectorAll("[data-sgr-multi-upload]").forEach(initMultiFileUploader);
    }
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initAll);
    } else {
        initAll();
    }
})();
