# Rewrite baseline and handoff

Date: 2026-10-02. Plan: [MASTER-PLAN.md](MASTER-PLAN.md).
This is evidence/status, not a product completion claim.

## Repository and authority

- Project is a subtree of `C:/Users/pc/.openclaw/workspace`, not a nested repo.
- Initial workspace branch `master`, HEAD `39f333d7d`; initial status clean.
- Project tree `d888bce60c1de213962bc581622ad3aaeac1d896`.
- Remote `oneiro-ostis`: `https://github.com/youlianvr/oneiro-ostis.git`.
- Local remote-tracking `main`: `1a9b9a9fb9690bc491af5f6701fbaf22aa68c689`
  (Russian); `v2`: `240f5039851d8dad2e2b0931ccf4822d386c7cba` (English).
  These are local refs, not a fresh remote fetch.
- No branch switch, remote change or publication in this foundation unit.
- Missing cloud PR no longer blocks implementation. Historic cloud claims are
  requirements/evidence of that session, not verification of local implementation.
- KB-RAG live lookup returned relevant branch/onboarding/PR history. Current
  source files and refs were checked rather than treating lookup as authority.
- Other parity files claim unrelated projects; Buffy record is historical. No
  other active claim to new package paths was found.

## Actual environment and services

Observed with Python import/metadata checks, socket connections and read-only
Docker/model endpoints, not inferred from old documents:

- Default Python 3.14.3; uv also lists installed 3.11, 3.12 and 3.13 interpreters.
- pytest 8.4.2, FastAPI 0.141.1, Uvicorn 0.41.0, httpx 0.28.1 installed.
- sc_client, sc_kpm, websocket importable; Python mypy not initially installed.
- Docker CLI installed; Docker Desktop Linux engine pipe absent (`docker version`
  fails). Do not claim a runnable container environment.
- 9899, 8090, 8000, 8130 closed on loopback at baseline.
- OmniRoute 20128 listening; `/v1/models` without authorization returns **401**.
  No successful model call or capability test yet. Provider key absent from this
  shell; existing owner configuration may supply it, never print its contents.
- Telegram bot token exists in environment; owner/chat pairing and ownership of
  that bot are not yet verified. No poll/send was made.
- No VirusTotal key in shell. VM availability not yet established.

## Preserved data (read-only inventory)

| Path | Files | Bytes | Handling |
|---|---:|---:|---|
| `kb.bin/` | 1 | 2,433 | Keep; directory size is NOT proof of a complete graph backup |
| `state/` | 39 | 1,928,349 | Keep existing proof/runtime state |
| `worktrees/` | 47,440 | 5,826,374,039 | Keep entire recorded work, no cleanup |
| `.runtime/` | 1,330 | 16,234,375 | Keep old installed console |
| `docs/pz/` | 11 | 4,818,669 | Preserve published paper/artifacts |
| `knowledge-base/` | 299 | 10,451,910 | Preserve ontology/vendor source |
| `bench/` | 13 | 136,223 | Preserve sources/measurements |
| `harness/` | 7,059 | 11,719,601 | Preserve experiments/task fixtures |

Docker-volume contents cannot be inventoried/restored while the engine is down.
No copy of a live graph was made and no migration/restore is claimed verified.
Before touching production graph: identify actual storage, establish consistent
snapshot, restore separate instance and check count/content. This remains a
blocking exit condition of stage 0, not a reason to stop independent packaging.

## Module census and planned disposition

Every tracked own-code family is included below; a family assignment is planned,
not equivalence evidence. Individual source/tests are read before each change.

