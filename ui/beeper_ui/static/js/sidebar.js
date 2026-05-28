/**
 * Beeper Sidebar State Management (Story 3.4 — FR44, AD-6, NFR17)
 *
 * CSS owns the responsive behaviour (the three-state width/label machine lives
 * in components/layout.html + sidebar.html via `group-data-[sidebar-state=…]`
 * utilities). This script is the ONLY JS the sidebar needs — it handles the two
 * user-driven concerns AD-6 reserves for the client:
 *
 *   1. Manual sidebar toggle (hamburger button or the `[` key). Flips the shell
 *      between `expanded` and `collapsed`, writing `sidebar-manual-override` to
 *      sessionStorage. The override is per-page: it is cleared on the next full
 *      navigation (a fresh document load), so each route falls back to its own
 *      {% block sidebar_state %} default (auto for most pages, collapsed for the
 *      investigation-detail view).
 *
 *   2. Per-group open/closed state (Observe / Learn / Manage). Persisted in
 *      sessionStorage keyed by the group label; defaults to all-expanded. Group
 *      state DOES persist across navigations within the tab session.
 *
 * No framework, no HTMX — plain DOM, matching command-palette.js conventions.
 */
(function () {
  "use strict";

  // sessionStorage keys.
  var MANUAL_OVERRIDE_KEY = "sidebar-manual-override";
  var GROUP_KEY_PREFIX = "sidebar-group:";

  // The shell's `lg:` breakpoint (1200px) — keep in sync with input.css
  // --breakpoint-lg so the JS notion of "wide" matches the CSS one.
  var WIDE_QUERY = "(min-width: 1200px)";

  // --- DOM helpers ---
  function getShell() {
    return document.getElementById("app-shell");
  }

  function getToggle() {
    return document.getElementById("sidebar-toggle");
  }

  function currentState() {
    var shell = getShell();
    return shell ? shell.getAttribute("data-sidebar-state") : "auto";
  }

  // Resolve the *effective* expanded/collapsed state, accounting for `auto`
  // (which defers to the viewport width via the same 1200px breakpoint).
  function effectiveExpanded() {
    var state = currentState();
    if (state === "expanded") return true;
    if (state === "collapsed") return false;
    // auto → responsive
    return window.matchMedia(WIDE_QUERY).matches;
  }

  // Keep the hamburger's aria-expanded in sync with the resolved state.
  function syncToggleAria() {
    var toggle = getToggle();
    if (toggle) {
      toggle.setAttribute("aria-expanded", effectiveExpanded() ? "true" : "false");
    }
  }

  // --- Sidebar collapse/expand (AC3) ---
  function toggleSidebar() {
    // Flip relative to whatever is currently shown (resolves `auto` first).
    var next = effectiveExpanded() ? "collapsed" : "expanded";
    var shell = getShell();
    if (shell) {
      shell.setAttribute("data-sidebar-state", next);
    }
    try {
      sessionStorage.setItem(MANUAL_OVERRIDE_KEY, next);
    } catch (e) {
      /* sessionStorage unavailable (private mode quota) — toggle still works */
    }
    syncToggleAria();
  }

  // --- Per-group open/closed (AC4) ---
  function setGroup(groupEl, open) {
    var items = groupEl.querySelector(".sidebar-group-items");
    var header = groupEl.querySelector(".sidebar-group-header");
    var chevron = groupEl.querySelector(".sidebar-group-chevron");
    if (items) items.classList.toggle("hidden", !open);
    groupEl.setAttribute("data-expanded", open ? "true" : "false");
    if (header) header.setAttribute("aria-expanded", open ? "true" : "false");
    // Chevron points down (▾) when open, right (▸ via -rotate-90) when closed.
    if (chevron) chevron.classList.toggle("-rotate-90", !open);
  }

  function toggleGroup(groupEl) {
    var open = groupEl.getAttribute("data-expanded") !== "false";
    var next = !open;
    setGroup(groupEl, next);
    var label = groupEl.getAttribute("data-group");
    if (label) {
      try {
        sessionStorage.setItem(GROUP_KEY_PREFIX + label, next ? "open" : "closed");
      } catch (e) {
        /* persistence is best-effort */
      }
    }
  }

  // --- Init (runs on every full navigation) ---
  function init() {
    // AC3: the manual override is scoped to a single page view. Clearing it on
    // each fresh document load is exactly "cleared on next full navigation" —
    // the server-rendered data-sidebar-state default stays in force.
    try {
      sessionStorage.removeItem(MANUAL_OVERRIDE_KEY);
    } catch (e) {
      /* ignore */
    }
    syncToggleAria();

    var groups = document.querySelectorAll(".sidebar-group");

    // AC4: restore persisted group state (defaults to all-expanded when unset).
    for (var i = 0; i < groups.length; i++) {
      var label = groups[i].getAttribute("data-group");
      var saved = null;
      try {
        saved = label ? sessionStorage.getItem(GROUP_KEY_PREFIX + label) : null;
      } catch (e) {
        saved = null;
      }
      if (saved === "closed") {
        setGroup(groups[i], false);
      }
      // null or "open" → leave as server-rendered (expanded).
    }

    // Wire group-header buttons to toggle their group.
    for (var j = 0; j < groups.length; j++) {
      (function (groupEl) {
        var header = groupEl.querySelector(".sidebar-group-header");
        if (header) {
          header.addEventListener("click", function () {
            toggleGroup(groupEl);
          });
        }
      })(groups[j]);
    }

    // Wire the top-bar hamburger to toggle the whole sidebar.
    var toggle = getToggle();
    if (toggle) {
      toggle.addEventListener("click", toggleSidebar);
    }
  }

  // --- `[` keyboard shortcut (AC3) ---
  document.addEventListener("keydown", function (e) {
    if (e.key !== "[") return;
    if (e.metaKey || e.ctrlKey || e.altKey) return;

    // Don't hijack `[` while the user is typing.
    var tag = (e.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select" || e.target.isContentEditable) {
      return;
    }
    // Defer to the command palette / help overlay when either is open.
    var palette = document.getElementById("command-palette-overlay");
    if (palette && palette.classList.contains("active")) return;
    var help = document.getElementById("keyboard-help-overlay");
    if (help && help.classList.contains("active")) return;

    e.preventDefault();
    toggleSidebar();
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
