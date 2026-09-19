# PROGRESS

## 2026-09-17

- Repo created: `youlianvr/oneiro-ostis` (private; subtree-push per projects/README.md rule).
- `.gitignore` workspace updated: `/projects/ostis/*` with `!/projects/ostis/oneiro-ostis/` — vendor stack stays out, project tracked.
- Old `consciousness-research-*.md` plans moved to `projects/ostis/_archive/` (superseded, kept).
- PLAN.md and README.md written.

## 2026-09-18

- Stage 1 stack work (owner confirmed network was the blocker: VPN throttled docker.io to ~10 KB/s; switched off):
  - Measured direct docker.io at ~12 KB/s even after VPN off; `mirror.gcr.io` fast for `library/` images (alpine 3.4s).
  - Non-`library/` mirrors (`docker.m.daocloud.io`, `dockerpull.org`, `docker.1ms.run`) cannot serve ostis images from cache — they hang proxying to the slow upstream.
  - `registry-mirrors` (mirror.gcr.io + docker.m.daocloud.io) added to `~/.docker/daemon.json` (backup at `Temp/daemon.json.bak`); daemon restarted; library pulls now seconds.
  - `ostis/sc-web:0.9.0` pulled via `docker.1ms.run` (worked slowly but completed) and retagged.
  - `ostis/sc-machine:0.10.0` from Docker Hub turned out to be the **generic sc-machine image** — no `/example-app/install`, container exit 127. The compose `image:` name is just what a local build would tag; local build of `machine` is mandatory. Lesson recorded.
  - Local build of `machine` running via schtasks (survives tool timeouts); base images cached; apt downloads at usable speed.
- Added `scripts/smoke-test.sh` — stage-1 acceptance test (containers up, healthcheck, HTTP probes :8000/:8090).
- Added `docs/ONTOLOGY-DRAFT.md` — draft sc-ontology of experience events (episode template, nrel dictionary, SCs example) for Stage 2.

### Gotchas (for future sessions)

- Long-running docker commands die with the tool's job object when the client is killed — run them via `schtasks /Create ... /Run` with a bat file; that survives everything.
- `docker compose up` with `image:` + `build:` pulls the named image first even when a local build is intended; use `docker compose build <service>` explicitly.
- containerd image store (`io.containerd.snapshotter.v1`) does NOT honor daemon registry-mirrors for build-time pulls; left enabled anyway (switching the store would wipe existing images — maigret/dnstwist kept intact).
- Windows + Git Bash: `MSYS_NO_PATHCONV=1` needed for `schtasks /Create /TN ...`; schtasks output is cp866 — pipe through `iconv -f cp866 -t utf-8`.

### 2026-09-18 (evening): conan eliminated, base image split

- Full `docker compose build` of example-app failed: `conan.ostis.net` unreachable
  (Errno 111 at the artifactory ping) — server-side outage, not our network.
- Discovery: GitHub releases ship **complete binary distributions** of sc-machine
  (headers + CMake package configs + .so + sc-builder/sc-machine binaries).
  The module can build against them directly, no conan needed.
- oneiro-ostis therefore got its own build system:
  - `scripts/install_cxx_problem_solver.sh` — downloads sc-machine 0.10.5 release
    archive from GitHub, keeps `include/` (module compiles against it);
  - `CMakePresets.json` — plain Ninja preset, `CMAKE_PREFIX_PATH` → `install/sc-machine`;
  - `CMakeLists.txt` — `find_package(sc-machine REQUIRED)` from the prefix, no conan;
  - `Dockerfile` — no pipx/conan, venv + prebuilt binaries + module build only;
  - `docker/base/Dockerfile` — separate toolchain base image `oneiro-base:latest`
    (apt layer with retries, cache-stable: apt was re-downloading 125MB of packages
    on every source change because COPY preceded it).
- Stage 2 artifacts landed meanwhile: ontology (`knowledge-base/ontology/experience.scs`,
  canonical `sc_node_class`/`sc_node_non_role_relation` conventions verified against
  example-app KB), C++ agents RecordAttempt/RetrieveAttempts (canonical binary-relation
  pattern verified against sc-machine sources: main CommonArc + rrel/nrel attribute arc,
  `SetResult` → `nrel_result` CommonArc), Python bridge (`python/bridge.py`,
  construction/template APIs verified against py-sc-client sources), core-loop test
  (`tests/test_core_loop.py`).

