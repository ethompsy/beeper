/*
 * sse.js — native EventSource streaming for the investigation pages (Task 4.3).
 *
 * AD-4: investigation real-time streaming uses the browser's native EventSource,
 * NOT the htmx SSE extension. This module replaces the htmx-ext-sse behaviour for
 * the investigation DETAIL and LIST pages while preserving the exact swap
 * semantics the old `sse-swap="<event>"` attribute provided: for each named SSE
 * event whose payload is an HTML partial, swap the innerHTML of the DOM element
 * registered for that event name.
 *
 * Responsibilities:
 *   1. Open an EventSource to the URL on `[data-sse-url]` (detail + list).
 *   2. Dispatch named events to their target containers (innerHTML swap),
 *      replicating sse-swap for every existing panel.
 *   3. step-update: merge the incoming step <li> elements into the timeline by
 *      their `order` field so steps land at the correct position (AC2, NFR4).
 *   4. Auto-reconnect on drop, with capped exponential backoff (≤5s, NFR9).
 *   5. On (re)connect, REST backfill from GET /api/v1/investigations/{id} and
 *      diff/insert any missed steps by `order` (AC3, AD-4).
 *   6. After MAX_RETRIES failed reconnects, surface the exact banner
 *      "Live updates unavailable — refresh to sync" without ever hiding the
 *      already-rendered investigation detail (AC4).
 *   7. New-investigation card highlight fades over 5s (AC5).
 *
 * No JS test runner exists (AD-8): runtime DOM behaviour is verified manually in
 * the browser. tests/test_sse_streaming.py pins the source contract below.
 */
