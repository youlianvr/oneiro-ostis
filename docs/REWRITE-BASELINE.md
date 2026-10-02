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

## 2026-10-02 — Cause of the lost writes: sc-machine ignores SIGTERM

The hypothesis in the brief — segment-dump configuration being off or too low —
is **wrong**, and it is ruled out by experiment below. The cause is in how the
process is stopped, and it is a property of the sc-machine build.

### The finding

`sc-machine` registers a signal handler at startup (every log ends with
`Signal handler`) but **does nothing on SIGTERM**. Docker stops a container with
SIGTERM, so the graceful path that dumps segments never runs, and after the grace
period Docker SIGKILLs the container. **SIGINT runs the full save path.**

### The experiment

All of it in scratch copies of the storage under `.runtime/`, on ports 8092–8094.
The live graph, its container and its configuration were not touched; the three
test containers were removed afterwards.

**Control — the live entrypoint unchanged, port 8092.** Wrote a node through
`python/bridge.py` (`write addr = ScAddr(196636)`, read back 1), then:

```
$ docker stop -t 60 kb-test-control
$ docker logs kb-test-control | grep -E "segments saved|Shutdown"
(nothing)
$ docker inspect kb-test-control --format '{{.State.ExitCode}}'
143
```

With a 60-second grace the shutdown produced **zero** output.

**Test — `sc-machine` launched with `exec` so it is PID 1, port 8093.** This was
my first hypothesis, that the `tini → bash → sc-machine` tree (`tini` PID 1,
`bash` PID 7, `sc-machine` PID 10) kept SIGTERM from reaching the server. The
process tree did change to `PID 1 sc-machine` — and it made no difference:

```
$ docker inspect kb-test-exec --format '{{.State.ExitCode}}'
137                      # SIGKILL: 60s grace expired, server never exited
$ docker exec kb-test-exec bash -c 'ps -eo pid,comm | grep sc-machine'
      1 sc-machine       # still alive after a direct kill -TERM
```

**The signal that works.** Sending SIGINT to the same PID:

```
[14:25:15][Info]: Shutdown ScKeynodes
[14:25:15][Info]: [sc-memory] Shutdown extensions
[14:25:16][Info]: [sc-fs-memory] Sc-memory segments saved
[14:25:16][Info]: [sc-fs-memory] All sc-fs-memory dictionaries saved
[14:25:16][Info]: [sc-fs-memory] Successfully shutdown
```

and the storage really changed:

```
baseline  ba99cf016e3a5745afc885161a999820  segments.scdb
after     3fe89ca32c99601b4ff2997b5a9d1f46  segments.scdb
```

**What rules configuration out.** `max_loaded_segments`, `dump_memory` and the
ini were not varied between the failing and the working case: the same image, the
same `knowledge-base/oneiro-ostis.ini`, the same storage, the same port mapping.
The only difference was which signal arrived. Nothing in that ini governs signal
handling. (The stock-config control was inconclusive: without `-c` sc-machine
exits at once with `Knowledge base binaries directory is required`.)

### The fix, and what applying it would take

`stop_signal: SIGINT` on the `machine` service in `docker-compose.yml`, so
`docker stop` and `docker compose stop` deliver the signal the server honours.
Alternative if SIGINT must not be relied on: a wrapper that traps SIGTERM and
re-raises it as SIGINT.

**Nothing was applied.** The live deployment is untouched: `oneiro-ostis-machine-1`
is still the container started before this pass, its storage differs from the
probe snapshot only by the dictionary entry the previous pass's probe left, and
`docker-compose.yml`, `knowledge-base/` and `scripts/` are unmodified in git.

### A second defect, still open

With the save path finally running, the probe node **still did not read back**
after the restart:

```
attempts read back after SIGINT shutdown + restart: 0
```

So SIGTERM is the reason writes were being lost, but it is not the whole story:
either the record is not fully persisted even when segments are saved, or
`action_retrieve_attempts` cannot find records once the server has reloaded. The
subject string is interned in the saved `strings2.scdb` but absent from the
SIGTERM-path control copy, so the write reached disk in the working case.

Deciding between those two needs a read path that does not go through the
retrieval agent — resolving the entity directly from a fresh connection — which
this pass did not do. Stage 2 stays blocked until both are closed.

### Not verified

- No fix was applied or tested against the live deployment, by instruction.
- Whether `stop_signal: SIGINT` survives a `docker compose up --force-recreate`
  in this Docker Desktop version is untested.
- The retrieval-side defect above is diagnosed but not explained.
- Only `record_attempt` was exercised; other bridge writers are untested against
  a restarted server.
- No conversation, onboarding or installer work was started.

## 2026-10-02 — Write persistence settled: the record survives, the signal does not

The previous pass left one question open and two candidate causes with opposite
consequences. Either the probe record was genuinely absent from saved storage
and the write path was still incomplete, or it was in storage and the retrieval
agent could not find records after a reload. The mission for this pass was to
decide between them with a read path that does not go through
`action_retrieve_attempts`, and to leave the live deployment, `docker-compose.yml`
and the live graph untouched. No fix was applied and no configuration was changed.

### Method

