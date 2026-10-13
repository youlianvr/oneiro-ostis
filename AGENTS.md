# AGENTS.md — Oneiro-OSTIS

> Working contract for **this folder**. It travels with the published repository, so it
> repeats the few workspace rules that must survive outside the workspace and adds the
> ones this project has of its own. `README.md` tells the product's story; this file tells
> you how to work on it without breaking it.

## What this is

Oneiro — a local persistent assistant whose memory is an OSTIS knowledge graph. One Python
package (`python/oneiro/`), a web console served same-origin on loopback, an installer for
Windows, and the graph stack underneath. Everything is local: no accounts, no telemetry, no
network service of our own.

**v1 is done when a person, without the author, can install Oneiro on Windows, open its own
window, have a conversation, see every tool call and every pending approval, connect an MCP
server, find a skill, put a task on a schedule, switch language and theme, and close and
reopen it — while no screen shows JSON, no panel lies, no undeclared capability runs, and no
retired module takes part in the work.** Acceptance is `docs/MASTER-PLAN.md` § 6, evidenced
row by row in `docs/ACCEPTANCE-REPORT.md`. No evidence, no row.

## Commands that work (verified on this machine 2026-10-13)

```bash
uv sync --locked --group dev          # dependencies from uv.lock; do not hand-edit uv.lock
uv run --locked oneiro doctor         # runtime prerequisites, models, graph
uv run --locked oneiro serve          # the product: 127.0.0.1:9899 (window, or --no-window)
python -m pytest -q                   # 805 passed, exit 0 (~4 min)
python -m mypy python                 # 47 source files, no issues, exit 0
python scripts/install.py --check     # what the install already has; changes nothing
python scripts/install.py             # the whole install path; safe to run again
```

The whole command line is one parser: `doctor`, `serve` (default), `verify-model`, `settings`,
`tasks`, `schedules`, `mcp`, `skills`, `research`, `office`, `hooks`, `drafts`. `python
python/config.py` is a compatibility shim that forwards to `oneiro settings`.

`mypy` is configured (`pyproject.toml`) to check `python/oneiro`; the stand in `bench/memory/`
resolves its imports through `sys.path` and is outside that scope, so treat a mypy failure
there as a finding about the stand, not a green build to be forced. The stand has its own
tests and passes them.

## Tests

- `tests/test_*.py` (48 files) run under `pytest`; `tests/chat_fakes.py` is a shared helper.
- `tests/live_*.py` (16 files) are **opt-in live checks** that need a running stack and real
  credentials. `pytest` does not collect them: a green `pytest` run is not evidence that they
  pass, and a broken one is not a broken suite. Run the one you name and report its own exit
  code.
- `tests/installed_smoke.py` and `tests/i18n_measure.py` are runners/measurements, not tests.

Never make a check green by weakening an assertion, skipping a test, swallowing an error or
adding a type/lint suppression. Fix the cause; if the requested behaviour itself requires
changing a check, say why and verify the behaviour directly.

## The graph is the memory — do not destroy it

- `docker compose up -d` brings the stack up: sc-machine on 8090, sc-web on 8000.
- The compose file's `stop_signal: SIGINT` and `stop_grace_period: 90s` are a measured pair,
  not decoration: sc-memory registers a SIGTERM handler that does nothing, so the default
  `docker stop` killed the process mid-write and lost every record since the last save.
  SIGINT runs the native save (about ten seconds). Leave both settings alone, and keep
  `scripts/docker_entrypoint.sh` using `exec sc-machine` — without the `exec` the signal
  never reaches the graph and the 90 s grace gets SIGKILLed.
- `REBUILD_KB=0` on a normal start: the existing graph on the `kb-binary` volume is kept. A KB
  rebuild happens only on an empty volume or on an explicit owner request (`REBUILD_KB=1`,
  `scripts/reset_stack.sh --yes`) — it wipes memory.
- Never `docker compose down -v`, never remove the `kb-binary` volume, never delete graph
  files. Removal anywhere in this folder is **trash-only**; the memory is the one artifact
  with no copy.

## Product invariants

A change that breaks one of these is a bug even if every check stays green.

- **No facade.** Nothing that appears to work may be a mock; a demo contains only what the
  system actually does.
- **No JSON on a screen.** Panels show states, counts and names in the user's language. The
  `--json` flags of the command line are for machines and are not a screen.
- **No panel lies.** An unavailable piece says it is unavailable and names itself; a refusal
  gives its reason; an unknown outcome (a write that may or may not have landed) is reported
  as unknown, never as success.
