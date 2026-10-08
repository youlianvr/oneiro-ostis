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
        body: JSON.stringify({text: pending.text, client_id: pending.clientId})});
      const result = await response.json();
      if (!response.ok) {
        fail(result.error || "The message was not answered.");
        return;
      }
      show("You", result.user.text);
      show("Oneiro", result.reply.text);
      pending = null;
      field.value = "";
    } catch (_) {
      fail("Server unavailable. Your message is not confirmed; sending it again keeps it to one copy.");
    }
  });
}
