# Oneiro v1 — decisions and borrowing audit

Companion to `docs/MASTER-PLAN.md` (v3). The plan states what v1 is; this file records
what was decided, what is taken from whom, and what is rewritten. The W0 package is not
closed until the audit below exists, because W2–W5 depend on it.

Owner decisions of 2026-10-09 that shape v1 are in `docs/MASTER-PLAN.md` § 1 and were
recorded in `_memory/l2-policy/decisions.md` (entry "Oneiro v1 scope and the package
route"). They are not repeated here.

## 1. Borrowing audit (verified on disk, 2026-10-09)

Every claim below was re-checked with a command on this machine on 2026-10-09, not read
from a note. Numbers are bytes or lines as measured then.

### 1.1 OpenCode — MCP list format

Source: `C:\Users\pc\.config\opencode\opencode.json` (the owner's live config).

- Top-level keys: `$schema`, `mcp`.
- `mcp` is a **map keyed by server name**, not a list. Verified entries:
  `unityMCP` (`type: remote`, `url` present, `enabled: true`) and
  `kogiQA-mcp-browser` (`type: local`, `command` present, `enabled: true`).
- Therefore a server entry is `{type, command|url, enabled, environment}`.

Legacy variant, still needed for import: `projects/AGGG-4.0/opencode.json` carries
`mcp.servers` as a map (`browsermcp`, `searchmcp`, …).

**Taken:** the on-disk shape — `mcp.<name>` with `type: local|remote`, `command`/`url`,
`enabled`, `environment` — as the format of `.oneiro/mcp.json`, and `mcp.servers` as an
accepted alias when reading someone else's file (W2). **Rewritten:** our own file, our own
reader, our own errors; we never write into another client's config.
**Attribution:** format only; no OpenCode code is copied, so the NOTICE records the format
provenance, not a licence obligation.

### 1.2 Hermes — provider and scheduler conventions

Source: `C:\Users\pc\AppData\Local\hermes\config.yaml` (outside the repository; read-only,
never written by the product).

- The provider block is `providers.<name>` with `base_url`, `key_env`, `discover_models`
  and a `models` list. Verified provider names: `hive-proxy`, `gwarden`, `app-ashna-ai`,
  `frevf`.
- Also present in the same file: `fallback_providers`, `agent.max_turns`, `terminal` and
  `web` sections — the conventions named in the plan.
- Scheduler is a **cron directory**, not a single file:
  `C:\Users\pc\AppData\Local\hermes\cron\jobs.json` (with `cron/.jobs.lock` and timestamped
  backups in `_archive/`), and the implementation is readable at
  `hermes-agent/cron/jobs.py`, `cron/scheduler.py`, `cron/scheduler_provider.py`,
  `tools/cronjob_tools.py`.

**Taken:** the settings vocabulary (`base_url`, `key_env`, `discover_models`, `models`),
the idea of `fallback_providers`, `agent.max_turns`, and the cron-like job record as the
model for `oneiro/schedule.py` (W1, W4). **Rewritten:** our own scheduler and our own
registry; Hermes' runtime state is neither read nor written. **Attribution:** conventions
and observed record shape; Hermes code is a reference for semantics, and if any of it is
copied verbatim, the NOTICE must name it — see § 1.6.

### 1.3 CowAgent console overlay — the interface source

Source: `projects/ostis/oneiro-ostis/console/overlay/` (MIT; the untouched original is
`console/vendor/cowagent-2.1.9.zip`, 4,394,330 bytes, and
`tests/test_console_overlay.py` fails if overlay and archive drift apart).

Measured size of the files to adapt: **25,145 lines** of `.js`/`.html`/`.css`:

| Lines | File |
| --- | --- |
| 17,951 | `channel/web/static/js/console.js` |
| 4,039 | `channel/web/static/css/console.css` |
| 2,336 | `channel/web/chat.html` |
| 9,888 | `channel/web/web_channel.py` (data layer) |
| 1,048 | `agent/tools/mcp/mcp_client.py` |
| 912 | `agent/tools/tool_manager.py` |
| 811 | `agent/tools/mcp/mcp_admin.py` |
| 398 | `agent/registry.py` |
| 318 | `common/i18n.py` (+12 `i18n_ru.py`) |
| 301 | `channel/web/oneiro_setup.py` |
| 257 | `channel/web/setup.html` |
| 311 | `static/js/mcp-admin.js`, 251 `oneiro-admin.js` |

**Taken:** conversation rendering, the composer, state handling and styling techniques —
as design and behaviour source. **Rewritten:** the shell, navigation and every panel, into
our own simple structure with our own API (W6). **Attribution:** MIT, recorded in NOTICE
with the archive name and version.

### 1.4 OpenCode reference copy

`tools/upstream/opencode-gaslight/` exists in the workspace as a reference for the agent
loop and TUI techniques (MIT). Used as reading, not as a dependency.

### 1.5 Skills catalog and design tokens

- `knowledge/wiki/skills-catalog.json` — 693,148 bytes; the source for the product's
  catalog (W3 ships a compact asset, measured before shipping).
- `tools/ux-ui-agent-skills/design-systems/library/` — 138 systems, each with a
  `DESIGN.md`. The five v1 theme names were matched against the library on 2026-10-09:
  `paper`, `editorial`, `cosmic`, `agentic` and `warm-editorial` exist as systems;
  `night` (dark warm) does not, so it is derived from `warm-editorial` for warmth plus a
  dark neutral base — stated in `docs/DESIGN.md` rather than pretended to be a library
  system.

### 1.6 NOTICE obligations, to be discharged in W8

The installer payload carries a `NOTICE` naming: CowAgent 2.1.9 (MIT, console overlay and
its archive), the design-systems library (local, provenance recorded), and any Hermes or
OpenCode code copied verbatim rather than reimplemented. Until a package copies code
rather than behaviour, no new obligation arises.

## 2. Decisions inside v1 that are not the owner's (recorded so they can be overruled)

- The catalogue of § 4 of the plan is one flat registry in `python/oneiro/config.py`; a
  setting is a declaration with key, env name, default, label, help, group, kind and
  legacy aliases. The settings page is generated from it, so a new setting needs no HTML.
- `pending: true` marks a setting that is declared and visible but not yet in force in the
  current build. The page shows it as declared-not-yet-active instead of hiding it, so the
  catalog never lies in either direction.
- Structured settings (`models.providers`, `models.fallback`, `skills.paths`,
  `research.sources`) are stored and edited as JSON, validated on write: provider records
  need `name` and `base_url` and may only use the declared fields.
- Legacy keys (`llm.*`, `mcp.source`, `dashboard.port`, `loop.rounds`, `series.seeds`,
  `world.seed`, `bench.*`) stay declared while the modules that read them exist; they are
  retired with those modules in W9, not silently dropped now.

## 3. Module ownership after the architecture pass (2026-10-09)

Recorded so later packages build with this shape instead of against it. This pass changed
shape only; behaviour is covered by the same tests plus the ones named here.

- **`oneiro/settings_registry.py` owns the catalog** — the `Setting` declaration,
  `DEFAULT_DATA_DIR`, `DEFAULT_PROVIDERS`, `JSON_LISTS`, the `SETTINGS` tuple and the two
  derived lookups (`_BY_KEY`, `_ATTR`). It is data, readable top to bottom as the product
  surface. 449 lines.
- **`oneiro/config.py` owns resolution and storage** — the five layers, coercion and JSON
  validation, the atomic write with its history and lease, `describe`/`save`/`reset`.
  609 lines after losing the catalog and the command line.
- **`oneiro/cli.py` owns the command line** — `doctor`, `serve`, `verify-model` and now
  `settings`; `python python/config.py` survives as a shim that forwards to it.
- **`oneiro/tools.py` owns the permission decisions** — `EFFECT_SETTINGS` maps each effect
  to the setting that governs it, beside `EFFECTS`/`SENSITIVE`/`ROLE_EFFECTS`. A new effect
  must be written into `EFFECT_SETTINGS` or `EFFECTS_WITHOUT_SETTING`, and
  `test_every_effect_is_governed_or_deliberately_not` fails until it is.
- **One vocabulary for permissions.** `Policy` takes `decisions` (the exact words the
  settings page shows) and `internet_enabled`, nothing else; the older `permission_mode`,
  `review_writes`, `ask_web_read` and `denied_effects` keys are gone. `agent.default_policy()`
  reads the catalog through `EFFECT_SETTINGS` and decides nothing itself.
- **The settings layer owns its refusal.** `config.SettingsRejected` carries one reason per
  problem, naming keys and expected shapes and never a submitted value, so `web.py` can hand
  the reasons to the page without inventing a general "invalid settings" sentence.

Verification of the pass: `pytest tests/ -q` 710 passed (exit 0), `python -m mypy` clean on
24 modules, the live page serving 62 keys in `night`, and a real refused save through the
browser showing "Nothing was saved. One setting needs a different value. /
models.providers: valid JSON was expected" with nothing written.

## 4. Decisions taken in W1 (tasks, schedule, initiative) — 2026-10-09

Recorded so W2+ builds with this shape, and so the owner can overrule any of them.

- **One attempt at a time, and never the same attempt twice.** A run is named
  `run-<task>-a<attempt>`, `start` refuses while the newest attempt is open, and the
  runtime lease means one writer. The set of runs this process is holding is in memory on
  purpose: it is the one fact a restart cannot recover, and it is what distinguishes "in
  flight" from "an attempt that never reported back".
- **An interrupted attempt is UNCERTAIN, not resumed.** Legacy `life_loop`/`heartbeat`
  resumed the same session after a restart. In v1 an attempt that stopped reporting is
  reported as unknown outcome and is not started again by the process; the task continues
  as its next attempt when the owner says so (acceptance row 11). A *failed* attempt, by
  contrast, is picked up again on its own up to `MAX_ATTEMPTS = 3`.
- **`waiting` means a dependency, and only that.** Asking the owner is the conversation's
  tool (`ask_owner`, effect `coordinate`, role `manager`); a task runs as `researcher` or
  `executor` and neither may ask, so `ROLE_EFFECTS` stays as it is and no task is reported
  as waiting on an answer. The former "waiting for your answer to a question" branch was
  removed rather than left as an unreachable claim.
- **Schedules are records, and the minute is the idempotency key.** `last_fired_at`,
  the task's request id and the publication's operation id are all made from the minute a
  firing belongs to, so a restarted process or a manual tick beside a background one
  writes the same records and the store answers the second with the first. A schedule is
  called off by publishing a CANCELLED revision, never deleted.
- **An unreadable value is the cautious one, and it is said out loud.**
  `initiative.level` that cannot be read means `off` (`settings_error()` says why);
  `initiative.quiet_hours` that cannot be read means never quiet, and `notices` reports
  the declared window. Neither degradation is silent.
- **A notification is a conversation message.** One record with label `notice`, plus
  `held` when it was written inside the quiet window: held notices are stored, not hidden,
  because the memory is the truth and the label is what tells the window not to interrupt.
  The window's rendering of them is W6 work; the records and the API are here now.

## 5. Decisions taken in W4 (models and providers) — 2026-10-10

Recorded so W5+ builds with this shape, and so the owner can overrule any of them.

- **One registry per process, and the ledger lives with the process.** `oneiro/models.py`
  holds the providers, the model per role, the discovery and probe caches and the ledger of
  every call. Oneiro is one process held by the runtime lease, so the accounting is the
  accounting; writing it to disk is deliberately not in this package, and `report()` says so
  rather than looking empty when `models.accounting` is off.
- **What a provider advertises is printed, never believed.** `/models` entries carry a
  `capabilities` map (`tool_calling`, `vision`, …). It is reported as what the provider says,
  beside what a real call showed, and nothing in the module decides anything from it. A
  capability the provider does not mention (`None`) stays distinct from one it denies
  (`False`); a capability that could not be established is *absent* rather than false, so
  "the probe failed" can never be read as "the model cannot".
- **The role's model is the owner's choice and is called as it is; a fallback is entered only
  on evidence.** A model is probed before it may answer a call in place of the primary, and
  only where the probe *showed* it covers what that call needs. A candidate that cannot be
  probed is skipped with the reason in the failure; one with no key is skipped naming the
  variable that was looked for. The same `verdict()` rule is what `verify-model` prints, so
  the report and the call path cannot disagree about what "compatible capability" means.
- **`needs` are read from the request.** Offering tools needs a model that can call them; a
  message carrying an image part needs one that can see. `needs_of()` derives it, so no
  caller can forget to declare it.
- **Retries are bounded and classified, not guessed from a sentence.** `ChatError` carries
  the HTTP status, whether another attempt could succeed (429, 5xx, a dropped connection, a
  timeout) and the provider's own `Retry-After`; 401/403/400 are the provider's answer and
  are taken at their word. Three attempts per model, backoff 1 s→8 s, and the whole chain
  bounded by `budget_for(timeout)` — the same number the turn uses as its outer wait, so the
  two cannot disagree about how long a turn may take.
- **A stop is honoured between requests, never in the middle of one.** A cancelled call
  raises `Canceled` (a `ChatError`, so every existing surface reports it) and says a request
  already on the wire may have been served. The web channel has no cancel control yet — the
  seam is here and the UI is W6.
- **The pre-registry names keep working, and say exactly what they still decide.**
  `llm.base_url` still decides the address of the provider named `local` while
  `models.providers` is still the shipped list; `llm.model` decides the default model while
  `models.default` was never set; `llm.api_key` answers for the *first* provider only, and
  only when its `key_env` finds nothing (the owner's key is in `keys.env` under
  `ONEIRO_LLM_API_KEY`, which the shipped `key_env` does not name). Writing an owned provider
  list ends the first rule. All three stay declared and read, and go in W9 as already
  planned.
- **`key_env` is a real lookup, not a comment.** `config.env_value(name)` resolves a name the
  catalog does not declare through the layers a secret falls through (the owner's keys file,
  then the environment, then the project `.env`), which is what makes a provider record able
  to name its key without storing it. A provider address that carries credentials is refused
  by name at read time, because a key must not travel in a URL.
- **The model settings are in force, and the honesty check moved with them.** The five
  `models.*` keys left `pending`; the check that a pending key acts behind the page now uses
  `skills.auto_use`, which is still declared-only, so both directions of that rule stay
  exercised.
- **One test was repaired, not weakened.** `test_the_app_starts_the_clock_when_it_is_asked_to`
  asserted the state seen at the *first* poll after the task appeared, while the clock's own
  turn creates the task and then runs it for a few milliseconds; the registry adds ~1 ms to a
  call (measured), which was enough to flip that coin deterministically. It now waits for a
  terminal state within the same 3-second deadline and still asserts `completed` and the
  schedule label.
