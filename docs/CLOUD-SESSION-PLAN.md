# Cloud Session Plan — Oneiro native rewrite (record from the session export)

Provenance: this is the reconstructed plan and execution log of the cloud
(Daytona/e2b, `/home/daytona/codebase`) session whose transcript was exported to
`export.txt` (1993 lines, 12 timestamp markers, 18:11 → 1:08). The cloud
sandbox filesystem is unreachable from the owner's machine (e2b returns 502),
so the export — and the PR the owner makes from that session — are the only
carriers of this work. This file is the local record to diff the PR against.

The session ran in three moves: **audit** of the whole project, **owner
interrogation** (8 rounds, decisions in `docs/GOAL-NATIVE-ONEIRO.md`), then
the **native rewrite** itself, ending with a full **census** ("полная
перепись") of the project around the native core.

## 1. Audit findings (defects confirmed in the old product plane)

Confirmed by small diagnostic checks, not assumed:

- A standalone clone does not detect itself as the repo root; check commands
  are still bound to the old nested path.
- The owner's free-text answer is **not persisted** into the legacy question
  result, and the executor treats `free_text` as a rejection and closes the
  task. Confirmed by executing the real task reducer with inert imports
  (`CONFIRMED: task reducer treats free_text as an answered job; collect()
  routes it to rejection`).
- The worker's directory limit is an instruction, not an enforced boundary;
  a worktree does not isolate executable tests from the host.
- Three overlay hashes drifted from the current files, which breaks a clean
  reinstall.
- The dashboard panel button **deletes the DB volume**; normal startup
  rebuilds the graph with `--clear` (`REBUILD_KB=1`) — the biography is
  wiped on every start.
- Russian remains in `dashboard/index.html` and
  `console/overlay/channel/web/setup.html` despite the "English everywhere"
  claim in the plan.
- The web chat runs through CowAgent, Telegram turns almost any message into
  a code-change task, and the manager chat exists but is not connected to
  those inputs.

Audit verdict: no total rewrite of everything is needed — one product loop
with clear responsibility boundaries. Keep Python, OSTIS, the useful tests
and the research records. CowAgent stays a shell; ONE manager service serves
web and Telegram; ONE owner of question/task state; tool execution moves
behind a real security boundary; research benches stay separated from the
everyday interface.

## 2. Interrogation decisions (8 rounds)

The binding decisions live in `docs/GOAL-NATIVE-ONEIRO.md` (already on disk
in full). Highlights:

- Priority: a continuously living, proactive personal assistant; both
  technical work and everyday assistance. Research initially, useful product
  eventually.
- No mandatory researcher → manager → executor ceremony on every message.
- Three configurable personalities in individual `SOUL.md` profiles; a
  personality is a behavioural configuration, not a claim of consciousness.
- Manager talks, reads, plans, delegates and arbitrates; does not write code.
  May escalate to the owner, revise the plan (re-read the project, adjust to
  actual information), or insist on execution within the owner's confirmed
  decision.
- Researcher reads anything, researches the web, keeps personal notes and
  shares findings; cannot install programs or modify working projects.
  Executor works within its task and reports objections and unexpected
  consequences. Permanent role boundaries cannot be relaxed by a prompt, a
  SOUL change or the manager's insistence.
- Each role owns its memory and may freely read the other roles' memory.
- Autonomy: independently perform the necessary steps within the agreed area;
  ask on access expansion, external effects or substantially new consequences.
- Proactive behavior is wanted (the owner pointed at the Hermes TG chat as the
  model: sometimes it writes first, not only reacts).
- "Native" = one model of conversation, tasks, memory and actions; web,
  Telegram and MCP are inputs and adapters of the core, not separate agents
  with their own rules. Ready protocols and libraries are fine; a foreign
  agent engine as a second center of control is not.
- Language: English interface, code and documentation; the manager talks to
  the owner in Russian.

## 3. Master plan v1 (on disk: `docs/MASTER-PLAN.md`, 144 lines)

Status board with honest markers (done = code exists and offline tests pass
here; live-blocked = needs real model/graph/keys):

| # | Phase | Status |
|---|-------|--------|
| 0 | Audit, interrogation, decision record | done |
| 1 | Native core: memory, policy, tools, service | done (20 tests) |
| 2 | Channels: native web UI + Telegram adapter | done offline (11 tests), preview runs |
| 3 | Memory safety, launch, diagnostics | done |
| 4 | Live model loop + real tools | live-blocked (keys, Docker) |
| 5 | Initiative and interests | code done, live-blocked |
| 6 | Legacy migration and removal | not started |
| 7 | Polish: media inspection, search, richer task views | not started |

Hard rules for every phase: no claimed success without real tool evidence;
missing keys/infrastructure reported as blockers, never simulated; permanent
role limits live in code (`policy.py`), SOUL.md is style only; the signing
path is one thing — an owner button on one exact saved action; old data and
research results are preserved through migration.

## 4. Master plan v2 (rewritten in the cloud session)

The session rewrote `docs/MASTER-PLAN.md` to the real scale: honest status
markers, phase "retire legacy plane" = **done**, and explicitly named as NOT
done: own install/update (phase 7), search/media/polish (phase 8), live run
(phase 5, blocked by keys). The full text of the rewritten plan arrives with
the PR — it is not in the export (the transcript records the file edit, not
its content).

## 5. Execution log — phase C: native core (already in the local tree)

Local tree = remote v2 tip `240f50398` (feb8435b6 + c0b20edc6). These files
are already on disk:

- `python/native/__init__.py`, `memory.py` — OSTIS is the durable truth
  (`GraphMemory` via the bridge's `record_native_event`/`load_native_events`,
  semantic links for actor/task/approval/note/interest/conversation).
  `TestMemory` is an explicit test double, never a production fallback; no
  silent SQLite/file fallback.
- `python/native/policy.py` — trusted tool metadata (roles, effect class) and
  the effect gate: deny / allow / **ask** (exact approval). Sensitive effects
  (configure, delete, database, sandbox, install, publish, send, upload)
  always require the owner's button. Autostart is unrepresentable as a tool.
- `python/native/tools.py` — read/list/write/configure/delete within a task
  workspace, cross-role memory notes and interests, public-URL fetch (no
  cookies/redirects/private IPs), delegated work, owner questions, reports,
  Docker sandbox (`--network=none`, read-only, capped, preinstalled image
  only — a worktree is not a sandbox), VirusTotal upload + analysis read.
  Credential files are invisible to models.
- `python/native/service.py` — conversation, tasks, questions, approvals, runs
  with checkpoint/resume across restarts, recovery (`executing` effects become
  `uncertain`, never silently re-run), SOUL loading/editing, settings
  validation, role prompts, the LLM/tool loop with per-step call budgets, fair
  scheduling (chat does not queue behind tasks), opt-in initiative with
  interest memory and quiet hours.
- `python/native/web.py` — same-origin sessions, CSRF for writes, local-first
  login (remote binding requires `ONEIRO_WEB_TOKEN`), secrets never echoed.
- `python/native/telegram.py` — owner-only, one poller per bot, offset
  persisted only after persistence of the update, approval buttons release
  exact actions, attachments named as un-inspected, never silently ignored.
- `profiles/{manager,researcher,executor}/SOUL.md` — the three personalities.
- `scripts/oneiro-native.py` — one entrypoint (web + scheduler + optional
  Telegram), `--check` diagnostics that name missing dependencies/keys. A
  proxied port without `ONEIRO_WEB_TOKEN` gets a one-time token printed to
  the run log — a fresh runtime token, never a stored secret.
- `interface/native/{index.html,app.js,style.css}` — the workspace UI
  (conversation, living work, shared memory, personalities & rules); English
  product language, no external fonts/trackers, CSP locked to same-origin.
- `tests/test_native_service.py` (20 tests), `tests/test_native_channels.py`
  (11 tests) — all green.
- `scripts/docker_entrypoint.sh` — `REBUILD_KB` default flipped so a normal
  container start never runs `sc-builder --clear` on an existing graph;
  rebuild happens only on an explicit request (`REBUILD_KB=1` or
  `scripts/reset_stack.sh --yes`).

Sandbox verification at this point: 20/20 native core tests; 243 total tests
pass, the 4 failures are missing sc_client/skills-catalog in the environment,
not the changes.

## 6. Execution log — phase D: own LLM layer (comes with the PR)

The native core still had a seam: it imported legacy `config` and `llm`.

- `python/native/model.py` (created) — own provider layer: bounded retries,
  real 429/5xx/broken-JSON handling, a call budget, model per role with a
  single fallback, honest recording of which upstream answered. (A triple
  `_dotenv` duplication was removed during the work.)
- `python/native/service.py` (edited) — switched onto the model layer; no
  longer imports legacy `config`/`llm`.
- `bench/memory/run.py` (edited) — switched to the model layer.
- `python/config.py` (edited) — loses `dashboard.port` together with the
  panel; `tests/test_config.py` adjusted.
- `python/llm.py` — archived to `legacy/python/llm.py` (nobody in the live
  contour imported it anymore).
- `tests/test_native_model.py` (created, ~17 tests).

Verification: 48/48 native tests green (20 service + 17 model + 11 channels).

## 7. Execution log — phase E: legacy plane archived (comes with the PR)

Everything moved with `git mv` — nothing deleted, an archive, not a trash
can:

- `console/` (CowAgent, 6 MB), `dashboard/`, `plugins/`, `oneiro_proxy.py`
  → `legacy/`
- `python/{life_loop,heartbeat,swarm,worker,roles,task_runner,telegram_entry,
  approval,question_tool,worktree_runner,hermes_plugin,llm}.py` →
  `legacy/python/`
- `scripts/{install.py,oneiro-app.py,oneiro-app.cmd,oneiro-phone.sh,
  tg-rehearsal.py,host-wire.py,wmi-seed}` → `legacy/scripts/`;
  `scripts/mcp-smoke.py` was moved and then **kept** in `scripts/` (it tests
  the graph MCP server, not the console)
- Tests → `legacy/tests/` (the mv loop listed: test_approval,
  test_console_overlay, test_dashboard_state, test_gateway_plugin,
  test_hermes_plugin, test_install_console, test_life_loop, test_oneiro_proxy,
  test_oneiro_setup, test_question_tool, test_roles, test_swarm_protocol,
  test_task_runner, test_telegram_entry, test_worker, test_worktree_runner,
  test_wmi_seed, test_heartbeat, test_llm — 19 names in the loop, the
  session's prose count says 18; one may have been missing, the loop output
  is not in the export)
- `__pycache__` directories removed under `legacy/`
- `legacy/README.md` (created) — what lives there, what replaces it, and the
  defects found (panel button deleted the DB volume, owner answer not
  persisted, worktree not isolating, three overlay hashes drifted, startup
  rebuilt the graph with `--clear`)
- `README.md` (rewritten) — no longer describes the console as the product
- `docs/MASTER-PLAN.md` (rewritten, see §4), `docs/GOAL-NATIVE-ONEIRO.md`
  (edited)

After the archive, exactly one live import of legacy remains: `python/bridge.py`,
the OSTIS graph client — intentional, the product reads the same graph the
research contour writes. The rest of the research contour (replay, world,
strategy, harness, bench, problem-solver) is real science and was not touched.

Verification: 48 native + 83 research-contour tests green; `--check` reports
provider, keys, Docker and `legacy_product_plane: archived`; preview answers
`/` 200, `/api/session` token_required, `/api/health` ready.

## 8. Execution log — phase F: the census (comes with the PR)

1. `python/native/search.py` (created) — Exa search as a plain POST, no SDK;
   becomes the researcher's first tool (before: only `fetch_url` by exact
   address). `policy.py`, `tools.py`, `service.py` (edited) wire search into
   the pipeline — without it, researcher initiative and owner pain points
   cannot work.
