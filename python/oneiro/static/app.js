"use strict";

// Every sentence on screen comes from the page's i18n block (`#i18n`, rendered by
// `oneiro/pages.py` from `oneiro/i18n.py`). This file holds markup and behaviour only:
// a literal sentence here could only ever be one language.
const i18nBlock = document.getElementById("i18n");
const T = i18nBlock ? JSON.parse(i18nBlock.textContent) : {};

const form = document.querySelector("#settings");
let csrf = "";

// A reason arrives as a code plus data, never as a sentence: the sentence is the
// catalog's, so it is written in the language of the page. A code the catalog does not
// know is printed as it came, which is visible and testable rather than silently
// English (the readiness panel used to print the backend's own English sentences).
function sayReason(item) {
  const code = typeof item === "string" ? item : String((item && item.code) || "");
  const text = T[code];
  if (!text) return code;
  const data = (item && typeof item === "object" && item.data) || {};
  return Object.keys(data).reduce(
    (said, key) => said.split("{" + key + "}").join(String(data[key])), text);
}

// The state of the machine, said in plain human sentences (never raw JSON blobs).
function statusLines(status) {
  const lines = [status.ready ? T["status.ready"] : T["status.not_ready"]];
  if (status.phase) lines.push(T["status.phase"].replace("{phase}", status.phase));
  const memory = status.memory || {};
  if (memory.verified) lines.push(T["status.memory_ok"]);
  else if (memory.tcp_reachable) lines.push(T["status.memory_readback"]);
  else lines.push(T["status.memory_unreachable"]);
  const model = status.model || {};
  if (model.verified) lines.push(model.used_tools ? T["status.model_ok_tools"] : T["status.model_ok"]);
  else if (model.reason_code) lines.push(sayReason(model.reason_code));
  else lines.push(T["status.model_unverified"]);
  const blocked = status.blocked || [];
  if (blocked.length) lines.push(T["status.blocked_title"], ...blocked.map(item => `  - ${sayReason(item)}`));
  return lines.join("\n");
}

