"use strict";
const form = document.querySelector("#settings");
let csrf = "";

async function prerequisites() {
  const response = await fetch("/api/status");
  if (!response.ok) throw new Error("status unavailable");
  const status = await response.json();
  document.querySelector("#status").textContent = JSON.stringify(status, null, 2);
}

// The page identity, the form and its values are rendered by the server from
// the declared settings registry. This script only refreshes the live state and
// submits what the owner typed.
function watchResult(response) {
  return response.json().then(result => {
    document.querySelector("#result").textContent = response.ok
      ? "Saved. Reloading to show the stored values." : result.error;
  });
}

if (form) {
  // Only what the owner actually changed is sent. Submitting the whole form
  // would store every declared default explicitly and make the file lie about
  // what is customized.
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
    if (!Object.keys(patch).length) {
      document.querySelector("#result").textContent = "Nothing changed; nothing written.";
      return;
    }
    try {
      const response = await fetch("/api/settings", {method: "POST",
        headers: {"Content-Type": "application/json", "X-Oneiro-CSRF": csrf},
        body: JSON.stringify(patch)});
      const message = await watchResult(response);
      if (response.ok) setTimeout(() => location.reload(), 400);
      else return message;
    } catch (_) {
      document.querySelector("#result").textContent = "Server unavailable. No successful save confirmed.";
    }
  });
}

fetch("/api/session").then(r => r.json()).then(session => { csrf = session.csrf; })
  .then(prerequisites)
  .catch(() => { document.querySelector("#status").textContent = "Server unavailable. No readiness confirmed."; });

// Curated memory on the settings page. Every write is checked by the server
// against the budget and the revision the owner read; a stale view is refused,
// never silently overwritten. Text is set with textContent only.
const factsBox = document.querySelector("#facts");
if (factsBox) {
  const list = document.querySelector("#facts-list");
  const meter = document.querySelector("#facts-meter");
  const errorBox = document.querySelector("#facts-error");
  const addForm = document.querySelector("#fact-add");
  const addField = document.querySelector("#fact-text");
  let pendingAdd = null;
  const say = message => { errorBox.textContent = message || ""; errorBox.hidden = !message; };
  const token = async () => {
    if (!csrf) csrf = (await (await fetch("/api/session")).json()).csrf;
    return csrf;
  };
  const send = async (method, path, body) => {
    const response = await fetch(path, {method,
      headers: {"Content-Type": "application/json", "X-Oneiro-CSRF": await token()},
      body: body === undefined ? undefined : JSON.stringify(body)});
    return {ok: response.ok, result: await response.json()};
  };
  const show = listing => {
    meter.textContent = `${listing.used_chars} of ${listing.limit_chars} characters used`;
    if (!listing.complete || listing.skipped) {
      meter.textContent += ". Stored memory could not be fully read, so changes are refused until it can be.";
    }
    list.replaceChildren();
    for (const fact of listing.facts) {
      const item = document.createElement("li");
      const area = document.createElement("textarea");
      area.rows = 2;
      area.maxLength = 2000;
      area.value = fact.text;
      const save = document.createElement("button");
      save.type = "button";
      save.textContent = "Save";
      save.addEventListener("click", async () => {
        const {ok, result} = await send("POST", `/api/memory/facts/${encodeURIComponent(fact.id)}/edit`,
          {text: area.value, client_id: crypto.randomUUID(), revision: fact.revision});
        if (ok) say(""); else say(result.error);
        await load();
      });
      const remove = document.createElement("button");
      remove.type = "button";
      remove.textContent = "Remove";
      remove.addEventListener("click", async () => {
        const {ok, result} = await send("POST", `/api/memory/facts/${encodeURIComponent(fact.id)}/remove`,
          {client_id: crypto.randomUUID(), revision: fact.revision});
        if (ok) say(""); else say(result.error);
        await load();
      });
      item.append(area, document.createElement("br"), save, document.createTextNode(" "), remove);
      list.append(item);
    }
  };
  const load = async () => {
    try {
      const response = await fetch("/api/memory/facts");
      const listing = await response.json();
      if (!response.ok) { say(listing.reason || listing.error); return; }
      show(listing);
    } catch (_) {
      say("Server unavailable. The fact list could not be read.");
    }
  };
  addForm.addEventListener("submit", async event => {
    event.preventDefault();
    const text = addField.value.trim();
    if (!text) return;
    // A retry of the same text reuses its client_id, so it cannot be stored twice.
    if (!pendingAdd || pendingAdd.text !== text) pendingAdd = {text, clientId: crypto.randomUUID()};
    try {
      const {ok, result} = await send("POST", "/api/memory/facts", {text, client_id: pendingAdd.clientId});
      if (!ok) { say(result.error); return; }
      pendingAdd = null;
      addField.value = "";
      say("");
      await load();
    } catch (_) {
      say("Server unavailable. The fact is not confirmed; saving it again keeps it to one copy.");
    }
  });
  load();
}