2. Initiative rewritten: it previously required `interest_exploration` and did
   nothing otherwise; the owner has three sources, not one. (A test that
   forgot to enable `interest_exploration` was fixed along the way.)
   `tests/test_native_research.py` (created) — search, request boundary, new
   initiative. **144 green.**
3. `python/native/install.py` + `scripts/oneiro-install.py` (created) — own
   installer for the native product (the old `install.py` went to the
   archive); `scripts/oneiro-native.py` (edited) learns to use the
   installer-issued token. `tests/test_native_install.py` (created).
   **153 green.**
4. `python/native/media.py` (created) — real attachment parsing for Telegram
   (attachments were previously declared "not connected"); wired into the tool
   registry (`tools.py`), the service and the Telegram channel
   (`telegram.py`, edited twice). `tests/test_native_media.py` (created)
   caught a real leak: an error text could contain the bot token — closed in
   the channel.
5. Budget hole closed: `look_at_image` made a model call outside the call
   budget; it now counts, with a test in `tests/test_native_media.py`.
6. UI evidence feed: `service.py` (edited) exposes an honest feed of recorded
   needs and evidence of work; `interface/native/{index.html,app.js,style.css}`
   (edited) render the `need-list` / `evidence-list` / `interest-list` hooks
   (verified in the preview). One style fix: `--mono` was not in the theme;
   replaced with the real stack.
