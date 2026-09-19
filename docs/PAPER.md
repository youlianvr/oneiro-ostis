# Oneiro-OSTIS — dreaming over a recorded experience tree in an OSTIS knowledge graph

> Working paper draft. Every number in this document comes from a run of the
> committed code against the live stack; the artifacts are `docs/results.md`,
> `docs/rounds.md` and `docs/demo-log.md` (all generated, none hand-written).

## 1. Idea

An agent's experience is recorded natively in an OSTIS knowledge graph: every
attempt it makes (action, object, outcome, numeric score, world state before
the action, legal actions before the action, producing strategy) becomes a
first-class sc-node linked by provenance and chronology relations. While the
agent "sleeps", it **dreams**: candidate strategies are proposed, each one is
judged by **exact replay over the recorded experience tree** — the judge walks
the recordings and never executes the world — and the winner is deployed into
the next online round.

The claim under test is behavioural, not philosophical: *an agent that
replays its own recordings can measurably improve its next day without
touching the environment during the dream.*

## 2. The world (the judge's ground truth)

A deterministic island expedition (`python/world/`, seed `oneiro-0`):

- 9 locations, 8 dig sites; travel costs −0.1 per step; 40-step budget;
- each site hides a fixed number of artefacts with fixed per-seed values;
- digging takes one artefact (carrying blocks digging); delivering converts
  the artefact into score × delivery multiplier: camp 1.0×, beach 1.2×,
  cove 1.5×;
- the world is fully deterministic and process-stable (sha256-derived values,
  no wall-clock, no `PYTHONHASHSEED` dependence — regression-tested).

Because the world is deterministic, the same seed observes identical values
in every run: recordings are comparable across days, and a replay that
matches a recording is exact by construction.

## 3. The graph schema

C++ agents (`ScAgent` API of sc-machine 0.10.5) do the core work:

- `action_record_attempt` — creates the attempt node (class `concept_attempt`),
  links subject/action/object/outcome, chains `nrel_prev_attempt`;
- `action_retrieve_attempts` — returns all attempts of a subject, and the
  bridge orders them along the chronology chain.

The Python bridge enriches each attempt with `nrel_source`, `nrel_kind`,
`nrel_score`, `nrel_timestamp` and the trajectory fields the dream replays:

```
nrel_episode      -> episode_<id>          (an episode is a graph entity)
nrel_step_index   -> integer link
nrel_state        -> string link (JSON: location, carrying, dug counts, score, step)
nrel_legal        -> string link ("travel:beach|dig:beach|…")
nrel_strategy     -> strategy_<name>
nrel_note         -> string link (human-readable step note)
```

Strategies are graph entities of class `concept_strategy`:
`nrel_strategy_descriptor` (JSON), `nrel_strategy_replay_score`,
`nrel_strategy_online_score`, `nrel_derived_from`, `nrel_dream_round`.

The result is a full "experience tree": episodes → steps → states → outcomes,
plus the dream history (every proposed strategy with its judged score and,
for deployed ones, its measured online score).

## 4. Memory experiment (stage 3): what the graph preserves

`python -m metrics.build_table` → `docs/results.md` (live stack, 25-step
episodes; recall — retrieved/recorded; order — adjacent-pair agreement with
occurrence-matched repeats; provenance — source/kind survive; contra —
retrieved records absent from ground truth):

| episode | recall | order | provenance | contradictions |
|---|---|---|---|---|
| context-only (window of 3) | 0.12 | 1.00 | 0.00 | 0 |
| flat store (unordered list) | 1.00 | 1.00 | 0.00 | 0 |
| **OSTIS memory** | **1.00** | **1.00** | **1.00** | 0 |
| OSTIS, temporal chaining ablated | 1.00 | **0.58** | 1.00 | 0 |
| OSTIS, provenance ablated | 1.00 | 1.00 | **0.00** | 0 |
| random floor | 0.00 | 0.00 | 0.00 | 0 |

The ablations are real switches, not cosmetics: the temporal ablation passes
`concept_no_temporal` as the fifth argument of the C++ action (the agent skips
`nrel_prev_attempt` chaining), the provenance ablation drops `nrel_source` at
write time. Retrieval latency is ≈60–100 ms per attempt.

## 5. The dream cycle (stages 4–5)

```
day:      strategy acts in the world  ->  every step recorded (C++)  ->  graph
explore:  two survey walks widen the recorded transition coverage
dream:    proposals -> exact replay judge -> winner persisted
deploy:   the winner acts the next day; its measured score goes onto its node
```

The judge (`python/replay/engine.py`) works on the recordings only:

- transitions are indexed by the *outcome-sufficient* signature
  (location, carried artefact, artefacts already taken from the current site)
  plus the qualified action — this signature fully determines the world's
  outcome for travel/dig/deliver in this world;
- at each step the candidate chooses among the *recorded* legal actions;
- a diverging choice is looked up anywhere in the tree; if the transition was
  recorded, its recorded outcome is taken and the walk continues from that
  recording's successor state;
- an unrecorded choice **truncates** the episode ("uncovered") — the judge
  never invents an outcome, and reports coverage for every candidate.

Tests that pin this down: `tests/test_replay_offline.py` (tree construction,
exactness, divergence, truncation, and replay with `ExpeditionWorld.step`
patched to raise — *zero executions*), `tests/test_replay_exactness.py` (same
property against live recordings; tolerance 1e-4 because scores are stored as
float32 sc-links), `tests/test_dream_improves.py` (the deployed winner beats
the incumbent in the measured online round).