| Existing family / modules | Disposition and reason | Evidence/status |
|---|---|---|
| `python/config.py` | Move implementation to installed `oneiro.config`; keep old import shim for science/legacy until their migration | Foundation in progress |
| `python/native/{memory,policy,tools,service,web,telegram}.py` | Rewrite/consolidate into package; old global model lock, full-history reads, duplicated settings and unsafe deletion cannot become new production runtime | Not migrated; contracts retained as baseline |
| `python/{llm,adapter_llm}.py` | Replace with one capability-aware model adapter | Not migrated; ancestor env search is legacy |
| `python/{approval,question_tool,roles,swarm,worker,task_runner,worktree_runner,life_loop,heartbeat,telegram_entry,hermes_plugin}.py` | Archive after replacements pass; multiple control planes and workspace coupling | Existing paths unchanged |
| `python/{bridge,agents}.py`, `host/ostis_mcp.py` | Split typed graph operations/ownership; replace host adapter dependencies | Live validation blocked by graph |
| `python/{strategy,strategy_workshop,episode,loop,loop_workshop,dream,series,viz}.py` | Review/rewrite on fixed-record invariants, preserve scientific semantics | Existing algorithms retained, not certified |
| `python/world/`, `python/replay/`, `python/metrics/`, `failure_taxonomy.py` | Retain only with evidence, fix consistency/successor contracts as necessary | Selected offline baseline passed |
| `python/{mcp_client,skills_index}.py` | Reviewed adapters; remove workspace-private dependencies from installation | Not in foundation wheel |
| `problem-solver/cxx/oneiro-module/{agents,keynodes,oneiroModule*}` | Review typed write/retrieve, chronology and durability; retain/rewrite with integration evidence | Build/OSTIS run pending |
| `knowledge-base/`, `cmake/`, CMake files | Additive ontology; pinned reproducible build | No data/schema mutation |
| `bench/memory/{arms,dataset,judge,retrieval,run,stores}.py` | Preserve arms/text identity; shared model/memory integration; remeasure separately | Offline baseline tests passed |
| `harness/{agent,critic,edits,noise,policy,publish,replay,report,rsi,run,runner}.py` | Separate search/gates/held-out/update supervisor; verify trajectory and repeat rules | Pending; task/lab data preserved |
| `harness/tasks/`, `harness/tests/`, `harness/lab/` | Keep fixtures/artifacts; classify and run harness-specific suite independently | Pending |
| `interface/native/`, `profiles/*/SOUL.md` | Rebuild channels/resources into wheel, keep behavioral/permission separation | Not packaged in foundation yet |
| `dashboard/`, `console/overlay*`, shipped CowAgent archive, `oneiro_proxy.py`, `plugins/oneiro-life/` | Archive after native installation/channel parity | Old runnable installation preserved |
| `scripts/{install,oneiro-app,oneiro-native,oneiro-phone,host-wire,tg-rehearsal,wmi-seed}` | Native package lifecycle/installer replace workspace-bound paths | Old entrypoints unchanged until parity |
| `scripts/{docker_entrypoint,install_cxx_problem_solver,reset_stack,healthcheck,smoke-test}` and Docker files | Reproducible build and data-preserving lifecycle; no `--clear` active graph | Pending; Docker engine unavailable |
| `scripts/{label-episodes,mcp-smoke}`, `demo/run_demo.py` | Migrate imports/commands and preserve demonstrations as measured examples | Pending |
| `scripts/{pz-build,pz-word,pz-feed-audit,pz-shots,take_shots}`, `docs/pz/`, figures/results | Keep historic products; build-tool review without changing published evidence | Untouched |
| `tests/test_*.py`, `tests/conftest.py` | Explicit offline/integration categories; new package tests independent of graph | Baseline below |
| README/current docs/historic plans | Current plan/decisions updated now; README/runbooks updated alongside working delivery; old reports retain provenance | Full README migration pending |

## Baseline checks

- `python -m pytest tests/ -q --maxfail=3`: **57 passed, 3 setup errors**
  in 11.93 s. All three errors in `test_core_loop` from absent sc-server,
  not missing installed Python dependencies. This is not a full passing suite.
- Explicit offline set: config, native service/channels, island/workshop worlds,
  offline replay, bridge vocabulary, memory bench and metrics:
  **100 passed**, 2 existing dependency deprecation warnings, 4.14 s.
- Historic eight ignores are not reused: bridge vocabulary and offline replay
  already run here. Core/dream/exact/two-round/workshop live graph scenarios still
  require server; skills tests need their own source/configuration classification.

## Foundation implementation and checks

Implemented this unit:

- `pyproject.toml` + `uv.lock`: installable `oneiro-ostis` wheel, explicit pinned
  FastAPI/Uvicorn + dev checks, `oneiro doctor|serve` entrypoints. Supported Python
  3.11–3.14 declared; actual installation verified on Windows Python 3.14.0 only.
  Other interpreter/OS/graph compatibility is not yet certified.
- `python/oneiro/config.py`: moved existing registry to one installed owner;
  `python/config.py` compatibility shim preserves scientific imports. Existing
  default file path preserved, explicit overrides supported. Path-sensitive cache,
  strict port/URL/type checks, kernel-locked writes and preserved previous config
  versions. No secret echo or ancestor `.env` discovery in the new package.
- `ownership.py` and `runtime.py`: kernel-owned lease prevents two owners and
  releases on process exit, without stale-PID guessing/deleting data. Async
  diagnostics do not block request intake on socket probes. No background legacy
  agent, provider request, graph mutation or memory replacement is started.
