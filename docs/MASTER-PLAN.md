# Oneiro — Master Plan v2 (2026-10-09)

Plan of record. Supersedes `docs/MASTER-PLAN-2026-10-07.md`, `docs/PLAN.md`,
`docs/PLAN-AGENT.md`, `docs/PLAN-V2.md`, `docs/PLAN-MEMORY.md`,
`docs/PLAN-ONE-PROCESS.md`, `docs/GOAL-NATIVE-ONEIRO.md`,
`docs/GOAL-LIVE-SWARM.md`. Those remain on disk as evidence, each with a banner.

## 1. Owner decisions in force (2026-10-09)

1. **The agent comes first.** Agent loop, tools, MCP and skills (Stage C of the
   previous plan) are the next work, before the interface.
2. **Everything except voice.** Voice, audio and video analysis or generation stay
   out of v1.
3. **The interface is the CowAgent console, wired to Oneiro's backend.** The
   console in `console/overlay/channel/web/` is the design and behaviour source
   (MIT; attribution kept in a NOTICE). CowAgent is not a host process and Oneiro
   does not depend on it at runtime.
4. **Two languages, RU and EN, with a switch.** The choice is stored in Oneiro's
   settings (server-side), not per browser.
5. **MCP list in our own file**, `.oneiro/mcp.json`. On first run the product
   offers to import the server list from popular clients already on the machine
   (OpenClaw, Claude Desktop, Cursor, VS Code, Windsurf). It never writes into
   another client's file.
6. **The skills catalog ships with the product**; its path is a setting.
7. **Local-only.** No push, deploy, PR or sending. Never Destroy: removal is
   trash-only.

## 2. Where the product stands

Verified done: installable package and consolidated config; typed records and
provenance; OSTIS memory with split writer/reader, bounded queries, one-shot
backup/restore evidence; one-process web on loopback 9899 (chat, settings, setup,
graph pages); owner chat round trip stored in the graph; curated owner facts with
a budget; conversations and search over stored history; Windows installer that
loads the graph image, starts the graph, opens the page and keeps data on
uninstall.

Not done, and therefore the subject of this plan: the agent runtime, the tool
surface, MCP inside the product, the skills catalog as a tool, role models and
research, attachments, Telegram, Linux computer use, the console interface,
RU/EN, native window/tray, and the scientific kernel in its new form. In the
previous plan's own words: "Foundation shell is not completed agent runtime."

## 3. Reuse, not rewrite

The previous project already wrote and tested most of the agent layer. It is
migrated into the `oneiro` package as one control plane, not rebuilt.

| Existing module | What it gives | Disposition | Its tests |
| --- | --- | --- | --- |
| `python/mcp_client.py` (393) | stdio JSON-RPC MCP client; bounded time and size; named failures; verbatim results | migrate into `oneiro/mcp.py` | `tests/test_mcp_client.py` (155) |
| `python/skills_index.py` (275) | deterministic skill-catalog ranking over `SKILL.md`, no network, no embeddings | migrate into `oneiro/skills.py` | `tests/test_skills_index.py` (205) |
| `python/native/tools.py` (237) + `native/policy.py` (84) | trusted tool surface with scope: no unrestricted host shell, secret/config names refused | migrate into `oneiro/tools.py` | `native/policy.py`: `tests/test_native_service.py` (240), which exercises the allow/deny/ask decisions. `native/tools.py`: **no direct test** — no test imports it, and it is reached only through `native/service.py`. Its tests must be written during the migration. |
| `python/question_tool.py` (182) | asking the owner a free-text question and persisting the answer | migrate into `oneiro/questions.py` | `tests/test_question_tool.py` (210) |
| `python/approval.py` (568) | approvals for risky effects; stale approvals rejected | migrate into `oneiro/approvals.py` | `tests/test_approval.py` (370); also imported by `test_question_tool.py` (210), `test_task_runner.py` (373) and `test_telegram_entry.py` (472) |
| `python/roles.py` (301) | role models (manager, researcher, executor) | migrate into `oneiro/models.py` | `tests/test_roles.py` (144) |
| `python/task_runner.py` (460), `worker.py` (460), `swarm.py` (236), `worktree_runner.py` (133), `life_loop.py` (528), `heartbeat.py` (198) | tasks, workers, initiative, scheduling | one runtime replaces them; retire after their tests pass against it | `tests/test_task_runner.py` (373), `test_worker.py` (245), `test_swarm_protocol.py` (169), `test_worktree_runner.py` (39), `test_life_loop.py` (239), `test_heartbeat.py` (170) |
| `python/bridge.py` (1498) | old graph bridge | typed graph operations already live in `oneiro/query.py`, `store.py`, `records.py`; bridge is reference, then retired | `tests/test_bridge_vocabulary.py` (52), `test_bridge_writer_contracts.py` (566), `test_core_loop.py` (104), `test_life_loop.py` (239), `test_heartbeat.py` (170), `test_replay_exactness.py`, `test_replay_offline.py`, `test_dream_improves.py` (84), `test_two_rounds.py`, `test_workshop_dream.py`. `test_sc_graph_contract.py` does **not** import bridge — it covers `oneiro/sc_graph.py`. |
| `python/llm.py` (281) + `adapter_llm/` | model access | consolidate into `oneiro/models.py` | `tests/test_llm.py` (125); `llm` is imported by `test_life_loop.py`, `test_roles.py` and `test_worker.py` too. `adapter_llm/` alone: `test_dream_improves.py` (84). |
| `console/overlay/channel/web/` | CowAgent console: `chat.html`, `console.css` (4039), `console.js` (17951), `setup.html`, `console.js` panels | design and behaviour source for the port; keep as provenance, do not serve from here | `tests/test_console_overlay.py` (152) |
| `console/vendor/cowagent-2.1.9.zip` | the MIT original the overlay patches | keep, untouched | checked by `tests/test_console_overlay.py` (152): it fails if the overlay and the archive drift apart |

