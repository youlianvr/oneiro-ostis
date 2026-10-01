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

## Next independent work

Implement package/config/runtime shell with native ASGI lifecycle, shared settings
and actionable prerequisite report; verify wheel outside workspace and cleanup.
Then migrate memory/role runtime/model adapters without abandoning graph restore,
Linux VM, full onboarding/installer/shortcut and live-production acceptance.
