"use strict";
const form = document.querySelector("#settings");
let csrf = "";
async function load() {
  const [session, settings, status] = await Promise.all([
    fetch("/api/session").then(r => r.json()),
    fetch("/api/settings").then(r => r.json()),
    fetch("/api/status").then(r => r.json())
  ]);
  csrf = session.csrf;
  for (const row of settings.settings) {
    const input = form.elements.namedItem(row.key);
    if (input && !row.secret) input.value = row.value;
  }
  document.querySelector("#status").textContent = JSON.stringify(status, null, 2);
  document.querySelector("#availability").textContent = status.ready ? "Ready" : "Assistant not ready — see prerequisites below.";
  document.querySelector("#title").textContent = location.pathname.startsWith("/oneiro") ? "Graph integration pending" : location.pathname === "/" ? "Conversation integration pending" : "Oneiro settings & setup";
  if (settings.error) document.querySelector("#result").textContent = settings.error;
}
form.addEventListener("submit", async event => {
  event.preventDefault();
  const patch = {};
  for (const [name, value] of new FormData(form)) {
    if (name === "llm.api_key" && !value) continue;
    patch[name] = name === "graph.port" ? Number(value) : value;
  }
  try {
    const response = await fetch("/api/settings", {method: "POST", headers: {"Content-Type": "application/json", "X-Oneiro-CSRF": csrf}, body: JSON.stringify(patch)});
    const result = await response.json();
    document.querySelector("#result").textContent = response.ok ? "Saved. Live integration checks are still required." : result.error;
    if (response.ok) { form.elements.namedItem("llm.api_key").value = ""; await load(); }
  } catch (_) { document.querySelector("#result").textContent = "Server unavailable. No successful save confirmed."; }
});
load().catch(() => { document.querySelector("#availability").textContent = "Server unavailable. No readiness confirmed."; });
