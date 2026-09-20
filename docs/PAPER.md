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
touching the environment during the dream.* It is tested on **two
structurally different deterministic worlds** (an island expedition and a
crafting economy) and over **eight independent runs**; every run improved
(§6.3).

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

### 6.1 Recursive loop, island — `python -m loop > docs/rounds.md`

| round | strategy | measured score | dream winner | replay verdict |
|---|---|---|---|---|
| 1 | weak_wander | 137.5 | cand_alpha_d4 | 933.2 over 3 episodes, coverage 1.00 |
| 2 | cand_alpha_d4 | 252.4 | cand_alpha_d4 (kept) | 1778.3 over 6 episodes |
| 3–5 | cand_alpha_d4 | 252.4 | kept | estimates keep widening with the tree (15 episodes, 600 steps) |

One dream moved the measured score from **137.5 to 252.4** and the policy then
stayed there — the value matches the best strategy found by exhaustively
running the whole candidate sweep in the world offline, i.e. the dream
reached the sweep's optimum, then the loop converged.

### 6.2 Second domain: the machinery transfers — `docs/rounds-workshop.md`

A second deterministic world (workshop crafting economy: five locations, three
resource nodes, recipes plank/ingot/rope and the combo item **cart**, worth
2.2x its components) exists to test that the dream loop is not an island
story. The judge contract is pluggable and tiny: a domain supplies
`signature(raw_state, action)` (workshop: location + full inventory + units
taken at the current node) and `observe(raw_state)`; the graph schema, the
recording path and the dream are shared.

| round | strategy | measured score | dream winner | replay verdict |
|---|---|---|---|---|
| 1 | ws_weak_plank | 16.6 | ws_cart_wof | 237.6 over 3 episodes, coverage 1.00 |
| 2 | ws_cart_wof | 79.2 | kept | — |
| 3 | ws_cart_wof | 79.2 | kept | per-episode replay 79.2 = measured 79.2 |

One dream lifted the measured score **16.6 → 79.2 (4.8x)** and then converged;
the candidate sweep and the judge never touched the world during the dream.
Notable honest observations: in this domain the gather *order* does not matter
(all resource nodes are one hop from the shop hub — the sweep discovered the
tie), and the replay judge was exact here (per-episode estimate equals the
measured online score) whereas on the island it over-estimates (see the
calibration section).

### 6.3 Multi-seed series — `docs/series.md`

Eight independent runs (5 island seeds, 3 workshop seeds, 3 rounds each,
online scores measured):

| domain | seeds improved | delta mean / median / min / max | ratio mean | judge bias (replay − measured) | conflicts |
|---|---|---|---|---|---|
| island | **5/5** | +77.8 / +88.0 / +14.7 / +114.9 | 1.58x | +56.9 (≈29.7% rel.) | 0 |
| workshop | **3/3** | +49.3 / +42.8 / +42.6 / +62.6 | 6.97x | +11.3 (≈22.9% rel.) | 0 |

Every seed improved after a single dream; the judge's replay estimate is
*positively biased* (it can follow recorded transitions that score better
than the episode they started from), yet its ranking survived the bias in all
eight runs — each deployed winner beat its incumbent. The honest lower bound
of the method on these worlds is the island seed `oneiro-1`: +14.7 (1.12x).

### 6.4 One-command demo — `python demo/run_demo.py` → `docs/demo-log.md`

- day 1 (`weak_wander`, 8 digs, 8 deliveries): **137.5**
- dream: 21 candidates replayed over 3 episodes / 120 steps / 76
  transitions in 9.1 s, 0 recording conflicts, winner `cand_alpha_d4`
- day 2 (`cand_alpha_d4`, 11 digs, 11 deliveries): **252.4**
- measured improvement: **+114.9 (+84 %)**, judged only from recordings,
  proven in the world.

### 6.5 RSI harness: the same cycle over a real coding agent — `docs/harness.md`

The island searches strategies in a world we wrote. The harness (stage 6)
searches the thing that surrounds a real agent: what it is shown, what it keeps,
when it stops. Subject: our own coding loop (`harness/agent.py`), six small
tasks with hidden tests, four of them the search set and two held out, model
`DeepSeek-V4-Flash-0731` through a host but not a model of ours.

