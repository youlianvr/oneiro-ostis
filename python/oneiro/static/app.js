"use strict";
const form = document.querySelector("#settings");
let csrf = "";

// The state of the machine, said in plain human sentences (never raw JSON blobs).
function statusLines(status) {
  const lines = [status.ready ? "Ready to work." : "Not ready yet — see below."];
  if (status.phase) lines.push(`Phase: ${status.phase}.`);
  const memory = status.memory || {};
  if (memory.verified) lines.push("Memory (OSTIS) is readable.");
  else if (memory.tcp_reachable) lines.push("Memory (OSTIS) answers, but nothing could be read back out of the graph.");
  else lines.push("Memory (OSTIS) is not reachable. It is required and has no substitute.");
  const model = status.model || {};
  if (model.verified) lines.push("The configured model answered a real call" + (model.used_tools ? ", including a tool call." : "."));
  else lines.push("The model is not verified yet" + (model.reason ? `: ${model.reason}.` : "."));
  const blocked = status.blocked || [];
  if (blocked.length) lines.push("Still blocked:", ...blocked.map(item => `  - ${item}`));
  return lines.join("\n");
}

async function prerequisites() {
  const statusEl = document.querySelector("#status");
  if (!statusEl) return;
  try {
    const response = await fetch("/api/status");
    if (!response.ok) throw new Error("status unavailable");
    const status = await response.json();
    statusEl.textContent = statusLines(status);
  } catch (_) {
    statusEl.textContent = "Server unavailable. No readiness confirmed.";
  }
}

// Token retrieval
async function getToken() {
  if (csrf) return csrf;
  try {
    const res = await (await fetch("/api/session")).json();
    csrf = res.csrf || "";
  } catch (_) {}
  return csrf;
}

// -------------------------------------------------------------
// 1. Conversation & Action Cards (Chat Screen)
// -------------------------------------------------------------
const chatForm = document.querySelector("#chat");
const transcriptList = document.querySelector("#transcript");
const attachBtn = document.querySelector("#btn-attach");
const attachInput = document.querySelector("#attachment-file");
const attachChip = document.querySelector("#attachment-chip");
const inspectorContent = document.querySelector("#inspector-content");
let pendingAttachments = [];

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text || "";
  return div.innerHTML;
}

function renderActionStep(step) {
  const isOk = step.ok !== false;
  const kind = isOk ? "step" : "refusal";
  let details = `<div class="action-card ${kind}">`;
  details += `<strong>Tool: ${escapeHtml(step.tool || "action")}</strong> — `;
  details += `<span>${isOk ? "Executed successfully" : escapeHtml(step.reason || "Refused by policy")}</span>`;
  if (step.arguments && Object.keys(step.arguments).length) {
    details += `<div><small>Args: ${escapeHtml(JSON.stringify(step.arguments))}</small></div>`;
  }
  if (step.result) {
    const resText = typeof step.result === "string" ? step.result : JSON.stringify(step.result);
    details += `<div><small>Result: ${escapeHtml(resText.slice(0, 300))}</small></div>`;
  }
  details += "</div>";
  return details;
}

function renderMessage(item) {
  const li = document.createElement("li");
  li.className = item.role === "user" || item.role === "owner" ? "user" : "assistant";
  
  let body = `<div><strong>${escapeHtml(item.role)}:</strong> ${escapeHtml(item.text || "")}</div>`;
  if (item.steps && item.steps.length) {
    body += `<div class="steps-container">${item.steps.map(renderActionStep).join("")}</div>`;
  }
  li.innerHTML = body;
  li.addEventListener("click", () => {
    if (inspectorContent) {
      inspectorContent.innerHTML = `
        <h4>Message Details</h4>
        <p><strong>Role:</strong> ${escapeHtml(item.role)}</p>
        <p><strong>Text:</strong> ${escapeHtml(item.text)}</p>
        <p><strong>Steps:</strong> ${item.steps ? item.steps.length : 0}</p>
        <p><strong>Attachments:</strong> ${item.attachments ? item.attachments.length : 0}</p>
      `;
    }
  });
  return li;
}

