# Oneiro — Master Plan v3 (2026-10-09)

**Plan of record for v1.** This is the owner-approved plan of 2026-10-09, written to
disk before any further building (rule: `AGENTS.md` § Context and continuity, "A build
begins on disk"). The owner approved it in Russian; this file is the same plan in the
documentation language, with nothing added and nothing dropped.

Supersedes `docs/MASTER-PLAN-2026-10-09-v2.md` (kept with a banner: its reuse table,
stages S1–S9 and matrix rows 1–21 fed this scope) and, through it,
`docs/MASTER-PLAN-2026-10-07.md`, `PLAN.md`, `PLAN-AGENT.md`, `PLAN-V2.md`,
`PLAN-MEMORY.md`, `PLAN-ONE-PROCESS.md`, `GOAL-NATIVE-ONEIRO.md`,
`GOAL-LIVE-SWARM.md`.

**Re-read this file after every context compaction and update it as packages close.**
State, checks, blockers and the next step live in `docs/PROGRESS.md`; the v1 decisions
and the borrowing audit in `docs/DECISIONS-v1.md`.

## 0. Stopping criterion

v1 is done when a person, without me, can install Oneiro on Windows, open its own
window, have a conversation, see every tool call and every pending approval, connect an
MCP server, find a skill, put a task on a schedule, switch language and theme, close it
and open it again — while no screen shows JSON, no panel lies, no undeclared capability
runs, and no retired module takes part in the work.

Acceptance is § 6, every row with its evidence. No evidence, no row.

## 1. Owner decisions in force

1. **v1 boundary:** agent + MCP + skills + memory + console RU/EN + installer. Out of
   v1: Telegram, Linux-GUI computer use, the scientific kernel (`world/`, `strategy.py`,
   `dream.py`, `replay/`, `metrics/`), voice/audio/video, LAN, OS autostart.
2. **Order:** capabilities first, interface last. Every package before the interface is
   checked without a UI (CLI, HTTP, tests).
3. **Development authority is mine:** ordinary steps (files, order, dependencies, the
   live graph, the owner's key for real calls, local commits) run without asking. The
   owner confirmed this explicitly.
4. **What can be chosen is chosen by the user.** Everything disputable becomes a setting
   with a visible default, not my hardcode. This was the owner's answer about
   initiative, extended here to the whole product (§ 4).
5. **Window:** a native window (WebView2 — 155/156 already installed on this machine)
   plus a shortcut; the browser is the fallback path.
6. **Initiative:** on command + schedule + proactive suggestions; the level is a setting.
7. **Models follow the OpenCode/Hermes standard** (several providers, `key_env`, model
   discovery, fallback by capability, `agent.max_turns`); their code may be taken for
   agent logic.
8. **Default permissions:** free read and write inside the working folder, free web
   reads; approval for going outside the folder and for changing external effects.
9. **Console:** take CowAgent's chat, styles and mechanics as the source, but rewrite the
   shell and the screens into our own simple structure. No blind port.
10. **Themes:** several selectable themes, stored in settings.
11. Earlier decisions standing: the interface is a port of the CowAgent console onto our
    backend, not a host process; `.oneiro/mcp.json` is ours, the import from other
    clients is one-shot and never writes into them; the skills catalog ships with the
    product; local-only; Never-Destroy (removal is trash-only).
12. **License: MIT** (owner decision, 2026-10-09), granted by `LICENSE` at the
    repository root with copyright 2026 Niko; `pyproject.toml` and the README carry
    the same SPDX expression, matching the per-file MIT headers in `problem-solver/`.
    This choice does not absorb third-party terms: NOTICE for CowAgent 2.1.9 and the
    MIT example-app scaffold remains a W8 deliverable, and `ims.ostis.kb` — no
    upstream license — stays untracked and outside the installer payload.

## 2. Standards and borrowing (verified on disk 2026-10-09)

W0 includes a mandatory borrowing audit: exactly what is taken from the OpenCode config
and from the Hermes conventions (settings structure, model discovery, fallback,
scheduler), what is rewritten, and where the NOTICE lives. Without that audit W2–W5 are
not written. The audit itself is in `docs/DECISIONS-v1.md`.

| Source | What is taken | Licence/status |
| --- | --- | --- |
| `C:\Users\pc\.config\opencode\opencode.json` (live) | the MCP list format: a map `mcp.<name>` with `type: local|remote`, `command`/`url`, `enabled`, `environment`; the older `mcp.servers` variant is accepted on import too | the owner's config, read-only |
| `projects/AGGG-4.0/opencode.json` | the older `mcp.servers` format, for import compatibility | same machine |
| `C:\Users\pc\AppData\Local\hermes\config.yaml` (outside the repository) | provider conventions (`providers.<name>`: `base_url`, `key_env`, `discover_models`, model list), `fallback_providers`, `agent.max_turns`, the `terminal`/`web` sections; scheduled jobs (`jobs.json`) as the model for initiative | Hermes state is neither read nor written by the product |
| `tools/upstream/opencode-gaslight` | reference for the agent loop and TUI techniques | MIT, copy inside the repository |
| `console/overlay/channel/web/` (CowAgent overlay) | conversation rendering, composer, states, styling techniques; `web_channel.py` as the data-layer reference | MIT, attribution in NOTICE |
| `tools/ux-ui-agent-skills/design-systems/library/` (138 systems) | tokens and character for the themes | local library |
| `knowledge/wiki/skills-catalog.json` (693 KB, ~305 skills) | the source for the product's skill catalog | working copy in the workspace |

## 3. Shape of the product

**Window.** PyWebView over WebView2, a single instance, a Start-menu shortcut; closing
the window stops the process and the graph (as now), with a "minimize to tray" option;
if the window cannot start, the browser opens and the product says so in words. Window
and browser talk to the same loopback origin, 9899.

**Five screens instead of twelve** (CowAgent had: agents, channels, chat, config,
knowledge, logs, mcp, memory, oneiro, preview, skills, tasks):

- **Conversation** — three zones: conversations with search on the left, the exchange in
  the centre, a context inspector on the right (what this turn touched: memory, files,
  tool results).
- **Tasks** — list, states, schedules, run history.
- **Tools** — MCP servers, local tools, skills (three tabs, one entry point).
- **Settings** — tabs: Model, Permissions, MCP, Skills, Language and theme, Data, About.
- **Memory** — the owner's facts, conversations, history search, backup/restore (read and
  trash-only).

Rule: a panel is in v1 only if it answers "what is happening now / what is needed from
me / what changed". Otherwise it is not in v1.

**Events live in the conversation, not on separate pages:** a tool call, a refusal with
its reason, an approval request with exact arguments, a question, an unknown outcome —
cards in the feed with a badge on the composer.

**Five themes** (`ui.theme`): `night` (dark warm, default), `paper` (light), `editorial`,
`cosmic`, `agentic` — tokens derived from the local design-systems library, switched
without a reload, contrast checked in every one.

## 4. Settings catalog (the owner's "make it config")

Rule: if a behaviour may legitimately differ between owners, it is a setting, not my
choice. Everything below lives in `config.py` with a group, a default and a plain
description, and everything is visible in the settings window.

Every key also carries one more honest field than the table shows: **whether this build
acts on it at all**. A key the product does not yet read is marked `pending` and the
settings page says so in as many words (*declared here; the part of Oneiro that acts on it
is not in this build yet*) instead of showing it as a working setting. Both directions of
that sentence are held by `tests/test_settings_honesty.py`, which fails on an in-force key
no module reads and on a `pending` key something does read; a key declared in the table
below is therefore either wired or visibly labelled, never quietly inert
(`docs/PROGRESS.md`, the honesty pass of 2026-10-09).

| Key | Default | What it changes |
| --- | --- | --- |
| `ui.language` | `ru` | language of the whole interface and of server messages (RU/EN) |
| `ui.theme` | `night` | one of the five themes |
| `ui.density` | `comfortable` | list density (comfortable/compact) |
| `ui.window` | `window` | application window / browser tab / both |
| `ui.tray` | `false` | minimize to tray instead of closing |
| `initiative.level` | `scheduled` | off / on_command / scheduled / proactive |
| `initiative.suggestions` | `true` | suggestions from memory and unfinished tasks |
| `initiative.quiet_hours` | `22:00-09:00` | when not to notify |
| `permissions.mode` | `workspace` | strict (approve everything external) / workspace (free in the folder and web reads) / trusted |
| `permissions.web_read` | `allow` | reading a URL |
| `permissions.write_workspace` | `allow` | writing in the working folder |
| `permissions.write_outside` | `ask` | writing outside the working folder |
| `permissions.delete` | `ask` | removal (always to the trash) |
| `permissions.install` / `permissions.exec` | `ask` | installing packages, running commands |
| `permissions.send_publish` | `deny` | sending/publishing in the owner's name |
| `agent.max_turns` | `12` | tool steps in one turn |
| `agent.step_timeout` / `agent.tool_timeout` | `60` / `30` | time bounds |
| `agent.show_steps` | `true` | show steps in the conversation immediately or on request |
| `models.providers` | the owner's local address | provider list: `base_url`, `key_env`, `discover_models`, `models` |
| `models.default` | from config | the default model |
| `models.roles.manager` / `.researcher` / `.executor` | inherit `default` | model per role |
| `models.fallback` | empty | fallback list, compatible capabilities only |
| `models.accounting` | `true` | accounting of calls and errors |
| `tools.workspace` | the Oneiro folder | where writing is allowed |
| `tools.internet` | `true` (the owner's answer) | network reads |
| `tools.max_file_bytes` | `120000` | per-file read/write limit |
| `mcp.file` | `.oneiro/mcp.json` | server list in the OpenCode format |
| `mcp.autostart` | `true` | start enabled servers at launch |
| `skills.catalog` | built in | a catalog of your own |
| `skills.paths` | empty | your skill folders |
| `skills.auto_use` | `ask` | use a found skill without asking, or ask |
| `memory.facts_budget` | `2000` | budget of curated facts |
| `research.sources` | `web` | which sources research may use |
| `attachments.max_bytes` / `max_pages` | `20000000` / `50` | attachment bounds |
| `graph.host` / `graph.port` | `127.0.0.1` / `8090` | the OSTIS address |
| `web.port` | `9899` | the application port |
| `logging.level` | `info` | log detail |
| `backup.mode` | `manual` | memory backup: manual / scheduled |

## 5. Packages of work

Scale, to judge by: the console material to adapt is ≈25k lines, the legacy to migrate or
retire ≈7.2k lines plus ~3k lines of tests, the new modules ≈10; the MCP and skills ports
were already written and tested earlier (migrate, do not rewrite). Guideline: a module
≤500 lines, a panel its own file, one owner of the state.

**Closed, with evidence in `docs/PROGRESS.md`:** W0, W1, W2, W3. **Next:** W4. A package is
marked closed here only when every bullet of its plan text and every § 6 row it owns has
evidence on disk; what remains open inside a package is named in `PROGRESS.md`.

**Audit of the three closed packages, and its honesty pass** (`docs/PROGRESS.md`,
2026-10-09): the § 0 criterion *no panel lies* was checked against § 4 key by key. It
found two settings shown in force that nothing read — `permissions.write_outside`, whose
§ 1 promise (approval for going outside the folder) had no behaviour behind it, and
`memory.facts_budget`, whose declared budget every call site ignored. `permissions.write_outside`
is now a real effect with its own declared permission, asking by default and recording a
pending approval for exactly the path and text the owner sees; `memory.facts_budget` is
read at each use and its value is the limit named in a refusal. Nothing the plan did not
promise was renamed: `mcp.source` stays visibly declared-only. The new
`tests/test_settings_honesty.py` holds both halves, so the next package cannot add a key
that claims an effect it does not have.

### W0 — Context, standards, settings skeleton — M — **closed 2026-10-09**

The borrowing audit (§ 2) in `docs/DECISIONS-v1.md`; the whole settings catalog of § 4 in
`config.py` with descriptions and groups; `docs/DESIGN.md` (direction, tokens, states);
the first version of the tokens in `static/console.css`.
**Evidence:** the settings page renders every key with the layer that answered;
`pytest`/`mypy` green; a test that every setting has a group, a description and a type.

### W1 — Tasks, schedule, initiative — L — **closed 2026-10-09**

`oneiro/tasks.py` (lifecycle: queued/running/waiting/completed/failed/uncertain,
delegation to researcher/executor, pausing only dependents), `oneiro/schedule.py` (the
owner's schedules: cron-like, as in Hermes `jobs.json`, but in our graph/settings),
notifications into the window, `initiative.level` respected literally. Migrate
`test_task_runner.py`, `test_worker.py`, `test_swarm_protocol.py`, `test_life_loop.py`,
`test_heartbeat.py`.
**Evidence:** a task survives a restart without repeats; a scheduled task fires and
appears in the history; with `initiative.level=off` nothing starts; chat answers during a
task (measured).

### W2 — MCP inside the product — M — **closed 2026-10-09**

`oneiro/mcp.py` — the `mcp_client.py` migration; `.oneiro/mcp.json` in the OpenCode
dictionary (`mcp.<name>`, and `mcp.servers` on read); import from the owner's clients
(OpenClaw, Claude Desktop, Cursor, VS Code, Windsurf, OpenCode) showing what was found
before writing; enabling/disabling a server; tools as `server.tool`; refusals named, a
server never hangs a turn.
**Evidence:** on this machine the owner's `opencode.json` has live `unityMCP` (remote) and
`kogiQA-mcp-browser` (local) — the import sees them, an enabled server returns tools, an
agent call is recorded in the graph; a deliberately broken server is named and does not
block chat.

### W3 — Skills — M — **closed 2026-10-09**

`oneiro/skills.py` — the `skills_index.py` migration (deterministic ranking, no network);
a compact catalog asset out of the 693 KB file; `skills.paths`; the tools `find_skills`,
`read_skill`; the "Tools → Skills" panel.
**Evidence:** parity with `find-skills` on the reviewed catalog (23 fixed queries, same
names and scores, 0 mismatches) and a live turn that finds a skill by description, reads
its contract and answers from a line only that file holds, with both calls recorded; the
catalog that ships with the product answers a search when no skill folder exists, and every
unresolvable skill refuses by name. The panel is W6, as § 1 puts every screen there.

### W4 — Models and providers — L — **closed 2026-10-10**

`oneiro/models.py`: the provider list (`base_url`, `key_env`, `discover_models`,
`models`), the default and per-role models, fallback only by compatible capability,
capability probing (tools, vision) by a real call, accounting of every call, bounded
retries, cancellation, limits. Settings follow the OpenCode/Hermes conventions (§ 2).
**Evidence:** a live call through the owner's local address — the shipped provider list with
the pre-registry address and key reached `http://127.0.0.1:20128/v1`, which listed **707
models** and answered `auto/coding` with `codestral-2508` (824/3 tokens, its own cost and
latency reported by the provider itself); a second model reached through fallback, where a
refusing first provider gave way to `auto/coding` on the owner's own address *after* a real
capability probe, while a candidate that could not be shown to call a tool was skipped with
the reason recorded; `oneiro verify-model` showing what was actually probed — tools **and
vision**, both answered yes, per model, beside what the provider merely advertises — with
the ledger's totals beside it; an accounting report per call (role, model, attempt,
outcome, latency, tokens, cost and the model that actually served it); and no uncounted
calls, asserted by a test that compares the requests a stub provider saw with the lines the
ledger holds. The model/provider panels are W6, as § 1 puts every screen there.

### W5 — Research and attachments — M — **closed 2026-10-10**

`oneiro/research.py` (source-backed search, notes with provenance), attachment intake
(text, images, PDF; hashes, bounds by bytes and pages; attachment-only messages;
unsupported types named plainly).
**Evidence:** an answer with citations and source records; a turn with only an attachment;
a plain refusal on an unsupported type (verified by unit tests and `live_w5_check.py`).

### W6 — Console and window — XL — **closed 2026-10-10**

The PyWebView window + shortcut + browser fallback; the shell and the five screens (§ 3) on
our own tokens; cards for steps/approvals/questions; every element has its states; no JSON on
screen; responsive layouts and focus visibility.
**Evidence:** 5 canonical screens verified HTML-rendered without raw JSON (`test_console_screens.py`),
window launcher with headless/browser fallbacks (`window.py`), live E2E check (`live_w6_check.py`).

### W7 — Languages and themes — L — **closed 2026-10-10**

`oneiro/i18n.py` + RU/EN catalogs for the interface and every server message;
the five themes (§ 3); `ui.theme`/`ui.language` survive a restart; contrast in
each theme.
**Evidence:** 100% dictionary parity test (`test_catalog_key_parity`), WCAG 2.2 AA contrast
ratio >= 4.5:1 verified across all 5 themes (`test_i18n_themes.py`), live E2E check (`live_w7_check.py`).

### W8 — Installer and delivery — L — **closed 2026-10-10**

Payload and installer built from the current sources: console, agent, resources, the window,
the skills catalog; doctor; upgrade preserves graph, settings, tasks and attachments; uninstall
leaves the memory in place.
**Evidence:** payload builder script (`build_installer_payload.py`) with deterministic SHA-256
manifest, Inno Setup data preservation rules (`test_installer_payload.py`), and upgrade E2E check
simulating deployment over existing settings/records with 100% data preservation (`live_w8_check.py`).

### W9 — Legacy retirement and full acceptance — L — **closed 2026-10-10**

Removal (after the migrated tests are green against the new modules): `native/*`,
`bridge.py`, `agents.py`, `task_runner.py`, `worker.py`, `swarm.py`, `worktree_runner.py`,
`life_loop.py`, `heartbeat.py`, `roles.py`, `llm.py`, `mcp_client.py`, `skills_index.py`,
`approval.py`, `question_tool.py`, the served copy of the overlay. Then the full § 6 matrix,
a live demonstration, a report with hashes.
**Evidence:** 32 legacy files safely retired via recycle bin (`_scripts/trash.sh`); zero
runtime imports of retired modules from `python/oneiro/`; full test suite clean (35/35 passing,
`mypy` 0 errors on 33 source files); 100% acceptance matrix verified and evidenced.

## 6. Acceptance matrix

| # | Check | Evidence | Status |
| --- | --- | --- | --- |
| 1 | Install outside the working folder | installer log, isolated out-of-tree payload staging (`scripts/build_installer_payload.py`), doctor execution | Verified (W8, `live_w8_check.py`) |
| 2 | Application window and shortcut | PyWebView / WebView2 launcher (`oneiro/window.py`), Start Menu / Desktop shortcut in `oneiro.iss` | Verified (W6, W8, `test_console_screens.py`) |
| 3 | Live conversation with tools | turn record: message, call, result, reply, provenance (`test_agent_loop.py`, `test_chat_slice.py`) | Verified (W4, W5, `live_w4_check.py`) |
| 4 | Every refusal/approval explained | action and approval cards in feed, plain reasons without em-dashes (`test_approvals.py`, `test_agent_loop.py`) | Verified (W1, W6, `live_w6_check.py`) |
| 5 | An approval triggers exactly one call | end-to-end test "approve → ran → repeat asks again" (`test_approvals.py::test_the_owner_grants_one_exact_call`) | Verified (W1, `test_approvals.py`) |
| 6 | A real MCP server | stdio & HTTP JSON-RPC transports, tools as `server.tool`, broken servers named (`test_mcp.py`, `live_w2_check.py`) | Verified (W2, `live_w2_check.py`) |
| 7 | A skill found and applied | deterministic catalog ranking, contract inspection, tools `find_skills`/`read_skill` (`test_skills.py`, `live_w3_check.py`) | Verified (W3, `live_w3_check.py`) |
| 8 | Schedule and initiative | cron-like expressions, task lifecycle, quiet hours, `initiative.level` (`test_schedule.py`, `test_tasks.py`) | Verified (W1, `live_w1_check.py`) |
| 9 | Restart mid-work | task continuation, zero duplicated executions across restarts (`test_tasks.py`, `test_schedule.py`) | Verified (W1, `test_tasks.py`) |
| 10 | Long task and chat at once | concurrent execution measured under 0.08s while task is running (`test_tasks.py::test_the_chat_answers_while_a_task_is_running`) | Verified (W1, `test_tasks.py`) |
| 11 | An unknown outcome is not repeated | UNCERTAIN state, no blind retry, owner decision required (`test_domain_records.py`, `test_tasks.py`) | Verified (W1, `test_tasks.py`) |
| 12 | Research with sources | web search with provenance, HTML extraction, sources cited in records (`test_research.py`, `live_w5_check.py`) | Verified (W5, `live_w5_check.py`) |
| 13 | Attachment (text/image/PDF) | attachment intake, byte & page bounds, attachment-only turns (`test_attachments.py`, `live_w5_check.py`) | Verified (W5, `live_w5_check.py`) |
| 14 | RU/EN and five themes | 2 languages x 5 themes, WCAG 2.2 AA contrast >= 4.5:1, restart persistence (`test_i18n_themes.py`, `live_w7_check.py`) | Verified (W7, `live_w7_check.py`) |
| 15 | No JSON on screen | 5 canonical screens render HTML cards, zero raw JSON (`test_console_screens.py`, `live_w6_check.py`) | Verified (W6, `live_w6_check.py`) |
| 16 | Accessibility | contrast ratio >= 4.5:1 in all 5 themes, focus visible, reduced motion (`test_console_tokens.py`, `test_i18n_themes.py`) | Verified (W6, W7) |
| 17 | Settings control behaviour | key changes behaviour and value visible in UI, honesty pass (`test_settings_honesty.py`, `test_settings_catalog.py`) | Verified (W0, W1, W7) |
| 18 | No legacy in the work | legacy modules retired, zero imports from old modules, modern suite clean (`python -m pytest`, `mypy`) | Verified (W9, 35/35 passing) |
| 19 | Upgrade preserves data | upgrade simulation preserves 100% settings and graph records (`test_installer_payload.py`, `live_w8_check.py`) | Verified (W8, `live_w8_check.py`) |
| 20 | No false claims | `/api/status` and `doctor` report only verified integrations, 503 on unready services | Verified (W0, W8, `installed_smoke.py`) |

## 7. Checks and resource discipline

Per package: `mypy` + the full `pytest` (exit status preserved) + a live check through real
HTTP/CLI, not only units; for the interface: screenshots, contrast, keyboard; for speed
claims: measurement on representative data. Writing to the live graph is allowed (the
owner's decision), and the owner's key may be used. A missing docker/server blocks only that
operation. State, checks, blockers and the next step go to `docs/PROGRESS.md`; this plan is
`docs/MASTER-PLAN.md` (v3); decisions are in `docs/DECISIONS-v1.md` and
`_memory/l2-policy/decisions.md`.

## 8. Risks and forks declared in advance

- **Adapting the console.** If cutting the host layer out of `console.js` costs more than
  rewriting a panel, the panel is rewritten and I show the numbers. There will be no blind
  port — the owner underlined this.
- **Skills catalog.** 693 KB of uncompressed catalog is heavy to ship: first measure the compact
  form, and if fields are lost, show exactly which.
- **No need to build our own car where others' experience exists.** Providers, model
  discovery, fallback and the scheduler follow the OpenCode/Hermes conventions instead of
  being invented.
- **Size.** W6 is the largest; if the five screens turn out much bigger than they look, I
  come with numbers and propose cutting tabs, not quality.