- `web.py` + packaged static assets: loopback-only same-origin setup/settings shell,
  CSRF/host checks, bounded body, explicit false readiness and 503 conversation/
  graph APIs. `/oneiro/` route exists but displays integration pending; **not** a
  completed graph panel. Configuration onboarding is initial, not full installer.
- README distinguishes new foundation from preserved historical implementation.
- Workspace docs gate had a pre-existing unclassified `docs/PROGRESS.md` (historical
  Oneiro log). Classified that existing file informative in manifest; did not move
  or rewrite its contents. Gate now passes.

Verification:

- `uv lock`, `uv build --wheel`: successful. Wheel includes only new package and
  assets, not legacy/science modules pretending migrated.
- `uv run --locked --group dev mypy python/oneiro`: **7 files, zero issues**.
- Locked isolated development environment: config + new package suite **34 passed**;
  Starlette warns that httpx TestClient is deprecated (non-failing dependency
  warning). Real installed HTTP smoke repeated and passed without resource warnings.
- Foundation/config/native/scientific offline selection: **116 passed**.
- Wider suite excluding only five identified live-server modules: first attempts
  **344 passed, 1 legacy transport failure** (`test_oneiro_setup` expected 401,
  received no status). Isolated legacy setup suite **23 passed**; diagnostic
  combined run **345 passed**. Intermittent combined-run transport behavior remains
  recorded, not suppressed or falsely called an entirely stable suite.
- Real installed-wheel HTTP smoke (`tests/installed_smoke.py`), using isolated
  `.runtime/foundation-smoke` interpreter with cwd **outside workspace** and no
  PYTHONPATH: root/settings/setup/graph route/assets all 200, no CORS; actual
  settings save 200; graph API 503; assistant readiness false; doctor exit 1;
  second CLI server refused occupied 9899 with exit 2. **Passed**.
- Graceful child stop verified; port 9899 closed afterward; OS lease reacquired.
  No owned process remains. Smoke state/env and diagnostic attempt retained under
  ignored `.runtime/`; existing data paths unchanged.
- Cross-process competing lease/abrupt child exit, corrupt config preservation,
  unknown stored fields/config history, concurrent writes and secret redaction
  covered by the 16 new package tests.
- Docs-route gate and whitespace checks pass. Browser visual walkthrough,
  provider completion, actual graph, VM, C++ build, migration/restore and desktop
  shortcut not verified in this unit.

Product remains **not ready**. A settings shell is an independent stage-1 slice,
not completion of stage 1's future domain contracts, nor a replacement for the old
working assistant. Old native/control-plane entrypoints remain untouched.

## Foundation defect pass (2026-10-02)

An audit of `3a2e663a4` graded the foundation SPEC 2, DESIGN 4, CORRECTNESS 6,
QUALITY 5 and named four defects. This pass fixed those four and nothing else:
no chat, graph, onboarding, installer or shortcut work was started.

### Changes

1. **One data root.** `config.data_root()` is now the single answer, defaulting to
   `~/.oneiro` and overridden by `ONEIRO_DATA_DIR`; `settings_path()` lives inside
   it and `runtime.py` takes the runtime lease from it. The old
   `~/.openclaw/oneiro` location — inside the agent workspace's parent — is no
   longer referenced by the product. Settings written there are **moved** into the
   data root on first read (`config._migrate_legacy`), never copied-and-left:
   history first, then the settings file, and the old directory is removed only
   when `rmdir` succeeds, so an unknown file keeps it alive for inspection.
   Migration is skipped entirely when `ONEIRO_SETTINGS_FILE` names a path, so a
   test or scripted run can never absorb the owner's real configuration.
2. **Route identity on the server.** New `python/oneiro/pages.py` owns what each
   route is; `web.py` names a page and `pages.render` produces the document from
   `static/page.html`. `/`, `/settings`, `/setup` and `/oneiro/` are four distinct
   documents with their own title, heading and notice. The client no longer
   rewrites a heading from `location.pathname`. The form is rendered on the two
   pages that need it (settings and setup); chat and graph carry status only.
3. **`writable` is measured, not claimed.** `config._writable` opens an existing
   file for writing without truncating it, or probes the nearest existing ancestor
   with a temporary file that is removed again, and returns the reason on failure.
   The page disables saving and states the reason when the file is not writable.
4. **The form comes from the registry.** All 19 declared settings render, grouped,
   including `llm.manager_model`, `llm.researcher_model`, `llm.executor_model` and
   `web.port`. `llm.api_key` stays write-only: a password control with no value
   attribute and a "currently set / not set" line. `runtime.data_dir` and
   `web.host` are declared `readonly` — the first because a file cannot relocate
   itself, the second because only loopback is accepted — so they render disabled
   and `config.save` refuses them by name.

