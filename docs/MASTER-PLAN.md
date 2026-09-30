# Oneiro — Master Plan

The single plan for turning `v2` into a coherent, usable, living assistant.
Written down on request after the interrogation rounds (owner decisions:
`docs/GOAL-NATIVE-ONEIRO.md`). Status markers are honest: **done** means the
code exists and its offline tests pass here; **live** means it needs a real
model/graph/keys that this workspace does not have yet.

## Definition of done (the product)

A personal assistant the owner actually uses: one configurable manager as the
conversational counterpart, an independent researcher and an executor with
permanent role limits, proactive work of its own, OSTIS memory, and permissions
the owner releases with a button. Web, Telegram and the scheduler are windows
into the same core. CowAgent/Hermes/OpenClaw are not the control plane.

## Status board

| # | Phase | Status | Evidence |
|---|-------|--------|----------|
| 0 | Audit, owner interrogation, decision record | **done** | `docs/GOAL-NATIVE-ONEIRO.md`, this file |
| 1 | Native core: memory, policy, tools, service | **done** | `python/native/`, `tests/test_native_service.py` (20 tests) |
| 2 | Channels: native web UI + Telegram adapter | **done (offline), preview runs** | `python/native/web.py`, `python/native/telegram.py`, `interface/native/`, `tests/test_native_channels.py` (11 tests) |
| 3 | Memory safety, launch, diagnostics | **done** | `scripts/oneiro-native.py`, entrypoint no longer clears an existing graph |
| 4 | Live model loop + real tools | **live-blocked** | needs `ONEIRO_LLM_*` / OmniRoute key, `VIRUSTOTAL_API_KEY`, Docker |
| 5 | Initiative and interests | **code done, live-blocked** | opt-in + interval + quiet hours + budgets in `service.py` |
| 6 | Legacy migration and removal | **not started** | after native acceptance scenarios pass on the owner's machine |
| 7 | Polish: media inspection, search, richer task views | **not started** | — |

## Phase 0 — Decisions (done)

Full interrogation of the owner; contradictions resolved before code. The
binding decisions are listed in `GOAL-NATIVE-ONEIRO.md`. Highlights: three
personalities in SOUL.md; permanent role limits that prompts cannot relax;
an exact-action permission model (a direct instruction authorises its own
scope; database/config changes need a separate button; text never approves);
remote LLM context and VirusTotal file upload as explicit egress exceptions;
no autostart; no forced three-agent ceremony; initiative is opt-in.

## Phase 1 — Native core (done)

`python/native/` — one control plane, no CowAgent:

- `memory.py` — OSTIS is the durable truth (`GraphMemory` via the existing
  bridge's new `record_native_event`/`load_native_events`, semantic links for
  actor/task/approval/note/interest/conversation). `TestMemory` is an explicit
  test double, never a production fallback. No silent SQLite/file fallback.
- `policy.py` — trusted tool metadata (roles, effect class) and the effect
  gate: deny / allow / **ask** (exact approval). Sensitive effects
  (configure, delete, database, sandbox, install, publish, send, upload)
  always require the owner's button. Autostart is unrepresentable as a tool.
- `tools.py` — the reviewed surface: read/list/write/configure/delete within
  a task workspace, cross-role memory notes and interests, public-URL fetch
  (no cookies/redirects/private IPs), delegated work, owner questions,
  reports, Docker sandbox (`--network=none`, read-only, capped, preinstalled
  image only — a worktree is not a sandbox), VirusTotal upload + analysis
  read. Credential files are invisible to models.
- `service.py` — conversation, tasks, questions, approvals, runs with
  checkpoint/resume across restarts, recovery (`executing` effects become
  `uncertain`, never silently re-run), SOUL loading/editing, settings
  validation, role prompts, the LLM/tool loop with per-step call budgets,
  fair scheduling (chat does not queue behind tasks), opt-in initiative with
  interest memory and quiet hours.
