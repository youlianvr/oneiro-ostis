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
interface/          sc-web — the knowledge graph as live proof
tests/              determinism, replay exactness, core loop, dream improvement
```

## Principles

- **No facades.** Demo and deliverables contain nothing the system does not actually do.
- **Exact dreaming.** The world is deterministic; every step's outcome is recorded in the graph; replay executes nothing.
- **Provider-agnostic LLM.** Strictly base_url + key; any OpenAI-compatible endpoint.
- **OSTIS-native memory.** Experience is sc-elements and ScAgents — not an external database.

## Layout

- `docs/PLAN.md` — implementation plan and current stage status.
- `docs/PROGRESS.md` — per-stage execution log.

## Status

Stage 1 (living stack) — in progress.
