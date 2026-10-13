# Oneiro-OSTIS

## Architecture and Status — v1 Rewrite Complete (2026-10-10)

The product architecture has been unified under [MASTER-PLAN](docs/MASTER-PLAN.md)
(packages W0 through W9 closed and verified).

Standalone installation & execution:

```bash
uv sync --locked --group dev
uv run --locked oneiro doctor  # checks runtime prerequisites & models
uv run --locked oneiro serve   # starts same-origin loopback server on 9899
```

The distribution packages `oneiro`, its web console static assets, compact skills catalog,
and configuration management:
- **Conversation:** 3-zone layout with live tools, provenance tracking, and cards.
- **Tasks & Schedules:** cron-like scheduled tasks, queued/running execution, quiet hours.
- **MCP & Skills:** local stdio and remote HTTP JSON-RPC MCP servers, deterministic skill indexing.
- **Models:** multi-provider LLM integration with capability probing, automatic fallback, and usage accounting.
- **Languages & Themes:** full RU/EN localization, 5 themes meeting WCAG 2.2 AA contrast standards.
- **Installer:** Windows Inno Setup payload preserving user data and knowledge graph on upgrades.

All legacy prototype scripts, unrouted channels, and provisional harnesses have been cleanly retired.


## Historical implementation and scientific record

**Oneiro-OSTIS** is a persistent intelligent agent whose autobiographical experience lives natively in an OSTIS knowledge graph — and which improves itself by *dreaming*: while the agent sleeps, alternative strategies are proposed by an LLM and judged by **exact replay over the recorded experience tree**. The winning strategy is deployed online; the tree of discoveries grows; the loop repeats.

Pattern: *Dream-RSI* (2026) — "accumulated history is already a simulator of the world." Our angle: the OSTIS semantic graph is that exact symbolic simulator.

## Architecture

```text
knowledge-base/     experience ontology: Discovery, Attempt, numeric Outcome,
                    Temporal/Causal links, Strategy, DreamCycle — the discovery tree lives here
problem-solver/     C++ ScAgents: RecordAttempt, RetrieveAttempt, ReplaySubtree, DeployStrategy
python/
  adapter_llm/      strategy generator — OpenAI-compatible (base_url + key, any provider)
  world/            deterministic mini-world with numeric outcomes per step
  replay/           exact replay over the recorded tree (zero executions)
  metrics/          baselines (context-only, flat store), metrics, results table
  llm.py            model access for the three roles (retries, fallbacks, budget)
  roles.py          researcher (options) and manager (one decision) prompts
  worker.py         bounded tool loop inside one isolated worktree
  swarm.py          role protocol: who may do what, and what stops the cycle
  heartbeat.py      one bounded cycle from session to PR packet
  worktree_runner.py  isolated branch, allowlisted check, PR evidence
  life_loop.py      restart-aware loop: cycles, budget, freeze reasons, journal
dashboard/          light Russian control panel (buttons, feed, measurements)
plugins/oneiro-life OpenClaw plugin: gateway lifecycle into the graph
interface/          sc-web — the knowledge graph as live proof
tests/              determinism, replay exactness, core loop, dream improvement
```

## Install

Two routes, both local, neither needing an account.

From a source clone:

```bash
uv sync --locked --group dev          # dependencies from uv.lock
uv run --locked oneiro doctor         # runtime prerequisites, models, graph
uv run --locked oneiro serve          # the product: 127.0.0.1:9899
```

For a packaged Windows install, `installer/` builds it: `installer/build-payload.ps1`
assembles the payload (embeddable Python with its pinned dependencies, the Oneiro
sources, the ontology, the graph image, the launchers, `LICENSE` and `NOTICE`), and
Inno Setup turns that payload into `OneiroSetup-0.2.0.exe` — per-user, no
administrator rights, no autostart, Docker Desktop required, and neither
`%USERPROFILE%\.oneiro` nor the graph volume is an uninstall target. The payload's
contents and the attribution it must carry are pinned by
`tests/test_installer_payload.py`; `docs/ACCEPTANCE-REPORT.md` carries the frames
from a real run.

The CowAgent console route — `scripts/install.py` unpacking
`console/vendor/cowagent-2.1.9.zip` and applying `console/overlay/` — was retired
with the v1 rewrite and left the repository on 2026-10-13; the product's console is
its own file set in `python/oneiro/static`, served on the same origin.
`docs/HOST.md` is the dated record of that earlier host.

After that there is one address: **http://127.0.0.1:9899** — the chat, the
*Настройки Oneiro* page and the graph panel at `/oneiro/` on a single origin.
The model and its API key are set on the settings page; nothing answers in the
chat until they are.

## First run