async function prerequisites() {
  const statusEl = document.querySelector("#status");
  if (!statusEl) return;
  try {
    const response = await fetch("/api/status");
    if (!response.ok) throw new Error("status-unavailable");
    const status = await response.json();
    statusEl.textContent = statusLines(status);
  } catch (_) {
    statusEl.textContent = T["status.unavailable"];
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
  details += `<strong>${escapeHtml(T["action.tool"])}: ${escapeHtml(step.tool || T["action.unnamed"])}</strong> — `;
  details += `<span>${isOk ? escapeHtml(T["action.executed"]) : escapeHtml(step.reason || T["action.refused"])}</span>`;
  if (step.arguments && Object.keys(step.arguments).length) {
    details += `<div><small>${escapeHtml(T["action.args"])}: ${escapeHtml(JSON.stringify(step.arguments))}</small></div>`;
  }
  if (step.result) {
    const resText = typeof step.result === "string" ? step.result : JSON.stringify(step.result);
    details += `<div><small>${escapeHtml(T["action.result"])}: ${escapeHtml(resText.slice(0, 300))}</small></div>`;
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
        <h4>${escapeHtml(T["inspector.heading"])}</h4>
        <p><strong>${escapeHtml(T["inspector.role"])}:</strong> ${escapeHtml(item.role)}</p>
        <p><strong>${escapeHtml(T["inspector.text"])}:</strong> ${escapeHtml(item.text)}</p>
        <p><strong>${escapeHtml(T["inspector.steps"])}:</strong> ${item.steps ? item.steps.length : 0}</p>
        <p><strong>${escapeHtml(T["inspector.attachments"])}:</strong> ${item.attachments ? item.attachments.length : 0}</p>
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
      console.error("attachment-upload-failed", e);
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
          errEl.textContent = err.error || T["chat.turn_refused"];
        }
      }
    } catch (e) {
      if (errEl) {
        errEl.hidden = false;
        errEl.textContent = T["chat.server_failure"];
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
          taskList.innerHTML = `<p class='muted'>${escapeHtml(T["tasks.none"])}</p>`;
        } else {
          taskList.innerHTML = tasks.map(t => `
            <div class="card-item">
              <div><strong>${escapeHtml(t.title)}</strong> <span class="pill">${escapeHtml(t.state)}</span></div>
              <small class="muted">${escapeHtml(T["inspector.role"])}: ${escapeHtml(t.assigned_role || "executor")}</small>
            </div>
          `).join("");
        }
      }
    } catch (_) {
      taskList.innerHTML = `<p class='bad'>${escapeHtml(T["tasks.load_failed"])}</p>`;
    }
  }

  if (schedList) {
    try {
      const res = await fetch("/api/schedules");
      if (res.ok) {
        const data = await res.json();
        const schedules = data.schedules || [];
        if (!schedules.length) {
          schedList.innerHTML = `<p class='muted'>${escapeHtml(T["schedules.none"])}</p>`;
        } else {
          schedList.innerHTML = schedules.map(s => {
            const state = s.enabled ? T["tasks.active"] : T["tasks.disabled"];
            return `
            <div class="card-item">
              <div><strong>${escapeHtml(s.task_title || s.title || "")}</strong> <code>${escapeHtml(s.cron || "")}</code></div>
              <small class="muted">${escapeHtml(T["tasks.status_label"].replace("{state}", state))}</small>
            </div>
          `;
          }).join("");
        }
      }
    } catch (_) {
      schedList.innerHTML = `<p class='bad'>${escapeHtml(T["schedules.load_failed"])}</p>`;
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
  const mcpSources = document.querySelector("#mcp-sources-list");
  const skillsContainer = document.querySelector("#skills-list");

  // The servers in *our* list: what Oneiro itself has been told to open.
  function renderMcp() {
    if (!mcpContainer) return;
    fetch("/api/mcp").then(r => r.json()).then(data => {
      const servers = data.servers || [];
      if (!servers.length) {
        mcpContainer.innerHTML = `<p class='muted'>${escapeHtml(T["mcp.none"])}</p>`;
      } else {
        mcpContainer.innerHTML = servers.map(s => `
          <div class="card-item">
            <div><strong>${escapeHtml(s.name)}</strong> (${escapeHtml(s.type || "local")}) <span class="pill">${escapeHtml(s.enabled ? T["mcp.enabled"] : T["mcp.disabled"])}</span></div>
            <small class="muted">${escapeHtml(s.command || s.url || "")}</small>
          </div>
        `).join("");
      }
    }).catch(() => { mcpContainer.innerHTML = `<p class='muted'>${escapeHtml(T["mcp.offline"])}</p>`; });
  }

  // The servers another harness already declares on this machine, each with the file it
  // was found in and a button that copies exactly that one into our list. Adopting reads
  // the other client's file and writes ours; nothing is written into theirs. A file that
  // could not be read is listed too, because a config silently missing from the screen is
  // how a person concludes it was not found — the reason itself is the command line's
  // (`oneiro mcp sources`), which keeps backend prose off a translated page.
  function renderMcpSources() {
    if (!mcpSources) return;
    fetch("/api/mcp").then(r => r.json()).then(data => {
      const reports = data.sources || [];
      const rows = reports.flatMap(report => (report.servers || []).map(server => ({
        ...server, client: report.client, file: report.path })));
      const unreadable = reports.filter(report => report.error);
      const html = rows.map(row => `
          <div class="card-item">
            <div><strong>${escapeHtml(row.name)}</strong> (${escapeHtml(row.kind || "local")})</div>
            <small class="muted">${escapeHtml(T["mcp.declared_in"])} ${escapeHtml(row.client)}: ${escapeHtml(row.file)}</small>
            <button type="button" class="mcp-adopt" data-name="${escapeHtml(row.name)}">${escapeHtml(T["mcp.adopt"])}</button>
          </div>
        `).join("") + unreadable.map(report => `
          <div class="card-item">
            <div><strong>${escapeHtml(report.client)}</strong></div>
            <small class="muted">${escapeHtml(report.path)} — ${escapeHtml(T["mcp.unreadable"])}</small>
          </div>
        `).join("");
      if (!html) {
        mcpSources.innerHTML = `<p class='muted'>${escapeHtml(T["mcp.sources_none"])}</p>`;
        return;
      }
      mcpSources.innerHTML = html;
      mcpSources.querySelectorAll("button.mcp-adopt").forEach(button => {
        button.addEventListener("click", async () => {
          const token = await getToken();
          try {
            const response = await fetch("/api/mcp/import", {
              method: "POST",
              headers: { "Content-Type": "application/json", "X-Oneiro-CSRF": token },
              body: JSON.stringify({ write: true, only: [button.dataset.name] })
            });
            const body = await response.json().catch(() => ({}));
            button.textContent = response.ok ? T["mcp.adopted"] : T["mcp.adopt_failed"];
            button.disabled = true;
            if (response.ok) renderMcp();
            else if (body.error) button.title = String(body.error);
          } catch (_) {
            button.textContent = T["mcp.adopt_failed"];
            button.disabled = true;
          }
        });
      });
    }).catch(() => { mcpSources.innerHTML = `<p class='muted'>${escapeHtml(T["mcp.offline"])}</p>`; });
  }

  renderMcp();
  renderMcpSources();

  if (skillsContainer) {
    fetch("/api/skills").then(r => r.json()).then(data => {
      const skills = data.skills || [];
      if (!skills.length) {
        skillsContainer.innerHTML = `<p class='muted'>${escapeHtml(T["skills.none"])}</p>`;
      } else {
        skillsContainer.innerHTML = skills.slice(0, 30).map(sk => `
          <div class="card-item">
            <div><strong>${escapeHtml(sk.name)}</strong></div>
            <small class="muted">${escapeHtml(sk.purpose || "")}</small>
          </div>
        `).join("");
      }
    }).catch(() => { skillsContainer.innerHTML = `<p class='muted'>${escapeHtml(T["skills.offline"])}</p>`; });
  }
}

// -------------------------------------------------------------
// 4. Drafts: the owner's press is the only way anything leaves
// -------------------------------------------------------------
const draftList = document.querySelector("#draft-list");
const draftSettled = document.querySelector("#draft-settled");
const draftMeter = document.querySelector("#draft-meter");

// Which argument a revision field edits. The arguments belong to the tool, so this is
// only the order the names a text field usually takes; a call with none of them keeps
// its own shape and says so instead of offering a field that would rewrite the wrong key.
const TEXT_KEYS = ["body", "text", "message", "content"];

function textKeyOf(arguments_) {
  const shape = arguments_ || {};
  return TEXT_KEYS.find(key => typeof shape[key] === "string") || "";
}

function stateText(state) {
  const key = "draft.state." + String(state || "");
  return T[key] || String(state || "");
}

function effectText(effect) {
  const outcome = String((effect || {}).outcome || "none");
  const key = "draft.effect." + outcome;
  return T[key] || outcome;
}

// A named refusal arrives as a code, so its sentence is the catalog's. With no code at
// all the read itself did not finish — the 503 routes answer that way, with an English
// sentence this translated page must not print — so the catalog's own sentence for an
// unanswered graph is shown. A code the catalog does not know is printed inside that
// sentence rather than bare: visible, and never silently English.
function refusalText(answer) {
  const code = String((answer && answer.reason) || "");
  if (!code) return T["draft.refused.unreachable"];
  return T["draft.refused." + code]
    || T["draft.action_failed"].replace("{reason}", code);
}

// The exact call, one field at a time. The text is shown as text: the owner is deciding
// whether *those bytes* may leave, so a summary would be a different decision.
function argumentRows(arguments_) {
  const shape = arguments_ || {};
  const textKey = textKeyOf(shape);
  return Object.keys(shape).map(key => {
    const value = escapeHtml(String(shape[key]));
    return key === textKey
      ? `<div class="draft-argument"><small>${escapeHtml(key)}</small><pre>${value}</pre></div>`
      : `<div class="draft-argument"><small>${escapeHtml(key)}</small><span>${value}</span></div>`;
  }).join("");
}

async function draftAction(id, path, body) {
  const token = await getToken();
  const response = await fetch("/api/drafts/" + encodeURIComponent(id) + path, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Oneiro-CSRF": token },
    body: JSON.stringify(body),
  });
  const answer = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(refusalText(answer));
  return answer;
}