- **No undeclared capability runs.** Every action is either inside the declared permissions or
  waits for an approval that shows its exact arguments.
- **Retired modules stay retired.** The v1 rewrite removed the old channels, bridge and
  prototype scripts on purpose; do not resurrect them or route work back through them.
- **Everything disputable is a setting with a visible default**, not a hardcode.
- **Language:** Russian with the owner in conversation, English in repository documents.

## Layout

| Path | What lives there |
| --- | --- |
| `python/oneiro/` | the product: agent loop, chat, tools, MCP hub, skills, memory, recall, records, schedules, tasks, proactive, drafts, hooks, office env, models, settings, web/pages/static, graph worker, checkpoints, i18n, migration |
| `python/oneiro/dream/` | the record-and-judge machinery the memory stand uses; not part of the v1 interface |
| `console/` | the retired CowAgent route: the upstream archive in `vendor/` and the overlay manifest. The v1 console is the product's own — `python/oneiro/static`, served on 9899 |
| `installer/`, `scripts/build_installer_payload.py` | the v1 Windows install path: the payload builder, the Inno Setup script, the launchers |
| `tests/` | 48 unit/integration suites plus the 16 opt-in live checks |
| `bench/memory/` | the measured memory comparison (LongMemEval: graph vs flat journal vs no memory) — its own README, its own sc-server container |
| `harness/` | candidate strategies judged by replay (`docs/harness.md`) |
| `scripts/` | build, probe, install and document tooling |
| `knowledge-base/` | the experience ontology; `ims.ostis.kb` stays untracked (no upstream license) |
| `docs/` | plan, state, evidence, talk and paper material |

## Where the truth lives

- **Current plan:** `docs/READY-2026-10-12.md` (its readiness table decides where plans
  disagree). **v1 plan of record and § 6 acceptance:** `docs/MASTER-PLAN.md`.
- **Evidence for the acceptance rows:** `docs/ACCEPTANCE-REPORT.md` — artifacts, hashes, live
  exit statuses, and what was *not* verified.
- **State and next step:** `docs/PROGRESS.md`. Read it before starting, close it when done.
- **Decisions and the borrowing audit:** `docs/DECISIONS-v1.md`.
- **Measured numbers:** `docs/PROJECT-CONTEXT.md` § 4.5, `docs/results.md`, `bench/memory/README.md`.
  A number in prose or on a slide must be traceable to the run that produced it.

## Secrets

`.env` and `.env.*` are ignored and must stay that way: keys are never committed, never
printed, never put on a screen. The model and its key are set by the owner in the console /
settings page; nothing answers in the chat until they are set, and an unconfigured product
says so instead of pretending.

## Publishing

This folder is published **by subtree** to `youlianvr/oneiro-ostis`, branch `main`, from the
workspace root. Only this folder — a subset remote must never receive the workspace root.
A push needs an explicit request, and one authorization covers one push.

Not everything on disk belongs in the repository: runtime artifacts stay out (`kb.bin/`,
`logs/`, `.runtime/`, `dist/`, `installer/payload/`, `.env*`, `graph-writer.lock`, `_tmp/`,
`state/`, `worktrees/`).

Licensing: MIT (`LICENSE`). Third-party attribution lives in `NOTICE` and is carried in the
installer payload — `tests/test_installer_payload.py` fails if it is missing.

## Working in this folder

- Read the current version of a file before editing it, and use the smallest edit that
  addresses the cause.
- Preserve edits you did not make; a dirty tree is not a reason to stop, but it is a reason
  not to stage broadly.
- One Oneiro process holds the runtime at a time (`oneiro/ownership.py`); a second command
  either waits or is pointed at its own `ONEIRO_DATA_DIR`.
- Local commits in small logical units are the working checkpoint; a push is a separate,
  explicitly requested act.
- `scripts/install.py` belongs to the retired CowAgent console route and no longer runs: its
  step 3 applies `console/overlay.py`, which `adf76694e` ("Land the Oneiro v1 rewrite and
  retire every module it replaced", 2026-10-11) deleted along with the overlay itself. The
  install path the acceptance report actually evidenced is the payload one
  (`scripts/build_installer_payload.py` → `installer/oneiro.iss`), and the `installed-*`
  frames plus `tests/live_w8_check.py` are its evidence. `README.md` still describes the
  retired command in its "Install" section — read it as history, not as instructions.