- `tests/test_native_service.py` — 20 offline tests covering role limits,
  exact approvals, text-is-never-approval, rejection, recovery, evidence,
  initiative gating, retry, settings validation. **All pass.**

## Phase 2 — Channels (done offline; web verified in the managed preview)

- `interface/native/` — the workspace UI (conversation, living work, shared
  memory, personalities & rules). English product language, no external
  fonts/trackers, CSP locked to same-origin.
- `python/native/web.py` — same-origin sessions, CSRF for writes, local-first
  login (remote binding requires `ONEIRO_WEB_TOKEN`), secrets never echoed.
- `python/native/telegram.py` — owner-only, one poller per bot, offset
  persisted only after persistence of the update, approval buttons release
  exact actions, replies/instructions/proactive messages share the same
  conversation. Attachments are named as un-inspected, never silently ignored.
- Channel seam tests (11): API closed until sign-in, CSRF on every write,
  one service for web and scheduler, token door for proxied access, owner-only
  Telegram intake, duplicate updates taken once, a button releases exactly one
  action (stale presses do nothing), words never release an action, manager
  output delivered once. All pass offline.
- The managed preview runs `scripts/oneiro-native.py`: a proxied port without
  `ONEIRO_WEB_TOKEN` gets a one-time token printed to the run log — a fresh
  runtime token, never a stored secret.

## Phase 3 — Memory safety and launch (done)

- Normal container start **never** runs `sc-builder --clear` on an existing
  graph anymore; rebuild happens only on an explicit request
  (`REBUILD_KB=1` or `scripts/reset_stack.sh --yes`).
- `scripts/oneiro-native.py` — one entrypoint for the native product:
  web + scheduler + optional Telegram, with `--check` diagnostics that name
  missing dependencies/keys instead of pretending. No autostart anywhere.

## Phase 4 — Live model and tools (next, environment-blocked)

Wire and verify against real services on the owner's machine:

1. Set `ONEIRO_LLM_BASE_URL` + `ONEIRO_LLM_API_KEY` (OmniRoute or any
   OpenAI-compatible endpoint), verify a real one-token call per role model.
2. Set `VIRUSTOTAL_API_KEY` only if the upload exception stays on; run one
   real hash lookup + one real upload of a public sample.
3. Docker present → one real sandbox run of a trivial command, proving the
   network/readonly caps.
4. Telegram: `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`, one real round trip.
5. Live acceptance: casual chat stays chat; a delegated task runs to a
   verified result; a destructive request is checked once and then executed
   after the button; a restart mid-action leaves the effect `uncertain`;
   a web decision and a Telegram decision reach the same service.

## Phase 5 — Initiative (code done, live-blocked)

Interests can emerge from discoveries or unfinished work; independent
exploration is a setting; owner pain points are another source. Initiative
writes are rate-limited, quiet-hour aware and budgeted; an initiative run
charges the model budget *before* enqueueing so a provider failure cannot
loop. No fixed briefing may masquerade as personality.

## Phase 6 — Legacy migration (not started)

The CowAgent console/installer/overlay and the research panel stay runnable
until native scenarios pass and data is migrated (graph records, worktrees
under `~/.openclaw/worktrees/`, benchmark artifacts). Known legacy defects
found in the audit remain recorded here so they are not rediscovered:
owner free-text answers are not persisted into the legacy question result
(the native core fixes this semantics), overlay hash drift breaks reinstall,
and `scripts/oneiro-app.py` hardcodes a workspace root that a standalone
clone does not have. None of these block the native path.

## Phase 7 — Polish (not started)

Media inspection (real image/video understanding instead of a named gap),
web search as a first-class researcher tool, richer task/evidence views,
multi-conversation support, and packaging for the owner's machine.

## Hard rules for every phase

- No claimed success without real tool evidence; no fabricated install/test.
- Missing keys/infrastructure are reported as blockers, never simulated.
- Permanent role limits live in code (`policy.py`); SOUL.md is style only.
- The signing path is one thing: an owner button on one exact saved action.
- Old data and research results are preserved through the migration.