Two consequences of (4) were found while verifying and are part of the same fix:
integer controls rendered with no `value` attribute, so submitting the page would
have posted `0` and been refused; and a full-form submit stored every declared
default explicitly, growing the owner's file from 4 keys to 15. The page now sends
only fields the owner actually changed and reports "Nothing changed" otherwise.

### Verified live in this pass

- Server started with `oneiro serve`; `/` 991 B, `/settings` 6571 B, `/setup`
  6515 B, `/oneiro/` 994 B — four distinct bodies with the headings
  Conversation / Oneiro settings / Setup / Graph panel. No CORS header present.
- **Real migration of the owner's own settings**: `~/.openclaw/oneiro/settings.json`
  and its `settings-history/` moved to `~/.oneiro/`; the file is byte-identical
  (md5 `8b3c4025b264…` before and after) and the old directory survived holding
  only `settings.json.write.lock`, as designed. The page reported the migration
  for that process. The owner's file was restored byte-exact after the probes.
- **Settings round-trip in a real browser**: changed `llm.manager_model` and
  `graph.host`, saved, `POST /api/settings` 200, reload showed the stored values.
  Saving with no edits reported "Nothing changed; nothing written" and wrote
  nothing. A one-field edit wrote exactly one key, leaving the other 14 untouched.
- `api_key` control has no `value` attribute in the served HTML; `web.host` and
  `runtime.data_dir` are `disabled`.
- `GET /api/settings` reports `writable: true`, empty reason, and the new root;
  with a non-directory in the settings path it reports `writable: false` and names
  the blocker. Save refuses `runtime.data_dir` with a read-only message.
- Tests: **44 passed** for config + package foundation (10 new). Whole suite
  **355 passed, 10 errors**, every error a `ConnectionAborted` to the absent
  sc-server in the same five live-server modules as the earlier baseline — no new
  failure. `uv run --frozen mypy`: **8 files, zero issues**.
- `uv build --wheel` then installed-wheel HTTP smoke outside the workspace with no
  PYTHONPATH: **passed**. A stale `build/lib` directory was packaging the deleted
  `index.html` into the wheel; it was recycled and the rebuilt wheel contains only
  the 8 modules and 3 static assets.
- Server stopped; port 9899 released; no owned process left running.

### Not verified in this pass

Conversation, the graph panel, the real OSTIS graph, memory/retrieval, model or
vision calls, Telegram, the Linux VM, C++ or ScAgents, scientific equivalence,
automatic updates, installer, desktop shortcut, migration/restore of the graph
itself, and any browser other than the loopback desktop Chromium used here. The
`/oneiro` and `/settings/` no-trailing-slash variants still answer 307; that was
out of scope for this pass and is recorded as a known rough edge, not a fixed
defect. The registry still declares settings (`dashboard.port`, `world.seed`,
`bench.*`, `workspace`, `mcp.source`) that no rewritten module consumes yet; they
were left declared on purpose and are not consumerless dead code by accident.

## 2026-10-02 — OSTIS start attempt: the knowledge base was rebuilt and cleared

**Outcome: stopped before writing anything. Stage 0's exit condition is NOT
closed, and the live graph was cleared as a side effect of starting Docker.**

Sequence, as it actually happened:

1. The Docker engine was down (`com.docker.service` STOPPED, the
   `dockerDesktopLinuxEngine` pipe absent). Docker Desktop 4.82.0 and WSL2 were
   installed, so the engine was started by launching Docker Desktop as a normal
   user process. Engine 29.6.1 came up in about ten seconds.
2. **The existing `oneiro-ostis` containers auto-started** through their
   `restart: unless-stopped` policy. `oneiro-ostis-machine-1` reported healthy and
   port 8090 began listening without any `docker compose` command from me.
3. The container then ran `sc-builder --clear` and re-imported all **201**
   knowledge-base sources between 13:26:31 and 13:26:35, wiping whatever the
   graph had held.

Verbatim from `docker logs -t --since 2026-10-02T13:26:00 oneiro-ostis-machine-1`:

```
13:26:31.592  Parse repo path file...
13:26:31.597  Collect all sources...
13:26:34.218  Build knowledge base from sources...
13:26:34.236  [1/201]: /knowledge-base/ontology/experience.scs - ok
...
13:26:35.736  Using default arguments.      <- sc-machine starts, after the rebuild
```

### Why it happened, and why the pre-flight check missed it

The container running the graph was created **2026-09-19** and was never
recreated. Its configuration is therefore older than the repository:

| | repository (on disk) | running container |
|---|---|---|
| `REBUILD_KB` | `0` (`docker-compose.yml`) | **`1`** |
| entrypoint | three-way branch: rebuild only on `REBUILD_KB=1` or empty storage | **two-way: `REBUILD_KB=1` → `sc-builder --clear`**, no storage check |

`grep -c "Existing graph found"` is `1` in `scripts/docker_entrypoint.sh` and `0`
in `/example-app/scripts/docker_entrypoint.sh` inside the image. The fix exists
in the repository and was never applied to the deployed container.

The mistake in the pre-flight check: I read `docker-compose.yml` and
`scripts/docker_entrypoint.sh` on disk, which both say the safe thing, instead of
`docker inspect`ing the container that actually owns the volume. The engine was
down when I started, so `docker inspect` was impossible at that moment — the
correct order was to start the engine with the auto-restart prevented (or to stop
the containers the instant they appeared, before the entrypoint ran), then
inspect, and only then decide. The `REBUILD_KB=1` in the container is exactly the
condition the owner asked to be ruled out first.

This was not a one-off: `docker logs` shows the same `Using default arguments.`
entry three times, at 2026-09-19 15:03, 2026-09-19 22:05 and 2026-10-02 13:26,
and sc-memory's `Last string offset` rose 103914 → 104483 → 104870 across those
runs, which is the signature of *rebuild then accumulate*, not *preserve*. The
graph in this deployment has therefore never survived a restart with agent
memory intact; the loss is cumulative and predates today.

### What was lost, and what can be recovered

Not quantifiable exactly: the volume was overwritten in place, and no copy was
taken beforehand. The evidence bounds it — the graph held the 201 KB sources plus
a small amount of runtime-written data (hundreds of bytes of strings between
restarts), and the agent was not running between 2026-09-19 and today. All 19
`kb-binary` volumes on the machine were inspected: every one is the same ~4.36 MB
rebuilt baseline dated 2026-09-20, so **no volume holds a pre-clear graph** and
there is nothing to restore from. The current volume is 4.3 MB, freshly built
from the same sources.

### Not done, deliberately

No node was written, no `python/bridge.py` round-trip was exercised, and no
snapshot or restore was attempted. Writing a test node and reporting a green
round-trip into a graph that had just been cleared would have hidden the loss
behind a passing check. The owner instruction was to stop and report when a start
wipes the knowledge base; that is the case here.

### State left behind

Docker Desktop is running with the engine up. `oneiro-ostis-machine-1` is
healthy, `oneiro-ostis-web-1` is up, ports 8090 and 8000 are listening,
`RestartCount` 0. **Both containers are left running as they are** — stopping or
recreating them is the owner's call, and either action is another start against
this configuration.

### The fix, for the owner to authorise

Recreate the machine container from the current repository so the safe entrypoint
and `REBUILD_KB=0` actually apply (`docker compose up -d --force-recreate
machine`), then confirm from the logs that the start line reads "Existing graph
found ... starting sc-machine without rebuilding" and that no `Build knowledge
base from sources...` appears. Only after that is a bridge round-trip and a
snapshot/restore meaningful evidence. The deeper fix belongs in stage 2: the
deployment must not be able to clear the graph on a routine start, and a verified
snapshot must exist *before* the next start, not after it.

## 2026-10-02 — OSTIS deployment fixed, snapshot proven, clearing guarded

Follows the incident above. Three things, in the order they were done, each
verified against the container that actually holds the volume.

### 1. The deployed container now runs the repository's entrypoint

The container that held the graph was created on 2026-09-19 and had never been
recreated, so it ran an entrypoint that called `sc-builder --clear` whenever
`REBUILD_KB=1`. The repository already had the fix; the deployment had drifted
away from it.

A full `docker compose build` was **not** used to re-sync it. `.dockerignore` is
empty and the build context is 5.7 GB, of which 5.6 GB is another agent's
`worktrees/`, followed by a C++ rebuild. `Dockerfile.entrypoint-sync` replaces
exactly the one file the container executes, on a pinned base
(`oneiro-ostis-machine:base-2026-09-19`) so repeated builds cannot stack the
overlay on itself. The image's script is byte-identical to the repository's:

```
image    /example-app/scripts/docker_entrypoint.sh  30fadc6605e0a18e0eb46adc9b9853dd
repo     scripts/docker_entrypoint.sh               30fadc6605e0a18e0eb46adc9b9853dd
```

**Live-verified from the container's own logs, not from the file on disk:**

| start | how | entrypoint said | "Build knowledge base" | sources imported |
|---|---|---|---|---|
| 1 | `docker compose up -d --force-recreate machine` | `Existing graph found in /kb.bin: starting sc-machine without rebuilding.` | 0 | 0 |
| 2 | `docker compose restart machine` (deliberate) | same | 0 | 0 |
| 3 | after adding the guard, recreated again | same | 0 | 0 |

`REBUILD_KB` is now `0` in the running container. The graph's five storage files
were md5-checksummed before the recreate and after every start: **byte-identical
across all three starts**, and sc-memory's `Last string offset` held at 104870
rather than resetting. That is the proof that failed before, now passing.

### 2. A snapshot, and a restore that was actually read back

Taken from a deliberately stopped server so the storage was quiescent, written to
a host file outside the Docker volume:

- snapshot: `.runtime/graph-snapshots/oneiro-kb-2026-10-02T13-36Z.tar.gz` (192,912 bytes, all five `.scdb` files)
- restored to: `.runtime/graph-restore-check/` — a scratch directory, never the live volume

Checksums of the extracted files are identical to the live graph's, and the live
volume was re-checksummed afterwards and was unchanged by the restore.

The readback is not a file listing. A separate container was booted **from the
restored copy** on port 8091, and the product's own bridge was pointed at it
(`.runtime/verify_restored_graph.py`, read-only: a template search and a
link-content read, no writes):

```
connected to ws://127.0.0.1:8091
  template search on ScAddr(65538): 1 result(s)
  relation identifier read back: nrel_system_identifier