// Chat: one owner message per submit. Retrying the same text reuses its client_id,
// so the server publishes the message and its reply at most once even if the
// first response was lost. Text is written with textContent only, never HTML.
const chat = document.querySelector("#chat");
if (chat) {
  const field = document.querySelector("#message");
  const transcript = document.querySelector("#transcript");
  const errorBox = document.querySelector("#chat-error");
  let pending = null;
  const show = (who, text) => {
    const item = document.createElement("li");
    const label = document.createElement("strong");
    label.textContent = who + ": ";
    item.append(label, document.createTextNode(text));
    transcript.append(item);
  };
  const fail = message => { errorBox.textContent = message; errorBox.hidden = false; };
  // Conversations: the server keeps every one; the page only chooses which to show.
  let conversation = "main";
  const select = document.querySelector("#conversation-select");
  const searchNote = document.querySelector("#search-note");
  const results = document.querySelector("#search-results");
  const csrfToken = async () => {
    if (!csrf) csrf = (await (await fetch("/api/session")).json()).csrf;
    return csrf;
  };
  const refreshConversations = async () => {
    const response = await fetch("/api/conversations");
    const listing = await response.json();
    if (!response.ok) { fail(listing.reason || listing.error); return; }
    const options = listing.conversations.map(item => [item.conversation_id, item.title || "Untitled conversation"]);
    if (!options.some(([id]) => id === conversation)) options.unshift([conversation, "New conversation"]);
    select.replaceChildren();
    for (const [id, label] of options) {
      const option = document.createElement("option");
      option.value = id;
      option.textContent = label;
      select.append(option);
    }
    select.value = conversation;
  };
  const openConversation = async id => {
    conversation = id;
    pending = null;
    transcript.replaceChildren();
    errorBox.hidden = true;
    const response = await fetch(`/api/conversations/${encodeURIComponent(id)}/messages`);
    const listing = await response.json();
    if (!response.ok) { fail(listing.reason || listing.error); return; }
    for (const message of listing.messages) show(message.role === "owner" ? "You" : "Oneiro", message.text);
    if (!listing.complete) {
      const note = document.createElement("li");
      note.className = "muted";
      note.textContent = `Only the newest ${listing.messages.length} messages are shown.`;
      transcript.prepend(note);
    }
    await refreshConversations();
  };
  select.addEventListener("change", () => openConversation(select.value));
  document.querySelector("#new-conversation").addEventListener("click", async () => {
    const response = await fetch("/api/conversations", {method: "POST", headers: {"X-Oneiro-CSRF": await csrfToken()}});
    const created = await response.json();
    if (response.ok) openConversation(created.conversation_id);
  });
  document.querySelector("#search").addEventListener("submit", async event => {
    event.preventDefault();
    const query = document.querySelector("#search-text").value.trim();
    if (!query) return;
    const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
    const found = await response.json();
    results.replaceChildren();
    if (!response.ok) { searchNote.textContent = found.error; return; }
    // The note states what was searched. It only says "no match" for a complete read.
    searchNote.textContent = found.note;
    for (const hit of found.results) {
      const item = document.createElement("li");
      const text = document.createElement("span");
      text.textContent = (hit.role === "owner" ? "You: " : "Oneiro: ") + hit.snippet;
      const open = document.createElement("button");
      open.type = "button";
      open.textContent = "Open";
      open.addEventListener("click", () => openConversation(hit.conversation_id));
      item.append(text, document.createTextNode(" "), open);
      results.append(item);
    }
  });
  openConversation(conversation);
  chat.addEventListener("submit", async event => {
    event.preventDefault();
    errorBox.hidden = true;
    const text = field.value.trim();
    if (!text) return;
    if (!pending || pending.text !== text) pending = {text, clientId: crypto.randomUUID()};
    try {
      if (!csrf) csrf = (await (await fetch("/api/session")).json()).csrf;
      const response = await fetch("/api/message", {method: "POST",
        headers: {"Content-Type": "application/json", "X-Oneiro-CSRF": csrf},
        body: JSON.stringify({text: pending.text, client_id: pending.clientId, conversation_id: conversation})});
      const result = await response.json();
      if (!response.ok) {
        fail(result.error || "The message was not answered.");
        return;
      }
      show("You", result.user.text);
      show("Oneiro", result.reply.text);
      // Said plainly when the reply was made with less than the owner's memory.
      if (result.context && result.context.status !== "complete") {
        const note = document.createElement("li");
        note.className = "muted";
        note.textContent = "Context: " + result.context.notes.join(" ");
        transcript.append(note);
      }
      pending = null;
      field.value = "";
    } catch (_) {
      fail("Server unavailable. Your message is not confirmed; sending it again keeps it to one copy.");
    }
  });
}
