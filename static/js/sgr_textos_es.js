/*
 * SGR - Ajustes exclusivamente visuales en los selectores.
 * No altera los valores de las opciones, los eventos, los formularios ni los modelos.
 * Se aplica también a formularios/modales cargados después del inicio de la página.
 */
(function () {
    "use strict";

    const traducciones = new Map([
        ["select an option", "Seleccione una opción"],
        ["select an option...", "Seleccione una opción"],
        ["select an option…", "Seleccione una opción"],
        ["select option", "Seleccione una opción"],
        ["choose an option", "Seleccione una opción"],
        ["choose an option...", "Seleccione una opción"],
        ["select a choice", "Seleccione una opción"],
        ["select an item", "Seleccione una opción"],
        ["---------", "Seleccione una opción"],
    ]);

    function normalizar(texto) {
        return String(texto || "").replace(/\s+/g, " ").trim();
    }

    function traducirTexto(texto) {
        const original = normalizar(texto);
        // Django 6.1 utiliza "- Select an option -" como etiqueta vacía.
        // Se traduce el texto visible, no el valor del campo.
        if (/^[-–—]?\s*select an option(?:\s*(?:\.\.\.|…))?\s*[-–—]?$/i.test(original)) {
            return "Seleccione una opción";
        }
        return traducciones.get(original.toLowerCase()) || null;
    }

    function esSelectorMeta(selector) {
        const nombre = selector.getAttribute("name") || "";
        const id = selector.getAttribute("id") || "";
        return nombre === "goal" || nombre.endsWith("-goal") ||
               id === "id_goal" || id.endsWith("-goal");
    }

    function traducirSelector(selector) {
        const selectorMeta = esSelectorMeta(selector);
        Array.from(selector.options).forEach(function (opcion) {
            const visible = normalizar(opcion.textContent);
            const traducido = opcion.value === "" ? traducirTexto(visible) : null;
            if (traducido && visible !== traducido) {
                opcion.textContent = traducido;
            } else if (selectorMeta && /^Goal\s*:/i.test(visible)) {
                opcion.textContent = visible.replace(/^Goal\s*:/i, "Meta:");
            }
        });
        traducirAtributos(selector);
    }

    function traducirAtributos(elemento) {
        ["placeholder", "data-placeholder"].forEach(function (atributo) {
            if (!elemento.hasAttribute(atributo)) return;
            const traducido = traducirTexto(elemento.getAttribute(atributo));
            if (traducido && elemento.getAttribute(atributo) !== traducido) {
                elemento.setAttribute(atributo, traducido);
            }
        });
    }

    function traducirSelectorEnriquecido(elemento) {
        // Solo textos sin hijos: no toca HTML ni estructuras de controles JS.
        if (elemento.children.length !== 0) return;
        const traducido = traducirTexto(elemento.textContent);
        if (traducido && normalizar(elemento.textContent) !== traducido) {
            elemento.textContent = traducido;
        }
    }

    const selectorConsultas = [
        "select", "input[placeholder]", "[data-placeholder]",
        ".select2-selection__placeholder", ".choices__placeholder",
        "[role='combobox']"
    ].join(", ");

    function revisarElemento(elemento) {
        if (!(elemento instanceof Element)) return;
        if (elemento.matches("select")) traducirSelector(elemento);
        else {
            traducirAtributos(elemento);
            if (elemento.matches(".select2-selection__placeholder, .choices__placeholder, [role='combobox']")) {
                traducirSelectorEnriquecido(elemento);
            }
        }
    }

    function revisarArbol(raiz) {
        if (raiz instanceof Element) revisarElemento(raiz);
        if (raiz && raiz.querySelectorAll) {
            raiz.querySelectorAll(selectorConsultas).forEach(revisarElemento);
        }
    }

    function iniciar() {
        revisarArbol(document);
        if (!document.body) return;

        const observador = new MutationObserver(function (cambios) {
            cambios.forEach(function (cambio) {
                // Al insertarse opciones, actualiza el select al que pertenecen.
                const elemento = cambio.target.nodeType === 1
                    ? cambio.target
                    : cambio.target.parentElement;
                if (elemento) {
                    const selector = elemento.closest("select");
                    if (selector) traducirSelector(selector);
                }
                cambio.addedNodes.forEach(function (nodo) {
                    if (nodo.nodeType === 1) revisarArbol(nodo);
                });
            });
        });
        observador.observe(document.body, { childList: true, subtree: true });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", iniciar, { once: true });
    } else {
        iniciar();
    }
})();
