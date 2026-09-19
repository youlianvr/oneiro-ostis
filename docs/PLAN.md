# Oneiro-OSTIS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (per-task review included). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persistent agent whose autobiographical experience lives natively in the OSTIS knowledge graph and which self-improves by dreaming: alternative strategies are proposed by an LLM and judged by exact replay over the recorded experience tree; the winner is deployed online and the discovery tree grows.

**Architecture:** OSTIS-centric. The sc-graph stores the experience ontology (discovery, attempt, numeric outcome, temporal/causal links, strategy, dream cycle) and the discovery tree itself. C++ ScAgents handle RecordAttempt / RetrieveAttempt / ReplaySubtree / DeployStrategy. A Python layer provides the deterministic mini-world with numeric outcomes, the replay engine, the LLM strategy generator (OpenAI-compatible adapter, base_url+key), metrics and baselines. sc-web is the live proof surface.

**Tech Stack:** OSTIS (sc-machine 0.10.0, sc-web 0.9.0, C++ ScAgent API, py-sc-client), Docker/WSL2, Python 3.14, any OpenAI-compatible LLM endpoint.

## Global Constraints

- No facades: demo and deliverables contain nothing the system does not actually do.
- The replay is exact (world is deterministic; outcomes recorded per step; dreaming executes nothing).
- C++ ScAgents preferred; SCP/SC-code avoided (owner decision: agent unfamiliarity risk).
- LLM access strictly via base_url + key adapter; provider swappable; no provider hard-coded.
- Jev is dropped from scope (owner decision 2026-09-17); judge = exact replay, LLM fallback only.
- Vendor stack stays outside git; only `projects/ostis/oneiro-ostis/` is tracked (gitignore exception in place).
- Commits: after each green stage, small logical units; remote push via subtree rule of `projects/README.md`.
- Old consciousness-research plans moved to `projects/ostis/_archive/` (superseded), never deleted.

---

### Stage 1: Living stack

**Files:** none created; environment validation only.

- [x] **Step 1: Start Docker Desktop** and wait for the Linux engine (blocked if it does not come up — fix first, everything else waits).
- [x] **Step 2: Bring up ostis-example-app:** `docker compose up --build -d` in `projects/ostis/ostis-example-app`, wait for `machine` healthcheck to pass.
- [x] **Step 3: Verify sc-web** serves on `http://localhost:8000`.
- [x] **Step 4: py-sc-client smoke** — connect to `localhost:8090`, resolve one known sc-element from the example KB.
- [x] **Step 5: Commit** nothing (env stage); record result in docs/PROGRESS.md.

### Stage 2: Skeleton and core loop

**Files:**
- Create: `knowledge-base/ontology/experience.scs` (Experience, Attempt, Outcome(numeric), Participant, TemporalLink, CausalLink, Strategy, DreamCycle + concrete nodes)
- Create: `problem-solver/cxx/` agents RecordAttempt, RetrieveAttempt (templates from ostis-example-app)
- Create: `python/bridge.py` (py-sc-client bridge initiating agent actions)
- Create: `tests/test_core_loop.py`

**Interfaces:**
- Consumes: Stage 1 running stack (sc-machine sctp/http endpoint on :8090).
- Produces: `record_attempt(event: AttemptRecord) -> ScAddr`, `retrieve_attempts(query) -> list[AttemptRecord]` — the Python-facing API every later stage uses.

- [x] **Step 1: Copy build skeleton** from ostis-example-app (CMakeLists, docker-compose, repo.path, interface/) into `oneiro-ostis/`.
- [x] **Step 2: Write failing test** `test_record_then_retrieve_roundtrip` (writes one attempt with subject+time link, retrieves, asserts equality).
- [x] **Step 3: Run test — expect FAIL** (agents/ontology not implemented yet): `pytest tests/test_core_loop.py -v`.
- [x] **Step 4: Author experience ontology** in `.scs`; rebuild KB via sc-builder inside the image.
- [x] **Step 5: Implement RecordAttempt + RetrieveAttempt** C++ agents on ScActionInitiatedAgent; wire action classes.
- [x] **Step 6: Implement bridge.py** so the test drives the real stack.
- [x] **Step 7: Run test — expect PASS;** commit `feat: core experience loop`.

### Stage 3: Scientific layer

