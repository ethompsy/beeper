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

  // Handle Enter key
  if (inputEl) {
    inputEl.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        window.sendCollabMessage();
      }
    });
  }

  function appendMessage(msg) {
    if (!messagesDiv) return;

    var div = document.createElement("div");
    div.className = "collab-message";

    if (msg.message_type === "user_joined" || msg.message_type === "user_left") {
      div.className += " collab-system";
      div.textContent = msg.content;
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