Every test reference in this table was verified on 2026-10-09 by grepping `tests/`
for imports of the named module, not inferred from file names. Every count in this
table was re-measured the same day with `wc -l`, and so were the port, page and
matrix numbers quoted elsewhere in this file. Where no test exists, the row says
so and the migration must add one before retiring the module.

## 4. Target architecture

One process. One loopback origin (9899). One durable memory (the OSTIS graph);
no second store, no fallback that pretends to be memory.

    owner → console page → /api/* → agent runtime → model adapter
                                          │
                                          ├─ tool registry ─→ local tools
                                          ├─ MCP client ────→ MCP servers
                                          ├─ skills catalog
                                          ├─ approvals / questions
                                          └─ graph (records, provenance)

## 5. Stages

### S1 — Agent runtime (the immediate work)

Deliverables: `oneiro/agent.py` (intake → context from recall → model call →
bounded tool loop → persist → answer); `oneiro/tools.py`; `oneiro/tasks.py`;
`oneiro/questions.py`; `oneiro/approvals.py`; new record kinds in
`oneiro/records.py` for task, step, tool call, tool result, decision, approval and
question, all in the graph with provenance; `agent.*` and `tools.*` settings.

Rules kept from the previous plan: bounded steps and per-step deadlines; intent
persisted before an effect, observed result after; an unknown outcome is inspected,
never blindly retried; a long task must not block chat; free-text answers and
decisions are persisted; waiting pauses dependent work only.

Exit evidence: one live turn in which the model calls at least one tool, with the
message, tool call, tool result and reply each readable from the graph with
provenance; a restart mid-task resumes without repeating what already happened; a
long task running while a chat request is answered (measured concurrently);
`pytest` and `mypy` green; the migrated behaviour tests for tasks, approvals and
questions pass against the new modules.

### S2 — Tools: MCP and skills

Deliverables: `oneiro/mcp.py` (port of `mcp_client.py`); server list from
`.oneiro/mcp.json`; a first-run import that scans known client configs (OpenClaw
`~/.openclaw/workspace/.mcp.json`, Claude Desktop, Cursor, VS Code, Windsurf),
deduplicates by name and shows what it found before writing; `oneiro/skills.py`
with the catalog shipped in the package and a `skills.catalog` override; MCP and
skills panels in the console from S4 depend on this API.

Exit evidence: the agent answers using a real tool from a real MCP server on this
machine, with the call and result recorded; a server that fails to start is
reported by name instead of hanging; skill lookup returns the same ranking as the
`find-skills` skill for a fixed query set (parity test).

### S3 — Models, research and attachments

Deliverables: `oneiro/models.py` (one OpenAI-compatible adapter, manager/
researcher/executor roles, capability probing for tools and vision rather than
inferring from names, every call accounted, bounded retries, cancellation,
rate-limit handling, capability-compatible fallback only, spend only where the
price is known); `oneiro/research.py` (source-backed search and extraction through
real integrations, notes with provenance in the graph); attachment intake for
text, images, screenshots and PDF under `.oneiro/attachments` with hashes, bounded
bytes and pages, attachment-only messages, unsupported audio/video stated plainly.

Exit evidence: live chat using tools and vision; a researched answer that cites
its sources; an attachment-only message answered; unsupported media reported;
no uncounted calls.

### S4 — Console UI (CowAgent) and RU/EN

Deliverables: the CowAgent console ported into `python/oneiro/static/`
(`console.css`, `console.js`, page template) and served by `oneiro/web.py`; panels
for chat with visible tool activity, conversations, search, curated memory,
settings (model, MCP servers, skills path, language), graph, tasks, approvals and
questions; panels with no backend are hidden rather than faked; `oneiro/i18n.py`
with `en` and `ru` catalogs and a `ui.language` setting, default from the browser
language when it is ru or en and otherwise en, the switch writing the setting.

Quality bar taken from the complaint that started this: chat first, no raw JSON on
any page, no internal jargon, every failure explained in plain words, keyboard
usable with a visible focus.

Exit evidence: a panel parity checklist; screenshots in both languages; no page
renders JSON; the language switch survives a restart; existing API tests pass.

### S5 — Telegram

Same core as the console: private owner-allowlisted bot, attachment intake,
restart-safe offsets and outbox, an unknown send outcome stays unknown, cancel and
decide across channels, stale callbacks rejected. Exit: one conversation visible in
both channels and surviving a restart.

### S6 — Tools and Linux computer use

Isolated execution for edits, package setup and tests; VM with the pinned low-level
Cua driver for capture, click, type, scroll and waits; owner-visible observation,
immediate stop and takeover; artifacts preserved before cleanup; scoped APIs for
account effects; no host desktop and no unrestricted host shell. Exit: a real
LibreOffice Writer task producing a formatted ODT and PDF, both reopened and
independently verified, with nothing written outside the VM or the Oneiro folder.

### S7 — Packaging, install and legacy retirement

The installer ships the console and the agent; doctor and one shortcut; upgrade
preserves graph, settings, tasks and attachments; the retired modules
(`native/*`, `bridge.py`, `agents.py`, the fragmented control planes, the served
copy of the overlay) are removed only after their replacements pass; no
workspace-private dependency remains. Exit: clean install outside the workspace;
upgrade preserves data; no active legacy imports.

### S8 — Scientific kernel and automatic improvement

Rewrite and retain `world/`, `strategy.py`, `dream.py`, `episode.py`, `replay/`,
`metrics/` only with invariant and equivalence evidence; frozen controls before
search; at least three paired repeats per stochastic task or abstention; promotion
and rollback protected from candidate writes; rollback must not erase newer owner
data. Exit: exact-replay proof, a protected gate, one real measured gain.

### S9 — Full acceptance and bilingual delivery

The acceptance matrix re-checked; a live demo; bilingual slides and PDFs;
an acceptance report with hashes. Local only.

Out of scope for v1: voice, audio and video; publication; LAN exposure; OS
autostart.

## 6. Acceptance matrix

The matrix of the previous plan is kept (rows 1–21: clean install, casual
conversation, sourced research, scoped execution, initiative, tools and vision,
attachments, the Writer GUI task, fault and restart behaviour, the archived old
graph, typed and idempotent upgrades, bounded queries, exact replay, a measured
dream gain, protected gates, both channels, the native UI, the memory explorer,
no legacy dependency, installed delivery with a bilingual demo, local-only
commits). Row 10 (old-graph archive) stays checked with its existing evidence;
every other row is unchecked until its own evidence exists.

## 7. Verification and resource discipline

Per unit: Python typecheck, relevant tests, scenario checks. Final matrix: Python,
C++, real OSTIS, browser, desktop, live model. The docs-route gate runs with every
commit that touches `docs/`. Performance claims need correctness and representative
timing measured, not asserted. Missing Docker, a VM, a toolchain, credentials or
access blocks only the affected operation; independent work continues. Historical
test counts are not a goal. A stage persists its state, checks, blockers and next
step in `docs/PROGRESS.md`.

## 8. Documents

Active: this file and `docs/PROGRESS.md`. Evidence and analyses, not plans:
`docs/REWRITE-BASELINE.md`, `docs/COWAGENT-COMPARISON.md`,
`docs/AGENT-COMPANY-COMPARISON.md`, `docs/SKILLS-COMPILATION.md`,
`docs/ONTOLOGY-DRAFT.md`. Historical plans with a banner:
`docs/MASTER-PLAN-2026-10-07.md`, `PLAN.md`, `PLAN-AGENT.md`, `PLAN-V2.md`,
`PLAN-MEMORY.md`, `PLAN-ONE-PROCESS.md`, `GOAL-NATIVE-ONEIRO.md`,
`GOAL-LIVE-SWARM.md`, `ARCHITECTURE-HYBRID.md`. **Not current — describes the
removed architecture** (CowAgent as the host process, the panel on port 8130,
`scripts/oneiro-app.cmd`, the host console); read them as history of how the
product used to run: `docs/PROJECT-CONTEXT.md`, `docs/HOST.md`. Session record
kept as provenance, whose authority pointer is stale: `docs/CLOUD-SESSION-PLAN.md`
(it names `GOAL-NATIVE-ONEIRO.md` as where the binding decisions live; section 1
of this file is that place now).

Research and demonstration artifacts of the previous project, kept as evidence and
not as current product documentation: `docs/rounds.md`, `docs/rounds-workshop.md`,
`docs/results.md`, `docs/series.md`, `docs/demo-log.md`, `docs/harness.md`,
`docs/dream-tree.html`, and the screenshots under `docs/shots/`. Presentation
material built on that work rather than on this plan: `docs/PAPER.md`,
`docs/SLIDES.md`, `docs/TALK.md` and `docs/pz/`. Neither evidence nor part of this
plan, and left untouched as another session's work in progress: the untracked
`docs/forumit-2026/`.

## 9. Blockers and open items

- A live model round trip from the installed copy still needs the owner's key
  entered on the settings page; it writes the owner's graph.
- `curated_fact` is not yet proven on a rebuilt graph; a rebuild is not authorized.
- The installer image is the owner's `oneiro-rewrite-machine:checkpoint` build,
  tagged for shipping; it is not rebuilt from current sources.
- The SHA-256 of the embeddable Python archive is not pinned in the installer build.
- S6 (Linux GUI) is the largest single item and needs a VM decision when S5 closes.