if (attachBtn && attachInput) {
  attachBtn.addEventListener("click", () => attachInput.click());
  attachInput.addEventListener("change", async () => {
    if (!attachInput.files || !attachInput.files.length) return;
    const file = attachInput.files[0];
    const token = await getToken();
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await fetch("/api/attachments", {
        method: "POST",
        headers: { "X-Oneiro-CSRF": token },
        body: formData,
      });
      if (res.ok) {
        const meta = await res.json();
        pendingAttachments.push(meta.id);
        if (attachChip) {
          attachChip.hidden = false;
          attachChip.textContent = `${meta.name} (${meta.size}b)`;
        }
      }
    } catch (e) {
      console.error("Upload error", e);
    }
  });
}

if (chatForm) {
  chatForm.addEventListener("submit", async event => {
    event.preventDefault();
    const input = document.querySelector("#message");
    const text = input ? input.value.trim() : "";
    if (!text && !pendingAttachments.length) return;
    const errEl = document.querySelector("#chat-error");
    if (errEl) errEl.hidden = true;

    const clientId = "web-" + Math.random().toString(36).substring(2, 10);
    const payload = {
      text: text,
      client_id: clientId,
      attachments: [...pendingAttachments]
    };

    // Render user message immediately
    if (transcriptList) {
      transcriptList.appendChild(renderMessage({ role: "owner", text: text }));
      transcriptList.scrollTop = transcriptList.scrollHeight;
    }
    if (input) input.value = "";
    pendingAttachments = [];
    if (attachChip) attachChip.hidden = true;

    try {
      const token = await getToken();
      const res = await fetch("/api/message", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Oneiro-CSRF": token },
        body: JSON.stringify(payload)
      });
      if (res.ok) {
        const replyDoc = await res.json();
        if (transcriptList && replyDoc.reply) {
          transcriptList.appendChild(renderMessage({
            role: replyDoc.reply.role || "assistant",
            text: replyDoc.reply.text,
            steps: replyDoc.steps
          }));
          transcriptList.scrollTop = transcriptList.scrollHeight;
        }
      } else {
        const err = await res.json();
        if (errEl) {
          errEl.hidden = false;
          errEl.textContent = err.error || "Turn refused";
        }
      }
    } catch (e) {
      if (errEl) {
        errEl.hidden = false;
        errEl.textContent = "Server communication failure";
      }
    }
  });
}

// -------------------------------------------------------------
// 2. Tasks & Schedules Screen
// -------------------------------------------------------------
async function loadTasksAndSchedules() {
  const taskList = document.querySelector("#task-list");
  const schedList = document.querySelector("#schedule-list");
  if (!taskList && !schedList) return;

  if (taskList) {
    try {
      const res = await fetch("/api/tasks");
      if (res.ok) {
        const data = await res.json();
        const tasks = data.tasks || [];
        if (!tasks.length) {
          taskList.innerHTML = "<p class='muted'>No active or completed tasks.</p>";
        } else {
          taskList.innerHTML = tasks.map(t => `
            <div class="card-item">
              <div><strong>${escapeHtml(t.title)}</strong> <span class="pill">${escapeHtml(t.state)}</span></div>
              <small class="muted">Role: ${escapeHtml(t.assigned_role || "executor")}</small>
            </div>
          `).join("");
        }
      }
    } catch (_) {
      taskList.innerHTML = "<p class='bad'>Failed to load tasks.</p>";
    }
  }

  if (schedList) {
    try {
      const res = await fetch("/api/schedules");
      if (res.ok) {
        const data = await res.json();
        const schedules = data.schedules || [];
        if (!schedules.length) {
          schedList.innerHTML = "<p class='muted'>No standing schedules configured.</p>";
        } else {
          schedList.innerHTML = schedules.map(s => `
            <div class="card-item">
              <div><strong>${escapeHtml(s.task_title || s.title || "")}</strong> <code>${escapeHtml(s.cron || "")}</code></div>
              <small class="muted">Status: ${s.enabled ? "Active" : "Disabled"}</small>
            </div>
          `).join("");
        }
      }
    } catch (_) {
      schedList.innerHTML = "<p class='bad'>Failed to load schedules.</p>";
    }
  }
}