7. Manager behavior prompt rewritten in `service.py` — the owner's main
   complaint was "деревянно, по сценарию" (wooden, scripted); new concrete
   behavior rules that do not contradict the policy; prompt sanity-checked by
   import.
8. `docs/MASTER-PLAN.md` + `README.md` updated to the actually-done state.

**Final state of the cloud session: 163 tests green** with the 8 known
ignores; `python3 scripts/oneiro-install.py --check` works; nothing in the
live contour imports legacy (`grep -rn "import legacy\|from legacy\|console\.\|dashboard\."
--include=*.py python/native scripts/oneiro-*.py` is empty); preview restart
clean, `/`, `/api/session`, `/api/health` all answering.

## 9. Verification protocol (as run in the session)

```bash
# full suite — expect 163 green
uvx pytest tests/ -q \
  --ignore=tests/test_bridge_vocabulary.py --ignore=tests/test_core_loop.py \
  --ignore=tests/test_dream_improves.py --ignore=tests/test_replay_exactness.py \
  --ignore=tests/test_replay_offline.py --ignore=tests/test_two_rounds.py \
  --ignore=tests/test_workshop_dream.py --ignore=tests/test_skills_index.py

# native only
uvx pytest tests/test_native_*.py -q

# integrity
python3 -m compileall -q python/native scripts/oneiro-native.py
python3 scripts/oneiro-native.py --check
python3 scripts/oneiro-install.py --check

# nothing live imports legacy
grep -rn "import legacy\|from legacy\|console\.\|dashboard\." \
  --include=*.py python/native scripts/oneiro-*.py
```