function draftSendNote(answer) {
  if (!answer || typeof answer !== "object") return "draft.send_unknown";
  if (answer.state === "uncertain" || answer.effect === "uncertain") return "draft.send_uncertain";
  if (answer.recorded === false) return "draft.send_unrecorded";
  if (answer.ok === false) return "draft.send_failed";
  return answer.ok === true && answer.state === "completed"
    && answer.effect === "succeeded" && answer.recorded === true
    ? "draft.sent" : "draft.send_unknown";
}

function draftCard(item) {
  const id = String(item.id || "");
  const shape = item.arguments || {};
  const textKey = textKeyOf(shape);
  const recipient = String(item.target || shape.to || "");
  const card = document.createElement("div");
  card.className = "card-item draft-card";
  card.dataset.draft = id;
  card.innerHTML = [
    `<div class="draft-head"><strong>${escapeHtml(String(item.tool || ""))}</strong>`,
    `<span class="pill">${escapeHtml(stateText(item.state))}</span></div>`,
    recipient
      ? `<p class="muted">${escapeHtml(T["draft.target"])}: ${escapeHtml(recipient)}</p>`
      : "",
    `<div class="draft-call"><small>${escapeHtml(T["draft.call_title"])}</small>`,
    argumentRows(shape),
    "</div>",
    `<div class="draft-actions">`,
    `<button type="button" class="btn-primary draft-send">${escapeHtml(T["btn.send_draft"])}</button>`,
    `<button type="button" class="btn-subtle draft-discard">${escapeHtml(T["btn.discard_draft"])}</button>`,
    "</div>",
    textKey
      ? `<form class="draft-revise">`
        + `<label for="revise-${escapeHtml(id)}">${escapeHtml(T["draft.revision_label"])}</label>`
        + `<textarea id="revise-${escapeHtml(id)}" name="revision" rows="4">`
        + `${escapeHtml(String(shape[textKey]))}</textarea>`
        + `<button type="submit" class="btn-subtle">${escapeHtml(T["btn.save_revision"])}</button></form>`
      : `<p class="muted">${escapeHtml(T["draft.text_missing"])}</p>`,
    `<p class="bad draft-error" hidden></p>`,
  ].join("");

  const error = card.querySelector(".draft-error");
  // A refusal is shown on the card that caused it and nothing is reloaded: the owner
  // must be able to read why, with the call still in front of them.
  function refused(why) {
    error.hidden = false;
    error.className = "bad draft-error";
    error.textContent = why;
  }
  // A decision that landed is read back from the store: the list is fetched again, and
  // the sentence about what happened goes to the meter, which is the page's own status.
  async function run(path, body, noteKey) {
    try {
      const answer = await draftAction(id, path, body);
      const resultKey = path === "/send" ? draftSendNote(answer) : noteKey;
      const refreshed = await loadDrafts();
      // A failed refresh must remain visible. A warning about the send itself is
      // retained as well; neither a 200 nor a stale list proves a saved success.
      if (draftMeter) {
        draftMeter.textContent = refreshed ? T[resultKey]
          : [T["draft.load_failed"], resultKey === "draft.sent" ? "" : T[resultKey]]
            .filter(Boolean).join("\n");
      }
    } catch (refusal) {
      refused(refusal.message);
    }
  }

  card.querySelector(".draft-send").addEventListener("click", () => {
    run("/send", {}, "draft.sent");
  });
  card.querySelector(".draft-discard").addEventListener("click", () => {
    run("/discard", { reason: "" }, "draft.discarded");
  });
  const revision = card.querySelector(".draft-revise");
  if (revision) {
    revision.addEventListener("submit", event => {
      event.preventDefault();
      // The revision replaces the whole call: same arguments, the edited text.
      run("/revise", { arguments: Object.assign({}, shape, { [textKey]: revision.elements.revision.value }) },
          "draft.revised");
    });
  }
  return card;
}

