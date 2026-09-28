# Oneiro-OSTIS

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

## Install (one command, from a fresh clone)

```bash
python scripts/install.py          # the whole path; safe to run again
python scripts/install.py --check  # what is already in place, changes nothing
```

The console is CowAgent 2.1.9, whose archive ships in `console/vendor/`; the
installer unpacks it into `.runtime/cowagent` inside the project, builds its
virtualenv, applies the product's own console files from `console/overlay/`
(the Oneiro chat page, the settings page, the sidebar entry, the Russian
strings, the server routes they call), seeds the console config for the web
channel, wires the graph memory into the host, brings up the graph stack with
Docker, and puts an **Oneiro** shortcut on the desktop.

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

What the installer deliberately does not do: overwrite a console file someone
else has since edited (it refuses and says which), touch a config that already
exists, or download anything it already has.

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

- `docs/PLAN.md` — implementation plan and current stage status.
- `docs/PROGRESS.md` — per-stage execution log.
- `docs/GOAL-LIVE-SWARM.md` — the live-swarm goal, its run log and evidence.
- `docs/ARCHITECTURE-HYBRID.md` — where Oneiro, Hermes and OpenClaw meet.
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
- Organization layer runs live: three roles on real models, restart-aware
  loop, isolated worktrees, unmerged PR packets, dashboard feed.