(function () {
    "use strict";

    // AC4/NFR9: stop reconnecting after 5 failed retries; reconnect window ≤5s.
    var MAX_RETRIES = 5;
    var BASE_RECONNECT_MS = 1000;
    var MAX_RECONNECT_MS = 5000; // ≤5s auto-reconnect (NFR9)
    var HIGHLIGHT_FADE_MS = 5000; // 5s new-card highlight fade (AC5)

    // Exact, user-facing copy required by AC4 — do not reword.
    var UNAVAILABLE_MESSAGE = "Live updates unavailable — refresh to sync";

    /**
     * Swap the innerHTML of `container` with `html`, replicating the old
     * htmx sse-swap="innerHTML" behaviour for a named event payload.
     */
    function swapInnerHtml(container, html) {
        if (!container) return;
        container.innerHTML = html;
    }

    /**
     * Parse an HTML fragment string into an array of top-level elements.
     */
    function parseFragment(html) {
        var tmpl = document.createElement("template");
        tmpl.innerHTML = html.trim();
        return tmpl.content;
    }

    /**
     * step-update handler — insert/replace steps by their `order` field so they
     * land at the correct position even if events arrive out of order or a step
     * was missed during a disconnect (AC2 + AC3 backfill share this path).
     *
     * The server sends the full <ul class="step-timeline"> partial; we reconcile
     * its <li data-order> children into the live timeline rather than blindly
     * replacing, so position is always driven by `order`.
     */
    function mergeStepsByOrder(container, incomingHtml) {
        if (!container) return;
        var list = container.querySelector(".step-timeline");
        var incoming = parseFragment(incomingHtml);
        var incomingList = incoming.querySelector(".step-timeline");

        // First paint (no live list yet): just swap it in wholesale.
        if (!list) {
            swapInnerHtml(container, incomingHtml);
            return;
        }
        if (!incomingList) {
            swapInnerHtml(container, incomingHtml);
            return;
        }

        var incomingItems = incomingList.querySelectorAll("li[data-order]");
        for (var i = 0; i < incomingItems.length; i++) {
            insertStepByOrder(list, incomingItems[i]);
        }
    }

    /**
     * Insert (or replace) a single step <li> into `list` at the position
     * dictated by its data-order, keeping the list sorted ascending by order.
     */
    function insertStepByOrder(list, item) {
        var order = parseInt(item.getAttribute("data-order"), 10);
        if (isNaN(order)) {
            list.appendChild(item);
            return;
        }
        var existing = list.querySelectorAll("li[data-order]");
        for (var i = 0; i < existing.length; i++) {
            var current = parseInt(existing[i].getAttribute("data-order"), 10);
            if (current === order) {
                // Replace the existing step in place (state/content update).
                list.replaceChild(item, existing[i]);
                return;
            }
            if (current > order) {
                // Insert the missed step before the first higher-ordered one.
                list.insertBefore(item, existing[i]);
                return;
            }
        }
        list.appendChild(item);
    }

    /**
     * Fade a newly-created investigation card highlight over 5s (AC5).
     */
    function startHighlightFade(el) {
        if (!el) return;
        el.classList.add("sse-new-highlight");
        window.setTimeout(function () {
            el.classList.remove("sse-new-highlight");
        }, HIGHLIGHT_FADE_MS);
    }

    /**
     * Snapshot the set of investigation-card identities (href) currently in a
     * container so we can tell which cards are genuinely new after a swap.
     */
    function cardKeySet(container) {
        var keys = {};
        if (!container) return keys;
        var cards = container.querySelectorAll(".investigation-card");
        for (var i = 0; i < cards.length; i++) {
            keys[cards[i].getAttribute("href")] = true;
        }
        return keys;
    }

    /**
     * Apply the 5s fade to cards that weren't present before the swap (AC5).
     * `priorKeys` is the cardKeySet() captured before innerHTML was replaced.
     */
    function highlightNewCards(container, priorKeys) {
        if (!container) return;
        priorKeys = priorKeys || {};
        var cards = container.querySelectorAll(".investigation-card");
        for (var i = 0; i < cards.length; i++) {
            var href = cards[i].getAttribute("href");
            if (!priorKeys[href]) {
                startHighlightFade(cards[i]);
            }
        }
    }

    /**
     * SSEController — owns one EventSource, its reconnect lifecycle, the named
     * event → container routing, and the REST backfill.
     */
    function SSEController(rootEl) {
        this.root = rootEl;
        this.url = rootEl.getAttribute("data-sse-url");
        // /api/v1/investigations/{id} backfill source (detail page only).
        this.backfillUrl = rootEl.getAttribute("data-sse-backfill-url") || null;
        this.source = null;
        this.retries = 0;
        this.reconnectTimer = null;
        this.closed = false;
        // Map of eventName → target element (replicates sse-swap registration).
        this.targets = this.collectTargets(rootEl);
    }

    /**
     * Build the eventName → element map from [data-sse-swap] attributes, which
     * replace the old htmx `sse-swap="<event>"` attributes 1:1. An element may
     * register several events with a whitespace-separated list (the list view
     * routes both FR24 events — investigation_created / investigation_status —
     * to the same container).
     */
    SSEController.prototype.collectTargets = function (rootEl) {
        var targets = {};
        function register(el) {
            var spec = el.getAttribute("data-sse-swap");
            if (!spec) return;
            var names = spec.split(/\s+/);
            for (var n = 0; n < names.length; n++) {
                if (names[n]) targets[names[n]] = el;
            }
        }
        register(rootEl);
        var nodes = rootEl.querySelectorAll("[data-sse-swap]");
        for (var i = 0; i < nodes.length; i++) {
            register(nodes[i]);
        }
        return targets;
    };

    SSEController.prototype.connect = function () {
        if (this.closed || !this.url) return;
        var self = this;
        var source = new EventSource(this.url);
        this.source = source;

        source.onopen = function () {
            // A successful (re)open clears the retry budget and triggers a REST
            // backfill so any steps missed while disconnected are reconciled.
            self.retries = 0;
            self.clearBanner();
            self.backfill();
        };

        // Wire one listener per known named event → its target container.
        var names = Object.keys(self.targets);
        for (var i = 0; i < names.length; i++) {
            (function (eventName) {
                source.addEventListener(eventName, function (evt) {
                    self.handleEvent(eventName, evt.data);
                });
            })(names[i]);
        }

        source.onerror = function () {
            // EventSource auto-reconnects on its own, but we cap retries and
            // surface the unavailable banner once the budget is exhausted.
            self.handleError();
        };
    };

    SSEController.prototype.handleEvent = function (eventName, data) {
        var target = this.targets[eventName];
        if (!target) return;
        if (eventName === "step-update") {
            // AC2: position steps by their `order` field.
            mergeStepsByOrder(target, data);
        } else if (eventName === "investigation_created") {
            // FR24: a new investigation appeared in the list. Capture the
            // existing cards, swap, then fade-highlight only the new one (AC5).
            var priorKeys = cardKeySet(target);
            swapInnerHtml(target, data);
            highlightNewCards(target, priorKeys);
        } else {
            // All other panels keep the htmx innerHTML-swap semantics.
            swapInnerHtml(target, data);
        }
    };

    SSEController.prototype.handleError = function () {
        if (this.closed) return;
        // The native EventSource will retry on its own; we close it so we own
        // the backoff schedule and can enforce MAX_RETRIES deterministically.
        if (this.source) {
            this.source.close();
            this.source = null;
        }
        this.retries += 1;
        if (this.retries > MAX_RETRIES) {
            // AC4: give up after 5 retries; show the banner but never blank the
            // already-rendered detail.
            this.showBanner();
            return;
        }
        var delay = Math.min(
            BASE_RECONNECT_MS * Math.pow(2, this.retries - 1),
            MAX_RECONNECT_MS
        );
        var self = this;
        this.reconnectTimer = window.setTimeout(function () {
            self.connect();
        }, delay);
    };

    /**
     * REST backfill (AC3, AD-4): fetch the current investigation state and
     * diff/insert any steps missed while the stream was down, keyed by `order`.
     */
    SSEController.prototype.backfill = function () {
        if (!this.backfillUrl) return;
        var self = this;
        var stepTarget = this.targets["step-update"];
        if (!stepTarget) return;
        fetch(this.backfillUrl, { headers: { Accept: "application/json" } })
            .then(function (resp) {
                if (!resp.ok) return null;
                return resp.json();
            })
            .then(function (payload) {
                if (!payload || !payload.steps) return;
                self.applyBackfillSteps(stepTarget, payload.steps);
            })
            .catch(function () {
                // Backfill is best-effort; the live stream remains authoritative.
            });
    };

    /**
     * Insert any backfilled steps that aren't already present, by `order`.
     */
    SSEController.prototype.applyBackfillSteps = function (container, steps) {
        var list = container.querySelector(".step-timeline");
        if (!list) return;
        for (var i = 0; i < steps.length; i++) {
            var step = steps[i];
            var order = step.order;
            var present = list.querySelector('li[data-order="' + order + '"]');
            if (present) continue;
            var li = document.createElement("li");
            li.setAttribute("data-order", String(order));
            li.setAttribute("data-step-state", step.state || "pending");
            li.className = "investigation-step";
            li.textContent = step.label || "";
            insertStepByOrder(list, li);
        }
    };

    SSEController.prototype.showBanner = function () {
        var banner = this.root.querySelector("[data-sse-banner]");
        if (!banner) {
            banner = document.createElement("div");
            banner.setAttribute("data-sse-banner", "true");
            banner.setAttribute("role", "status");
            banner.className = "sse-banner";
            // Insert at the top so the detail content below remains viewable (AC4).
            this.root.insertBefore(banner, this.root.firstChild);
        }
        banner.textContent = UNAVAILABLE_MESSAGE;
        banner.hidden = false;
    };

    SSEController.prototype.clearBanner = function () {
        var banner = this.root.querySelector("[data-sse-banner]");
        if (banner) {
            banner.hidden = true;
        }
    };

    SSEController.prototype.close = function () {
        this.closed = true;
        if (this.reconnectTimer) window.clearTimeout(this.reconnectTimer);
        if (this.source) this.source.close();
    };

    function initSSE() {
        var roots = document.querySelectorAll("[data-sse-url]");
        for (var i = 0; i < roots.length; i++) {
            var controller = new SSEController(roots[i]);
            controller.connect();
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initSSE);
    } else {
        initSSE();
    }
})();