search results: 1; identifier strings read back: 1
```

The restored server also logged `Existing graph found in /kb.bin: starting
sc-machine without rebuilding.` — it opened the restored storage and needed no
rebuild. Running the same probe against the **live** server on 8090 returned an
identical result, so the restored copy behaves like the original rather than
merely existing.

**Known limits of this readback, stated plainly:** the anchored template search
returned 1 result, not thousands, and the per-arc link accessor in the probe
(`triple.get(2)`) returned `ScAddr(0)`, so per-arc identifier strings were not
read. The probe proves the restored storage is traversable and that identifier
strings come back out of it; it does not measure graph size or enumerate content.
A stronger check belongs in stage 2 with the typed memory layer.

### 3. A routine start can no longer clear the graph silently

`REBUILD_KB=1` alone is now refused. Clearing requires a second, unambiguous
signal, and the refusal exits before either binary runs:

```
REFUSING TO CLEAR THE KNOWLEDGE BASE. Starting nothing.
  REBUILD_KB=1 asks for sc-builder --clear, which destroys every record in /kb.bin.
  On 2026-10-02 that wiped a live graph during a routine start.
  To rebuild from sources on purpose, start the container with:
    CONFIRM_KB_CLEAR=I_UNDERSTAND_THE_GRAPH_WILL_BE_CLEARED