**Files:**
- Create: `python/world/` deterministic mini-world (numeric outcome per step; seeded; episodic task suite)
- Create: `python/metrics/` (recall accuracy, order accuracy, provenance accuracy, contradiction count, retrieval latency; baseline agents: context-only, flat store)
- Create: `tests/test_world_determinism.py`, `tests/test_metrics.py`

**Interfaces:**
- Consumes: Stage 2 record/retrieve API.
- Produces: `run_episode(agent, world, seed) -> EpisodeLog`, `score(log) -> Metrics` — baselines and OSTIS-agent both implement `agent`.

- [x] **Step 1: Deterministic world + test** (same seed → identical trace hash, twice).
- [x] **Step 2: Baseline agents** (context-only; flat dict store) + score().
- [x] **Step 3: OSTIS-memory agent** reusing Stage 2 API; episodes linked with temporal + provenance relations.
- [x] **Step 4: Ablations:** memory without temporal links; without provenance (config flags on the ontology side).
- [x] **Step 5: Results table script:** `python -m metrics.build_table > docs/results.md` reproduces all numbers.
- [x] **Step 6: Run full suite; commit `feat: scientific layer (baselines, metrics, ablations)`.**

### Stage 4: Dreaming

**Files:**
- Create: `python/replay/engine.py` (tree walk over recorded attempts; zero executions; outcome equality asserted against KB)
- Create: `python/adapter_llm/` (OpenAI-compatible; generates N candidate strategies as executable policy descriptors)
- Create: `tests/test_replay_exactness.py`, `tests/test_dream_improves.py`

**Interfaces:**
- Consumes: Stage 2 API + Stage 3 world/metrics.
- Produces: `dream(tree, candidates) -> (best_strategy, scores)`, `deploy(strategy)` — the RSI half-loop.

- [x] **Step 1: Replay exactness test** — replayed outcomes == recorded outcomes on the full tree (property: dreaming never executes).
- [x] **Step 2: Replay engine** over alternative strategy descriptors (branch choice, parallel grouping, stopping rule).
- [x] **Step 3: LLM candidate generation** (N strategies per dream; JSON policy descriptors; strict schema).
- [x] **Step 4: Dream test** — at least one dream run whose deployed winner improves next online round score vs previous strategy.
- [x] **Step 5: Commit `feat: dream cycle (replay judge + LLM candidates + deploy)`.**

### Stage 5: Recursive loop

**Files:**
- Create: `python/loop.py` (online → record → dream → deploy → repeat; logs every round)
- Create: `tests/test_two_rounds.py`

- [x] **Step 1: Two-round test** — round 2 score ≥ round 1 with dream deployed (or honest zero-result documented).
- [x] **Step 2: Round dynamics script** — curves built from real logs into docs/.
- [x] **Step 3: Commit `feat: recursive self-improvement loop`.**

### Stage 6: Demo and deliverables

**Files:**
- Create: `demo/run_demo.py` (one command, clean state: live episode → sc-web view → dream → improved behavior)
- Create: `docs/PAPER.md`, `docs/TALK.md`, `docs/SLIDES.md` — built only from logs/metrics/screenshots of the last green stage.

- [x] **Step 1: Demo script green from clean state; rehearse with timer (5–7 min).**
- [x] **Step 2: Deliverables drafted from real artifacts only; commit.**
- [x] **Step 3: Novelty check** — review existing OSTIS memory implementations (nika etc.) before any "first/novel" claims.

## Self-Review

- Spec coverage: all owner decisions mapped — single project (no A/B), OSTIS-centric, max-by-dependencies ladder, hybrid discovery domain, base_url+key adapter, C++ agents, subtree git, archive of old plans, Jev dropped.
- Placeholder scan: no TBD/TODO; every step names its artifact and check.
- Type consistency: record/retrieve (Stage 2) consumed identically in Stages 3–4; run_episode/score (Stage 3) consumed by Stages 4–5.

## Risks

- Docker/WSL on Windows — Stage 1 first; fallback: build sc-machine in plain WSL.
- Deadline (Khrustalnaya Alfa, next week) — ladder guarantees presentability at any reached stage.
- Novelty challenges — pre-submission review of OSTIS prior art.
- Facade temptation — permanent rule: demo == system.