// A draft that is already decided is shown, not offered: its call, its state, and what is
// known about the effect. Nothing here writes.
function settledCard(item) {
  const recipient = String(item.target || "");
  const card = document.createElement("div");
  card.className = "card-item draft-card settled";
  card.dataset.draft = String(item.id || "");
  card.innerHTML = [
    `<div class="draft-head"><strong>${escapeHtml(String(item.tool || ""))}</strong>`,
    `<span class="pill">${escapeHtml(stateText(item.state))}</span></div>`,
    recipient
      ? `<p class="muted">${escapeHtml(T["draft.target"])}: ${escapeHtml(recipient)}</p>`
      : "",
    `<small class="muted">${escapeHtml(effectText(item.effect))}</small>`,
  ].join("");
  return card;
}

async function loadDrafts() {
  if (!draftList && !draftSettled) return;
  try {
    const response = await fetch("/api/drafts");
    if (!response.ok) throw new Error("drafts-unavailable");
    const listing = await response.json();
    const waiting = listing.drafts || [];
    const settled = listing.settled || [];
    if (draftMeter) {
      draftMeter.textContent = T["draft.meter"].replace("{n}", String(listing.waiting || 0));
    }
    if (draftList) {
      draftList.innerHTML = waiting.length
        ? "" : `<p class='muted'>${escapeHtml(T["draft.none_waiting"])}</p>`;
      waiting.forEach(item => draftList.appendChild(draftCard(item)));
    }
    if (draftSettled) {
      draftSettled.innerHTML = settled.length
        ? "" : `<p class='muted'>${escapeHtml(T["draft.none_settled"])}</p>`;
      settled.forEach(item => draftSettled.appendChild(settledCard(item)));
    }
    return true;
  } catch (_) {
    if (draftMeter) draftMeter.textContent = T["draft.load_failed"];
    return false;
  }
}

