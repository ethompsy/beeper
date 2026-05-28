/*
 * kb-panel.js — Related Knowledge Base panel expand/collapse (Task 4.4, FR26).
 *
 * The panel (components/kb.html → #kb-panel) is an anchored count bar that
 * expands UPWARD on wide screens (≥1200px) and renders inline on narrow ones.
 * This file owns ONLY the panel-level expand/collapse toggle:
 *   - flips aria-expanded on the toggle button,
 *   - shows/hides + grows/shrinks the body (#kb-panel-body) via max-height
 *     utility classes (the body sits ABOVE the bar in source order, so growing
 *     it pushes content upward),
 *   - rotates the caret and updates the action label,
 *   - respects prefers-reduced-motion (the transition classes are already
 *     gated with motion-reduce: in the template; JS adds no extra animation).
 *
 * Per-entry expand uses native <details>/<summary> — no JS needed there.
 *
 * The panel arrives via HTMX (lazy hx-get + the kb-update SSE swap), so we
 * (re)bind on DOMContentLoaded AND on htmx:afterSwap. Binding is idempotent via
 * a data-kb-bound marker so repeated swaps never double-wire a toggle.
 *
 * Dependency-free (no new libs).
 */
(function () {
  "use strict";

  var EXPANDED_MAX_H = "max-h-96";
  var COLLAPSED_MAX_H = "max-h-0";

  function setExpanded(panel, expanded) {
    var toggle = panel.querySelector("[data-kb-panel-toggle]");
    var body = panel.querySelector("[data-kb-panel-body]");
    if (!toggle || !body) return;

    panel.setAttribute("data-expanded", expanded ? "true" : "false");
    toggle.setAttribute("aria-expanded", expanded ? "true" : "false");

    if (expanded) {
      body.hidden = false;
      body.classList.remove(COLLAPSED_MAX_H);
      body.classList.add(EXPANDED_MAX_H);
    } else {
      body.classList.remove(EXPANDED_MAX_H);
      body.classList.add(COLLAPSED_MAX_H);
      body.hidden = true;
    }

    var caret = toggle.querySelector(".kb-panel-caret");
    if (caret) caret.classList.toggle("rotate-180", expanded);

    var action = toggle.querySelector(".kb-panel-action");
    if (action) action.innerHTML = expanded ? "collapse ↓" : "expand ↑";
  }

  function bindPanel(panel) {
    if (!panel || panel.getAttribute("data-kb-bound") === "true") return;
    var toggle = panel.querySelector("[data-kb-panel-toggle]");
    if (!toggle) return;
    panel.setAttribute("data-kb-bound", "true");

    toggle.addEventListener("click", function () {
      var nowExpanded = panel.getAttribute("data-expanded") !== "true";
      setExpanded(panel, nowExpanded);
    });
  }

  function bindAll(root) {
    var scope = root && root.querySelectorAll ? root : document;
    var panels = scope.querySelectorAll("[data-kb-panel]");
    for (var i = 0; i < panels.length; i++) bindPanel(panels[i]);
  }

  document.addEventListener("DOMContentLoaded", function () {
    bindAll(document);
  });

  // The panel is swapped in by HTMX (lazy load + kb-update SSE). Re-bind the
  // freshly-inserted markup; the marker keeps it idempotent.
  document.body.addEventListener("htmx:afterSwap", function (evt) {
    bindAll(evt.target || document);
  });
})();
