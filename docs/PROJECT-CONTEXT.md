# Oneiro-OSTIS — full project context

> Handover document. It is written to be read by an outside model or person who
> has no access to the session that produced it. Every number and claim below
> comes from an artifact on disk, and where a claim is weak or refuted the
> document says so. Paths are relative to the project root
> `projects/ostis/oneiro-ostis/` unless stated otherwise.
>
> Documents produced alongside this one: `docs/PROJECT-CONTEXT.md` (this file)
> and `docs/SKILLS-COMPILATION.md` (the working methods of the workshop that
> built it).

## 0. What the reader is asked to do

The project works. The problem is that nobody has been convinced it is
**needed**. The owner's own words: "our system, I could not convince anyone it
is necessary, because you do something very narrow that you could have done
yourself".

So the reader is asked to answer, on the evidence in this document:

1. Is there a version of this system that a real person would actually need, and
   what would that version be?
2. If not, what is the honest smallest thing this work is worth (a methods
   result, a tool for its own author, a published negative result)?
3. If yes, what is the shortest path from what exists now to that version?

Two rules constrain every answer, because breaking either one has already cost
this project real time:

- **No facade.** Nothing may be claimed that the system does not actually do.
  A demo that shows more than the system does is a defect, not a demo. This
  comes from the existing plan (`docs/PLAN.md`, "Global Constraints").
- **No number without a run.** Every quoted number must be reproducible from a
  recording on disk. This project's most recent work is a long demonstration of
  why: see section 4.4.

## 1. The project in one page

**Oneiro-OSTIS** is a persistent agent whose autobiographical experience lives
natively in an OSTIS knowledge graph, and which improves itself by *dreaming*:
while the agent is idle, alternative strategies are proposed by a language
model, judged by **exact replay over the recorded experience tree** (no
execution, no provider calls), and the winner is deployed online. The tree of
discoveries grows; the loop repeats.