An unconfigured product says so instead of pretending: while the model, the
graph stack or the panel is not answering, the chat carries a red bar naming
what is missing, and **http://127.0.0.1:9899/setup** is the page that reads
live state and offers to fix each piece — the model credentials (saved into the
console *and* into the Oneiro panel settings, checked against the provider with
one real one-token call), and the graph stack (`docker compose up -d`).

It is not a one-time wizard. Every answer comes from state read at the moment
of asking — the console's own config, the panel's settings API, a TCP connect
to sc-machine — so when the environment later breaks, the chat bar and the
setup page come back on their own and name the piece that broke.

The graph panel at `/oneiro/` reads its snapshot in the background: the first
open shows a live count of the read (minutes on a graph as large as this one's)
instead of an error, then the numbers, and later visits are instant.

## Principles

- **No facades.** Demo and deliverables contain nothing the system does not actually do.
- **Exact dreaming.** The world is deterministic; every step's outcome is recorded in the graph; replay executes nothing.
- **Provider-agnostic LLM.** Strictly base_url + key; any OpenAI-compatible endpoint.
- **OSTIS-native memory.** Experience is sc-elements and ScAgents — not an external database.

## The living organization

The project also runs as a small autonomous organization whose memory is this
same graph:

- **researcher** proposes 2 to 4 options from the project's own dossier;
- **manager** picks exactly one with acceptance criteria, or stops the cycle;
- **worker** makes the change inside a real git worktree, runs the allowlisted
  check, and leaves an **unmerged PR packet** for a human.

Nothing merges, pushes, or approves itself. Each cycle writes role-tagged
records into OSTIS; the loop reads that journal before proposing again, so a
long-lived run stops rediscovering the same weakness.

```bash
python python/life_loop.py --cycles 2        # one bounded run, no merge, no push
```

The dashboard at `http://localhost:8130` shows the organization feed
(`/api/swarm`): roles, proposals, the manager's decision, PR packets, freeze
reasons. Worktrees stay under `~/.openclaw/worktrees/` as evidence.

OpenClaw hosts the long life: `plugins/oneiro-life` records the gateway's own
lifecycle into the graph and runs in the isolated `--dev` profile; see its
README for the install commands. The night run that produced this layer is
documented in `docs/GOAL-LIVE-SWARM.md`.

## Layout

- `docs/PLAN.md` — historical implementation plan (superseded by
  `docs/MASTER-PLAN.md`).
- `docs/PROGRESS.md` — per-stage execution log.
- `docs/ACCEPTANCE-REPORT.md` — the v1 acceptance bundle: artifact hashes, live-check exit
  statuses, and the list of what was not verified; the pictures it cites are in
  `docs/shots/oneiro-v1/`.
- `docs/GOAL-LIVE-SWARM.md` — the live-swarm goal, its run log and evidence.
- `docs/ARCHITECTURE-HYBRID.md` — where Oneiro, Hermes and OpenClaw meet.
- `docs/PLAN-V2.md` — historical: the `v2` branch's original intent. The product
  is bilingual RU/EN with a switch, per `docs/MASTER-PLAN.md` section 1.
- `docs/pz/` — the research work for the school competition (markdown source,
  Word and PDF builds, dashboard figures). Rebuild with
  `python scripts/pz-build.py` then `python scripts/pz-word.py`; the numbers in
  it come from the artifacts listed in its appendix В.

## Status

- Living OSTIS stack: sc-machine, C++ ScAgents, sc-web, one graph.
- Memory, offline comparison in `docs/results.md`; the public benchmark
  (LongMemEval, graph against a flat journal and against no memory) in
  `bench/memory/` with its measured numbers in `docs/PROJECT-CONTEXT.md` § 4.5;
  harness series in `docs/harness.md` (candidates judged by replay, winners
  measured online).
- The v1 product is one package, `python/oneiro/`: agent loop, MCP hub, skills, memory,
  research, schedules and the console, plus the installer. The office layer that used to run
  here — three roles on live models, worktrees and unmerged PR packets — was retired with the
  modules that carried it; its place is taken by tasks and schedules the owner sets.
- Acceptance for v1 is `docs/MASTER-PLAN.md` § 6, evidenced row by row in
  `docs/ACCEPTANCE-REPORT.md`; `docs/PROGRESS.md` closes with what is left after v1.

## License

MIT © 2026 Niko — the full grant is in [LICENSE](LICENSE), and the
`Distributed under the MIT License` headers already carried by
`problem-solver/` agree with it. `pyproject.toml` declares the same SPDX
expression.

Third-party material keeps its own terms regardless of this choice: CowAgent
2.1.9, the OSTIS example-app scaffold, sc-machine and py-sc-client are MIT.
The attribution obligation of `docs/DECISIONS-v1.md` § 1.6 is discharged by
[NOTICE](NOTICE), which the installer payload carries beside `LICENSE`.
`knowledge-base/ims.ostis.kb` has no upstream license at all, so it stays
untracked in this repository and out of the installer payload.
