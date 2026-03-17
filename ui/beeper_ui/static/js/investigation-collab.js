/**
 * Investigation collaboration panel — SocketIO client.
 *
 * Connects to Flask-SocketIO for real-time collaboration on active investigations.
 * Coexists with HTMX SSE (which handles step progress, findings, evidence).
 */
(function () {
  "use strict";

  var panel = document.getElementById("collab-panel");
  if (!panel) return;

  var investigationId = panel.dataset.investigationId;
  if (!investigationId) return;

  var messagesDiv = document.getElementById("collab-messages");
  var inputEl = document.getElementById("collab-input");
  var activeUsersEl = document.getElementById("active-users");
  var statusEl = document.getElementById("collab-status");

  // Annotation/redirect input elements
  var annotationArea = document.getElementById("collab-annotation-input");
  var annotationInput = document.getElementById("annotation-text");
  var redirectArea = document.getElementById("collab-redirect-input");
  var redirectInput = document.getElementById("redirect-text");

  // Approve/reject elements
  var approvalBar = document.getElementById("collab-approval-bar");
  var approveBtn = document.getElementById("approve-btn");
  var rejectFixBtn = document.getElementById("reject-fix-btn");
  var approvalContext = document.getElementById("approval-context");
  var rejectArea = document.getElementById("collab-reject-input");
  var rejectReasonInput = document.getElementById("reject-reason-text");

  // Reconnection: track last seen message timestamp
  var storageKey = "collab-last-seen-" + investigationId;
  var lastSeen = sessionStorage.getItem(storageKey) || null;

  // Connect to SocketIO
  var socket = io();

  socket.on("connect", function () {
    if (statusEl) statusEl.textContent = "Connected";
    socket.emit("join_investigation", {
      investigation_id: investigationId,
      last_seen_timestamp: lastSeen,
    });
  });

  socket.on("disconnect", function () {
    if (statusEl) statusEl.textContent = "Reconnecting\u2026";
  });

  // Receive message history on join/reconnect
  socket.on("message_history", function (messages) {
    if (!Array.isArray(messages)) return;
    var pendingProposal = null;
    messages.forEach(function (msg) {
      appendMessage(msg);
      // Track approval bar state from history
      if (msg.message_type === "fix_proposed") {
        pendingProposal = msg;
      } else if (msg.message_type === "fix_applied") {
        pendingProposal = null;
      }
    });
    // Restore approval bar if a fix_proposed is still pending
    if (pendingProposal) {
      showApprovalBar(pendingProposal);
    }
    // Update lastSeen to most recent message so reconnection doesn't re-fetch
    if (messages.length > 0) {
      updateLastSeen(messages[messages.length - 1].timestamp);
    }
    scrollToBottom();
  });

  // Receive new messages in real time
  socket.on("new_message", function (msg) {
    appendMessage(msg);
    updateLastSeen(msg.timestamp);
    scrollToBottom();
  });

  // Receive annotations in real time
  socket.on("annotation_added", function (msg) {
    appendMessage(msg);
    updateLastSeen(msg.timestamp);
    scrollToBottom();
  });

  // Receive redirects in real time
  socket.on("investigation_redirected", function (msg) {
    appendMessage(msg);
    updateLastSeen(msg.timestamp);
    scrollToBottom();
  });

  // Receive fix proposals — show approval bar
  socket.on("fix_proposed", function (msg) {
    appendMessage(msg);
    updateLastSeen(msg.timestamp);
    scrollToBottom();
    showApprovalBar(msg);
  });

  // Receive fix approval confirmation
  socket.on("fix_approved", function (msg) {
    appendMessage(msg);
    updateLastSeen(msg.timestamp);
    scrollToBottom();
    setApproveExecuting();
  });

  // Receive fix rejection confirmation
  socket.on("fix_rejected", function (msg) {
    appendMessage(msg);
    updateLastSeen(msg.timestamp);
    scrollToBottom();
  });

  // Receive fix applied result
  socket.on("fix_applied", function (msg) {
    appendMessage(msg);
    updateLastSeen(msg.timestamp);
    scrollToBottom();
    hideApprovalBar();
  });

  // Receive KB relevance feedback confirmation
  socket.on("kb_feedback_recorded", function (data) {
    updateKBFeedbackUI(data.entry_id, data.is_relevant);
  });

  // User presence updates
  socket.on("user_joined", function (data) {
    updateActiveUsers(data.active_users);
  });

  socket.on("user_left", function (data) {
    updateActiveUsers(data.active_users);
  });

  // Error handling — only reset approve button if it was in executing state
  socket.on("error", function (data) {
    console.error("Collaboration error:", data.message);
    if (approveBtn && approveBtn.classList.contains("collab-approve-executing")) {
      resetApproveButton();
    }
  });

  // Send message
  window.sendCollabMessage = function () {
    if (!inputEl) return;
    var content = inputEl.value.trim();
    if (!content) return;

    socket.emit("send_message", {
      investigation_id: investigationId,
      content: content,
    });
    inputEl.value = "";
  };

  // --- Annotation ---
  window.toggleAnnotationInput = function () {
    if (!annotationArea) return;
    var visible = annotationArea.style.display !== "none";
    annotationArea.style.display = visible ? "none" : "block";
    if (redirectArea) redirectArea.style.display = "none";
    if (rejectArea) rejectArea.style.display = "none";
    if (!visible && annotationInput) annotationInput.focus();
  };

  window.submitAnnotation = function () {
    if (!annotationInput) return;
    var text = annotationInput.value.trim();
    if (!text) return;

    socket.emit("annotate", {
      investigation_id: investigationId,
      text: text,
    });
    annotationInput.value = "";
    if (annotationArea) annotationArea.style.display = "none";
  };

  window.cancelAnnotation = function () {
    if (annotationInput) annotationInput.value = "";
    if (annotationArea) annotationArea.style.display = "none";
  };

  // --- Redirect ---
  window.toggleRedirectInput = function () {
    if (!redirectArea) return;
    var btn = document.getElementById("redirect-btn");
    if (btn && btn.disabled) return;
    var visible = redirectArea.style.display !== "none";
    redirectArea.style.display = visible ? "none" : "block";
    if (annotationArea) annotationArea.style.display = "none";
    if (rejectArea) rejectArea.style.display = "none";
    if (!visible && redirectInput) redirectInput.focus();
  };

  window.submitRedirect = function () {
    if (!redirectInput) return;
    var instruction = redirectInput.value.trim();
    if (!instruction) return;

    socket.emit("redirect", {
      investigation_id: investigationId,
      instruction: instruction,
    });
    redirectInput.value = "";
    if (redirectArea) redirectArea.style.display = "none";
  };

  window.cancelRedirect = function () {
    if (redirectInput) redirectInput.value = "";
    if (redirectArea) redirectArea.style.display = "none";
  };

  // --- Fix Approval ---
  window.submitApprove = function () {
    if (!approveBtn || approveBtn.disabled) return;

    // Optimistic UI: immediately show executing state
    approveBtn.textContent = "Executing\u2026";
    approveBtn.classList.add("collab-approve-executing");
    approveBtn.disabled = true;
    if (rejectFixBtn) rejectFixBtn.disabled = true;

    socket.emit("approve_fix", {
      investigation_id: investigationId,
    });
  };

  // --- Fix Rejection ---
  window.toggleRejectInput = function () {
    if (!rejectArea) return;
    var visible = rejectArea.style.display !== "none";
    rejectArea.style.display = visible ? "none" : "block";
    if (annotationArea) annotationArea.style.display = "none";
    if (redirectArea) redirectArea.style.display = "none";
    if (!visible && rejectReasonInput) rejectReasonInput.focus();
  };

  window.submitReject = function () {
    var reason = rejectReasonInput ? rejectReasonInput.value.trim() : "";

    socket.emit("reject_fix", {
      investigation_id: investigationId,
      reason: reason,
    });
    if (rejectReasonInput) rejectReasonInput.value = "";
    if (rejectArea) rejectArea.style.display = "none";
  };

  window.cancelReject = function () {
    if (rejectReasonInput) rejectReasonInput.value = "";
    if (rejectArea) rejectArea.style.display = "none";
  };

  // --- Approval bar helpers ---
  function showApprovalBar(msg) {
    if (!approvalBar) return;
    approvalBar.style.display = "flex";
    resetApproveButton();

    // Set context text from fix proposal details
    if (approvalContext && msg.content) {
      var contextText = msg.content;
      approvalContext.textContent = contextText;
      approvalContext.title = contextText;
    }
  }

  function hideApprovalBar() {
    if (approvalBar) approvalBar.style.display = "none";
  }

  function setApproveExecuting() {
    if (approveBtn) {
      approveBtn.textContent = "Executing\u2026";
      approveBtn.classList.add("collab-approve-executing");
      approveBtn.disabled = true;
    }
    if (rejectFixBtn) rejectFixBtn.disabled = true;
  }

  function resetApproveButton() {
    if (approveBtn) {
      approveBtn.textContent = "Approve";
      approveBtn.classList.remove("collab-approve-executing");
      approveBtn.disabled = false;
    }
    if (rejectFixBtn) rejectFixBtn.disabled = false;
  }

  // Handle Enter key on main input
  if (inputEl) {
    inputEl.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        window.sendCollabMessage();
      }
    });
  }

  // Handle Enter key on annotation input
  if (annotationInput) {
    annotationInput.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        window.submitAnnotation();
      } else if (e.key === "Escape") {
        window.cancelAnnotation();
      }
    });
  }

  // Handle Enter key on redirect input
  if (redirectInput) {
    redirectInput.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        window.submitRedirect();
      } else if (e.key === "Escape") {
        window.cancelRedirect();
      }
    });
  }

  // Handle Enter key on reject reason input
  if (rejectReasonInput) {
    rejectReasonInput.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        window.submitReject();
      } else if (e.key === "Escape") {
        window.cancelReject();
      }
    });
  }

  // Keyboard shortcuts: n=annotate, r=redirect, a=approve, x=reject (when not focused on an input)
  document.addEventListener("keydown", function (e) {
    var tag = (e.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select") return;

    if (e.key === "n") {
      e.preventDefault();
      window.toggleAnnotationInput();
    } else if (e.key === "r") {
      e.preventDefault();
      window.toggleRedirectInput();
    } else if (e.key === "a") {
      e.preventDefault();
      window.submitApprove();
    } else if (e.key === "x") {
      e.preventDefault();
      window.toggleRejectInput();
    }
  });

  // --- KB Relevance Feedback ---
  window.sendKBFeedback = function (entryId, isRelevant) {
    // Optimistic UI — immediately update button state
    updateKBFeedbackUI(entryId, isRelevant);

    socket.emit("kb_relevance_feedback", {
      investigation_id: investigationId,
      entry_id: entryId,
      is_relevant: isRelevant,
    });
  };

  function updateKBFeedbackUI(entryId, isRelevant) {
    var card = document.querySelector('.kb-surfacing-entry[data-entry-id="' + entryId + '"]');
    if (!card) return;
    var relevantBtn = card.querySelector('.kb-feedback-relevant');
    var notRelevantBtn = card.querySelector('.kb-feedback-not-relevant');
    if (isRelevant) {
      if (relevantBtn) {
        relevantBtn.classList.add("selected-relevant");
        relevantBtn.disabled = true;
      }
      if (notRelevantBtn) {
        notRelevantBtn.classList.remove("selected-not-relevant");
        notRelevantBtn.disabled = true;
      }
    } else {
      if (notRelevantBtn) {
        notRelevantBtn.classList.add("selected-not-relevant");
        notRelevantBtn.disabled = true;
      }
      if (relevantBtn) {
        relevantBtn.classList.remove("selected-relevant");
        relevantBtn.disabled = true;
      }
    }
  }

  function appendMessage(msg) {
    if (!messagesDiv) return;

    var div = document.createElement("div");
    div.className = "collab-message";

    if (msg.message_type === "user_joined" || msg.message_type === "user_left") {
      div.className += " collab-system";
      div.textContent = msg.content;
    } else if (msg.message_type === "annotation") {
      div.className += " collab-annotation";
      appendLabeledMessage(div, "Annotation", "collab-annotation-label", msg);
    } else if (msg.message_type === "redirect") {
      div.className += " collab-redirect";
      appendLabeledMessage(div, "Redirect", "collab-redirect-label", msg);
    } else if (msg.message_type === "fix_proposed") {
      div.className += " collab-fix-proposed";
      appendLabeledMessage(div, "Fix Proposed", "collab-fix-proposed-label", msg);
      if (msg.confidence) {
        var badge = document.createElement("span");
        badge.className = "collab-confidence-badge";
        badge.textContent = msg.confidence + "% confidence";
        div.appendChild(badge);
      }
    } else if (msg.message_type === "fix_approved") {
      div.className += " collab-fix-approved";
      appendLabeledMessage(div, "Approved", "collab-fix-approved-label", msg);
    } else if (msg.message_type === "fix_rejected") {
      div.className += " collab-fix-rejected";
      appendLabeledMessage(div, "Rejected", "collab-fix-rejected-label", msg);
    } else if (msg.message_type === "fix_applied") {
      div.className += " collab-fix-applied";
      appendLabeledMessage(div, "Fix Applied", "collab-fix-applied-label", msg);
    } else if (msg.message_type === "kb_feedback") {
      div.className += " collab-kb-feedback";
      appendLabeledMessage(div, "KB Feedback", "collab-kb-feedback-label", msg);
    } else {
      var header = document.createElement("div");
      header.className = "collab-msg-header";

      var userSpan = document.createElement("span");
      userSpan.className = "collab-msg-user";
      userSpan.textContent = msg.user;

      var timeSpan = document.createElement("span");
      timeSpan.className = "collab-msg-time";
      timeSpan.textContent = formatTime(msg.timestamp);

      header.appendChild(userSpan);
      header.appendChild(timeSpan);

      var body = document.createElement("div");
      body.className = "collab-msg-body";
      body.textContent = msg.content;

      div.appendChild(header);
      div.appendChild(body);
    }

    messagesDiv.appendChild(div);
  }

  function appendLabeledMessage(div, labelText, labelClass, msg) {
    var label = document.createElement("div");
    label.className = "collab-type-label " + labelClass;
    label.textContent = labelText;

    var header = document.createElement("div");
    header.className = "collab-msg-header";

    var userSpan = document.createElement("span");
    userSpan.className = "collab-msg-user";
    userSpan.textContent = msg.user;

    var timeSpan = document.createElement("span");
    timeSpan.className = "collab-msg-time";
    timeSpan.textContent = formatTime(msg.timestamp);

    header.appendChild(userSpan);
    header.appendChild(timeSpan);

    var body = document.createElement("div");
    body.className = "collab-msg-body";
    body.textContent = msg.content;

    div.appendChild(label);
    div.appendChild(header);
    div.appendChild(body);
  }

  function updateLastSeen(timestamp) {
    if (timestamp) {
      lastSeen = timestamp;
      sessionStorage.setItem(storageKey, timestamp);
    }
  }

  function updateActiveUsers(users) {
    if (activeUsersEl && Array.isArray(users)) {
      activeUsersEl.textContent = users.length + " online";
    }
  }

  function scrollToBottom() {
    if (messagesDiv) {
      messagesDiv.scrollTop = messagesDiv.scrollHeight;
    }
  }

  function formatTime(isoStr) {
    if (!isoStr) return "";
    try {
      var d = new Date(isoStr);
      return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    } catch (e) {
      return "";
    }
  }

  // Clean up on page unload
  window.addEventListener("beforeunload", function () {
    socket.emit("leave_investigation", {
      investigation_id: investigationId,
    });
  });
})();
