/*
SSE Extension for htmx 1.9.x
Provides Server-Sent Events support via sse-connect and sse-swap attributes.
Based on the official htmx SSE extension pattern.
*/
(function() {
    /** @type {import("../htmx").HtmxInternalApi} */
    var api;

    htmx.defineExtension('sse', {
        init: function(apiRef) {
            api = apiRef;
        },

        onEvent: function(name, evt) {
            var parent = evt.target || evt.detail.elt;

            switch (name) {
                case "htmx:beforeCleanupElement":
                    var internalData = api.getInternalData(parent);
                    if (internalData.sseEventSource) {
                        internalData.sseEventSource.close();
                    }
                    return;

                case "htmx:afterProcessNode":
                    ensureEventSourceOnElement(parent);
                    return;
            }
        }
    });

    function ensureEventSourceOnElement(elt) {
        if (elt == null) return;

        // Find elements with sse-connect attribute
        if (elt.getAttribute && elt.getAttribute("sse-connect")) {
            createEventSourceOnElement(elt);
        }

        // Check children
        if (elt.querySelectorAll) {
            var sseElements = elt.querySelectorAll("[sse-connect]");
            for (var i = 0; i < sseElements.length; i++) {
                createEventSourceOnElement(sseElements[i]);
            }
        }
    }

    function createEventSourceOnElement(elt) {
        var internalData = api.getInternalData(elt);

        if (internalData.sseEventSource) {
            return; // Already connected
        }

        var url = elt.getAttribute("sse-connect");
        if (!url) return;

        var source = htmx.createEventSource(url);
        internalData.sseEventSource = source;

        // Register swap listeners
        registerSwapListeners(elt, source);

        source.onerror = function(err) {
            api.triggerEvent(elt, "htmx:sseError", { error: err, source: source });
        };
    }

    function registerSwapListeners(elt, source) {
        // Find all elements with sse-swap
        var swapElements = [];
        if (elt.getAttribute("sse-swap")) {
            swapElements.push(elt);
        }
        if (elt.querySelectorAll) {
            var children = elt.querySelectorAll("[sse-swap]");
            for (var i = 0; i < children.length; i++) {
                swapElements.push(children[i]);
            }
        }

        for (var j = 0; j < swapElements.length; j++) {
            var swapElt = swapElements[j];
            var eventName = swapElt.getAttribute("sse-swap");

            if (eventName) {
                registerSwapListener(swapElt, source, eventName);
            }
        }
    }

    function registerSwapListener(elt, source, eventName) {
        source.addEventListener(eventName, function(event) {
            // If the data is HTML, swap it
            if (isHtmlContent(event.data)) {
                var swapSpec = api.getSwapSpecification(elt);
                var target = api.getTarget(elt);
                var settleInfo = api.makeSettleInfo(target);

                api.oobSwap(swapSpec.swapStyle, target, target, event.data, settleInfo);
            }

            api.triggerEvent(elt, "htmx:sseMessage", {
                data: event.data,
                event: event,
                type: eventName
            });
        });
    }

    function isHtmlContent(data) {
        // Simple heuristic: if it starts with < it's likely HTML
        var trimmed = data.trim();
        return trimmed.charAt(0) === '<';
    }
})();
