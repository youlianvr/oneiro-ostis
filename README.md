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

## Status

- Living OSTIS stack: sc-machine, C++ ScAgents, sc-web, one graph.
- Memory benchmark in `docs/results.md`; harness series in `docs/harness.md`
  (candidates judged by replay, winners measured online).
- Organization layer runs live: three roles on real models, restart-aware
  loop, isolated worktrees, unmerged PR packets, dashboard feed.