// -------------------------------------------------------------
// 3. Tools Screen Tabs & Listings
// -------------------------------------------------------------
function setupTabs() {
  const tabs = document.querySelectorAll(".tab-btn");
  tabs.forEach(btn => {
    btn.addEventListener("click", () => {
      tabs.forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
      btn.classList.add("active");
      const target = document.querySelector(`#${btn.dataset.tab}`);
      if (target) target.classList.add("active");
    });
  });

  const mcpContainer = document.querySelector("#mcp-servers-list");
  const skillsContainer = document.querySelector("#skills-list");
  if (mcpContainer) {
    fetch("/api/mcp").then(r => r.json()).then(data => {
      const servers = data.servers || [];
      if (!servers.length) {
        mcpContainer.innerHTML = "<p class='muted'>No MCP servers configured.</p>";
      } else {
        mcpContainer.innerHTML = servers.map(s => `
          <div class="card-item">
            <div><strong>${escapeHtml(s.name)}</strong> (${escapeHtml(s.type || "local")}) <span class="pill">${s.enabled ? "enabled" : "disabled"}</span></div>
            <small class="muted">${escapeHtml(s.command || s.url || "")}</small>
          </div>
        `).join("");
      }
    }).catch(() => { mcpContainer.innerHTML = "<p class='muted'>MCP service offline.</p>"; });
  }

  if (skillsContainer) {
    fetch("/api/skills").then(r => r.json()).then(data => {
      const skills = data.skills || [];
      if (!skills.length) {
        skillsContainer.innerHTML = "<p class='muted'>No skills in catalog.</p>";
      } else {
        skillsContainer.innerHTML = skills.slice(0, 30).map(sk => `
          <div class="card-item">
            <div><strong>${escapeHtml(sk.name)}</strong></div>
            <small class="muted">${escapeHtml(sk.purpose || "")}</small>
          </div>
        `).join("");
      }
    }).catch(() => { skillsContainer.innerHTML = "<p class='muted'>Skills catalog offline.</p>"; });
  }
}

// -------------------------------------------------------------
// 4. Settings Form Submission
// -------------------------------------------------------------
if (form) {
  const asEntered = new Map();
  for (const field of form.elements) {
    if (field.name) asEntered.set(field.name, field.value);
  }
  form.addEventListener("submit", async event => {
    event.preventDefault();
    const patch = {};
    for (const [name, value] of new FormData(form)) {
      const field = form.elements.namedItem(name);
      if (field.disabled || field.value === asEntered.get(name)) continue;
      if (name === "llm.api_key" && !value) continue;
      patch[name] = name.endsWith(".port") ? Number(value) : value;
    }
    const resEl = document.querySelector("#result");
    if (!Object.keys(patch).length) {
      if (resEl) resEl.textContent = "Nothing changed; nothing written.";
      return;
    }
    try {
      const token = await getToken();
      const response = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Oneiro-CSRF": token },
        body: JSON.stringify(patch)
      });
      const result = await response.json();
      if (response.ok) {
        if (resEl) resEl.textContent = "Saved. Reloading to show the stored values.";
        setTimeout(() => location.reload(), 400);
      } else {
        const why = (result.reasons || []).join("\n");
        if (resEl) resEl.textContent = [result.error, why].filter(Boolean).join("\n");
      }
    } catch (_) {
      if (resEl) resEl.textContent = "Server unavailable. No successful save confirmed.";
    }
  });
}

// Initializations
getToken().then(prerequisites).then(loadTasksAndSchedules).then(setupTabs);