A fresh scratch copy of the graph was taken from the live volume
(`.runtime/probe-addr/`, baseline `segments.scdb ba99cf01…`) and served by a
throwaway container on a spare port with `sc-machine` as PID 1. One record was
written through the product's own bridge, which reported where it landed:

```
{"subject_string": "addr_probe_subject_2026_10_02",
 "subject_addr": "ScAddr(196609)", "attempt_addr": "ScAddr(196636)"}
```

The container was then stopped with the SIGINT sequence proven in the previous
pass, and the scratch copy reloaded into a second throwaway container. Nothing
was read back through the retrieval agent until the last step.

### The read path had to be rebuilt first

Two facts about reading this server had to be established before any of them
could be used as evidence, and both would have produced false conclusions if
assumed.

**`search_by_template` returns no real results on this build.** Against arcs that
were directly observed to exist, every raw `ScTemplate` came back empty, and the
one non-empty result was a degenerate echo of the relation itself:

```
concrete (196609, 196612, 196610): 0 returned
outgoing (196609, VAR, VAR):       0 returned
attempt outgoing (196636, VAR, VAR): 0 returned
reverse sweep (VAR, VAR, 196610): 0 returned
sweep (VAR, 65538, VAR):           1 returned -> (0, 65538, 0)
idtf string search "addr_probe_subject_2026_10_02": 0 returned
```

The last line is the same query that `memory.probe()` performs, run against the
live graph on 8090, which reproduces the identical `1 returned, 0 resolved`. So
this is not a property of the scratch copy, and it is why the earlier baseline
already recorded a wildcard-only anchor result. Template search is therefore
unusable as a witness in either direction, and the agent's own C++ search is a
different implementation that is not covered by this finding.

**`resolve_keynodes` creates what it cannot find.** A string that had never been
seen resolved to a live `CONST_NODE` with a fresh identifier link, and resolved
to the same address on a second call. On this server, "it resolved" is not
evidence that the element existed beforehand. Any check that treats a successful
resolve as proof of prior existence is void.

**The absent-element signature** is a `ServerError` —
`InvalidParams: Specified sc-element sc-address is invalid to get sc-type` — for
an address outside the allocated segments, and an error-free `ScType(0)` for an
unused offset inside one. `get_elements_types` answers; it is the only read
primitive here that can be trusted.

### What is in storage

`get_elements_types` plus `get_link_content`, addressed directly with no search
involved, over segment 3 of the reloaded copy. The write is intact — node,
identifier link, relation arcs and all:

```
ScAddr(196609) CONST_NODE
ScAddr(196610) CONST_NODE_LINK  content='addr_probe_subject_2026_10_02'
ScAddr(196611) CONST_COMMON_ARC  ScAddr(196612) CONST_PERM_POS_ARC
ScAddr(196613) CONST_NODE        ScAddr(196614) CONST_NODE_LINK content='addr_probe_action'
ScAddr(196615) CONST_COMMON_ARC  ScAddr(196616) CONST_PERM_POS_ARC
ScAddr(196617) CONST_NODE        ScAddr(196618) CONST_NODE_LINK content='addr_probe_object'
ScAddr(196619) CONST_COMMON_ARC  ScAddr(196620) CONST_PERM_POS_ARC
ScAddr(196621) CONST_NODE        ScAddr(196622) CONST_NODE_LINK content='addr_probe_outcome'
ScAddr(196623) CONST_COMMON_ARC  ScAddr(196624) CONST_PERM_POS_ARC
...
ScAddr(196636) CONST_NODE                                  <- the attempt node
ScAddr(196653) CONST_NODE_LINK  content='addr-probe'
ScAddr(196658) CONST_NODE_LINK  content='address capture probe'
```

Segment 3 holds 79 live elements in the reloaded copy against 14 in the live
baseline, and the extra 65 include link and arc types, not just nodes. **The
record is in storage.** The first candidate cause is refuted.

### What the retrieval agent sees

Queried last, on the reloaded copy:

```
action_retrieve_attempts('addr_probe_subject_2026_10_02') -> 1
  ScAddr(196636) | addr_probe_subject_2026_10_02 | addr_probe_action
                | addr_probe_outcome | addr_probe_object
```

To rule out the possibility that the read probes above had put the graph into a
retrievable state, that container was stopped with SIGINT again
(`segments.scdb 209f4280…` → `ba8cab97…`, exit 0, `Successfully shutdown`) and
reloaded into a third container on port 8096, where the retrieval agent was the
*first* thing run, with no other read beforehand:

```
CLEAN RELOAD action_retrieve_attempts -> 1
  ScAddr(196636) | addr_probe_subject_2026_10_02 | addr_probe_action
                | addr_probe_outcome | addr_probe_object
```

Two consecutive save-and-reload cycles, both returning the record. The second
candidate cause is refuted as well: the retrieval agent sees records after a
reload.

### Verdict

Both candidate causes are resolved, and both are resolved against the hypothesis
that motivated them.

- **Is the record absent from saved storage? No.** Every element, arc and link
  content the write created is present after reload.
- **Is it present but invisible to `action_retrieve_attempts` after a reload?
  No.** The agent returns it on a clean reload, twice.