### 2026-09-18 (late evening): STAGE 1 + STAGE 2 GREEN

- `oneiro-base:latest` toolchain image built (one-time ~40 min apt through the
  flaky network; now cached forever).
- Build fixes, each verified: missing python3-venv; CRLF in shell scripts
  (normalized in BOTH devdeps and builder stages — `COPY . .` re-breaks it);
  stale include in OneiroKeynodes.hpp.
- **Ontology fix (root-caused in sc-machine sources):** an action class is valid
  only if it is included (`nrel_inclusion`) in one of receptor/effector/
  behavioral/information_action. Added `<= nrel_inclusion: information_action;;`
  for both action classes; KB rebuilt from scratch (volume removed).
- Bridge fixes: explicit `connect(ws://...)`, `ScTemplate` import,
  `sc_types` (deprecated) → `sc_type` constants.
- **Roundtrip verified against the live stack:**
  record_attempt('test_subject_alpha','walk','room1','concept_success') →
  retrieve_attempts returns the attempt with all four fields intact.
  `pytest tests/test_core_loop.py` → **2 passed in 1.06s**.
- Both containers healthy: machine (healthy, OneiroModule loaded) + web (:8000 → 200).

Stage 1 ✅ Stage 2 ✅ — next: Stage 3 (scientific layer: world, baselines, metrics).

## Stage 3 closed — scientific layer on the live stack (2026-09-19)

- Deterministic expedition world (`python/world/`), fixed island graph, numeric
  outcomes, seeded RNG only. Unit-tested for determinism.
- Baseline agents (context-only, flat store, random floor) + OSTIS memory agent
  with ablation flags; all share one interface (`agents.py`).
- Metrics: recall, order accuracy (adjacent pairs, first-occurrence positions,
  identical keys skipped), provenance, contradictions, retrieval latency
  (`metrics/`). `build_table` runs the full experiment on the live stack and
  writes `docs/results.md`.
- Ablations are real, not cosmetic:
  - `no_temporal` passes `concept_no_temporal` as rrel_5; the C++ agent skips
    `nrel_prev_attempt` chaining -> order accuracy drops to 0.50.
  - `no_provenance` drops `nrel_source` at write time -> provenance = 0.
- Full KB build restored: the whole IMS common KB (201 sources) plus our
  ontology now loads at container start (REBUILD_KB=1, repo.path, storage=/kb.bin).

### Gnarly bugs found on the way (documented for future sessions)
1. `repo.path` resolves paths relative to the file itself; the compose mount
   must match that layout (`./knowledge-base:/knowledge-base`).
2. `storage = kb.bin` resolves relative to the process CWD; use absolute
   `/kb.bin` so binaries land in the named volume, not the sources mount.
3. SCs canonical form: `=> nrel_main_idtf:` on the line after the node name;
   `;;` terminates statements. Verified against the IMS corpus.
4. Race in action initiation: build action node + class arc + rrel arguments in
   one construction, then generate the `action_initiated` arc in a SECOND
   request. Otherwise the agent can fire before arguments exist.
5. `ScAction::GetArguments<N>` returns Empty for missing N; optional arguments
   are safe.
6. Result structures: the record action returns a wrapper node around the
   attempt; retrieve returns a structure of attempts. Unwrap accordingly.
7. py-sc-client 0.10: `sc_type.VAR_LINK` does not exist (use `VAR_NODE_LINK`);
   `sc_client.client.disconnect()` must be called or the process hangs on exit
   (non-daemon socket threads).
8. `SC_SERVER_PARALLEL_ACTIONS=0`: parallel processing corrupts the
   chronological chain (determinism requirement).
9. Agent file loggers need their directory to exist (logs/ created pre-start).

## 2026-09-19 (night): the dream works — stages 4, 5, 6 closed

### World fixes (surfaced while building the dream layer, before any stage-4 code)