The 8 ignores require `sc_client` / the skills catalog, which the sandbox does
not have: test_bridge_vocabulary, test_core_loop, test_dream_improves,
test_replay_exactness, test_replay_offline, test_two_rounds,
test_workshop_dream, test_skills_index.

Preview checks: `curl / /app.js /style.css /api/session /api/health` on the
preview port (9899 in the session); `curl -s / | grep -o "need-list\|evidence-list\|interest-list"`.

## 10. Honest blockers

The live run (phase 5 of the plan) is impossible in the sandbox: no
`ONEIRO_LLM_BASE_URL` / `ONEIRO_LLM_API_KEY`, no `TELEGRAM_BOT_TOKEN` /
`TELEGRAM_CHAT_ID`, no `VIRUSTOTAL_API_KEY`, no Docker, no `sc_client`. That
is "not checked", not "almost done". On the owner's machine the order is in
phase 4 of `docs/MASTER-PLAN.md`: LLM endpoint + key → one real call per role
model; VirusTotal (if the upload exception stays) → one hash lookup + one real
upload; Docker → one real sandbox run; Telegram → one real round trip; then
the live acceptance scenarios (chat stays chat; a delegated task runs to a
verified result; a destructive request is checked once and executed after the
button; a restart mid-action leaves the effect `uncertain`; a web decision and
a Telegram decision reach the same service).

## 11. Procedure on PR arrival (local side)

1. `git fetch oneiro-ostis pull/N/head`
2. Diff the PR head against the inventory in §5–§8 (the PR must bring
   `python/native/{model,search,media,install}.py`, `scripts/oneiro-install.py`,
   `tests/test_native_{model,research,media,install}.py`, the whole `legacy/`
   tree with `legacy/README.md`, the rewritten `README.md`, `docs/MASTER-PLAN.md`,
   the manager prompt in `service.py`, the evidence-feed UI, and the edits to
   `policy.py`/`tools.py`/`service.py`/`telegram.py`/`config.py`/`bench/memory/run.py`/
   `tests/test_config.py`).
3. Run the suite per §9 — expect **163 green**.
4. Watch for a conflict against `240f50398` in `tests/test_native_service.py`
   (the quiet-hours pin, commit `c0b20edc6`) before merging.
5. Take it into `v2` — the owner's explicit instruction 2026-10-01
   ("возьмёшь в v2"); confirm the push scope right before pushing.

Environment notes: the sandbox had python3.10, `uv`/`uvx` (no system pytest),
pip for the preview install; `freebuff-preview` is a Freebuff tool that runs as
its own command (not chainable with `;` or pipes). Locally (owner's machine)
there is no Docker, no sc_client, no API keys either — the same 8 ignores
apply, and live scenarios stay blocked until keys exist.