```

**Live-verified in a real container** with `REBUILD_KB=1` and no confirmation —
the exact 2026-10-02 condition, against the live volume: exit code **3**, the
message above, and the live graph's checksums unchanged afterwards.

Covered by `tests/test_entrypoint_guard.py` (**6 passed**), which runs the real
script with stub binaries and asserts: refuse-and-start-nothing without the
confirmation; a wrong phrase is still refused; a confirmed rebuild does pass
`--clear`; an existing graph starts with `sc-machine` and never `sc-builder`; a
first-run build happens **without** `--clear`; and two routine starts rebuild
nothing. The tests pass the parent environment through in full and use Git's MSYS
bash launcher, because a stripped environment or `usr\bin\bash.exe` fails to
start in a way that looks like a test failure but is not one.

### Test suite consequence

The graph-backed tests that errored with `ConnectionAborted` now run:

- whole suite: **371 passed, 0 errors** (was 355 passed, 10 errors)
- `test_core_loop` + `test_replay_exactness` against the live server: **7 passed**
- `uv run --frozen mypy`: **8 files, zero issues**

### Not verified

- **No write was made to the graph.** The bridge round-trip the owner originally
  asked for (write a node, read it back) was not performed: the graph is a
  freshly rebuilt KB, and a probe on it would describe the rebuild, not the
  product's memory.
- The full `Dockerfile` build was **not** re-run, so the C++ module, the venv and
  the extensions in the image are still the 2026-09-19 build. Only the entrypoint
  was re-synced. A `.dockerignore` is needed before that build is practical.
- The snapshot proves restore of *this* graph. It does not prove restore of a
  graph containing agent-written records, because none exist to snapshot.
- The snapshot lives in the project's gitignored `.runtime/`. A copy off this
  machine is still wanted; nothing here is protected against losing the checkout.
- Container-level restore onto a different Docker host, and restore while the
  live server is running, were not attempted.
- `ostis-example-app-*` containers from an older project were left untouched.
- The `/oneiro` and `/settings/` 307s, the settings POST handler's inline
  imports, the per-request `_writable` probe, and `tests/installed_smoke.py`
  lacking a `test_` prefix all remain open from the previous pass.

## 2026-10-02 — Stage 1b: typed records, event envelopes, memory seam

### What was built

- **`python/oneiro/records.py`** — one schema for conversation, task, run, action,
  decision, note, experience, experiment and release. Versioned (`SCHEMA_VERSION`),
  frozen dataclasses, and `decode` is the only way in, so a truncated store fails
  there rather than becoming a record missing its meaning. Three decisions are
  load-bearing: `Provenance` separates what the owner said from what a model
  claimed from what a tool actually did; `State.UNCERTAIN` gives interrupted work a
  real name; and `Action.may_retry()` is the single place that decides retrying,
  and it refuses whenever an effect's outcome is unknown.
- **`python/oneiro/events.py`** — envelopes with `causation_id` and
  `correlation_id`, so a Telegram reply and the web request it answers share one
  correlation while each event points at what caused it. Every event carries a
  digest that detects an edited or replayed envelope, and `read_events` reports a
  torn final line rather than discarding records that were already durable.
- **`python/oneiro/memory.py`** — the read seam. No substitute store exists and
  none was added. `sc_client` is imported inside the probe, so a wheel installed
  without it still starts and still says why it cannot read memory.

### Live-verified

- `oneiro serve` on 9899; `/api/graph` answers **200** in ~0.26 s with
  `required: OSTIS`, `fallback: null`, `reachable: true`, `verified: false`,
  `arcs_found: 1`, and the reason in `blocked`.
- `/oneiro/` renders those same facts server-side; the four routes remain four
  distinct documents with their own headings.
- Whole suite **387 passed, 0 errors** (was 371). `uv run --frozen mypy`:
  **11 files, zero issues**. 16 new domain tests.

Three bugs were caught by the new tests rather than by inspection: `to_dict` did
not serialize the nested `Effect`; the event digest was circular because
`to_dict` embedded the field holding the hash; and `sequence()` invented event
names outside the declared set, so every wrapped record would have been rejected
on the way back in.

### The finding that matters more than the code

**The graph answers the protocol but holds no traversable knowledge base.**

The single arc matching `nrel_system_identifier` has unresolved wildcard endpoints
on both sides — sc-memory echoing the relation itself back, not content hanging off
it. Searching for identifier arcs attached to that node returns zero. The
container log does show the compiled agent module subscribing to
`action_initiated`, so the graph is not entirely empty, but a traversal cannot find
knowledge-base content.

So the 13:26 rebuild reported all 201 sources as `ok` and yet produced a graph that
does not demonstrably contain them. **Stage 2's exit condition "old data queryable"
cannot be evaluated until this is explained**, and nothing in this pass was built
on the assumption that the KB is loaded.

### Not verified

- No node was written. The write/read-back round-trip through `python/bridge.py`
  is still outstanding, and it is the next thing that would settle the question
  above: if a written node reads back, the write path works and the emptiness is
  about imported KB content; if it does not, the storage path is broken.
- `memory.probe` proves reachability and traversal only. It does not measure graph
  size, and its anchor search returns one result, so it cannot answer "how much is
  in there".
- The records are not yet persisted anywhere; `decode_many` and the JSON-lines
  format are exercised by tests, not by a real store.
- The 5.7 GB build context is unfixed, so reproducible-build compatibility (the
  remainder of stage 1, tracked as 1c) is untouched.
- Conversation is still `503`; `/api/message` is unchanged and honest.

## 2026-10-02 — Probe round-trip: writes do not survive a restart

Stage 1b left one open question that a single round-trip would settle: the graph
answers the protocol but a traversal finds no knowledge-base content. This pass
took the snapshot first, wrote one clearly-marked probe through
`python/bridge.py`, and read it back through the same path.

**The answer is not the one that was hoped for. The write works inside one server
session and does not survive a restart.**

### Recovery point taken first

Clean stop, then tar of the quiescent storage to
`.runtime/graph-snapshots/oneiro-kb-preprobe-20261002T1412Z.tar.gz` (199,940
bytes). Storage checksums recorded before the stop and again at snapshot time
were **identical**, which establishes that a clean stop by itself moves nothing —
so any later difference is attributable to the probe and not to the shutdown.

```
1afa09c4734479ea7714b8401641ae49  strings2.scdb
64f599223d13198412810a97935bfe9f  string_offsets_link_hashes.scdb
6639f2b5fc8c7a833a6b87dd8cb084f8  term_string_offsets.scdb
ba99cf016e3a5745afc885161a999820  segments.scdb
f0db8422ab951f4350dd06868f4c1ed1  strings1.scdb
```

### The write, through the product's own path

`python .runtime/probe_bridge_roundtrip.py` — `OneiroBridge.record_attempt`, which
resolves four entities through `resolve_entity` (creating ConstNodes when absent)
and runs the compiled C++ agent `action_record_attempt`:

```
connecting to localhost:8090
connected; running the product's own agents
write returned addr=ScAddr(196645)
re-reading through the same path
read back 1 attempt(s) for the marker
["probe_2026_10_02_bridge_roundtrip", "verify_storage_roundtrip", "oneiro_probe_node", "written_through_python_bridge", "rewrite-stage-1b-probe", "", null]
OK: the written node came back through the product's own path
exit=0
```

**That part genuinely works.** The bridge, the entities, the C++ agents and the
retrieval path are all sound.

### What the restart exposes

`record_attempt` writes before it reads, so on its own it cannot distinguish a
persisted node from one it just created. `.runtime/probe_readonly.py` writes
nothing and asks the server what it already holds.

After a clean stop and start, with **no write in between**:

```
=== step 1: read-only BEFORE the stop ===
attempts stored for the marker: 1
  addr=ScAddr(196637) subject=probe_2026_10_02_bridge_roundtrip action=verify_storage_roundtrip outcome=written_through_python_bridge
