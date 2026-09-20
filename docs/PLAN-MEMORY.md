# PLAN-MEMORY — the persistent-memory line (draft, being interrogated)

> Status: **draft**. This file is a protocol of decisions, not a task list. It is
> filled in while the owner is interrogated branch by branch; anything not yet
> decided is listed at the end as an open branch, and nothing in the open list is
> executed. Supersedes the "harness" line, which is frozen (see Non-goals).
>
> Owner's rule in force while this file is written (`_memory/HARD_RULES.md` H25):
> a plan presentation ends with its open decisions, never with a request for a
> verdict.

## Goal

An agent that remembers itself over time. Its life and its experience live in the
OSTIS graph as typed nodes and relations; state is carried from one session to the
next; before acting, it retrieves its own past; and for any thing it did it can
answer "why" out of its own record. It is judged on memory and on behaviour, not
on tokens.

Origin, in the owner's words (2026-08-15, the first statement of the project):
"накопление опыта, персистентность, понятие времени"; the failure it answers:
"ИИ не знает, почему писал прошлый ответ... контекст это скорее как чел с
амнезией, который просыпается перед дневником".

## Confirmed decisions

| # | decision | decided | reason |
|---|---|---|---|
| D1 | Main line is memory and experience in the graph; the harness line is frozen as a recorded trace | 2026-09-20 | The harness search optimizes what the papers already optimize (Meta-Harness, SoL-Pi), and touches neither persistence, nor time, nor the graph |
| D2 | A **session** is one agent run, from start to stop | 2026-09-20 | Exact boundaries, no dependence on people or calendars, measurable |
| D3 | What is carried between sessions is a **full self-model with a confidence value per skill** | 2026-09-20 | The owner wants the agent to have a model of itself, not just a fact log |
| D4 | The main measurement is **existing public benchmarks**, first of all LongMemEval (large part of it), compared against a flat store and against no memory | 2026-09-20 | Numbers must stand next to published ones instead of being invented; the comparison isolates the graph's contribution from the model's |
| D5 | **Freshness is an expectation, never evidence** (H26): a record carries when it was written and how long it is expected to hold, and nothing may be stated as current truth past its shelf life | 2026-09-20 | The owner hit this in practice: "quota exhausted today" is a day-long expectation, "version X is current" needs no recheck until a new version appears |
| D6 | Shelf life is a **retrieval policy, never deletion**: expired records stop surfacing by default and remain in the graph as history | 2026-09-20 | Matches never-destroy; matches Zep's closed validity window instead of deletion |
| D7 | The judge's powers over memory are exactly three: **close** (a validity window contradicted by a later record), **extend** (keep alive what was retrieved and useful), **cancel** (mark a record that was wrong) | 2026-09-20 | Keeps history intact; rewriting and merging are refused because history is the main argument in front of a jury |
| D8 | The judge runs **at the end of every session**, and may also run on its own during work | 2026-09-20 | Bound to the session boundary the owner already chose; a self-triggered pass is allowed but is not the default |
| D9 | The invented world stays as an **internal test bench**; its island/workshop themes never appear in the story, and the bench is meant to be replaced by the agent's real work later | 2026-09-20 | The themes were introduced by the agent on 2026-09-18 without an owner decision and the owner read them as "little things running around"; the bench keeps the free, noiseless behaviour measurement that a benchmark cannot give |
| D10 | Benchmark models are chosen by **measured durability** on the local OmniRoute proxy (`:20128`), never from its catalog | 2026-09-20 | The catalog lists 306 models; a probe of the 83 free-looking ones answered 15. A catalog entry is a claim, not a working set (H26) |
| D11 | The benchmark compares **three bases**: full context, flat records, no memory | 2026-09-20 | Full context is the benchmark's own standard base, flat records isolate the graph's contribution, no memory is the floor |
| D12 | The first thing the jury sees is the **session feed with a growing curve** | 2026-09-20 | It answers "what is this" without words before any number is quoted |

## The memory model (consequence of D5-D8)

Every record is a graph node, not a row. Fields:

