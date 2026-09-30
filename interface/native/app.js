/* Native Oneiro workspace client. No frameworks, no external origins. */
"use strict";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const state = { csrf: "", conversation: "owner", replyTo: "" };

const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

async function api(path, body) {
  const options = body === undefined ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Oneiro-CSRF": state.csrf },
    body: JSON.stringify(body),
  };
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}

function showError(error) {
  const box = $("#error");
  box.textContent = error instanceof Error ? error.message : String(error);
  box.hidden = false;
  clearTimeout(showError.timer);
  showError.timer = setTimeout(() => { box.hidden = true; }, 12000);
}

function toast(text) {
  const box = $("#toast");
  box.textContent = text;
  box.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { box.hidden = true; }, 4000);
}

/* --------------------------------------------------------------- views */

const titles = { conversation: "Conversation", activity: "Living work",
  memory: "Shared memory", settings: "Personalities & rules" };

$$(".nav").forEach((button) => button.addEventListener("click", () => {
  $$(".nav").forEach((b) => b.classList.toggle("active", b === button));
  const view = button.dataset.view;
  $("#view-title").textContent = titles[view];
  $$(".view").forEach((section) => { section.hidden = section.id !== view; });
  refresh();
}));

/* --------------------------------------------------------------- render */

function renderMessages(rows) {
  const list = $("#messages");
  const sorted = [...rows].sort((a, b) => a.at - b.at);
  $("#intro").hidden = sorted.length > 0;
  list.innerHTML = sorted.map((row) => `
    <article class="message ${row.side}">
      <div class="message-meta">${row.side === "owner" ? "You" : "Oneiro"} · ${esc(row.channel || "native")}
        ${row.reply_to ? `<span class="muted">· replying</span>` : ""}
        ${row.status && row.status !== "completed" ? `<span class="pill">${esc(row.status)}</span>` : ""}</div>
      <div class="message-body">${esc(row.text)}</div>
      <button class="link-button" data-reply="${esc(row.id)}">Reply</button>
    </article>`).join("");
  $$("[data-reply]", list).forEach((button) => button.addEventListener("click", () => {
    state.replyTo = button.dataset.reply;
    const context = $("#reply-context");
    context.hidden = false;
    context.textContent = `Replying to: ${button.closest("article").querySelector(".message-body").textContent.slice(0, 80)}`;
    $("#message").focus();
  }));
  list.scrollTop = list.scrollHeight;
}

function renderApprovals(rows) {
  $("#approvals").innerHTML = rows.filter((row) => row.status === "pending").map((row) => `
    <div class="approval" role="group" aria-label="Pending action">
      <span class="eyebrow">AWAITING YOUR BUTTON</span>
      <h3>${esc(row.tool)} — nothing has run yet</h3>
      <p>${esc(row.reason)}</p>
      <pre>${esc(JSON.stringify(row.args, null, 2))}</pre>
      <div class="approval-actions">
        <button class="primary" data-decision="${esc(row.id)}" data-approved="true">Approve exact action</button>
        <button class="danger" data-decision="${esc(row.id)}" data-approved="false">Reject</button>
      </div>
    </div>`).join("");
  $$("[data-decision]").forEach((button) => button.addEventListener("click", async () => {
    try {
      await api("/api/decision", { id: button.dataset.decision, approved: button.dataset.approved === "true" });
      toast("Decision recorded");
      refresh();
    } catch (error) { showError(error); }
  }));
}

function renderQuestions(rows) {
  $("#questions").innerHTML = rows.filter((row) => row.status === "open").map((row) => `
    <div class="approval">
      <span class="eyebrow">ONEIRO ASKS</span>
      <h3>${esc(row.question)}</h3>
      <div class="approval-actions">
        <input id="answer-${esc(row.id)}" placeholder="Your words close the question — only a button approves actions">
        <button class="primary" data-answer="${esc(row.id)}">Answer</button>
      </div>
    </div>`).join("");
  $$("[data-answer]").forEach((button) => button.addEventListener("click", async () => {
    try {
      await api("/api/answer", { id: button.dataset.answer, text: $(`#answer-${button.dataset.answer}`).value });
      toast("Answer recorded");
      refresh();
    } catch (error) { showError(error); }
  }));
}

function renderActivity(tasks) {
  $("#task-count").textContent = tasks.filter((task) => ["queued", "running"].includes(task.status)).length;
  $("#activity-list").innerHTML = tasks.length ? tasks.map((task) => `
    <div class="task ${task.status}">
      <div class="task-head"><span class="pill">${esc(task.role)}</span><span class="pill">${esc(task.status)}</span>
        ${task.initiative ? `<span class="pill">self-started</span>` : ""}</div>
      <h3>${esc(task.text.slice(0, 140))}</h3>
      ${task.result ? `<p class="muted">${esc(task.result.slice(0, 400))}</p>` : ""}
      ${["failed", "interrupted", "budget_exhausted"].includes(task.status)
        ? `<button class="link-button" data-retry="${esc(task.id)}">Inspect and retry</button>` : ""}
    </div>`).join("") : `<p class="muted">No independent work right now. Conversation alone is a complete interaction.</p>`;
  $$("[data-retry]").forEach((button) => button.addEventListener("click", async () => {
    try {
      await api("/api/retry", { kind: "task", id: button.dataset.retry });
      toast("Task queued again");
      refresh();
    } catch (error) { showError(error); }
  }));
  const interests = JSON.parse(sessionStorage.getItem("interests") || "[]");
  $("#interest-list").innerHTML = interests.length ? interests.map((row) => `
    <div class="task"><div class="task-head"><span class="pill">${esc(row.role)}</span></div>
      <h3>${esc(row.topic)}</h3><p class="muted">${esc(row.reason)}</p></div>`).join("")
    : `<p class="muted">Interests appear when an agent notices an unfinished thread. Independent exploration is opt-in.</p>`;
}