RESULT: at least one attempt survived
=== step 2: clean stop ===
 Container oneiro-ostis-machine-1 Stopped
=== step 3: start (no rebuild expected) ===
 Container oneiro-ostis-machine-1 Started
=== step 4: read-only AFTER the stop/start, nothing written in between ===
attempts stored for the marker: 0
RESULT: nothing persisted
```

One attempt before, **zero** after. The node does not survive.

### Where the write goes

Of the five storage files, exactly one changed across the whole probe:

```
< 1afa09c4734479ea7714b8401641ae49  strings2.scdb      (before the probe)
> 3f0cb5d94b344e6bca495ce6e93f74da  strings2.scdb      (after)
```

`segments.scdb` — the file that holds node and arc data — is **byte-identical**.
Only the string dictionary grew. There is no container-internal `kb.bin` at
`/example-app/kb.bin` or `/example-app/install/sc-machine/kb.bin`, so the
dictionary is genuinely reaching the named volume while the segment data is not.

That is the defect: sc-memory is updating its string dictionary on disk but not
persisting node and arc content, so every write is lost at shutdown. The probe
marker is still sitting in `strings2.scdb` as dangling dictionary strings; it is
clearly marked and safe to discard, and it was left in place rather than
"cleaned up" so the residue is visible.

### What this means for stage 2

Stage 2's exit condition — "new records survive restart" — **cannot be met on
this stack**, and it is not a contract problem that typed records can solve: the
storage underneath drops writes. "Old data queryable" cannot be evaluated for the
same reason, and the near-empty graph reported in the previous pass is now
explained better than "imported content is missing": content that was written is
discarded on shutdown, so the graph can only ever hold what a single session
wrote.

The 201 sources sc-builder reported as `ok` were also written in a session that
has since ended, which is consistent with what the traversal now shows.

Nothing was worked around: no configuration was changed, no container was
recreated or re-imported, and no substitute store was added.

### Not verified

- The root cause inside sc-memory is not diagnosed. Whether it is
  `max_loaded_segments`, the dump manager being off, or a shutdown-flush
  behaviour is unestablished; that needs the sc-machine sources or a controlled
  experiment, not another guess.
- Only `record_attempt` was exercised. Other bridge writers may behave
  differently, though a storage-layer failure would affect all of them.
- The 13:26 rebuild is not re-examined; this pass did not re-import anything.
- Conversation, onboarding and the installer were not started.

## Next independent work

Stage 1b: typed, versioned domain records and event envelopes in `oneiro`, and the
memory/retrieval seam behind `/api/graph`. Keep the graph-dependent exit condition
honest — attempt a consistent OSTIS snapshot and isolated restore as soon as the
sc-machine is reachable, otherwise record the blocker and continue.

The four audit items still open from the earlier review, none of which this pass
was asked to touch: `/oneiro` and `/settings/` answer 307 without their trailing
slash; the settings POST handler imports `json`/`asyncio` inside the function
while its siblings are module-level; `describe()` per-row work is now hoisted but
`_writable` still touches the filesystem on every settings page hit; and
`tests/installed_smoke.py` still has no `test_` prefix, so a normal `pytest` run
does not execute it.
