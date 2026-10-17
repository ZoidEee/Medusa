(function () {
  "use strict";

  /* ---------- Globals ---------- */
  const socket = io();

  let currentMode = null;      // "group" | "dm" | null
  let currentGroupId = null;
  let currentDmUserId = null;

  const title           = document.getElementById("chat-title");
  const leaveGroupBtn   = document.getElementById("leave-group-btn");
  const messagesEl      = document.getElementById("messages");
  const form            = document.getElementById("chat-form");
  const input           = document.getElementById("message-input");
  const errorBox        = document.getElementById("error-box");

  const accountButton   = document.getElementById("account-button");
  const accountDropdown = document.getElementById("account-dropdown");

  const searchInput   = document.getElementById("search-input");
  const searchResults = document.getElementById("search-results");

  const groupList   = document.getElementById("group-list");
  const newGroupBtn = document.getElementById("new-group-btn");

  /* ---------- Helpers ---------- */
  function showError(msg) {
    if (!errorBox) return;
    errorBox.textContent = msg;
    errorBox.style.display = "block";
    console.error(msg);
  }
  function clearError() {
    if (!errorBox) return;
    errorBox.textContent = "";
    errorBox.style.display = "none";
  }

  function tempId() {
    return "tmp-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 8);
  }

  function cssEscape(val) {
    if (window.CSS && typeof window.CSS.escape === "function") {
      return window.CSS.escape(String(val));
    }
    return String(val).replace(/["\\]/g, "\\$&");
  }

  function setLeaveButtonVisible(visible) {
    if (!leaveGroupBtn) return;
    leaveGroupBtn.hidden = !visible;
  }

  function makeMessageEl(sender, body, createdAt, opts) {
    opts = opts || {};
    const wrap = document.createElement("div");
    wrap.className = "message"
      + (opts.pending ? " message-pending" : "")
      + (opts.failed ? " message-failed" : "");

    const avatar = document.createElement("div");
    avatar.className = "message-avatar";

    const content = document.createElement("div");
    content.className = "message-content";

    const row = document.createElement("div");

    const author = document.createElement("span");
    author.className = "message-author";
    author.textContent = sender;
    row.appendChild(author);

    if (createdAt) {
      const t = document.createElement("span");
      t.className = "message-time";
      t.textContent = new Date(createdAt).toLocaleTimeString([], {
        hour: "2-digit", minute: "2-digit",
      });
      row.appendChild(t);
    }

    if (opts.pending) {
      const p = document.createElement("span");
      p.className = "message-status";
      p.textContent = "sending…";
      row.appendChild(p);
    } else if (opts.failed) {
      const p = document.createElement("span");
      p.className = "message-status message-status-failed";
      p.textContent = "failed";
      row.appendChild(p);
    }

    const bodyEl = document.createElement("div");
    bodyEl.className = "message-body";
    bodyEl.textContent = body;

    content.appendChild(row);
    content.appendChild(bodyEl);
    wrap.appendChild(avatar);
    wrap.appendChild(content);
    return wrap;
  }

  function addMessage(sender, body, system, createdAt, opts) {
    if (system) {
      const wrap = document.createElement("div");
      wrap.className = "system-message";
      wrap.textContent = sender;
      messagesEl.appendChild(wrap);
    } else {
      messagesEl.appendChild(makeMessageEl(sender, body, createdAt, opts));
    }
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function setActive(el) {
    document.querySelectorAll(".channel-btn").forEach((b) =>
      b.classList.remove("active")
    );
    if (el) el.classList.add("active");
  }

  async function loadJson(url, opts) {
    const res = await fetch(url, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
      ...(opts || {}),
    });
    if (!res.ok) {
      throw new Error(`${res.status} ${res.statusText}`);
    }
    return res.json();
  }

  /* ---------- Room loading ---------- */
  async function openGroup(groupId, buttonEl, groupName) {
    try {
      currentMode = "group";
      currentGroupId = String(groupId);
      currentDmUserId = null;

      setActive(buttonEl);
      clearError();
      messagesEl.innerHTML = "";

      // Title: prefer passed name, then existing button label, then placeholder.
      const resolvedName =
        groupName ||
        (buttonEl && buttonEl.dataset.groupName) ||
        (buttonEl && buttonEl.textContent.replace(/^#\s*/, "").trim()) ||
        "";

      title.textContent = resolvedName ? `# ${resolvedName}` : "Loading group…";
      setLeaveButtonVisible(true);

      if (socket.connected) {
        socket.emit("join_group", { group_id: currentGroupId });
      }

      const data = await loadJson(`/groups/${groupId}`);
      if (!data || !Array.isArray(data.messages)) {
        throw new Error("Invalid group history response.");
      }

      if (!resolvedName) {
        title.textContent = "# Group";
      }

      if (data.messages.length === 0) {
        addMessage("No messages yet. Send the first one!", "", true);
      } else {
        data.messages.forEach((m) =>
          addMessage(m.sender, m.body, false, m.created_at)
        );
      }
    } catch (e) {
      showError(`Could not open group: ${e.message}`);
    }
  }

  async function openDm(userId, buttonEl, username) {
    try {
      currentMode = "dm";
      currentGroupId = null;
      currentDmUserId = String(userId);

      setActive(buttonEl);
      clearError();
      messagesEl.innerHTML = "";

      const resolvedName =
        username ||
        (buttonEl && buttonEl.dataset.username) ||
        (buttonEl && buttonEl.textContent.replace(/^@\s*/, "").trim()) ||
        "";

      title.textContent = resolvedName ? `@ ${resolvedName}` : "Loading direct messages…";
      setLeaveButtonVisible(false);

      if (socket.connected) {
        socket.emit("join_dm", { user_id: currentDmUserId });
      }

      const data = await loadJson(`/dm/${userId}`);
      if (!data || !Array.isArray(data.messages)) {
        throw new Error("Invalid DM history response.");
      }

      if (!resolvedName) {
        title.textContent = "@ Direct message";
      }

      if (data.messages.length === 0) {
        addMessage("No messages yet. Send the first one!", "", true);
      } else {
        data.messages.forEach((m) =>
          addMessage(m.sender, m.body, false, m.created_at)
        );
      }
    } catch (e) {
      showError(`Could not open direct message: ${e.message}`);
    }
  }

  /* ---------- Event delegation for channels ---------- */
  document.addEventListener("click", (event) => {
    const groupBtn = event.target.closest(".group-btn");
    if (groupBtn) {
      openGroup(groupBtn.dataset.groupId, groupBtn, groupBtn.dataset.groupName);
      return;
    }

    const dmBtn = event.target.closest(".dm-btn");
    if (dmBtn) {
      openDm(dmBtn.dataset.userId, dmBtn, dmBtn.dataset.username);
      return;
    }
  });

  /* ---------- Composer ---------- */
  if (form) {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      clearError();

      const body = input.value.trim();
      if (!body) return;

      if (!socket.connected) {
        showError("Not connected to the server.");
        return;
      }

      const id = tempId();

      if (currentMode === "group" && currentGroupId) {
        const el = makeMessageEl("You", body, new Date().toISOString(), { pending: true });
        el.dataset.tempId = id;
        messagesEl.appendChild(el);
        messagesEl.scrollTop = messagesEl.scrollHeight;

        socket.emit("group_message", {
          group_id: currentGroupId,
          body,
          temp_id: id,
        });
      } else if (currentMode === "dm" && currentDmUserId) {
        const el = makeMessageEl("You", body, new Date().toISOString(), { pending: true });
        el.dataset.tempId = id;
        messagesEl.appendChild(el);
        messagesEl.scrollTop = messagesEl.scrollHeight;

        socket.emit("dm_message", {
          recipient_id: currentDmUserId,
          body,
          temp_id: id,
        });
      } else {
        showError("Select a group or direct message first.");
        return;
      }

      input.value = "";
      input.focus();
    });
  }

  /* ---------- Socket events ---------- */
  socket.on("connect", () => {
    clearError();
    if (currentMode === "group" && currentGroupId) {
      openGroup(currentGroupId, null, title.textContent.replace(/^#\s*/, "").trim());
    } else if (currentMode === "dm" && currentDmUserId) {
      openDm(currentDmUserId, null, title.textContent.replace(/^@\s*/, "").trim());
    }
  });

  socket.on("connect_error", (err) => {
    showError(`Socket.IO connection failed: ${err.message}`);
  });

  socket.on("error", (data) => {
    showError((data && data.message) || "Server error.");
  });

  socket.on("group_message", (data) => {
    if (currentMode !== "group" || String(data.group_id) !== String(currentGroupId)) return;

    if (data.temp_id) {
      const existing = messagesEl.querySelector(
        `[data-temp-id="${cssEscape(data.temp_id)}"]`
      );
      if (existing) {
        existing.replaceWith(
          makeMessageEl(data.sender, data.body, data.created_at, {})
        );
        return;
      }
    }
    addMessage(data.sender, data.body, false, data.created_at);
  });

  socket.on("group_message_ack", (data) => {
    if (currentMode !== "group" || String(data.group_id) !== String(currentGroupId)) return;
    const el = messagesEl.querySelector(`[data-temp-id="${cssEscape(data.temp_id)}"]`);
    if (el && el.classList.contains("message-pending")) {
      el.classList.remove("message-pending");
      const status = el.querySelector(".message-status");
      if (status) status.remove();
    }
  });

  socket.on("group_message_failed", (data) => {
    const el = messagesEl.querySelector(`[data-temp-id="${cssEscape(data.temp_id)}"]`);
    if (el) {
      el.classList.remove("message-pending");
      el.classList.add("message-failed");
      const status = el.querySelector(".message-status");
      if (status) {
        status.classList.add("message-status-failed");
        status.textContent = "failed";
      }
    }
    showError((data && data.error) || "Message failed to send.");
  });

  socket.on("dm_message", (data) => {
    if (currentMode !== "dm" || !currentDmUserId) return;

    if (data.temp_id) {
      const existing = messagesEl.querySelector(
        `[data-temp-id="${cssEscape(data.temp_id)}"]`
      );
      if (existing) {
        existing.replaceWith(
          makeMessageEl(data.sender, data.body, data.created_at, {})
        );
        return;
      }
    }

    const relevant =
      String(data.sender_id) === String(currentDmUserId) ||
      String(data.recipient_id) === String(currentDmUserId);
    if (relevant) {
      addMessage(data.sender, data.body, false, data.created_at);
    }
  });

  socket.on("dm_message_ack", (data) => {
    const el = messagesEl.querySelector(`[data-temp-id="${cssEscape(data.temp_id)}"]`);
    if (el && el.classList.contains("message-pending")) {
      el.classList.remove("message-pending");
      const status = el.querySelector(".message-status");
      if (status) status.remove();
    }
  });

  socket.on("dm_message_failed", (data) => {
    const el = messagesEl.querySelector(`[data-temp-id="${cssEscape(data.temp_id)}"]`);
    if (el) {
      el.classList.remove("message-pending");
      el.classList.add("message-failed");
      const status = el.querySelector(".message-status");
      if (status) {
        status.classList.add("message-status-failed");
        status.textContent = "failed";
      }
    }
    showError((data && data.error) || "Message failed to send.");
  });

  socket.on("system", (data) => {
    addMessage(data.message, "", true);
  });

  socket.on("group_left", (data) => {
    const id = String(data.group_id);
    const btn = document.querySelector(
      `.group-btn[data-group-id="${cssEscape(id)}"]`
    );
    if (btn) {
      const li = btn.closest("li");
      if (li) li.remove();
    }
    if (currentMode === "group" && String(currentGroupId) === id) {
      currentMode = null;
      currentGroupId = null;
      messagesEl.innerHTML = "";
      title.textContent = "Select a chat";
      setLeaveButtonVisible(false);
    }
  });

  /* ---------- Leave group ---------- */
  function leaveCurrentGroup() {
    if (currentMode !== "group" || !currentGroupId) return;

    if (!window.confirm("Leave this group? You will stop receiving its messages.")) {
      return;
    }

    const token = document.querySelector("meta[name='csrf-token']")?.content || "";
    const groupId = currentGroupId;

    fetch(`/groups/${groupId}/leave`, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "X-CSRFToken": token,
        "Accept": "application/json",
      },
    })
      .then(async (res) => {
        if (!res.ok) {
          let msg = "Could not leave group.";
          try {
            const data = await res.json();
            if (data.error) msg = data.error;
          } catch (_) {}
          throw new Error(msg);
        }

        const btn = document.querySelector(
          `.group-btn[data-group-id="${cssEscape(groupId)}"]`
        );
        if (btn) {
          const li = btn.closest("li");
          if (li) li.remove();
        }
        currentMode = null;
        currentGroupId = null;
        messagesEl.innerHTML = "";
        title.textContent = "Select a chat";
        setLeaveButtonVisible(false);
      })
      .catch((err) => showError(err.message));
  }

  if (leaveGroupBtn) {
    leaveGroupBtn.addEventListener("click", leaveCurrentGroup);
  }

  /* ---------- Account dropdown ---------- */
  function closeAccountDropdown() {
    if (accountDropdown) accountDropdown.classList.remove("open");
  }

  document.addEventListener("click", (event) => {
    if (accountButton && accountButton.contains(event.target)) {
      event.preventDefault();
      accountDropdown.classList.toggle("open");
      return;
    }
    if (accountDropdown && accountDropdown.contains(event.target)) {
      return;
    }
    closeAccountDropdown();
  });

  /* ---------- Search ---------- */
  let searchTimeout = null;

  function renderSearchResults(results) {
    searchResults.innerHTML = "";

    if (!results.groups.length && !results.users.length) {
      const empty = document.createElement("div");
      empty.className = "search-empty";
      empty.textContent = "No matches";
      searchResults.appendChild(empty);
      return;
    }

    if (results.groups.length) {
      const h = document.createElement("div");
      h.className = "search-heading";
      h.textContent = "Groups";
      searchResults.appendChild(h);

      results.groups.forEach((g) => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "search-result";
        b.textContent = `# ${g.name}`;
        b.addEventListener("click", () => {
          searchResults.innerHTML = "";
          searchInput.value = "";
          const existing = document.querySelector(
            `.group-btn[data-group-id="${cssEscape(g.id)}"]`
          );
          openGroup(g.id, existing, g.name);
        });
        searchResults.appendChild(b);
      });
    }

    if (results.users.length) {
      const h = document.createElement("div");
      h.className = "search-heading";
      h.textContent = "People";
      searchResults.appendChild(h);

      results.users.forEach((u) => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "search-result";
        b.textContent = `@ ${u.username}`;
        b.addEventListener("click", () => {
          searchResults.innerHTML = "";
          searchInput.value = "";
          const existing = document.querySelector(
            `.dm-btn[data-user-id="${cssEscape(u.id)}"]`
          );
          openDm(u.id, existing, u.username);
        });
        searchResults.appendChild(b);
      });
    }
  }

  async function runSearch(q) {
    if (!q) {
      searchResults.innerHTML = "";
      return;
    }
    try {
      const data = await loadJson(`/search?q=${encodeURIComponent(q)}`);
      renderSearchResults(data);
    } catch (e) {
      showError(`Search failed: ${e.message}`);
    }
  }

  if (searchInput && searchResults) {
    searchInput.addEventListener("input", () => {
      clearTimeout(searchTimeout);
      const q = searchInput.value.trim();
      searchTimeout = setTimeout(() => runSearch(q), 250);
    });

    document.addEventListener("click", (event) => {
      if (!searchResults.contains(event.target) &&
          event.target !== searchInput) {
        searchResults.innerHTML = "";
      }
    });
  }

  /* ---------- Create group modal ---------- */
  function openCreateGroupModal() {
    let modal = document.getElementById("create-group-modal");
    if (modal) {
      modal.classList.add("open");
      modal.querySelector("input[name='name']").focus();
      return;
    }

    modal = document.createElement("div");
    modal.id = "create-group-modal";
    modal.className = "modal-backdrop open";
    modal.innerHTML = `
      <div class="modal" role="dialog" aria-modal="true">
        <h3>Create a group</h3>
        <form id="create-group-form">
          <label for="new-group-name">Group name</label>
          <input
            id="new-group-name"
            name="name"
            type="text"
            maxlength="80"
            placeholder="e.g. Project Alpha"
            required
          >
          <div class="modal-error" id="create-group-error"></div>
          <div class="modal-actions">
            <button type="button" class="btn btn-secondary" id="cancel-create-group">
              Cancel
            </button>
            <button type="submit" class="btn">Create</button>
          </div>
        </form>
      </div>
    `;
    document.body.appendChild(modal);

    modal.addEventListener("click", (e) => {
      if (e.target === modal) modal.classList.remove("open");
    });

    const formEl = modal.querySelector("#create-group-form");
    const errEl = modal.querySelector("#create-group-error");

    modal.querySelector("#cancel-create-group").addEventListener("click", () => {
      modal.classList.remove("open");
    });

    formEl.addEventListener("submit", async (e) => {
      e.preventDefault();
      errEl.textContent = "";

      const name = formEl.elements["name"].value.trim();
      if (!name) {
        errEl.textContent = "Group name is required.";
        return;
      }

      try {
        const token = document.querySelector(
          "meta[name='csrf-token']"
        )?.content || "";

        const res = await fetch("/groups", {
          method: "POST",
          credentials: "same-origin",
          headers: {
            "Content-Type": "application/x-www-form-urlencoded",
            "X-CSRFToken": token,
            "Accept": "application/json",
          },
          body: new URLSearchParams({ name }).toString(),
        });

        if (!res.ok) {
          let msg = "Could not create group.";
          try {
            const data = await res.json();
            if (data.error) msg = data.error;
          } catch (_) {}
          throw new Error(msg);
        }

        const data = await res.json();
        modal.classList.remove("open");

        const btn = document.createElement("button");
        btn.className = "channel-btn group-btn";
        btn.type = "button";
        btn.dataset.groupId = data.id;
        btn.dataset.groupName = data.name;
        btn.textContent = `# ${data.name}`;

        const li = document.createElement("li");
        li.appendChild(btn);
        groupList.appendChild(li);

        openGroup(data.id, btn, data.name);
      } catch (err) {
        errEl.textContent = err.message;
      }
    });
  }

  if (newGroupBtn) {
    newGroupBtn.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      openCreateGroupModal();
    });
  }
})();