// -------------------------------------------------------------
// 5. Settings Form Submission
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
      if (resEl) resEl.textContent = T["settings.client.nothing_changed"];
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
        if (resEl) resEl.textContent = T["settings.client.saved"];
        // The address may carry an older ?lang=; a plain reload would keep it and the
        // page would stay in the language the owner just changed away from.
        const language = patch["ui.language"];
        setTimeout(() => {
          if (language) {
            location.href = location.pathname + "?lang=" + encodeURIComponent(language);
          } else {
            location.reload();
          }
        }, 400);
      } else {
        const why = (result.reasons || []).join("\n");
        if (resEl) resEl.textContent = [result.error, why].filter(Boolean).join("\n");
      }
    } catch (_) {
      if (resEl) resEl.textContent = T["settings.client.unavailable"];
    }
  });
}

// -------------------------------------------------------------
// 4. Curated Memory Screen
// -------------------------------------------------------------
const factsList = document.querySelector("#facts-list");
const factsMeter = document.querySelector("#facts-meter");
const factsError = document.querySelector("#facts-error");
const factForm = document.querySelector("#fact-add");
const factField = document.querySelector("#fact-text");

// A stored stamp is ISO with an offset. It is shown cut to the minute rather than
// reformatted by the browser's own locale: the page already has a language, and a
// stamp read through the browser's would differ from the one in the record.
function stampText(stamp) {
  return String(stamp || "").slice(0, 16).replace("T", " ");
}

function sourceText(provenance) {
  const value = String(provenance || "");
  return T["facts.source." + value] || value;
}

