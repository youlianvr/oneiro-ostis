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