function renderNotes(notes, query) {
  const needle = (query || "").toLowerCase();
  const rows = notes.filter((note) => !needle || JSON.stringify(note.data).toLowerCase().includes(needle));
  $("#note-list").innerHTML = rows.slice(-60).reverse().map((note) => `
    <div class="note"><span class="pill">${esc(note.actor)}</span>
      <p>${esc(note.data.text || "")}</p>
      ${(note.data.sources || []).length ? `<span class="muted">sources: ${esc(note.data.sources.join(", "))}</span>` : ""}</div>`).join("")
    || `<p class="muted">No notes match.</p>`;
}

function renderSettings(settings, souls) {
  const fields = { permission_mode: "permission_mode", workspace: "setting-workspace",
    sandbox_image: "sandbox_image", initiative_interval: "initiative_interval",
    max_calls: "max_calls", quiet_start: "quiet_start", quiet_end: "quiet_end",
    manager_model: "manager_model", researcher_model: "researcher_model", executor_model: "executor_model" };
  for (const [key, id] of Object.entries(fields)) {
    const element = document.getElementById(id);
    if (element && document.activeElement !== element) element.value = settings[key];
  }
  for (const key of ["internet_enabled", "initiative_enabled", "interest_exploration",
                     "remote_llm_context", "virustotal_uploads"]) {
    const element = document.getElementById(key);
    if (element && document.activeElement !== element) element.checked = Boolean(settings[key]);
  }
  const role = $("#soul-role").value;
  const soul = $("#soul-text");
  if (document.activeElement !== soul) soul.value = souls[role] || "";
  $("#life-status").textContent = settings.initiative_enabled ? "Initiative on" : "Initiative off";
}

/* --------------------------------------------------------------- state */

async function refresh() {
  try {
    const data = await api("/api/state");
    sessionStorage.setItem("interests", JSON.stringify(data.interests));
    renderMessages(data.messages);
    renderApprovals(data.approvals);
    renderQuestions(data.questions);
    renderActivity(data.tasks);
    renderNotes(data.notes, $("#memory-search")?.value);
    renderSettings(data.settings, data.souls);
    $("#memory-status").textContent = `◈ ${data.memory}`;
    if (data.diagnostics) showError(data.diagnostics);
  } catch (error) {
    showError(error);
  }
}

/* --------------------------------------------------------------- forms */

$("#chat-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = $("#message");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  const replyTo = state.replyTo;
  state.replyTo = "";
  $("#reply-context").hidden = true;
  try {
    await api("/api/message", { text, reply_to: replyTo });
    refresh();
  } catch (error) { showError(error); }
});

$$("[data-starter]").forEach((button) => button.addEventListener("click", () => {
  $("#message").value = button.dataset.starter;
  $("#message").focus();
}));

$("#memory-search").addEventListener("input", () => refresh());

$("#settings-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await api("/api/settings", {
      permission_mode: $("#permission_mode").value,
      workspace: $("#setting-workspace").value,
      internet_enabled: $("#internet_enabled").checked,
      initiative_enabled: $("#initiative_enabled").checked,
      interest_exploration: $("#interest_exploration").checked,
      remote_llm_context: $("#remote_llm_context").checked,
      virustotal_uploads: $("#virustotal_uploads").checked,
      initiative_interval: Number($("#initiative_interval").value),
      max_calls: Number($("#max_calls").value),
      quiet_start: Number($("#quiet_start").value),
      quiet_end: Number($("#quiet_end").value),
      sandbox_image: $("#sandbox_image").value,
      manager_model: $("#manager_model").value,
      researcher_model: $("#researcher_model").value,
      executor_model: $("#executor_model").value,
    });
    toast("Rules saved");
    refresh();
  } catch (error) { showError(error); }
});

$("#soul-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await api("/api/soul", { role: $("#soul-role").value, text: $("#soul-text").value });
    toast("Personality saved");
    refresh();
  } catch (error) { showError(error); }
});

$("#soul-role").addEventListener("change", () => refresh());

/* --------------------------------------------------------------- login */

async function start() {
  const session = await api("/api/session");
  if (session.authenticated) {
    state.csrf = session.csrf;
    $("#login").hidden = true;
    $("#workspace").hidden = false;
    refresh();
    setInterval(refresh, 4000);
    return;
  }
  if (!session.token_required) $("#token").placeholder = "Local access — just press Enter";
}

$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const answer = await api("/api/login", { token: $("#token").value });
    state.csrf = answer.csrf;
    $("#login").hidden = true;
    $("#workspace").hidden = false;
    refresh();
    setInterval(refresh, 4000);
  } catch (error) { showError(error); }
});

start().catch(showError);
