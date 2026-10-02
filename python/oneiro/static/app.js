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