| field | meaning |
|---|---|
| kind | key action, work result, session takeaway, self-model entry |
| source | the episode or session that produced it (provenance, never optional) |
| created | session number plus real time |
| shelf life | how long it is expected to hold, from a rule set by kind (see open branch OB1) |
| validity window | for facts: valid from / valid to, where "to" is closed by the judge on contradiction |
| confidence | for self-model entries: the agent's own claim about itself |
| state | live, expired, cancelled, contradicted-by |

Two retrieval keys, in this order: **time first** ("what was true then", "what
holds now", "what happened in that session"), **similarity second**. This is the
owner's formulation: memory as *when was it*, not only *what is relevant*.

## Prior art, and what is ours

| work | what it already does | source |
|---|---|---|
| Zep / Graphiti | bi-temporal fact graph; contradiction closes an edge's validity window instead of deleting it; point-in-time queries | arXiv 2501.13956 (2025-01) |
| Generative Agents | retrieval as relevance x recency (exponential decay) x importance | 2023 |
| MemoryBank | Ebbinghaus forgetting curve with reinforcement: what is recalled more often lives longer | 2024 |
| 2026 industry writing | "forgetting by design", TTL for episodic memory, memory eviction: an agent that remembers everything recalls badly | design guides, Mem0 blog |

Ours is not the mechanism. Ours is the **judge**: an explicit reviewer that walks
the whole memory as a pass, decides close/extend/cancel, and leaves every decision
in the graph with its reason, so the decision can be replayed and argued. Plus the
memory lives in a typed semantic graph with an ontology and mandatory provenance.

## Model durability instrument (2026-09-20)

`_scripts/model-durability-probe.py` probes which OmniRoute models actually
answer, how fast and how often, and appends every run to
`_scripts/model-durability.json` so durability becomes history rather than a
snapshot. First run (2026-09-20, free-looking slice, one call each):

| measurement | value |
|---|---|
| models in the catalog | 306 |
| free-looking slice probed | 83 |
| answered all calls | **15** |
| failure modes seen | HTTP 400/401/403/404/429/502/503, timeouts |
| usable at that moment (examples) | `dahl/MiniMaxAI/MiniMax-M2.7`, `vyceai-com/deepseek-v4-flash`, `anymodel-org/ag/gemini-3-flash`, `anymodel-org/ag/gemini-2.5-flash-lite`, `auto/cheap`, `auto/gemini` |

Consequence for the run: pick a primary from models that survive several checks,
keep a fallback chain, and record which model actually served each call. A row
of results belongs to one model; if that model dies mid-row the row is re-run and
labelled, never silently mixed.

## Freshness in this workspace (owner instruction, 2026-09-20)

The same rule now applies to the workshop's own knowledge, not only to the
project: a claim about the world (a quota, a version, a service state, a model
capability) carries an expected lifetime and must be re-verified at its source
before being repeated as fact. Recorded as H26.

## Verification discipline to reuse (already built, currently frozen with the harness)

Frozen acceptance rules per experiment; at least three runs per task before any
number is quoted; a measured noise floor; held-out tasks never touched by the
search; a ledger of what each experiment cost; corrections written beside what
they correct rather than instead of it.

## Open branches (nothing here is executed)

- **OB1** Shelf-life rule set: which kinds of record get which expected lifetime,
  and who owns the table.
- **OB2** Self-model calibration: how a claimed confidence is checked against
  measured performance, and what happens to the self-model when they disagree.
- **OB3** Key-action granularity: every step, every decision, or only actions the
  agent marks as key; and who marks them.
- **OB4** How the agent's own life and the benchmark fit together: the world gives
  behaviour, LongMemEval gives memory quality, and the plan must say which one is
  the story and which one is the instrument.
- **OB5** Benchmark budget: how much of LongMemEval is run, with what model and
  provider, and what is done when the provider refuses.
- **OB6** The single thing the jury sees first.

## Non-goals

No harness development (rounds, criteria versions, harness policy search stop
here; `docs/harness.md` and `harness/` stay as the record of what was measured).
No facade. No claim without a run behind it. No deletion of anything, ever:
expiry is a retrieval policy. No scale claims beyond the tasks actually measured.
