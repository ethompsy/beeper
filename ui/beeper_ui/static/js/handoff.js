/**
 * Shift Handoff Summary — clipboard copy + SBAR section toggle.
 */

/* Copy handoff summary to clipboard as readable text */
function copyHandoff() {
    var container = document.getElementById("handoff-content");
    var jsonUrl = container ? container.getAttribute("data-handoff-json") : "/handoff/json";

    fetch(jsonUrl)
        .then(function (res) { return res.json(); })
        .then(function (data) {
            var text = formatHandoffText(data);
            return navigator.clipboard.writeText(text).then(function () {
                showCopyToast();
            });
        })
        .catch(function () {
            /* Fallback: copy visible text */
            var el = document.getElementById("handoff-content");
            if (el) {
                return navigator.clipboard.writeText(el.innerText).then(function () {
                    showCopyToast();
                });
            }
        })
        .catch(function () {
            /* Clipboard API unavailable (HTTP or permission denied) */
            showCopyError();
        });
}

/* Format JSON summary as human-readable SBAR text */
function formatHandoffText(data) {
    var lines = ["=== Shift Handoff Summary ===", "Generated: " + data.generated_at, ""];

    if (data.is_all_clear) {
        lines.push("ALL CLEAR — No active investigations or recent incidents.");
        if (data.slo_status && data.slo_status.length) {
            lines.push("", "SLO Overview:");
            data.slo_status.forEach(function (s) {
                lines.push("  - " + s.name + ": " + s.condition);
            });
        }
        return lines.join("\n");
    }

    /* Situation */
    lines.push("[S] SITUATION");
    if (data.active_investigations && data.active_investigations.length) {
        lines.push(data.active_investigations.length + " active investigation(s):");
        data.active_investigations.forEach(function (inv) {
            lines.push("  - " + inv.id + " (" + inv.service + ") — " + inv.severity + ", " + inv.status);
        });
    } else {
        lines.push("  No active investigations.");
    }
    lines.push("");

    /* Background */
    lines.push("[B] BACKGROUND");
    if (data.resolved_incidents && data.resolved_incidents.length) {
        lines.push(data.resolved_incidents.length + " incident(s) resolved (past 8h):");
        data.resolved_incidents.forEach(function (inc) {
            lines.push("  - " + inc.id + " (" + inc.service + ") — resolved " + inc.completed_at);
        });
    } else {
        lines.push("  No recently resolved incidents.");
    }
    lines.push("");

    /* Assessment */
    lines.push("[A] ASSESSMENT");
    if (data.slo_status && data.slo_status.length) {
        data.slo_status.forEach(function (s) {
            lines.push("  - " + s.name + ": " + s.condition);
        });
    } else {
        lines.push("  No SLO data available.");
    }
    lines.push("");

    /* Recommendation */
    lines.push("[R] RECOMMENDATION");
    if (data.items_to_watch && data.items_to_watch.length) {
        data.items_to_watch.forEach(function (item) {
            lines.push("  - [" + item.type + "] " + item.description);
        });
    } else {
        lines.push("  No items requiring immediate attention.");
    }

    return lines.join("\n");
}

/* Brief toast confirmation */
function showCopyToast() {
    var toast = document.getElementById("copy-toast");
    if (!toast) return;
    toast.style.display = "block";
    toast.style.opacity = "1";
    setTimeout(function () {
        toast.style.opacity = "0";
        setTimeout(function () { toast.style.display = "none"; }, 300);
    }, 2000);
}

/* Error toast when clipboard is unavailable */
function showCopyError() {
    var toast = document.getElementById("copy-toast");
    if (!toast) return;
    toast.textContent = "Copy failed — use HTTPS or check permissions";
    toast.style.display = "block";
    toast.style.opacity = "1";
    setTimeout(function () {
        toast.style.opacity = "0";
        setTimeout(function () {
            toast.style.display = "none";
            toast.textContent = "Copied!";
        }, 300);
    }, 3000);
}

/* Toggle SBAR section visibility */
function toggleSbar(header) {
    header.classList.toggle("collapsed");
}