The pattern comes from *Dream-RSI* ("accumulated history is already a simulator
of the world"). The claimed angle of this project: **the OSTIS semantic graph is
that symbolic simulator**, not a file store.

- Owner: a single person, building this as a science-competition project with a
  non-technical jury (the plan names the event as Khrustalnaya Alfa; the
  deadline is not fixed in the repository).
- Started 2026-09-17; the material below was produced by 2026-09-20.
- Stack: OSTIS (sc-machine built locally, sc-web, py-sc-client), Python, Docker,
  any OpenAI-compatible LLM endpoint.

The intended story for the jury was always: *an agent that grows by sleeping,
and whose memory you can look at*. Section 2 explains why that story has not
landed.

## 2. The honest problem

Four separate problems, in order of severity.

1. **The graph is not load-bearing where the real work happens.** There are two
   tracks. In the toy world, the dream loop genuinely reads its experience tree
   from the OSTIS graph (`python/dream.py` via `python/bridge.py`). In the real
   coding-agent track (`harness/`), the judge replays recordings kept as
   `record.json` files on disk, and the graph receives the search tree only
   afterwards, as a publication step (`harness/publish.py`). So the project's
   central claim ("experience lives in the graph") is true for a simulation and
   decorative for the real system. Nobody has run the ablation that would show
   the graph matters: the same loop with graph memory, with flat-file memory,
   and with no memory.
2. **No user exists.** The original plan (`docs/PLAN.md`) defines a mechanism,
   not a job. Nothing in it says who has a task, what they get, or how anyone
   outside would measure success. The deterministic island/world domain was
   invented precisely because no real domain had been chosen: it supplied a
   numeric outcome, not a purpose.
3. **"Experience" was never defined as a reusable artifact.** The ontology has
   Attempt, Outcome, Strategy, TemporalLink, CausalLink. What was never written
   down is the thing the project is named after: an experience is
   (situation, action, cost, outcome) that can be **retrieved when a similar
   situation appears**. Accumulation without retrieval is storage, not
   experience. The dream loop improves strategies *inside one world*; nothing
   was ever built that makes a *new task* cheaper because of past tasks.
4. **The measured benefit is small, and it lives on toy tasks.** The best
   measured result in the real-agent track is a 13.3% token saving on a search
   set of four small Python tasks and 28.5% on two held-out tasks, measured over
   three runs per task on a provider whose run-to-run noise floor is about ±20%
   on the same policy. The toy world produces much larger ratios (up to 6.97x)
   but a non-technical jury reads it as "little things running around", which is
   exactly what the owner said.

## 3. What exists

### 3.1 OSTIS knowledge graph (the intended centre)

| Path | What it is |
|---|---|
| `knowledge-base/ontology/experience.scs` | The experience ontology: Discovery, Attempt, numeric Outcome, Participant, TemporalLink, CausalLink, Strategy, DreamCycle, and the harness classes (HarnessPolicy, HarnessRound, and their relations) |
| `problem-solver/cxx/` | C++ ScAgents: RecordAttempt, RetrieveAttempts (canonical action-class pattern, `nrel_result` on completion) |
| `python/bridge.py` | py-sc-client bridge. Public API: `record_attempt`, `retrieve_attempts`, `mark_strategy_online_score`, `save_harness`, `load_harnesses`, `save_harness_round`, `load_harness_rounds` |
| `interface/`, `docker-compose.yml`, `Dockerfile` | sc-web (`:8000`), sc-machine with SCTP (`:8090`); the machine image is built locally, the knowledge base is rebuilt from `.scs` sources at container start |

The KB is not an opaque blob: the ontology is source, and the machine reloads it
on boot, so new node classes can be added without rebuilding an image.

### 3.2 Deterministic worlds (the toy track, where the loop is complete)

| Path | What it is |
|---|---|
| `python/world/` | Two worlds: `island` (expedition: travel, dig, carry, deliver, numeric score) and `workshop` (gather/craft/sell). Seeded, deterministic, numeric outcome per step |
| `python/replay/engine.py` | Builds `ExperienceTree` from recorded steps; `replay(strategy)` walks it with **zero executions**; reports coverage, mean score, truncated episodes, and a recording-consistency check |
| `python/dream.py` | The dream: loads the recorded tree **from the OSTIS graph**, asks the LLM adapter for candidate strategies, judges each by replay, returns the winner plus a dream table |
| `python/adapter_llm/` | Provider-agnostic OpenAI-compatible client (base_url + key) |
| `python/loop.py` | Online → record → dream → deploy → repeat; writes the deployed strategy's online score back into the graph |
| `python/agents.py`, `python/metrics/` | Memory agents (context-only, flat store, OSTIS memory with ablation flags, random floor) and the memory metrics: recall, order accuracy, provenance accuracy, contradiction count, retrieval latency |

### 3.3 Real coding-agent track ("the harness")

| Path | What it is |
|---|---|
| `harness/agent.py` | Our own tool loop (`list_files`, `read_file`, `write_file`, `edit_file`, `run_tests`, `run_command`) over a scratch copy of a task; every episode recorded to `record.json` (exact messages, tool calls, observations, tokens, history length) |
| `harness/tasks/` | Six small Python tasks, each with visible tests and a hidden test file the agent never sees. Search set: `t01-start-total`, `t02-clamp-bounds`, `t03-parse-duration`, `t05-retry-backoff`. Held out: `t04-dedupe-order`, `t06-csv-column-total` |
| `harness/policy.py` | A policy is eleven fields describing what the agent is shown: file list, initial test output, `context_mode`, `window_steps`, `observation_chars`, read line budget, step budget, whether failing tests re-enter, temperature |
| `harness/replay.py` | The judge: rebuilds, from a recording alone, the messages a candidate policy *would have sent*, and computes what they would have cost. It splits every candidate into exact steps (prompt rebuilt as recorded, cost is a measurement) and abstained steps (prompt differs, cost is an extrapolation). `decision_replayable` is the share of exact steps and is reported as a first-class number |
| `harness/rsi.py` | The loop: freeze criteria → propose (LLM reads full trajectories) → judge by replay → gate on evidence → deploy and measure online, three runs per task. Implements criteria versions v1 to v5 and re-checks old rounds under later rules |
| `harness/publish.py` | Publishes the baseline, every round and every hand-written reference policy into the OSTIS graph (idempotent) |
| `harness/tests/` | 19 offline tests: judge exactness, gate behaviour, accounting, honesty of provider refusals |
| `harness/report.py`, `docs/harness.md` | Results table generator, and the full write-up with every number |

### 3.4 Surfaces

`dashboard/server.py` + `dashboard/index.html` (port 8130 by default) render the
loop state, the rounds and the harness panel; `docs/*.md` hold PAPER, TALK,
SLIDES, PROGRESS, PLAN and the results tables.

## 4. What has been measured

### 4.1 The dream loop in the deterministic worlds

Source: `docs/series.md` (island 5 seeds × 3 rounds; workshop 3 seeds × 3
rounds, generated against the live stack on 2026-09-19).

| world | seeds improved | delta mean | ratio mean | judge bias (replay − measured) |
|---|---|---|---|---|
| island | 5/5 | +77.8 score | 1.58x | +56.9 (29.7% relative) |
| workshop | 3/3 | +49.3 score | 6.97x | +11.3 (22.9% relative) |

8/8 seeds improved after a single dream; the smallest improvement was +14.7
(seed `oneiro-1`), which is the honest lower bound of the method on this world.
Recording conflicts across all dream trees: 0.

The important caveat is in the numbers themselves: the replay estimate carries a
**positive bias of 22-30% relative**, so the judge ranks well but must never be
quoted as a prediction. This bias is the same phenomenon the real-agent track
later measured independently (section 4.3).

### 4.2 What the graph buys as memory

Source: `docs/results.md` (one episode, 25 recorded attempts).

| memory | recall | order | provenance | latency/attempt |
|---|---|---|---|---|
| context-only | 0.12 | 1.00 | 0.00 | 0 ms |
| flat store | 1.00 | 1.00 | 0.00 | 0 ms |
| OSTIS graph | 1.00 | 1.00 | 1.00 | 100 ms |
| graph, provenance relations dropped | 1.00 | 1.00 | 0.00 | 63 ms |
| graph, temporal relations dropped | 1.00 | **0.58** | 1.00 | 84 ms |
| random floor | 0.00 | 0.00 | 0.00 | 0 ms |

Reading: the graph is not needed to *remember* (a flat store also reaches 1.00),
but it is what preserves **order** (0.58 without temporal links) and
**provenance** (0.00 without provenance relations). This table is the strongest
existing evidence that the graph is load-bearing for something, and it is a
retrieval-quality proxy measured on a single episode, not a downstream effect.
No experiment connects this table to the improvement the dream loop produces.

### 4.3 The real coding-agent track: what the judge can and cannot do

Source: `docs/harness.md`.

Judge accuracy on the six normal recordings: prompt sizes rebuilt character for
character 6/6; token model cross-validated (fitted on the other tasks, predicting
this one) mean relative error 5.9%, worst 17.3%; a candidate identical to the
recorded policy replays with decision ratio 1.00 and cost ratio 1.00.

The control experiment: all seven hand-written policies judged from recordings
alone (free) and then measured online with three runs per task.

| policy | judge | replayable | online search | online held-out | bias |
|---|---|---|---|---|---|
| baseline | +0.0% | 100% | +20.6% | +10.4% | −20.6% (the noise floor) |
| windowed | +0.0% | 100% | +1.3% | +9.9% | −1.3% |
| window3 | +7.5% | 73% | +12.4% | +81.8% | −4.8% |
| window2 | +15.1% | 55% | **−10.8%** | +0.0% | +25.9% |
| terse | +32.6% | 0% | +19.7% | +47.3% | +12.9% |
| blind | +33.7% | 0% | +62.9% | +58.1% | −29.3% |
| cautious | +0.0% | 100% | +43.0% | +21.5% | −43.0% |

Four findings that survive: (1) the provider's noise floor is about ±20%, so a
single run proves nothing; (2) the judge errs in **both directions** and its
error spans −43% to +26%; (3) the two candidates with 0% replayable coverage
were the two worst online, so a 0%-coverage estimate is noise dressed as a
number; (4) the only policy that actually saved tokens (`window2`, −10.8%) did
not transfer to held-out tasks. Replay judges what the agent *saw*, never the
steps it will then take.

### 4.4 The loop's own history, including its failures

Eleven rounds, 29 candidates, four deployments. For the first ten rounds not one
result survived honest measurement.

| round | criteria | candidates | outcome |
|---|---|---|---|
| 1 | v1 | 3 | none deployed |
| 2 | v1 | 3 | deployed `no_initial_tests`; online **+27.0%** tokens (worse) |
| 3 | v1 | 2 | deployed `no_initial_tests_window`; online **+21.1%** (worse) |
| 4 | v2 | 3 | refused on evidence (all at 0% replayed decisions) |
| 5-7 | v3 | 8 | nothing cleared the saving threshold |
| 8 | v4 | 3 | measured and refused (predicted +32.0%, measured +1.5%) |
| 9 | v4 | 3 | deployed `no_initial_tests_deploy` on **one run per task** (−3.4%); under three runs per task the same policy reads **+4.0%** and does not transfer |
| 10 | v5 | 3 | nothing cleared the threshold |
| 11 | v5 | 1 | deployed `no_initial_tests_obs1500`: search **−13.3%**, held-out **−28.5%**, 4/4 and 1/2 solved, transferred |

Two notes on that table. The token deltas stored *inside* rounds 2 and 3 were
computed against a baseline that included a broken one-step run of
`t04-dedupe-order`; recomputed against normal runs only, and comparing tokens
only on tasks both sides solved, the same runs read **+27.0%** and **+21.1%**
(see `harness/round-02.json` and the "Corrections" section of `docs/harness.md`).
Both values are kept on disk; the corrected ones are quoted here. And round 9's
stored −3.4% is the number its own single-run measurement produced, which is
exactly the measurement criteria v5 later banned.

Round 11 is the only defensible saving in the whole history. The policy is two
fields: no initial test output in the first prompt, and longer tool observations
(1500 instead of 1000 characters). Neither field alone saves anything (round 2
is the first field alone, at +27%); the combination is what works, a fact only
an online measurement could produce.

The acceptance rules were revised five times, and none of the revisions moved a
numeric threshold. Each closed a way the gate could claim more than it knew:
v2 wired a coverage floor into the gate (after rounds 2-3 deployed
zero-coverage candidates); v3 gave candidates the online path instead of a
silent ban (after round 4 measured nothing at all); v4 required online
measurement for any policy that changes what the agent sees (after the
hand-written `window3` measurement); v5 required three runs per task before any
online number is quoted (after round 9's single-run deployment reversed under
repeats). Each round stores the rules that applied to it, so a later revision
never relabels an earlier result.

**The ledger.** 26 online runs were actually spent; measuring every one of the
29 candidates once per search task would have cost 116. So the recordings saved
90 runs (4.5x) on the way to those decisions. This is the closest thing the
project has to an economic argument, and it is an argument about the *method*,
not about a user.

**What this history is really evidence of.** Not that the method works, but that
the method refuses to lie. Four deployments happened before the gate was strong
enough; two of them were worse than doing nothing, one was noise, and one was
real.

## 5. Related work: what already exists, and where it beats us

The owner supplied four papers and one general article. All of them do a version
of this project, at a scale this project cannot reach.

| work | claim | numbers |
|---|---|---|
| **Dream-RSI** (Google/DeepMind/UMD, arXiv 2609.14858) | Accumulated recorded history is already a simulator of the world; search policies against it without re-execution | The pattern this project is built on |
| **Meta-Harness** (arXiv 2603.28052) | End-to-end optimization of the *harness* (the code around the model, not the model): an agent reads a filesystem holding all prior candidates' code, traces and scores, and proposes the next harness; all logs are kept | Uses **full logs** (about 10 MTok per iteration) against the 0.002-0.026 MTok text-optimization baselines; the harness, not the policy, is the object worth searching |
| **SoL-Pi** (NVIDIA/NTU/MIT, arXiv 2609.20519) | Recursively scaling an auto-research loop at the harness layer across many environments; four mechanisms survive selection (action fusion, online context compaction, observation packing, evidence-preserving reduction) | 51-task EdgeBench: score comparable to Pi across GPT-5.6 Sol and Opus 5 while cutting recorded token traffic **44.7-49.0%** and API cost by about a third; $8.75-13.50 saved per hour against native Codex/Claude Code harnesses |
| **GAVEL** (arXiv 2609.19315) | An explicit graph world model (object relations, action pre/post-conditions, probabilistic beliefs) verifies and repairs LLM plans for free, and reserves LLM replanning for errors that need semantic reasoning | BEHAVIOR-1K with Qwen3-8B: single-task success 41.2% → **91.8%**, multi-task 19.9% → **92.6%**; distributional belief reasoning cuts travel distance about 5.4% |
| General RSI article (owner-supplied press piece) | Framing of recursive self-improvement as a strategy | No numbers taken; framing only |

Reading honestly: **Meta-Harness is our harness track with a bigger budget and
full logs; SoL-Pi is our harness track with results that actually matter;
GAVEL is our graph-as-judge idea in robotics with a 50-point success gain.**
What this project can claim that they do not:

- The experience tree is a **typed semantic graph with an ontology** and
  queryable relations, not files or logs. (Evidence: section 4.2.)
- The **acceptance rules are frozen before the search and versioned per round**,
  and the loop re-checks its own past verdicts under later rules
  (`--recheck`: under v2, 3 of the verdicts recorded before it would be refused,
  including both deployments of that era). SoL-Pi has the frozen-criteria idea;
  the self-recheck of historical verdicts is ours.
- The judge is **provably free and exact** on the steps it can cover
  (6/6 rebuilt prompts, a test asserts that replay executes nothing).

What they have that we do not: scale (51 tasks vs our 6), real savings, real
users, and in GAVEL's case an external task domain.

## 6. Proven, unproven, refuted

| claim | status |
|---|---|
| Dreaming over a recorded experience tree improves a strategy online | **Proven in the toy worlds** (8/8 seeds, 1.58x island, 6.97x workshop, single dream) |
| The OSTIS graph preserves order and provenance that a flat store loses | **Proven** (order 1.00 vs 0.58; provenance 1.00 vs 0.00), on one episode, as a retrieval proxy |
| Exact replay can judge what a candidate policy would have cost, for free | **Proven** on covered steps (6/6 prompts, 5.9% mean token error); **refuted** as a predictor of the agent's actual behaviour whenever the prompt changes |
| Replay can replace online measurement for harness search | **Refuted** by the control experiment (bias −43% to +26%, and it is wrong in both directions) |
| The loop can find a transferring, real saving | **Proven once** (round 11: −13.3% search, −28.5% held-out, three runs per task), on six small tasks at a ±20% noise floor |
| The graph is what makes the improvement possible | **Never tested**. This is the single largest hole in the project |
| Experience accumulates so that new tasks are cheaper | **Not built**. Retrieval of past experience into a new task does not exist |
| The agent has a user or an external job | **Does not exist** |

## 7. The forks we are stuck on

1. **Where does the graph have to be load-bearing for the project to be what it
   says it is?** Options: the judge reads recordings out of the graph in the
   real-agent track too (needs full trajectories stored as sc-elements, volume
   untested); or the graph stays the toy track's substrate and the project
   honestly shrinks its claim; or the graph is dropped from the real track.
2. **Is there a job where a persistent, inspectable experience graph beats a file
   store for a person who is not an AI researcher?** Candidates that were
   floated and not decided: an agent that stops repeating its own environment
   mistakes (there is real material for it in the workshop's own history); a
   small-code-task agent whose savings a person can see per task; a research
   assistant that accumulates what it read with provenance and contradiction
   checks.
3. **Shrink or scale the real-agent track?** The measured saving exists at six
   tasks and a ±20% noise floor. Twelve to twenty tasks with three runs each
   would make the numbers quotable, at the cost of hours of provider time on a
   free tier that already returns 429s under load.
4. **What is the deliverable to the jury?** Live run (the provider is the risk),
   the graph in sc-web as the visible artefact, a recorded demo, or slides built
   only from measured numbers.

## 8. Constraints any plan must respect

- **No facade.** Demo equals system. Nothing shown that the system does not do.
- **No number without a run**, and no claim without a recording behind it.
- **Never destroy data.** Deletion is recycling through `_scripts/trash.sh` in
  the workspace; permanent deletion is not an available operation.
- **One LLM provider now**: `https://inference.dahl.global/v1`, key from the
  environment variable `INFERENCE_DAHL_GLOBAL_KEY` (workspace `.env`). It is a
  free tier that admits paid accounts first, so it refuses requests under load;
  refusals are recorded as "not measured", never as failures. No other key is
  authorized.
- **Provider-agnostic adapter** in code: base_url + key, no provider hard-coded.
- **Do not push to any remote** without an explicit, one-time authorization.
- The jury is non-technical: anything presented must be legible without AI
  vocabulary.
- Python for everything except the C++ ScAgents; tests must stay offline and
  green (`python -m pytest harness/tests -q` = 19 tests).

## 9. How to run everything

```bash
# the stack (sc-web :8000, sc-machine :8090; KB rebuilt from .scs on start)
docker compose up -d

# the toy world loop
PYTHONPATH=python ONEIRO_ROUNDS=3 python -m loop

# the real-agent track
python harness/run.py --task t01-start-total          # one recorded episode
python harness/report.py                              # table from recordings
python harness/rsi.py --state                         # the whole loop as JSON
python harness/rsi.py --show --recheck --ledger       # what the rounds established
python harness/rsi.py --reference                     # judge the hand-written policies
python harness/rsi.py --round 12                      # propose, judge, gate, measure
python harness/publish.py                             # the search tree into the graph

# the surfaces and the offline tests
python dashboard/server.py                            # http://localhost:8130
python -m pytest harness/tests -q                     # 19 tests, no network
```

## 10. Environment facts

| fact | value |
|---|---|
| Agent model (real track) | `deepseek-ai/DeepSeek-V4-Flash-0731` |
| Proposer model (dream/search) | `zai-org/GLM-5.3-Flash`, with a fallback chain when the provider refuses |
| Provider | `https://inference.dahl.global/v1`, env `INFERENCE_DAHL_GLOBAL_KEY` |
| Ports | sc-web 8000, sc-machine SCTP 8090, dashboard 8130 (`ONEIRO_DASH_PORT`), bridge default 8090 |
| Containers | `ostis/sc-web:0.9.0` from the registry; `sc-machine` built locally from a GitHub release binary distribution (no conan; `conan.ostis.net` is unreachable) |
| Recordings | `harness/lab/runs/<task>-<label>-r<N>-<stamp>/record.json`; rounds in `harness/lab/rsi/round-*.json`; criteria in `harness/lab/rsi/criteria.json` |
| Repo | Only `projects/ostis/oneiro-ostis/` is tracked; the vendor OSTIS stack stays outside git |
