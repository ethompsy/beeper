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
    messages.forEach(function (msg) {
      appendMessage(msg);
    });
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

  // User presence updates
  socket.on("user_joined", function (data) {
    updateActiveUsers(data.active_users);
  });

  socket.on("user_left", function (data) {
    updateActiveUsers(data.active_users);
  });

  // Error handling
  socket.on("error", function (data) {
    console.error("Collaboration error:", data.message);
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

  // Keyboard shortcuts: n=annotate, r=redirect (when not focused on an input)
  document.addEventListener("keydown", function (e) {
    var tag = (e.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select") return;

    if (e.key === "n") {
      e.preventDefault();
      window.toggleAnnotationInput();
    } else if (e.key === "r") {
      e.preventDefault();
      window.toggleRedirectInput();
    }
  });

  function appendMessage(msg) {
    if (!messagesDiv) return;

    var div = document.createElement("div");
    div.className = "collab-message";

    if (msg.message_type === "user_joined" || msg.message_type === "user_left") {
      div.className += " collab-system";
      div.textContent = msg.content;
    } else if (msg.message_type === "annotation") {
      div.className += " collab-annotation";

      var label = document.createElement("div");
      label.className = "collab-type-label collab-annotation-label";
      label.textContent = "Annotation";

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
    } else if (msg.message_type === "redirect") {
      div.className += " collab-redirect";

      var label = document.createElement("div");
      label.className = "collab-type-label collab-redirect-label";
      label.textContent = "Redirect";

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