Candidate generation: a deterministic sweep (site orders × dig limits ×
delivery preferences) plus an OpenAI-compatible LLM adapter
(`python/adapter_llm/`, `ONEIRO_LLM_BASE_URL`/`_API_KEY`/`_MODEL`), with strict
JSON-schema validation and automatic fallback to the sweep. The papers'
numbers below were produced by the offline sweep.

## 6. Results

### 6.1 Recursive loop — `python -m loop > docs/rounds.md`

| round | strategy | measured score | dream winner | replay verdict |
|---|---|---|---|---|
| 1 | weak_wander | 137.5 | cand_alpha_d4 | 933.2 over 3 episodes, coverage 1.00 |
| 2 | cand_alpha_d4 | 252.4 | cand_alpha_d4 (kept) | 1778.3 over 6 episodes |
| 3–5 | cand_alpha_d4 | 252.4 | kept | estimates keep widening with the tree (15 episodes, 600 steps) |

One dream moved the measured score from **137.5 to 252.4** and the policy then
stayed there — the value matches the best strategy found by exhaustively
running the whole candidate sweep in the world offline, i.e. the dream
reached the sweep's optimum, then the loop converged.

### 6.2 One-command demo — `python demo/run_demo.py` → `docs/demo-log.md`

- day 1 (`weak_wander`, 8 digs, 8 deliveries): **137.5**
- dream: 21 candidates replayed over 3 episodes / 120 steps / 76
  transitions in 9.1 s, 0 recording conflicts, winner `cand_alpha_d4`
- day 2 (`cand_alpha_d4`, 11 digs, 11 deliveries): **252.4**
- measured improvement: **+114.9 (+84 %)**, judged only from recordings,
  proven in the world.

## 7. Honest limitations

- The judge is conservative: a candidate whose decisions were never recorded
  is truncated, not extrapolated (its coverage column says so). This biases
  the dream towards strategies similar to the recorded ones — visible in the
  loop: proposals that were under-covered in round 1 won only after the
  exploration walks widened the tree.
- Recorded scores are float32 sc-links; replay equality holds to ~1e-7
  relative precision, not bit-exact float64.
- The LLM adapter is implemented and schema-validated but was **not**
  exercised in the numbers above (no provider configured); all reported
  candidates come from the deterministic sweep.
- The world is small and deterministic by design — that is what makes the
  *exact* replay judge possible. Scaling to stochastic environments would
  require the judge to handle conflicting recordings (the tree's consistency
  check reports them; currently: 0 conflicts).
- "Improvement" means the measured online score with the same world seed and
  budget; it is a controlled, single-world comparison, not a statistical
  claim across worlds.

## 8. Related work and novelty (bounded search)

Searches run 2026-09-19 via web search (queries: "OSTIS memory agent episodic
memory…", "OSTIS 'dreaming' replay self-improvement…", '"ОСТИС" ИЛИ "OSTIS"
эпизодическая память агента проект Ника', '"НИКА ОСТИС" ассистент', '"learning
by dreaming" replay experience agent self-improvement'):
- "Dreaming" as policy improvement inside a learned world model is the
  established Dreamer-style model-based RL line (search hits: 2025–2026 theses
  on "learning by dreaming"); there, dreaming *executes the learned model*.
- Graph-backed agent memory (episodic memory as structured event logs) is
  common industry practice (IBM/mem0/Atlan articles).
- The OSTIS ecosystem hits in the bounded search are knowledge-processing and
  semantic-technology works (BSUIR/Minsk), not experience-replay optimizers.

In-ecosystem prior art, checked explicitly as the plan demanded: **NIKA** is
an OSTIS-based intelligent dialogue assistant (BSUIR; Sadovsky 2023, "Model
for personalization of user interfaces", applied within NIKA) — semantic
assistant work, not an experience-replay optimiser. The OSTIS-2025
conference materials likewise cover knowledge-processing and design
automation. No OSTIS work was found that records an agent's full action
trajectory as graph entities and optimises it by exact replay.

Within this bounded search, no prior work was found that (a) records the full
trajectory of an agent natively in an OSTIS sc-graph and (b) improves the
agent by *exact replay over its own recordings* with (c) the deployed winner
measured online and (d) replay/online evidence stored back into the graph.
This is a bounded-search statement, not a certified novelty review.

The closest thing the authors themselves must not hide: a team could get the
same behaviour with any relational store. The specific contribution here is
the OSTIS-native formulation — the experience tree, the strategies and the
dream history are all sc-graph entities reachable from sc-web, and the judge
is a pure reading of that graph.

## 9. Reproducing everything

```bash
docker compose up -d --build            # stack (KB rebuilt from sources)
python -m pytest tests/ -q              # full suite (offline + live)
PYTHONPATH=python python -m metrics.build_table > docs/results.md
PYTHONPATH=python ONEIRO_ROUNDS=5 python -m loop > docs/rounds.md
python demo/run_demo.py                 # → docs/demo-log.md
```

Stack: sc-machine 0.10.5 (GitHub release binaries; conan eliminated),
sc-web 0.9.0, py-sc-client, Python 3.14, Docker. KB: the IMS common KB
(201 sources) + the Oneiro ontology.