// A fact with what it replaced. The earlier value is not decoration: it is what the
// current one contradicts, so it is shown with its own date and source instead of
// disappearing when the fact is edited.
function factCard(fact) {
  const earlier = Array.isArray(fact.superseded) ? fact.superseded : [];
  const card = document.createElement("li");
  card.className = "card-item fact-card";
  card.dataset.fact = String(fact.id || "");
  card.innerHTML = [
    `<div class="fact-text">${escapeHtml(String(fact.text || ""))}</div>`,
    `<small class="muted fact-meta">${escapeHtml(T["facts.source"])}: `
      + `${escapeHtml(sourceText(fact.provenance))}`
      + ` · ${escapeHtml(T["facts.recorded"])}: ${escapeHtml(stampText(fact.created_at))}`
      + ` · ${escapeHtml(T["facts.updated"])}: ${escapeHtml(stampText(fact.updated_at))}</small>`,
    earlier.length
      ? `<div class="fact-earlier"><small class="muted">${escapeHtml(T["facts.earlier"])}`
        + ` — ${escapeHtml(T["facts.earlier_note"])}</small>`
        + earlier.map(older => `<div class="fact-older">`
          + `<span class="fact-older-text">${escapeHtml(String(older.text || ""))}</span>`
          + `<small class="muted">${escapeHtml(T["facts.source"])}: `
          + `${escapeHtml(sourceText(older.provenance))}`
          + ` · ${escapeHtml(T["facts.updated"])}: `
          + `${escapeHtml(stampText(older.updated_at))}</small></div>`).join("")
        + `</div>`
      : "",
  ].join("");
  return card;
}

async function loadFacts() {
  if (!factsList) return false;
  try {
    const response = await fetch("/api/memory/facts");
    if (!response.ok) throw new Error("facts-unavailable");
    const listing = await response.json();
    const facts = listing.facts || [];
    if (factsMeter) {
      factsMeter.textContent = T["facts.meter"]
        .replace("{n}", String(listing.used_chars || 0))
        .replace("{limit}", String(listing.limit_chars || 0))
        + (listing.history_complete === false ? " — " + T["facts.history_partial"] : "");
    }
    factsList.innerHTML = facts.length ? "" : `<li class='muted'>${escapeHtml(T["facts.empty"])}</li>`;
    facts.forEach(fact => factsList.appendChild(factCard(fact)));
    return true;
  } catch (_) {
    if (factsMeter) factsMeter.textContent = T["facts.load_failed"];
    return false;
  }
}

if (factForm) {
  factForm.addEventListener("submit", async event => {
    event.preventDefault();
    if (factsError) {
      factsError.hidden = true;
      factsError.textContent = "";
    }
    const text = factField ? factField.value.trim() : "";
    if (!text) return;
    try {
      const token = await getToken();
      const response = await fetch("/api/memory/facts", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Oneiro-CSRF": token },
        body: JSON.stringify({
          text: text,
          client_id: "web-" + Math.random().toString(36).substring(2, 10),
        }),
      });
      const answer = await response.json().catch(() => ({}));
      if (!response.ok) {
        // The refusal is the store's own sentence — the budget, the text, the read that
        // did not finish — shown as it came rather than replaced by a friendlier one.
        const why = String(answer.error || "");
        if (factsError) {
          factsError.hidden = false;
          factsError.textContent = T["facts.add_failed"].replace("{reason}", why);
        }
        return;
      }
      if (factField) factField.value = "";
      const refreshed = await loadFacts();
      if (factsMeter && refreshed) {
        factsMeter.textContent = answer.duplicate ? T["facts.duplicate"] : T["facts.added"];
      }
    } catch (_) {
      if (factsError) {
        factsError.hidden = false;
        factsError.textContent = T["facts.add_failed"].replace("{reason}", T["facts.unreachable"]);
      }
    }
  });
}

// Initializations
getToken().then(prerequisites).then(loadTasksAndSchedules).then(loadDrafts)
  .then(loadFacts).then(setupTabs);