- **The earlier "0 after restart" is not reproduced.** It could not be recreated
  from the same saved bytes, and no mechanism was found that would make it
  reproducible. It is recorded as an unexplained result of that experiment's
  setup, which this pass did not repeat and can no longer inspect, not as a
  property of the system. This is a residual unknown, not a closed question.

The stage 2 blocker is therefore **only** the signal. Persistence and retrieval
both work once the save path runs; under the shipped configuration `docker stop`
sends SIGTERM, sc-machine registers a handler and does nothing, and the record
is lost. The fix identified in the previous pass — `stop_signal: SIGINT`, or a
wrapper that re-raises SIGTERM as SIGINT — remains correct and remains
deliberately unapplied.

### A second defect, found on the way

Raw `ScTemplate` search from the Python client is non-functional on this build,
while the C++ agent path is not. That is a real defect in its own right and it is
not the stage 2 blocker, because the product's sanctioned read route is the
agent. It matters because several Python-side readers depend on the broken path
and will return empty rather than fail:

- `bridge.all_subjects()` walks `concept_attempt` with `search_by_template`.
- `oneiro.memory._read_graph()` anchors on `nrel_system_identifier` with
  `search_by_template` and, correctly, refuses to call a wildcard-only match a
  populated graph — so `/api/graph` and `/oneiro/` are reporting the graph as
  unreachable-content rather than as populated, which is honest but is not the
  same as reading it.

Stage 2 retrieval contracts must not be written against
`sc_client.search_by_template` until this is characterised. Its cause is not
diagnosed here and was not in scope.

### Not verified

- The exact arc endpoints in the segment 3 dump were inferred from the standard
  node / membership-arc / perm-arc layout and the observed type sequence, not
  read back, because the search that would confirm them is the broken one. The
  elements and their link content are read directly and are not inferred.
- Only `record_attempt` was exercised against a restarted server. Other bridge
  writers (`save_strategy`, `save_memory_sessions`, the dream-cycle paths) are
  untested across a restart.
- The SIGINT fix is still unapplied and untested against the live deployment,
  and whether `stop_signal: SIGINT` survives `docker compose up --force-recreate`
  in this Docker Desktop version is untested.
- The cause of the non-functional template search is undiagnosed.
- No conversation, onboarding or installer work was started.

### State left behind

Test containers `kb-probe`, `kb-probe2` and `kb-probe3` were removed. The live
deployment was not stopped, restarted or reconfigured; after all of the above its
storage is byte-identical to the recorded baseline and it is healthy:

```
ba99cf016e3a5745afc885161a999820  segments.scdb
f0db8422ab951f4350dd06868f4c1ed1  strings1.scdb
3f0cb5d94b344e6bca495ce6e93f74da  strings2.scdb
64f599223d13198412810a97935bfe9f  string_offsets_link_hashes.scdb
6639f2b5fc8c7a833a6b87dd8cb084f8  term_string_offsets.scdb
```

`docker-compose.yml` is unchanged. The diagnostic scripts used here live in the
gitignored `.runtime/` and are not part of the product.

> **Correction (Block C, later the same day).** The section immediately above blamed `search_by_template` for returning no real results. That was wrong: the probes placed a node type (`VAR_NODE_LINK`, `0x43`) in the connector slot, which matches nothing. Template search works; the real defect was one reader of our own. See 'Block C: template search was never broken'.



The approved four-block plan runs A reproducible build (1c), B the SIGINT fix
in the live compose, C the OSTIS read-path characterisation, D the stages after
2. Block A is complete. It stopped or restarted nothing: the live machine ran
3 hours uninterrupted through it and its graph was not written to.

### What the 5.6 GB was

`projects/ostis/oneiro-ostis/worktrees/` held four directories, 1.42 GB each:

```
oneiro-live-tg2855-a1-a023212-c1        [agent/live-tg2855-a1-a023212-c1]
oneiro-live-tg2855-a1-a023354-c1        [agent/live-tg2855-a1-a023354-c1]
oneiro-live-tg2855-a2-a023951-c1        [agent/live-tg2855-a2-a023951-c1]
oneiro-live-tgtrehearsal-1-a021621-c1   [agent/live-tgtrehearsal-1-a021621-c1]
```

They are registered git worktrees of the **parent workspace repository**, not of
oneiro-ostis, created 2026-09-23 by a Telegram ("live-tg") session and all
checked out at the same commit `dc8661682`. Each is a full checkout of the
entire workspace — `projects/` alone is 750 MB of it. They are another agent's
working copies. Nothing in this pass read, moved or removed them; they are
excluded from the build context only.

### `.dockerignore` did not exist

The previous baseline recorded it as "empty"; it was in fact absent, so Docker
was packing everything. Measured before the change:

```
6.02 GB in 61,095 files across 17,876 directories
```

Written as 15 rules covering the worktrees, build outputs, the local virtualenv
and tool caches, `.runtime/`, the live graph directory, runtime state and
repository history. Every rule is justified in the file itself. What the C++
build actually reads was checked first, so the rules exclude only things no
stage uses: `CMakeLists.txt` adds only `problem-solver/`, `SC_BUILD_TESTS` is
off, and `cmake/` is referenced solely for the test and clang-format modules
that are not included. Measured after:

```
31.2 MiB in 7,619 files across 4,394 directories   (computed)
23.50 MB                                          (Docker's own report)
```

The second figure is BuildKit's, from `transferring context: 23.50MB 2.8s`, and
is the one to trust.

### Full build

Built with `docker build -f Dockerfile -t oneiro-ostis-machine:verify-1c .`.
Deliberately **not** tagged `oneiro-ostis-machine:latest`, because that tag
carries the deployed image and overwriting it would change what a future
`docker compose up` deploys. The live container is unaffected by a retag in any
case, but there was no reason to disturb the reference.

Every stage ran; only the base pull was cached. The C++ module compiled from
scratch — GCC 13.3.0, CMake configured fresh, all three sources built and
`liboneiro-module.so` linked:

```
[1/4] Building CXX object .../oneiroModule.cpp.o
[2/4] Building CXX object .../agents/RetrieveAttemptsAgent.cpp.o
[3/4] Building CXX object .../agents/RecordAttemptAgent.cpp.o
[4/4] Linking CXX shared library extensions/liboneiro-module.so
```

It took 1.5 s because the ccache mount was warm, so this proves the dependency
graph and the link step, not a cold-cache compile time. The sc-machine 0.10.5
release archive was downloaded during the build, so network reachability held.

### The overlay is no longer needed

`Dockerfile.entrypoint-sync` exists because the deployed container had been
created on 2026-09-19 with a stale entrypoint and a full build was not available
to replace it. The freshly built image carries the repository entrypoint
byte-for-byte:

```
30fadc6605e0a18e0eb46adc9b9853dd  /example-app/scripts/docker_entrypoint.sh   (image)
30fadc6605e0a18e0eb46adc9b9853dd  scripts/docker_entrypoint.sh                (repo)
```

That md5 is the one recorded for the guard commit and for the deployed
container, so the full build and the overlay agree. The overlay is still the
cheaper way to ship a one-line shell change; it is no longer the only way, which
is what made the entrypoint drift possible in the first place. Nothing was
changed to remove it — see the open items.

### The built image boots and answers

Run from `oneiro-ostis-machine:verify-1c` on port 8097 against a scratch copy of
the graph taken from the live volume **read-only**, with the live container
running throughout. The real image entrypoint was used, so this also exercised
tini.

```
Existing graph found in /kb.bin: starting sc-machine without rebuilding.
[sc-memory] Initialize module: /example-app/build/Release/extensions/liboneiro-module.so
[sc-server] Sc-server run
[sc-memory] Successfully initialized
```

Health check inside the container: exit 0.

Product round-trip through the bridge against that container — write, SIGINT
save, reload, read back:

```
write   {"subject_addr": "ScAddr(196610)", "attempt_addr": "ScAddr(196637)"}
        in-session retrieval agent sees: 1
save    Successfully shutdown, exit 0, segments.scdb ba99cf01… -> 2c23b826…
reload  action_retrieve_attempts -> 1
        ScAddr(196637) | addr_probe_subject_2026_10_02 | addr_probe_action
                      | addr_probe_outcome | addr_probe_object
```

### One process-model fact for Block B

The image entrypoint is `tini -- docker_entrypoint.sh`, so in the real deployment
`sc-machine` is **not** PID 1 — it is a child of tini:

```
1  /usr/bin/tini -- /example-app/scripts/docker_entrypoint.sh run
10 /example-app/install/sc-machine/bin/sc-machine -c ...
```

This pass's earlier persistence probes ran `sc-machine` as PID 1 via an
overridden entrypoint, which is why `kill -INT 1` worked there. In the real
image, `kill -INT 1` reaches tini alone and the container stayed up; signalling
the child (`kill -INT 10`) ran the save and the container exited 0. Block B's
`stop_signal: SIGINT` therefore has to be verified as *docker → tini →
sc-machine*, not as a direct signal, and that verification is Step 5.

### Live state after Block A

Never stopped, never restarted, never written to by this pass:

```
ba99cf016e3a5745afc885161a999820  segments.scdb
f0db8422ab951f4350dd06868f4c1ed1  strings1.scdb
a8569a7fdf0cefdd6f682ea77b41c214  strings2.scdb
64f599223d13198412810a97935bfe9f  string_offsets_link_hashes.scdb
6639f2b5fc8c7a833a6b87dd8cb084f8  term_string_offsets.scdb
health=healthy  running=true  up 3h
```

One observation that is not a Block A result and is not explained: the live
`strings2.scdb` reads `3f0cb5d9…` at the start of this pass and `a8569a7f…` now,
while `segments.scdb` is unchanged and the container has not saved. Something in
the running stack interned strings into the live graph. No write was issued
against port 8090 from this pass — the two scripts run there use
`get_elements_types`, `search_by_template`, `search_links_by_contents_substrings`
and `get_link_content`, all reads, and neither resolves keynodes. The cause is
unestablished and is recorded as an open item, not as a finding.

### Not verified

