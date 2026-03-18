/**
 * Beeper Command Palette & Keyboard Shortcuts
 *
 * Provides Cmd+K/Ctrl+K command palette with substring filtering,
 * chord keyboard shortcuts (g+i, g+s, etc.), and a help overlay.
 */
(function () {
  "use strict";

  // --- Command Registry ---
  var COMMANDS = [
    // Navigation targets
    {
      label: "Investigations",
      href: "/investigations/",
      category: "navigation",
      keywords: ["inv", "incidents", "anomaly"],
      shortcut: "g i",
    },
    {
      label: "Knowledge Base",
      href: "/knowledge/",
      category: "navigation",
      keywords: ["kb", "wiki", "docs", "knowledge"],
      shortcut: "g k",
    },
    {
      label: "Sources",
      href: "/sources/",
      category: "navigation",
      keywords: ["source", "data", "prometheus", "loki"],
    },
    {
      label: "Health",
      href: "/health/",
      category: "navigation",
      keywords: ["health", "status"],
      shortcut: "g h",
    },
    {
      label: "Metrics",
      href: "/metrics/",
      category: "navigation",
      keywords: ["metric", "dashboard", "chart"],
      shortcut: "g m",
    },
    {
      label: "Spending",
      href: "/spending/",
      category: "navigation",
      keywords: ["spend", "cost", "budget", "llm"],
    },
    {
      label: "Cost Insights",
      href: "/spending/costs",
      category: "navigation",
      keywords: ["cost", "insight", "spending"],
    },
    {
      label: "SLO Dashboard",
      href: "/slo/",
      category: "navigation",
      keywords: ["slo", "objective", "burn", "error budget"],
      shortcut: "g s",
    },
    {
      label: "Services Health",
      href: "/services/",
      category: "navigation",
      keywords: ["service", "health", "feed", "reliability"],
      shortcut: "g v",
    },
    {
      label: "Topology",
      href: "/topology/",
      category: "navigation",
      keywords: ["topology", "service", "dependency", "map"],
      shortcut: "g t",
    },
    {
      label: "Notifications",
      href: "/notifications/",
      category: "navigation",
      keywords: ["notification", "alert", "slack", "pagerduty"],
      shortcut: "g n",
    },
    {
      label: "Handoff",
      href: "/handoff/",
      category: "navigation",
      keywords: ["handoff", "shift", "handover"],
    },
    {
      label: "Trust Settings",
      href: "/settings/trust/",
      category: "navigation",
      keywords: ["trust", "settings", "config", "level"],
    },
    {
      label: "Reports",
      href: "/reports/",
      category: "navigation",
      keywords: ["report", "executive", "investor"],
    },
    // Action commands
    {
      label: "Request Handoff",
      href: "/handoff/",
      category: "action",
      keywords: ["handoff", "shift", "transfer"],
    },
    {
      label: "View SLO Dashboard",
      href: "/slo/",
      category: "action",
      keywords: ["slo", "dashboard", "compliance"],
    },
    {
      label: "View Topology Map",
      href: "/topology/",
      category: "action",
      keywords: ["topology", "service", "map"],
    },
    {
      label: "Keyboard Shortcuts Help",
      action: "show-help",
      category: "action",
      keywords: ["help", "shortcut", "keyboard", "keys"],
      shortcut: "?",
    },
  ];

  // --- State ---
  var selectedIndex = 0;
  var filteredItems = [];
  var previousFocus = null;
  var pendingKey = null;
  var pendingTimer = null;
  var paletteOpen = false;

  // --- Chord Shortcuts ---
  var CHORD_SHORTCUTS = {
    i: "/investigations/",
    s: "/slo/",
    k: "/knowledge/",
    n: "/notifications/",
    t: "/topology/",
    h: "/health/",
    m: "/metrics/",
    v: "/services/",
  };

  // --- DOM Helpers ---
  function getOverlay() {
    return document.getElementById("command-palette-overlay");
  }

  function getInput() {
    return document.getElementById("command-search");
  }

  function getResultsList() {
    return document.getElementById("command-results");
  }

  function getHelpOverlay() {
    return document.getElementById("keyboard-help-overlay");
  }

  // --- Palette Open/Close ---
  function openPalette() {
    var overlay = getOverlay();
    if (!overlay) return;
    previousFocus = document.activeElement;
    overlay.classList.add("active");
    paletteOpen = true;
    var input = getInput();
    if (input) {
      input.value = "";
      input.setAttribute("aria-expanded", "true");
      input.focus();
    }
    selectedIndex = 0;
    filterAndRender("");
  }

  function closePalette() {
    var overlay = getOverlay();
    if (!overlay) return;
    overlay.classList.remove("active");
    paletteOpen = false;
    var input = getInput();
    if (input) {
      input.setAttribute("aria-expanded", "false");
    }
    if (previousFocus && previousFocus.focus) {
      previousFocus.focus();
    }
    previousFocus = null;
  }

  // --- Filter & Render ---
  function filterCommands(query) {
    var q = (query || "").toLowerCase().trim();
    if (!q) return COMMANDS.slice();
    return COMMANDS.filter(function (cmd) {
      if (cmd.label.toLowerCase().indexOf(q) !== -1) return true;
      for (var i = 0; i < cmd.keywords.length; i++) {
        if (cmd.keywords[i].toLowerCase().indexOf(q) !== -1) return true;
      }
      return false;
    });
  }

  function groupByCategory(items) {
    var groups = {};
    var order = ["action", "navigation"];
    for (var i = 0; i < items.length; i++) {
      var cat = items[i].category || "other";
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push(items[i]);
    }
    var result = [];
    for (var o = 0; o < order.length; o++) {
      if (groups[order[o]]) {
        result.push({ category: order[o], items: groups[order[o]] });
      }
    }
    return result;
  }

  function renderResults(items) {
    var list = getResultsList();
    if (!list) return;
    list.innerHTML = "";
    filteredItems = items;

    var groups = groupByCategory(items);
    var globalIdx = 0;

    for (var g = 0; g < groups.length; g++) {
      var group = groups[g];
      // Group header
      var header = document.createElement("li");
      header.setAttribute("role", "presentation");
      header.className = "command-result-group";
      header.textContent =
        group.category.charAt(0).toUpperCase() + group.category.slice(1);
      list.appendChild(header);

      for (var i = 0; i < group.items.length; i++) {
        var item = group.items[i];
        var li = document.createElement("li");
        li.setAttribute("role", "option");
        li.setAttribute("id", "cmd-" + globalIdx);
        li.className = "command-result-item";
        if (globalIdx === selectedIndex) {
          li.setAttribute("aria-selected", "true");
        }

        var labelSpan = document.createElement("span");
        labelSpan.className = "command-result-label";
        labelSpan.textContent = item.label;
        li.appendChild(labelSpan);

        if (item.shortcut) {
          var badge = document.createElement("span");
          badge.className = "command-shortcut-badge";
          badge.textContent = item.shortcut;
          li.appendChild(badge);
        }

        li.dataset.index = globalIdx;
        li.addEventListener("click", function (e) {
          var idx = parseInt(this.dataset.index, 10);
          executeItem(filteredItems[idx]);
        });

        list.appendChild(li);
        globalIdx++;
      }
    }

    // Update aria-activedescendant
    var input = getInput();
    if (input && filteredItems.length > 0) {
      input.setAttribute("aria-activedescendant", "cmd-" + selectedIndex);
    } else if (input) {
      input.removeAttribute("aria-activedescendant");
    }
  }

  function filterAndRender(query) {
    var items = filterCommands(query);
    selectedIndex = 0;
    renderResults(items);
  }

  // --- Execute Command ---
  function executeItem(item) {
    if (!item) return;
    closePalette();
    if (item.action === "show-help") {
      toggleHelp();
    } else if (item.href) {
      window.location.href = item.href;
    }
  }

  // --- Selection Navigation ---
  function moveSelection(delta) {
    if (filteredItems.length === 0) return;
    var prev = document.getElementById("cmd-" + selectedIndex);
    if (prev) prev.removeAttribute("aria-selected");

    selectedIndex =
      (selectedIndex + delta + filteredItems.length) % filteredItems.length;

    var next = document.getElementById("cmd-" + selectedIndex);
    if (next) {
      next.setAttribute("aria-selected", "true");
      next.scrollIntoView({ block: "nearest" });
    }

    var input = getInput();
    if (input) {
      input.setAttribute("aria-activedescendant", "cmd-" + selectedIndex);
    }
  }

  // --- Help Overlay ---
  function toggleHelp() {
    var help = getHelpOverlay();
    if (!help) return;
    if (help.classList.contains("active")) {
      help.classList.remove("active");
    } else {
      help.classList.add("active");
    }
  }

  function closeHelp() {
    var help = getHelpOverlay();
    if (help) help.classList.remove("active");
  }

  // --- Event Handlers ---

  // Global keydown handler
  document.addEventListener("keydown", function (e) {
    var tag = (e.target.tagName || "").toLowerCase();
    var isInput = tag === "input" || tag === "textarea" || tag === "select";

    // Cmd+K / Ctrl+K: always open palette (even from inputs)
    if ((e.metaKey || e.ctrlKey) && e.key === "k") {
      e.preventDefault();
      if (paletteOpen) {
        closePalette();
      } else {
        openPalette();
      }
      return;
    }

    // If palette is open, handle palette-specific keys
    if (paletteOpen) {
      if (e.key === "Escape") {
        e.preventDefault();
        closePalette();
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        moveSelection(1);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        moveSelection(-1);
        return;
      }
      if (e.key === "Enter") {
        e.preventDefault();
        executeItem(filteredItems[selectedIndex]);
        return;
      }
      // Let typing flow through to the input
      return;
    }

    // If help overlay is open
    var help = getHelpOverlay();
    if (help && help.classList.contains("active")) {
      if (e.key === "Escape") {
        e.preventDefault();
        closeHelp();
        return;
      }
    }

    // Skip shortcuts when focused on inputs
    if (isInput) return;

    // ? for help overlay
    if (e.key === "?") {
      e.preventDefault();
      toggleHelp();
      return;
    }

    // Chord shortcuts: g + second key
    if (pendingKey === "g") {
      clearTimeout(pendingTimer);
      pendingKey = null;
      var target = CHORD_SHORTCUTS[e.key];
      if (target) {
        e.preventDefault();
        window.location.href = target;
        return;
      }
      // Unrecognized second key — ignore
      return;
    }

    if (e.key === "g") {
      e.preventDefault();
      pendingKey = "g";
      pendingTimer = setTimeout(function () {
        pendingKey = null;
      }, 500);
      return;
    }
  });

  // Search input handler
  document.addEventListener("DOMContentLoaded", function () {
    var input = getInput();
    if (input) {
      input.addEventListener("input", function () {
        filterAndRender(this.value);
      });
    }

    // Click outside to close palette
    var overlay = getOverlay();
    if (overlay) {
      overlay.addEventListener("click", function (e) {
        if (e.target === overlay) {
          closePalette();
        }
      });
    }

    // Click outside to close help
    var helpOverlay = getHelpOverlay();
    if (helpOverlay) {
      helpOverlay.addEventListener("click", function (e) {
        if (e.target === helpOverlay) {
          closeHelp();
        }
      });
    }

    // Close button for help overlay
    var helpCloseBtn = document.getElementById("keyboard-help-close-btn");
    if (helpCloseBtn) {
      helpCloseBtn.addEventListener("click", function () {
        closeHelp();
      });
    }
  });
})();