What the replay judge does at this scale, over ten rounds: 6 of 6 recorded
episodes rebuilt character for character (33 steps), token model cross-validated
at 5.9% mean relative error (17.3% worst), 19 of 28 proposed candidates refused
on recordings alone with no agent run spent, 22 online runs against the 112 a
sweep of the same candidates costs.

What the loop cannot do, measured rather than assumed. Five revisions of the
frozen acceptance rules, each forced by a measurement:

| revision | what it added | what forced it |
|---|---|---|
| v2 | coverage floor: a saving claim needs its decisions replayed | rounds 2 and 3 deployed at **0 of 26** replayed decisions; both then cost **more** online (+27.0%, +21.1%) |
| v3 | an online path for candidates replay cannot judge | three candidates at +22.5..26.6% predicted with no replayed decision at all and no way to decide them |
| v4 | a trajectory-changing policy is measured online before deployment, whatever its coverage | the `window3` control: +7.6% predicted at 72.7% coverage, measured **+12.4%** over three runs per task, held-out **+81.8%** |
| v5 | three runs per task before any online number is quoted | round 9: **-3.4%** from one run per task, **+4.0%** net from three, per-task spreads up to 90.8% of the baseline |

Result, stated the way this project has to state it: **the harness loop has not
saved a token it can defend.** All three deployments failed their own promise:
round 2 (+22.5% predicted, +27.0% measured), round 3 (+26.1% predicted, +21.1%
measured and one search task lost), round 9 (-3.4% on single runs, +4.0% once
repeated). What holds is the discipline: the judge decides most candidates for
free, every claim is either measured online or labelled an estimate, and the
loop's own refutations sit in the same record as its claims. The round 9 policy,
measured three times per task, is genuinely cheaper on three tasks (`t01` -18.6%
at 0.04% spread, `t02` -8.3%, `t06` -32.5% held out) and gives it all back on two
(`t03` +48.4%, `t05` +20.8%): a per-task harness would take it, one harness for
six tasks cannot, and no measured net saving survives anywhere.

The harness tree is published into the same OSTIS graph as the island's
strategies: `concept_harness` nodes carry the policy, the judge's estimate, the
gate verdict and the online comparison, `concept_harness_round` nodes carry the
frozen criteria that applied.

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
- The judge's replay estimate is biased upwards (~20–30% relative here) even
  though its *ranking* was correct in all eight series runs; the estimate must
  not be quoted as a performance prediction (see `docs/series.md`).
- "Improvement" means the measured online score with the same world seed and
  budget: the series covers eight world instances over two domains — a
  controlled comparison, not a claim about arbitrary task families.
- The harness (§6.5) is six tasks, one model and one provider, and the agent's
  own run-to-run spread reaches 90.8% of the baseline on one task. Every saving it
  produced was falsified by the next measurement; the loop's value so far is its
  refusals, not its deploys. It also runs with a corpus far too small for the
  capability gate to mean anything: the gate's tolerance (at most one task lost)
  is one sixth of the corpus.
- The harness proposer never found the efficient region: everything that cleared
  the gate was hand-written or a variation of one family. On a corpus this small
  that is a statement about proposer quality, and it is not flattering.

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

Three contemporary works read in full and used as the frame for §6.5:
**Dream-RSI** (Google/DeepMind/UMD, arXiv 2609.14858) makes recorded history the
simulator for policy search; **Meta-Harness** (arXiv 2603.28052) shows a
proposer fed full trajectories beats one fed summaries, and that the harness is
the object worth searching; **SoL-Pi** (arXiv 2609.20519) freezes acceptance
criteria before the search and keeps a held-out set out of it. Those three
supply the method this project uses. The addition this work makes is not a new
loop but an account of where the loop lies: replayability as a first-class
number (what is rebuilt exactly, what is extrapolated, what cannot be judged at
all), and the rule that a trajectory-changing policy may not be deployed on a
replay estimate however high its coverage, because coverage counts aligned
prompts and not the steps the agent will then take. Our measured refutations
(the `window3` control, round 9's repeats) are the evidence for that rule, and
we have not found them stated in the three works themselves.

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