- The build used a warm ccache, so cold-cache compile time is unmeasured.
- `oneiro-base:latest` is a **local, undeclared base image**. It exists here
  (782 MB), so the build ran, but a clean checkout on another machine cannot
  build this Dockerfile today. This is a stage 1 exit condition ("reproducible
  build") and stage 8's "clean Docker build without undeclared local base image"
  at the same time. Not fixed here: publishing or vendoring a base image is a
  larger decision than Block A authorises, and it borders on publication.
- The build was verified for `oneiro-ostis-machine` only. The `web` service
  pulls `ostis/sc-web:0.9.0` from a registry and is out of scope.
- No `docker compose build` was run, only a direct `docker build`; the compose
  build path itself is therefore unverified with the new `.dockerignore`.
- The image built here is tagged `verify-1c` and is not deployed. The live
  service still runs the 2026-09-19 image with the overlay.

## 2026-10-02 — Block B: the SIGINT fix, and the half that does not work

Block A turned up a process-model fact that changed how Block B had to be
verified, so Block B ran in the reverse order: the mechanism was proven on a
scratch compose project first, and the live service was stopped once, for the
snapshot and the application together.

### The approved fix does not work on its own

`stop_signal: SIGINT` was proposed by the previous pass and authorised for the
live compose. Applied on its own to a scratch compose project, it fails
completely:

```
docker compose stop      20:44:11 -> 20:45:42   (the full 90s grace period)
exit code                137                    (SIGKILL)
shutdown output          none
segments.scdb            ba99cf01... -> ba99cf01...  (unchanged)
```

The container was killed after the grace period expired having never run the
save path. Applying exactly that to live would have left the graph just as
unsafe as before, with a longer stop and an extra line in the compose file to
show for it.

### Why

The process tree in the real image is three deep, not two:

```
1   /usr/bin/tini -- /example-app/scripts/docker_entrypoint.sh run
7   bash /example-app/scripts/docker_entrypoint.sh run
10  /example-app/install/sc-machine/bin/sc-machine -c ...
```

`docker stop` signals PID 1. tini forwards to bash. Bash does not forward
signals to its foreground child, so sc-machine never receives anything. SIGINT
and SIGTERM both stop there — which is why the save has never run on a stop,
and why the earlier probes that appeared to contradict this had overridden the
entrypoint and made sc-machine a direct child of the container.

### The fix is a pair, and both halves are now in place

`scripts/docker_entrypoint.sh` launches sc-machine with `exec`, so it replaces
the shell and becomes tini's direct child. `docker-compose.yml` then sets
`stop_signal: SIGINT` and `stop_grace_period: 90s`.

Proven as a pair, first on scratch, through the real `docker compose stop`:

```
process tree        tini(1) -> sc-machine(7)          (bash gone)
docker compose stop 20:52:31 -> 20:52:35
exit code           0
log                 [sc-fs-memory] Successfully shutdown
segments.scdb       22a714f5... -> 15c7a4d1...
reload              action_retrieve_attempts -> 2
                    ScAddr(196636) and ScAddr(262156), both intact
```

Both records written before the stop were still there after it. The same test
against a container whose entrypoint lacked the `exec` gave exit 137 and an
unchanged `segments.scdb`, so the two halves are individually insufficient and
individually necessary.

The `exec` is protected by `tests/test_entrypoint_guard.py`, which asserts both
sc-machine invocations are exec-prefixed, so it cannot be removed later as if it
were cosmetic. That test checks the shape of the script rather than container
behaviour, because the behaviour needs a container; the runtime proof is the
round-trip above.

### Applied to live

Live checksums before, taken while the container was running:

```
ba99cf016e3a5745afc885161a999820  segments.scdb
f0db8422ab951f4350dd06868f4c1ed1  strings1.scdb
ec64501ab153efc57e80006b4100265a  strings2.scdb
64f599223d13198412810a97935bfe9f  string_offsets_link_hashes.scdb
6639f2b5fc8c7a833a6b87dd8cb084f8  term_string_offsets.scdb
```

Snapshot taken from the stopped container with the proven procedure:
`.runtime/graph-snapshots/oneiro-kb-preSIGINT-20261002T1754Z.tar.gz`, 200,141
bytes, five files, `segments.scdb` inside it checksumming to `ba99cf01…` and so
matching what the live container reported.

The pre-fix `docker compose stop machine` exited **143** — SIGTERM, no save —
which is the defect reproducing live, on demand.

The image was replaced with the entrypoint-sync overlay rebuilt from the
updated script, and the container recreated:

```
Existing graph found in /kb.bin: starting sc-machine without rebuilding.
process tree      tini(1) -> sc-machine(7)
docker compose stop machine   17:56:00 -> 17:56:02
exit code         0
log               [sc-fs-memory] Successfully shutdown
```

Live checksums after:

```
93cea54c02b22a92f6ee329c15639e61  segments.scdb              <- rewritten
f0db8422ab951f4350dd06868f4c1ed1  strings1.scdb              <- unchanged
ec64501ab153efc57e80006b4100265a  strings2.scdb              <- unchanged
7cfb78b61334e53e703838e39fec016e  string_offsets_link_hashes.scdb  <- rewritten
7062aafff1e16e6ee2ba47cc978b7c1a  term_string_offsets.scdb        <- rewritten
```

Restarted, `health=healthy`, `Existing graph found ... without rebuilding`, the
graph intact, and the checksums identical across the restart. The web container
was never recreated and has been up throughout. Container healthcheck exit 0.

**No test record was written to the live graph.** Verifying the save path does
not require one: that `segments.scdb` was rewritten and the log ends
`Successfully shutdown` is the proof, and record survival across the same chain
was proven on scratch. The live graph was not used as a test fixture.

### Rollback

Two independent parts, either sufficient on its own.

- **Data**: `docker run --rm -v oneiro-ostis_kb-binary:/from -v <abs>:/to
  alpine sh -c "tar xzf /to/oneiro-kb-preSIGINT-20261002T1754Z.tar.gz -C /from"`
  with the machine stopped, then start it.
- **Configuration**: revert `stop_signal` / `stop_grace_period` in
  `docker-compose.yml` and drop the `exec` from `scripts/docker_entrypoint.sh`,
  or simply recreate from the preserved image
  `oneiro-ostis-machine:rollback-20261002` (`8db1f0887f7c`), which is the exact
  image the live container was running before this block.

### The strings2 question, now with two more samples

The unexplained `strings2.scdb` change from Block A is confirmed to be
recurring: `3f0cb5d9…` at the start of the session, `a8569a7f…` at 20:44, and
`ec64501a…` at 20:53, while `segments.scdb` stayed `ba99cf01…` throughout and no
save had run. Something in the running stack rewrites the string dictionary on
its own. Since this block it has stayed at `ec64501a…`, so the writer stopped
around the recreate. Cause unestablished; recorded as an open item, not a
finding.

### Live state

```
oneiro-ostis-machine-1   healthy, image sha256:93542a08 (entrypoint-sync overlay
                         rebuilt from the exec-carrying script)
oneiro-ostis-web-1       untouched, up throughout
```

### Not verified

- Record survival was proven on scratch, not by writing to the live graph. The
  live evidence is that the save path executes and rewrites storage.
- `stop_signal: SIGINT` was verified for `docker compose stop`. A host reboot,
  `docker kill`, or an OOM kill still bypasses it and will still lose the graph.
  Nothing here changes that.
- The full `Dockerfile` build with the `exec` is proven in Block A
  (`oneiro-ostis-machine:verify-1c`, `:sigint-fix`), but live runs the overlay,
  not a full build. Reconciling the two is open.
- Only the SIGINT path is characterised. `docker-compose.isolated.yml` was not
  examined and may carry its own machine service without the fix.
- No conversation, onboarding or installer work was started.

## 2026-10-02 — Block C: template search was never broken; one of our readers was

### The previous two sections are wrong about the cause

The "write persistence settled" section reported that `search_by_template`
"returns no real results on this build", that the C++ agent path works while
the raw template machinery does not, and that half the Python-side readers
silently return empty as a result. **That diagnosis was wrong.** The searches
returned nothing because the probes were malformed. Template search works.

The mistake was mine and it was a specific one. In OSTIS a template triple is
`(source, connector, target)`, and the connector slot must hold a **connector
type**. The probes used `sc_type.VAR_NODE_LINK`, which is `0x43` — the var bit
plus `NODE_LINK`, i.e. a *node* type. Put in the connector slot it matches
nothing:

```
VAR_NODE_LINK              0x43     <- a NODE type
VAR_CONNECTOR             0x4040   <- connector types live in the 0x40xx range
VAR_COMMON_ARC            0xc048
VAR_PERM_POS_ARC          0xc8d0
```

What the probes actually established, restated correctly:

- **`(concrete, VAR_CONNECTOR, concrete)` works.** On a scratch graph whose
  layout had already been read directly, it returned `(196609, 196611, 196610)`
  — exactly the arc the per-address type census had predicted.
- **A pure relation sweep — variable source AND variable target with a concrete
  connector — does not work.** `(VAR, nrel_system_identifier, VAR)` returned
  exactly one result whose endpoints were both `ScAddr(0)`, for every
  combination of variable types tried.
- **A variable source with a concrete target works.** `(VAR_NODE,
  VAR_COMMON_ARC, <corpus node>)` returned both session nodes.
- `get_elements_types` and `get_link_content` work, as they always did.
- `resolve_keynodes` creates what it cannot find, as previously recorded.

So the rule is narrow: **at least one end of the triple must be concrete.** The
C++ agents were never evidence of a working alternative path; they simply anchor
on concrete sources, which is why they worked. `py-sc-client` 0.4.0 is the
current release and is not the problem, though it remains an undeclared and
unpinned dependency of this repository.

### The real defect, and its fix

Exactly one place in the product used the one shape that cannot work:
`oneiro.memory._read_graph`, which swept `(VAR_NODE_LINK, anchor,
VAR_NODE_LINK)`. It is now anchored on the resolved relation as the **source**
instead:

```python
anchor = ScKeynodes[ANCHOR_RELATION]
template.triple(anchor, sc_type.VAR_COMMON_ARC, sc_type.VAR_NODE_LINK)
```

A relation node carries its own identifier through a common arc, so reading
that string back is still the proof the module exists for. Against both the
scratch copy and the live graph:

```
reachable: True | verified: True | arcs: 1 | identifiers: ['nrel_system_identifier']
```

Before this change the same probe reported `verified: False` and the message
"the graph answers the protocol but holds no traversable knowledge base", so
`/api/graph` and `/oneiro/` have been under-reporting a loaded, readable graph
as empty. `bridge.idtf_of` and every other loader in `bridge.py` were checked and
use concrete sources correctly.

`tests/test_memory_probe_template.py` pins the shape: the triple's source must
not be a `sc_type` variable, the relation slot must hold a connector type, and
an unreachable server must still produce `reachable=False` with a reason.

### Writers other than `record_attempt`

`save_strategy` was exercised end to end against a scratch server and survives
a restart. `save_memory_sessions` does not round-trip at all, and the failure
has nothing to do with persistence.

`save_strategy`, before and after a SIGINT save and reload:

```
{"derived_from": null, "descriptor": {"policy": ["left", "right"], "seed": 7},
 "dream_round": null, "name": "probe_strategy_2026_10_02",
 "online_score": 2.5, "replay_score": 1.5}
```

`save_memory_sessions("probe_corpus_2026_10_02", [2 sessions])` reports 2
written. `load_memory_sessions` returns 0 — in-session, before any restart.
Localised to the payload relation:

```
bridge quintuple as written   -> 2 resolved, both session nodes
session node 327723 outgoing  -> 3 arcs
(327723, 327729, 327727)      -> 1 resolved          <- the payload arc, findable
(327723, 327715, VAR_NODE_LINK)-> 0 resolved         <- what the reader searches for
link 327727 content           -> {"answer": "a1", "date_epoch": 1700000000,
                                   "question": "q1", "score": 0.5}
```

The data is in the graph and is reachable by address. The reader searches for
the relation keynode `nrel_memory_session_payload` (`ScAddr(327715)`, idtf
confirmed) as the connector, but the arc that actually joins the session node to
its payload is `ScAddr(327729)`, type `0xc028` — a different element. So this
is a mismatch between how `_add_json_relation` writes the attribute and how
`_json_relation` looks for it, not a storage or search failure. It is left
unfixed: it is bridge write-path behaviour with test implications and is a
decision for stage 2, not something to change inside a characterisation block.

### Not verified

- Whether a concrete **connector** with two variable ends ever works. Every such
  probe returned one unresolved tuple, but no case was found where such an arc
  was independently proven to exist, so the rule above is "at least one end must
  be concrete", not a proven impossibility.
- Only `save_strategy` and `save_memory_sessions` were exercised. `save_harness`,
  `save_harness_round`, `save_memory_bench_result`, the life/organization
  loaders and the dream-cycle writers are untested against a restarted server.
- The `_add_json_relation` / `_json_relation` mismatch is localised but not
  diagnosed.
- The memory fix was verified against the live graph read-only. No live write
  was performed in this block.
- The rewrite is **not deployed**. `oneiro-ostis-web-1` runs the legacy
  `ostis/sc-web:0.9.0` image and has no `oneiro` module at all, so the memory
  fix was verified by calling `probe()` against the live OSTIS server, not
  through the live HTTP surface. `/api/graph` and `/oneiro/` still serve old code.

## 2026-10-02 — Block C part 2: the session loader was never broken either

Stage 2's remaining blocker was reported as "load_memory_sessions cannot read
back what save_memory_sessions writes", localised to a write/read
representation mismatch. **That was also wrong**, and the previous localisation
is what made it look like one. Every element involved turned out to be
reachable. This is the second correction to a claim made in this document, and
both came from trusting a probe over the contract.

### What the carrier arc actually is

`_add_json_relation` and the inlined equivalent in `save_memory_sessions` build a
two-arc structure. For each session node:

```
node      --common_arc-->   payload_link        (A = ScAddr(327729))
relation  --perm_pos_arc-->  A                   (B = ScAddr(327730))
```

The payload is the link `ScAddr(327727)`. The reader must therefore anchor on
the **common arc A** and join B, which is exactly what the quintuple in
`_relation_value_link_addr` does:

```
triple1 (node, VAR_COMMON_ARC, VAR_NODE_LINK)  -> (327723, 327729, 327727)
triple2 (rel,  VAR_PERM_POS_ARC, 327729)       -> (327715, 327730, 327729)
_relation_value_link_addr(node, ...)           -> ScAddr(327727)
```

Both halves resolve and the helper returns the payload link on the first try.
There is no representation mismatch. The earlier probe that appeared to show
one searched `(node, relation_keynode, VAR_NODE_LINK)` — the relation keynode in
the connector slot, which is the same malformed shape that produced the
phantom search defect two sections ago.

### What actually dropped the rows

```
_json_relation(ScAddr(327723), NREL_MEMORY_SESSION_PAYLOAD)
    -> {'answer': 'a1', 'date_epoch': 1700000000, 'question': 'q1', 'score': 0.5}
load_memory_sessions('probe_corpus_2026_10_02') -> []
```

The payload was read perfectly. The loader then discarded it:

```python
payload = self._json_relation(node, NREL_MEMORY_SESSION_PAYLOAD)
if payload and payload.get("session_id"):
    rows.setdefault(str(payload["session_id"]), payload)
```

`save_memory_sessions` stores the caller's dict **verbatim** and invents
nothing, so `session_id` is a caller guarantee. The real producer,
`bench.memory.dataset.session_to_dict`, emits `session_id`, `date`, `date_epoch`
and `turns`, and the real consumer `bench.memory.retrieval.rank_graph` reads
`date_epoch` back. The loader's filter is correct for the contract. The probe
had invented `{question, answer, date_epoch, score}`, which the contract does not
produce, and every row was correctly dropped as unidentifiable.

### Proof across a restart

Re-run with contract-shaped payloads from `session_to_dict`, on the scratch copy
at `.runtime/probe-addr/` on port 8095:

```
write   save_memory_sessions -> 2 sessions
        in-session load_memory_sessions -> 2: ['s-0001', 's-0002']

SIGINT  exit 0, segments.scdb 40eeb6ca... -> ffb286a1...

read    AFTER RESTART load_memory_sessions -> 2
        {"date": "2024-01-05", "date_epoch": 1704412800, "session_id": "s-0001",
         "turns": [{"content": "what is ostis?", "role": "user"},
                   {"content": "a knowledge base", "role": "assistant"}]}
        {"date": "2024-02-11", "date_epoch": 1707225600, "session_id": "s-0002", ...}
        AFTER RESTART load_strategies -> the strategy written before the reload,
        with descriptor, replay_score and online_score intact
```

Both writers now have a measured round-trip through a real save and reload.
The strategy that had been written before the stop still reads back, so the
session work did not disturb it.

### All-variable template audit

The measured rule is that at least one end of a triple must be concrete; a pure
relation sweep returns one result with both endpoints at `ScAddr(0)`. Every
`.triple(`, `.quintuple(` and `.triple_with_relation(` call in the product tree
was scanned for a template whose source and target are both `sc_type` values:

```
python/bridge.py                            0
python/oneiro/*.py                          0
whole product tree, worktrees/.runtime
and vendored trees excluded                 0
```

`memory._read_graph` was the only one and is fixed. Nothing else to change.

### Regression tests

`tests/test_memory_session_contract.py` pins the producer/loader agreement: the
real producer must emit the key the loader filters on, must emit the keys
`rank_graph` reads back, the writer must still store the caller's dict
verbatim, and the loader's identity key must stay the one the test names. A
caller or probe that invents its own payload shape now fails there instead of
returning a silent empty list.

There is deliberately **no** test written to fail against
`load_memory_sessions`. Its shape is correct; a test that failed against it
would encode the mistake and then break the suite the moment someone fixed it
back.

### Not verified

- `save_harness`, `save_harness_round`, `save_memory_bench_result`, the life and
  organization loaders, and the dream-cycle writers are still untested across a
  restart. `record_attempt` and `save_strategy` and `save_memory_sessions` now
  have measured round-trips; the rest remain unproven, which is different from
  broken.
- `load_strategies` does not deduplicate by name: writing the same strategy
  twice yields two rows. Whether that is intended is not decided here.
- The contract test reads the bridge and producer sources to pin the agreement.
  That is deliberate, and it will need attention if either is restructured.
- Live-verified: none in this block. It ran entirely on the scratch copy at port
  8095. The live graph was not read, written or restarted, and `docker-compose.yml`
  is unchanged.

## Next independent work

The four-block plan is approved. Blocks A, B and C are done, including the two
reported blockers that turned out not to be defects. Block D and the stages
after 2 are next.

- **Block D and the stages after 2** — agent runtime and recoverable scheduling,
  model access, tools and the Linux VM, the scientific kernel, unified web and
  Telegram, then packaging and migration.

Carried open from Blocks A and B, none of it worked on:

- `oneiro-base:latest` is an undeclared local base image, so a clean checkout
  cannot build `Dockerfile` today. This is a stage 1 exit condition.
- Live runs the entrypoint-sync overlay rather than a full build. Both carry
  the same entrypoint now, but the two paths should be reconciled.
- `stop_signal: SIGINT` covers `docker compose stop` only. A host reboot, a
  `docker kill` or an OOM kill still bypasses it and still loses the graph.
- `save_harness`, `save_harness_round`, `save_memory_bench_result`, the life and
  organization loaders and the dream-cycle writers are still untested across a
  restart. Unproven, which is not the same as broken.
- Something in the running stack rewrites the live `strings2.scdb` on its own
  while `segments.scdb` stays put. Cause unestablished.
- `docker-compose.isolated.yml` may carry its own machine service without the
  SIGINT fix; it was not examined.

Still open from the earlier review: `/oneiro` and `/settings/` answer 307 without
their trailing slash; the settings POST handler imports `json`/`asyncio` inside
the function while its siblings are module-level; `_writable` still touches the
filesystem on every settings page hit; and `tests/installed_smoke.py` has no
`test_` prefix, so a normal `pytest` run does not execute it.