1. **Delivery was impossible.** `legal_actions()` offered `deliver:<neighbour>`
   while the executor requires `arg == current location` — every offered
   deliver was rejected as illegal, so stage-3 first-pass scores were empty
   travel dust (≈ −0.1 per episode). Fixed: deliver at the current location,
   only at delivery points; travels offered separately.
2. **Dig stopped at half a site.** Legality used `dug_count < remaining`
   instead of `remaining > 0` — half of every site's artefacts were
   unreachable. Fixed; regression test digs a site out completely.
3. **Values differed between processes.** Artefact values were derived via
   Python's `hash()`, which is randomized per process (PYTHONHASHSEED).
   Replaced with sha256-derived site codes; cross-process stability is now a
   test (same trace hash in two fresh interpreters).
4. **Order metric mis-scored identical sequences.** First-occurrence position
   mapping gave flat store 0.71 on a sequence that was literally equal to the
   ground truth (repeated dig/deliver cycles). Metric now maps the k-th
   occurrence of a key to the k-th occurrence; identical sequences score 1.00
   by construction, and the original test expectations (reversed = 0.0,
   partial = 0.5) still hold.

`docs/results.md` regenerated on the fixed world: OSTIS 1.00/1.00/1.00,
no-temporal order 0.58, no-provenance 0.00, context-only recall 0.12.

### Stage 4 — dream cycle

- `python/strategy.py` — Strategy descriptors (site priority, dig limit,
  delivery preference) as executable policies + deterministic candidate
  sweep + named baselines (weak incumbent, two surveys). Policy keeps
  per-episode memory of exhausted sites (a stateless version ping-ponged
  between two locations forever — found in a trace, fixed).
- `python/episode.py` — online runner: records every step with the state and
  legal actions BEFORE the action.
- `python/replay/engine.py` — the judge: experience tree from recordings,
  outcome-sufficient signature (location, carried artefact, dug-at-site),
  transition index, exact walk, uncovered → truncation, consistency check
  (conflicting recordings for the same signature+action = alarm), coverage.
- `python/dream.py` — propose → judge → persist winner; `python/adapter_llm/`
  — OpenAI-compatible generator (base_url+key+model from env, strict schema,
  offline fallback; not exercised without a provider).
- Ontology: trajectory relations (`nrel_episode`, `nrel_step_index`,
  `nrel_state`, `nrel_legal`, `nrel_strategy`, `nrel_note`) + strategy class
  and dream relations; bridge stores strategies as `concept_strategy` nodes
  with descriptor / replay score / online score / dream round / parent.
- Gotcha: recordings carry the world's Step (verb + object: `travel`/`beach`),
  the legal list carries qualified actions (`travel:beach`) — the engine's
  `full_action` bridges the two; a verb-only index key produced false
  "conflicts" (three different destinations under one key).
- Gotcha: sc-link floats are float32 — replay equality vs in-memory float64
  holds to ~1e-4, tests use that tolerance.

### Stage 4/5 numbers (live, `docs/rounds.md`, `docs/demo-log.md`)

- First live dream (single exploration): 137.5 → 156.0 measured.
- After adding the second exploration walk (farthest-first survey, better
  edge coverage): the dream found `cand_alpha_d4`, measured **252.4** —
  equal to the best value of the whole offline sweep; the loop then converged
  (rounds 3–5 stable).
- Demo: 21 candidates, 3 episodes / 120 steps / 76 transitions judged in
  9.1 s, 0 conflicts, **+114.9 (+84 %)** measured on the deployed winner.

### Stage 6 — demo and deliverables

- `demo/run_demo.py` — one command, writes `docs/demo-log.md` from the run.
- `docs/PAPER.md`, `docs/TALK.md`, `docs/SLIDES.md` — built from the three
  generated artifacts only.
- Novelty: bounded web search 2026-09-19 (queries in PAPER §8). Nearest
  neighbours: Dreamer-style "learning by dreaming" (which executes a learned
  model) and graph-memory agents (logs without replay optimization). No prior
  OSTIS + exact-replay self-improvement found; stated as bounded search.
