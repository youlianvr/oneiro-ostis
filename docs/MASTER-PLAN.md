# Oneiro — full-project rewrite

Authority: full local-delivery Mission approved in this conversation on
2026-10-07, incorporating the decisions of 2026-10-02/06 and the final interview.
This plan replaces the limited product-plane rewrite and missing-cloud-PR wait.
The complete approved execution sequence is recorded below (units A-I).
Approval is not implementation evidence.
Progress and baseline evidence: [REWRITE-BASELINE.md](REWRITE-BASELINE.md).
Binding owner decisions: [GOAL-NATIVE-ONEIRO.md](GOAL-NATIVE-ONEIRO.md).

## Objective and authority

Rebuild Oneiro as one coherent standalone project: a persistent assistant with
OSTIS memory, three configurable roles, proactive work, Linux computer use, and
measured self-improvement. Every own-code layer is in scope, including scientific
implementation, installation and documentation.

The missing cloud PR is not a prerequisite. CLOUD-SESSION-PLAN.md remains a
historical source of requirements, not proof that missing code exists or works.

Approval authorizes all stages without further architecture/requirement
questions, project-local dependency setup and verification, working configured
OmniRoute models and small local commits of owned implementation. It does not
permit unrelated changes, permanent destruction or ungranted administrator work.

Latest Mission requires Windows 11 native-window/tray delivery: onboarding,
installation, **one desktop shortcut**, and **http://127.0.0.1:9899** for chat,
relative settings/setup routes and graph panel **/oneiro/**, without CORS or
manual port discovery. Closing the window leaves the manually started instance
in the tray; explicit exit safely stops owned processes. No OS autostart.

**Owner override, 2026-10-07: local delivery only.** Earlier eventual-publication
authority is superseded: no push, deploy, PR or sending materials in this Mission.
Preserve Russian `main` / English `v2` history and unrelated workspace changes.
Small local commits are authorized for own verified units. A report distinguishes
actual installed/live checks from plans, historical evidence and remaining gaps.

## Confirmed owner decisions

- Preserve scientific meaning, historical measurements and owner artifacts;
  review/rewrite implementations where needed, including existing native code.
  **Data override (2026-10-06, approved 2026-10-07):** start on a clean volume,
  not migrated old graph data. First make one verified old-volume archive outside
  Git; retain the old volume stopped/intact and never use it as the new seed.
- Deliver a living proactive assistant with integrated self-improvement.
- Manager/researcher/executor have independent configurable personalities and
  shared readable memory. No mandatory three-agent ceremony.
- Manager converses/coordinates; researcher researches/records findings;
  executor implements/verifies. Prompts cannot relax permanent role boundaries.
- OSTIS is mandatory durable memory; no silent production SQLite/JSON fallback.
- OmniRoute first, with provider adapters for alternatives. Working models exposed
  by the router may be used for development and live acceptance.
- Configured AI providers may receive relevant text, selected attachments and VM
  screenshots without per-request approval. Credential values are excluded from
  ordinary model context/logs; other account permissions remain scoped.
- Computer use begins in a separate Linux desktop VM, not the owner's desktop.
- Real accounts may be connected with scoped permissions. VM isolation alone
  does not enforce account-side restrictions.
- Automatic self-improvement/application updates after verification are wanted.
  Permissions, secrets and update controller are outside agent-modifiable scope.
- No OS autostart. A manually started instance may continue until stopped.
- English UI/code/new docs; Russian owner conversation. Russian main is retained.
- No further clarification questions after approval: record infrastructure/access
  blockers and continue independent work, without changing agreed scope.
- **Order (2026-10-06):** follow the stage ladder in order - close stage 2, then
  3 and 4. Scientific rigour waits until live trials are possible (stage 4).
- **First usable version (2026-10-06):** all four are required - chat and the
  graph panel on one origin 9899, proactive initiative and tasks, computer use
  in the Linux VM, and Telegram as a second channel. Only deep metric rigour
  may land after it.
- **Graph durability (2026-10-06/07):** agreed snapshots/checkpoints must prove
  a hard-kill graph-memory loss window <=300 seconds on disposable new storage.
  Snapshot duration counts; a timer or in-memory read-back is not durability.
  Persist safe action intentions before effects; unknown outcomes are inspected,
  not blindly retried after recovery.
- **Stochastic comparisons (2026-10-06):** at least 3 paired runs, otherwise
  abstain; effort goes into the key result rather than methodological polish.
- **Artifact (2026-10-06/07):** live demo plus a product the owner keeps using;
  paper/slides/talk are written at the end, using raw evidence recorded meanwhile.
  Scientific result is numerical comparison with context-only/flat-store baselines
  plus a reusable debuggable artifact; no historical numbers silently replaced.
- **Pace/resources (2026-10-06/07):** coherent units take hours-days, not planned
  months; redesign a stalled unit rather than extending it indefinitely. The
  exclusive overnight window authorizes background builds/downloads/measurements
  with logs/stop paths, not administrator work, unrelated process termination or
  a guaranteed one-night completion. No hard deadline was given.
- **Channels (2026-10-06/07):** local native app and Telegram equally required.
  One shared conversation; important notifications delivered to both, without
  duplicate tasks/events/decisions. New owner-allowlisted bot; userbot read-only.
  No network exposure of local UI; mobile access is through Telegram.
- **Initiative (2026-10-07):** active conversation and independent reversible work
  from needs, unfinished tasks and interests; finite cycles, cooldowns, dedupe,
  configurable quiet hours/mute, not repetitive timed status messages.
- **Work/consent (2026-10-06/07):** autonomous edits only in the Linux VM and a
  separate Oneiro folder. Other projects are not connected automatically. Money,
  publication, host-desktop access and expanded grants need an owner decision;
  permanent destruction stays forbidden, even on request.
- **Failures (2026-10-06):** resume the last safe step after restart; inspect or
  ask about unsafe/unknown outcomes. Router/model failure is explicit; complete
  model-independent work and retry eligible model steps later, finitely.
- **v1 media/platform (2026-10-07):** Windows 11; text, images/screenshots and
  PDF. Voice/audio/video analysis, mobile app and own-model training are deferred
  beyond v1. Recording the product demo is still a required delivery artifact.
- **Graph UI (2026-10-07):** linked real-memory explorer and literally growing
  strategy tree; stable record IDs/current graph addresses, provenance and scores.
  Local pinned anime.js/licence; no CDN, React or Tailwind. Static/reduced-motion
  view remains usable. Never invent nodes/edges or hide unavailable/truncated reads.
- **Demo (2026-10-07):** request -> plan -> GUI actions in Linux LibreOffice
  Writer -> formatted ODT/PDF -> reopen/independent checks. Include headings,
  table and image; script-created files cannot replace claimed GUI actions.
- **Scientific exit (2026-10-07):** real measured improvement on at least one
  preselected scenario is mandatory, but need not be the GUI task. Freeze control
  criteria before search; label deterministic-world vs coding/GUI-agent evidence.
  No proven gain means the scientific part remains unfinished, not a fake success.
- **Presentation (2026-10-07):** Russian and English editable slides, PDFs and
  talk scripts with matching numbers/limitations; real demo recording and live
  demonstration. Do not fabricate performance or citations from reference posts.
- **Recovery/update:** graph memory/strategies, pending tasks/intentions,
  settings/connections and Telegram queue/delivery are covered. Verified automatic
  updates have a journal and rollback that preserves newer owner data. Candidate
  writes cannot alter grants, secrets, update supervisor or control tests.

## Rewrite scope and preservation

Assign every own-code module to rewrite, merge, retain with evidence or archive:

1. Native/legacy coordination, agent loops, tasks, decisions and initiative.
2. Model access, configuration, tools and MCP.
3. OSTIS bridge, ontology, C++ agents, persistence and retrieval.
4. Worlds, strategies, episodes, replay/dream, harness, metrics and benchmarks.
5. Web, Telegram, media, research/search and computer use.
6. Installer, launcher, Docker/build, diagnostics, lifecycle and updating.
7. Tests, current docs and scientific-artifact build tools.

Do not gratuitously rewrite dependencies: pin upstream components and use thin
reviewed adapters. Existing native code is not exempt from review.

Preserve owner files, unfinished work, experimental records, published results
and school-paper artifacts. The old-graph preservation requirement is explicitly
superseded by the clean-start decision above: archive it once, retain its stopped
volume, and do not migrate/restore it into the product or compare it with the new
graph. Archive verification checks files, not an old-server restart.
Never silently replace historical numbers. Keep old code paths until replacements
pass relevant scenarios, then archive; no active imports, launch commands or
installation dependencies may use legacy.

Use workspace trash operations during workspace work; standalone product needs
its own reversible archive/trash and restoration tests. Reset/rebuild must create
separate recoverable storage, not clear the active graph.

## Architecture

A modular Python application with one authoritative state coordinator. Separate
workers/graph-access processes execute work, not independent control planes.

```text
Web / Telegram / approved MCP adapters
                   |
Conversation, task, decision and event contracts
                   |
Coordinator + scheduler + shared role runtime
       Manager / Researcher / Executor
                   |
Models / OSTIS memory / tools / Linux VM
                   |
Observed results and evidence

Independent update supervisor:
candidate -> checks -> trial -> promotion or rollback
```

### Stack decisions and alternatives

- Installable `oneiro` package, explicit imports/dependencies and locked project
  environment, rather than path injection and workspace-specific layout.
- Async Python coordination, bounded workers, short state-critical sections;
  blocking graph/desktop calls cannot block HTTP intake.
- FastAPI/Uvicorn for HTTP/streaming/uploads/lifecycle rather than expanding the
  custom stdlib HTTP server. These are planned project dependencies.
- Existing HTML/CSS/JS reorganized into modules; no second frontend framework.
  Thin Windows native WebView window/tray over the same loopback backend. Evaluate
  a WebView2-based Python wrapper with real packaging/CSP/lifecycle checks before
  pinning it; no privileged arbitrary JS-to-host bridge. Pinned local anime.js is
  progressive animation only, with licence, static view and reduced-motion mode.
- Existing sc-client/sc-machine ecosystem behind reviewed memory contracts;
  compatible releases pinned after actual round-trip verification.
- One OpenAI-compatible model adapter for OmniRoute/research/vision/experiments.
- MIT Cua Driver low-level interface inside Linux VM, not its agent framework.
  Verify exact Linux support and pin a working release. No implicit Spaces,
  cloud hosting or separately licensed optional perception dependency.
- Existing VM management available on the host. Windows: supported Hyper-V if
  available, otherwise evaluated QEMU or configured remote Linux VM. Containers
  are not advertised as satisfying VM isolation. Ungranted privilege is a blocker.
- Scientific algorithms independent of channels/UI, sharing model/memory contracts.
- No Redis, second durable product DB, distributed microservices, custom
  hypervisor or general plugin/agent framework without an unmet requirement.

### Core contracts

Versioned typed conversation/task/run/action/decision/note/experience/experiment/
release records. Provenance distinguishes owner instructions, model claims,
observations and verified tool outcomes.

Explicit queued/running/waiting/completed/failed/cancelled/interrupted/uncertain
states where applicable. Unknown effect outcome after a crash is not permission
to repeat it. Channels share the same task/decision truth.

OSTIS is not presumed ACID or whole-storage crash atomic. Coordinated writer,
stable operation IDs, completion markers, read-back and incomplete-batch recovery
must be verified on the actual stack. New-graph ontology upgrades run on a
consistent copied graph before promotion, not on the old archived volume.
A recovery journal, if technically required, is an explicit protocol, never an
alternative semantic memory store. Durable intent is required before effects;
in-memory read-back/completion markers alone cannot prove crash durability.

## Implementation checklist

Only checked items have current evidence. Historical native/cloud green counts
are not completion of these phases.

- [x] Recover approved requirements; 2026-10-07 full Mission is recorded here.
- [x] Prerequisite A archive/inventory/docs validation: terminal restored,
      stopped old volume archived once with full SHA-256/extraction/read-again
      verification; see the 2026-10-07 baseline continuation. Local commit is
      recorded in Git history; archive artifacts remain ignored outside Git.
- [x] Inspect actual repository, dependency/service presence and data locations.
- [ ] Complete module disposition/equivalence evidence as modules are touched.
- [x] Verify consistent graph snapshot and isolated restore before migration
      (2026-10-02: snapshot taken from a stopped server, restored to scratch, read back
      through the bridge; note the graph was cleared before that snapshot existed).
- [x] 1a: installed wheel/shared settings/process ownership/ASGI foundation; see baseline checks.
- [x] 1b: typed versioned records, event envelopes, and the memory read seam.
- [x] 1c: reproducible build context. 6.02 GB -> 23.50 MB via a new
      .dockerignore; full build runs and the image boots and round-trips a
      record. Still open: oneiro-base:latest is an undeclared local base image.
- [ ] 2: memory/retrieval/migration contracts and live OSTIS validation.
      Persistence blocker CLEARED 2026-10-02 and applied to live. The cause was
      two-part, not one: sc-memory ignores SIGTERM, AND scripts/docker_entrypoint.sh
      ran it under bash, which does not forward signals, so SIGINT was swallowed
      too. Fix is the pair - exec in the entrypoint plus stop_signal: SIGINT with
      a 90s grace - verified through docker -> tini -> sc-machine on scratch
      (records survive) and on live (stop exits 0 in 2s, save runs, graph intact).
      Snapshot and rollback image preserved.
      Read path CORRECTED 2026-10-02: template search is not broken. The earlier
      claim came from probes that placed a node type in the connector slot. The
      rule measured is that at least one end of a triple must be concrete; only a
      pure relation sweep fails. memory._read_graph used exactly that shape and
      is fixed - /api/graph and /oneiro/ now verify the graph and return a real
      identifier instead of reporting it unreadable.
      Both read paths CORRECTED 2026-10-02. save_memory_sessions and
      load_memory_sessions agree and round-trip through a real save and reload;
      the earlier "representation mismatch" was a probe writing payloads that
      omit session_id, which the loader requires and the real producer
      bench.memory.dataset.session_to_dict supplies. Tests pin that agreement.
      An audit of every .triple/.quintuple/.triple_with_relation call in the
      product tree found no remaining all-variable template, which is the one
      shape this sc-memory build does not answer.
      Every writer now has a measured write -> read -> SIGINT -> reload -> read
      round trip 2026-10-02: save_harness, save_harness_round,
      save_memory_bench_result, the life and organization loaders, the native
      event writer, save_memory_sessions, save_strategy in both its plain and
      its dream-cycle shape, and record_attempt. None of them was broken; no
      product code changed in that block. The round trips ran on a byte-identical
      copy of the live graph on a spare port, never on live.
      The last untested writer was found by following python/dream.py's own
      save_strategy call: it passes dream_round and derived_from, and no earlier
      probe had ever passed either, so the numeric nrel_dream_round link and the
      nrel_derived_from parent link were genuinely unexercised until now.
      Contract tests are the default for this seam: a writer added to bridge.py
      without a contract test against its real producer fails the suite, and the
      producers are called rather than re-implemented.
      Query and migration contracts DONE 2026-10-05: entity/cursor/range/
      page/recent/latest reads and the additive idempotent ontology
      migration are proven against a byte-copy of the live graph on a spare
      port (a page of 50 reads in 0.64-0.76s where the full class cost
      11.2s; the migration run twice, the second run creates nothing;
      missing classes are reported, never faked; a stopped server, a missing
      class and a malformed record each report instead of reading as empty).
      Tests: tests/test_graph_query_contract.py,
      tests/test_migrate_contract.py. This proves the tested query semantics,
      not fully bounded storage work: 2026-10-07 source review found that
      BridgeBackend still materializes all class addresses and latest() does
      not use scan_limit. Production consumer integration and 1k/10k/100k
      measurements remain open; do not claim the retrieval stage is complete.
      Retry/provenance correction recorded 2026-10-06 at b68f52fe6 is retained;
      its prior test results are historical, not a rerun on today's checkout.
      Still open in this stage: fault validation (connections, concurrency,
      partial writes, reconnect), the content/time/entity/relation retrieval
      benchmark against the existing arms, and live validation through the
      web surface - the web container still runs the legacy
      ostis/sc-web:0.9.0 with no oneiro module.
      See REWRITE-BASELINE.md.
- [ ] 3: concurrent, recoverable runtime/tasks/initiative.
- [ ] 4: shared model/research/media adapters and live capabilities.
- [ ] 5: isolated executor/tools and Linux desktop integration.
- [ ] 6: scientific equivalence and measured automatic updates/rollback.
- [ ] 7: unified production web/Telegram/chat/settings/graph.
- [ ] 8: installer/onboarding/one shortcut/migration/legacy retirement.
- [ ] Full acceptance, installed local delivery and bilingual demo/presentation.
      External publication is excluded, not deferred work inside this Mission.

## Stages and exit conditions

### 0 — Baseline, inventory and decision record

Inspect Git status/branch, foreign changes, ownership, services and data. Do not
stop unrelated processes or overwrite foreign work. Update this plan/goal and
supersede the PR wait. Inventory imports, entrypoints, settings, graph schemas,
datasets and artifacts. Run old tests, distinguishing failures/prerequisites.
Establish a consistent snapshot and isolated restore; a hot file copy is not
assumed consistent.

Exit: written decisions/disposition map/reproducible baseline/identified data;
verified old-volume file archive, retained inactive original, independent new data
root/volume. New-data recovery is proven in Stage 2; old-graph migration is out.

### 1 — Package, configuration and reproducible build

Installable package, explicit supported Python/dependencies/locked environment;
consolidated validated config/env; typed records and event envelopes; one
installer/launcher/doctor/stop route; separate dev/graph/desktop/live groups.
Offline tests cannot depend accidentally on workspace catalogs.

Exit: clean checkout installs outside workspace; imports without live keys/graph;
missing prerequisites explicit. Foundation shell is not completed agent runtime.

### 2 — OSTIS memory and retrieval

Split/rewrite oversized bridge, remove legacy product config dependency. Stable
IDs/schema/provenance/relations. Entity/cursor/range/page queries replace full-log
reads. Bounded current-state projections and rebuildable derived search indexes
are not durable memory substitutes. Content/time/entity/relation retrieval cites
records; compare representative questions and existing benchmark arms.

Validate connections, concurrency, partial writes, reconnect and persistence under
faults. Additive/idempotent ontology migration on restored copy; no startup clear.

Exit: a clean graph restores equivalently (stable IDs/content/types/relations);
new records survive restart; retry yields one logical event; partial operations
are detectable; ontology upgrade is additive and idempotent. Prove <=300-second
hard-kill graph-memory loss, safe external-effect recovery and truly bounded query
work with current consumers and representative 1k/10k/100k measurements.

### 3 — Agent runtime and recoverable scheduling

Separate intake/scheduler/model/tools; remove locks across network calls. Bounded
lanes reserve conversation/control capacity, preserve order and prevent duplicate
claims. Deadlines/cancellation/quotas/checkpoints/dependencies/transitions. Persist
intent before effect, observed result afterward; inspect unknown outcomes rather
than retry non-idempotent work. Persist free-text answers and decisions; waiting
pauses dependent work only.

Initiative from unfinished tasks, owner needs and interests, with deduplication,
cooldowns, quiet hours and independent research. SOUL is not capability authority.

Exit: long tasks don't block chat/control; waits don't freeze system; restart
retains work/decisions without blind repeats; interests aren't the only trigger.

### 4 — Model access, research and media

One OmniRoute-compatible adapter replaces duplicate clients. Discover model IDs
and probe tools/vision rather than infer from names/listing. Bounded timeouts,
retries/cancellation/rate-limit handling/validation/capability-compatible fallback.
Account for every call including vision/generation/judging; bound calls/tokens/time,
optional spend only where price is known. Record requested/returned/disclosed
upstream; undisclosed is unknown.

Source-backed search/extraction through actual usable integrations; no presumed
search key. Web/Telegram attachments: text/images/screenshots/PDF, including
attachment-only intake; bound bytes/pages/context and label uninspected or
unsupported media. Voice/audio/video analysis is outside v1.

Exit: live chat/tools/vision work; supported media yields grounded results;
unsupported functions explicit; no runaway retries or uncounted calls.

### 5 — Tools and Linux computer use

Reviewed schemas/roles/scopes/execution IDs/results; approved local and model
requests don't repeatedly ask. Practical isolated dev execution supports edits,
package setup and tests; separate network setup from offline checks appropriately.

VM+Cua capture/click/type/scroll/keys/waits/result checks. Validate version/API/
license/desktop support. Owner-visible observation, immediate stop/human takeover;
preserve artifacts before cleanup. No host desktop/unrestricted host shell.
Prefer scoped APIs for account effects; where GUI cannot enforce scope, keep
sensitive operations observed/manual/blocked, never claim screenshot classifier
is a reliable permission boundary. Reversible deletion/reset/restore.

Exit: real Linux LibreOffice Writer GUI task creates formatted ODT and PDF,
both reopened and independently verified; no script-generation substitute.
Host desktop untouched; stop/takeover/restoration functional, account actions
within available grants and work files confined to VM/Oneiro folder.

### 6 — Scientific kernel and automatic improvement

Review/rewrite worlds/strategies/episodes/replay/dream/C++/harness/metrics/bench;
retain healthy code only with invariant/equivalence evidence. Fixed-record
comparisons preserve deterministic semantics and separate historical numbers.
Check consistency before selection; reject conflicting transitions, validate
state signatures/successors, leave unknown transitions uncovered.

Exact world replay differs from stochastic LLM/GUI evaluation. Trajectory-changing
candidates require real trials; abstention is not a capability verdict. Freeze
criteria/control tasks before search; paired repeats start at >=3 per stochastic
task, increase or abstain if noise prevents a supported conclusion.

Observe -> candidate -> isolated checks -> acceptance trial -> promote/reject.
Protect manifests/gates/control datasets/supervisor from candidate writes using
actual authority separation, not just process names. Versioned releases and schema
compatibility; rollback must not erase newer owner data. Faulty rollback trial and
one real candidate through entire cycle; measured improvement is a separate claim.

Exit: known replay correct, uncertainty prevents unsupported promotion,
scientific comparisons reproducible, at least one preselected scenario has a
real measured gain. Update/reject/rollback work without weakening their gate or
erasing newer owner data. GUI demonstration need not be the gain scenario.

### 7 — Unified web and Telegram

API/UI over typed records: streaming chat/media/conversations/tasks/evidence/
memory/roles/providers/live status. Separate liveness/readiness/integration checks.
Telegram same core, attachment-only intake, stable question/reply mapping,
restart-safe updates and outbox recovery. Unknown send outcomes remain unknown:
no impossible exactly-once promise. Cross-channel cancel/decide; stale callbacks
can't release new actions. Desktop observation/stop/takeover; small-screen checks.

Exit: one shared conversation/state in both channels; important notifications
reach both without duplicate logical work; chat/delegation/answers survive
restart. New private owner-allowlisted bot, attachments not dropped, no parallel
channel agent logic. Native window/tray, one origin/routes, linked real-memory
explorer/tree and truthful degraded/static views are verified.

### 8 — Packaging, migration and legacy retirement

Own install without foreign control planes or workspace-private services. Clean
Docker build without undeclared local base image, pinned artifacts/verification.
Manual start/stop/update/rollback/ports/process ownership; inspect listeners first,
clean only owned processes. First install and upgrade preserve graph/settings/
artifacts/experiments/pending work. Native onboarding reads real state and helps
configure missing prerequisites. One desktop shortcut launches/reuses own instance.

Retire old console/dashboard/plugins/launchers/loops after replacement checks;
archive. Update README/runbooks; mark historical plans historical, preserve
published evidence and versions. No active legacy imports/launch/install deps.

Exit: clean install outside workspace and new-data upgrades/recovery pass;
old planes unnecessary, data preserved. Chat/settings/graph share loopback 9899;
one native shortcut, tray/reopen/explicit-exit lifecycle. Local installer and
bilingual delivery files are verified; no publication.

## Acceptance matrix and verification

Check a row only when the named evidence exists; archive preservation is a
prerequisite verified independently of the future delivered product revision.

- [ ] 1. Windows 11 clean install/start outside workspace with isolated settings.
- [ ] 2. Casual streaming conversation without compulsory task/delegation.
- [ ] 3. Source-backed research, retrievable notes and inspectable provenance.
- [ ] 4. Executor changes/tests/results inside VM/Oneiro folder only.
- [ ] 5. Active initiative from needs, unfinished work and interests; dedupe,
      mute/cooldown/quiet-hours controls and finite cycles.
- [ ] 6. Live model text/tools/vision plus bounded failures; accounted calls/tokens.
- [ ] 7. Text/image/PDF and attachment-only intake in both channels; unsupported
      audio/video explicitly reported, no silent drop.
- [ ] 8. Real Writer GUI task: headings/table/image, ODT/PDF, reopen/content checks,
      owner stop/takeover and untouched host desktop.
- [ ] 9. Fault/restart during model/writes/effects/intake/delivery/update; resume
      safe steps, inspect unknown effects, reject stale approvals.
- [x] 10. Old-graph archive outside Git: pre-rewrite-20261006T211110Z.tar.gz;
      SHA-256, safe extraction, full file set/content and source-state checks pass.
      Original remains stopped/intact; do not attach it to subsequent trials.
- [ ] 11. Separate clean graph, correctly typed/additive/idempotent upgrades,
      equivalent new-data restore and measured hard-kill memory loss <=300s.
- [ ] 12. Bounded live queries with cursor/scanned/skipped/truncated; no full-class
      materialization on request paths; correctness/latency/RAM at 1k/10k/100k.
- [ ] 13. Exact deterministic replay with zero world effects, coverage/conflict
      checks; numeric memory comparison against context-only and flat-store arms.
- [ ] 14. At least one real measured dream gain on a preselected scenario;
      frozen controls, >=3 paired stochastic repeats or abstention. Clearly
      distinguish deterministic-world from coding/GUI-agent evidence.
- [ ] 15. Protected checks/supervisor, actual candidate promotion/rejection and
      rollback after newer owner data; neither gate weakening nor data erasure.
- [ ] 16. New private Telegram bot and native UI share conversation/tasks/decisions;
      important notifications reach both; offset/outbox restart/uncertain-send
      checks; userbot stays read-only, no exactly-once promise.
- [ ] 17. Onboarding/settings/chat/graph at localhost 9899, one native shortcut,
      reuse/reopen/tray/explicit-exit, no OS/container autostart or LAN exposure.
- [ ] 18. Linked live memory explorer/growing strategy tree with real IDs/edges/
      provenance/scores, errors/truncation/cycles/orphans; local animation licence,
      static/reduced-motion view and safe CSP.
- [ ] 19. No active legacy/foreign control-plane/workspace-private dependency;
      pinned verified build/install assets, ownership-safe lifecycle/cleanup.
- [ ] 20. Installed reusable product, live demo, genuine demo recording, bilingual
      editable slides/PDFs/talks, traceable figures, acceptance report and hashes.
- [ ] 21. Local-only delivery, own-change commits, preserved historical branches/
      owner artifacts; no push/deploy/PR or external sending.

Exact output names and verification paths are in approved units A-I below.
Existing evidence does not check a full acceptance row by itself.

Every nontrivial unit: Python typecheck, relevant tests and scenario checks. Final
matrix: Python/C++/real OSTIS/browser/desktop/live model. Run docs-route gate.
Historical 163-test count is not a goal; prior eight ignores become explicit test
categories/prerequisites, not proof of full acceptance.

Memory benchmarks: 1k/10k/100k events, no whole-history page/query materialization;
control requests cannot wait for model calls. Record hardware/latency/memory and
freeze supported thresholds from baseline before optimization.

## Autonomous execution and blockers

No new architecture/continuation questions after approval. Choose reversible
implementation details and record alternatives. Use working router models for
bounded tests. Missing Docker/VM/toolchain/credentials/admin/login/2FA/access or
busy ownership: block only affected operation and continue independent work.
Do not rewrite live router config to manufacture availability, use mocks as live
acceptance, or widen permissions.

Preserve foreign changes; commit only owned hunks. This Mission is local-only:
no push, deploy, PR or sending materials. Do not switch historical branches or
stage the workspace to manufacture a project checkpoint.
Each stage persists current work/checks/blockers/next step in owning docs and task
memory. Report paths, committed vs pending, evidence, gaps and decision reasons.
Only required live evidence completes the task; partial implementation is partial.

## Full approved execution sequence — 2026-10-07

This is the on-disk recovery of the complete plan approved in this conversation,
not a new scope proposal. Units A-I preserve the dependency order: prerequisite,
Stage 2 plus necessary Stage 1 repairs, then 3 -> 4 -> 5 -> 7 -> 8 -> 6 -> final
acceptance. Implement healthy retained work, not ceremonial reruns of old units.
Prerequisite A's old-volume archive is verified; proceed to B after its local
checkpoint. B-I remain implementation work, not completed.

### A — Decisions, source inventory and old-volume archive

Reconcile this plan, GOAL-NATIVE-ONEIRO and REWRITE-BASELINE with every confirmed
interview decision; explicitly record supersession of old-data migration,
publication, media and native delivery clauses. Preserve historical evidence.
Inspect current branch/status, tracked/ignored/untracked data, current processes,
listeners and actual overlaps; stale parity `alive: yes` is not a live lock.

First establish the host's ordinary terminal. If its configured Bash cannot
spawn, report the exact infrastructure blocker; do not use browser automation,
elevation, installed-client modifications or an unrelated remote/container shell
to bypass it. Source reads/document edits can continue, but no fabricated Git,
Docker, checksum, validator or commit evidence.

Archive target, relative to project root:
`.runtime/graph-snapshots/pre-rewrite-<UTC>.tar.gz`, with SHA-256 manifest and
verification report beside it. `.runtime/` must be Git-ignored and the archive
must not be staged. Create one archive only after confirming the correct old
volume and that every writer is stopped; never start the old graph to validate
it. Source file inventory must cover the entire volume, not just five known
files; compare relative paths, types, sizes and SHA-256 before and after archive.
Extract this exact archive safely to a separate new verification directory,
reject unsafe paths/links, and compare completeness/content to the source.
Check archive SHA-256 independently. Any symlinks/metadata need an explicit
preservation/comparison rule, not silent omission. Keep source stopped/intact.
Do not substitute October 2 snapshots, assume they match, use a hot copy,
`down -v`, erase the volume, or attach it to the new product as seed.

Exit: checked archive plus inactive original, documented current inventory,
full decision/acceptance record, passing `python _scripts/validate_doc_routes.py`
from workspace root, reviewed own-change local commit. Archive extraction proves
file recovery, not a claimed old-server restart or semantic migration.

### B — Memory and reproducible clean foundation (Stages 2/1)

2026-10-07 checkpoint: typed graph-owned revision/publication protocol, isolated
deadline-bounded graph worker, HTTP page/entity consumer, non-destructive startup,
standalone pinned-image build, clean boot and explicit Save/KILL/independent
restore scenario are implemented and exercised. One-shot recovery is not the
scheduled RPO guarantee. Real 1k measurement is saved; 10k/100k, periodic verified
snapshot/effect barrier and remaining fault/consumer acceptance remain open.
See REWRITE-BASELINE continuation; no full Stage 2 completion box is checked.

Fix only Stage 1 prerequisites needed now: undeclared `oneiro-base:latest`, pinned
versions/checksums and proper ontology initialization on a separate new volume.
No startup-clear. Repeated migration is not proof of correct sc-types.
Review/split bridge at reader/writer seams; coordinated writes, stable IDs,
revisions, completion/read-back and incomplete-operation recovery. Check ID
collisions, idempotency and provenance. Retain the measured retry fix unless
current evidence requires repair.

Complete query contracts: bounded graph work/buffering, cursor/error/reporting,
insertion vs timestamp semantics, unknown vs absent, and consumer integration.
Keep whole-log loaders for explicit offline export/bench, with a test forbidding
their use on request paths. Existing backend enumerates all member addresses;
`latest()` ignores scan_limit, so current payload-bound claims are insufficient.
Measure real 1k/10k/100k inputs for correctness, latency, RAM and address/payload
reads. If upstream search inherently materializes everything, select a thin
bounded native path or rebuildable projection from measurements; do not conceal
O(N) work or introduce alternative durable memory.

Snapshots/checkpoints must prove save/restore and <=300-second loss including
snapshot duration; late durable checkpoints cause visible degradation. Before
unsafe effects, prove persistent intent, not merely read-back in server RAM.
Fault trials on disposable new storage: concurrent writers, reconnect, partial
write at boundaries, retry, malformed records, hard kill and restore. Compare
stable IDs/content/types/relations/counts; graph addresses are not eternal IDs
after rebuilding. A technical recovery journal is explicit and limited, never
a SQLite/JSON fallback memory system.

Exit: Stage 2 exit above plus actual request-path and representative measurements.
Old accumulated graph migration is excluded; all product/recovery tests use new
storage. Finish remaining foundation portability checks as the layers integrate.

### C — Recoverable runtime/tasks/initiative (Stage 3)

One authoritative async coordinator, bounded separate workers and shared typed
records/events. No state lock held across model/network/desktop calls; reserve
chat/control capacity. Explicit transitions, leases, dependencies, deadlines,
cancellation and safe checkpoints. Store intent before effect/result afterward;
unknown effect requires inspection/decision. Persist free-text answers and their
question/correlation, pausing dependent work only. Initiative has real reasons,
memory of earlier work, mute/quiet-hours/cooldown/dedupe and bounded cycles.

Exit: long work/waits do not freeze chat/control; safe restart and no duplicate
claim/effect; needs, unfinished work and interests all drive tested initiative.

### D — Shared models, research and supported media (Stage 4)

One OmniRoute-compatible adapter, configurable role models, actual tools/vision
capability probes, timeouts/cancellation/finite retries and capability-compatible
fallback. Count every call/token, including vision/generation/judging; no invented
prices/provider attribution. Router/model outage postpones only dependent steps.
Use working configured router freely within finite budgets, never reconfigure it.

Scope usable search/extraction adapters. If a new developer service is necessary,
research it and ask only for required account/credentials, not known decisions.
Bound text/image/PDF bytes/pages/context, preserve source/provenance, support
attachment-only intake and mark unsupported/uninspected input explicitly.

Exit: live chat/tools/vision/sourced research, actual supported attachments,
failure/retry/cancellation/accounting checks; no secrets in ordinary context/logs.

### E — Isolated tools and Linux GUI (Stage 5)

Verify Hyper-V at source; administrative setup needs the host's elevation prompt.
Use a light Linux desktop and tested/pinned low-level Cua Driver, not its agent
framework. If unsupported, establish the cause and evaluate a minimal compatible
driver/VM backend; containers cannot substitute for VM isolation.
Reviewed tool schemas/scopes/execution IDs/results. VM/Oneiro-folder autonomous
work only, screenshot/click/type/scroll/key/wait, visible observation and immediate
stop/human takeover. Account effects need genuine scopes, not a pixel classifier
presented as a reliable security boundary. Preserve artifacts, reversible removal.

Principal scenario uses Writer GUI to create headings/table/image, save
`gui-demo.odt`, export `gui-demo.pdf`, reopen both and independently check content.
Script file generation may assist independent verification, never replace the
claimed GUI creation. Host desktop remains untouched.
Exit: real files/scenario, stop/takeover/recovery and tested isolation.

### F — Native app, graph/tree and Telegram (Stage 7)

Thin Windows native WebView around the same FastAPI/HTML/CSS/JS. Provisional
WebView2-based Python wrapper requires packaging/CSP/tray/lifecycle smoke before
pinning. No privileged arbitrary JS-to-host bridge or weaker CSP for convenience.
Root chat, `/settings`, `/setup`, `/oneiro/`; streaming/tasks/evidence/memory/roles/
provider status, single source of truth. One shortcut launches/reuses native
window; close-to-tray, reopen, safe full exit and crash recovery are verified.

Linked memory explorer and botanical strategy tree: actual IDs/edges/rounds/
scores/provenance, stable layout and true event growth; animation never invents
nodes or uses glow to claim unmeasured gain. Cycles/orphans/corrupt/truncated/
unavailable reads remain visible. Static and reduced-motion views are useful;
anime.js pinned and shipped locally with licence, no CDN/framework migration.

New private owner-allowlisted Telegram bot with long polling (no public inbound
endpoint), shared conversation and important-notification fan-out. Restart-safe
intake offset/outbox, attachment-only messages, question/reply correlation and
cross-channel cancel/decide; stale callbacks refused. Unknown sends remain unknown,
not blindly repeated or promised exactly-once. Existing userbot stays read-only.
Exit: actual conversation/task/channel handoff, media, lifecycle and error trials.

### G — Install, new-data upgrades and legacy retirement (Stage 8)

Local Windows installer/runtime/shortcut without shared-workspace or CowAgent/
Hermes/OpenClaw prerequisites. Isolated clean install outside checkout with fresh
data root; no ambient credentials masquerading as onboarding. Diagnose missing
WebView2/Docker/VM. System enabling/installs need approval, not silent mutation.
First downloads pinned; assets local; a model still requires a real provider.

One data root, secrets/grants outside candidate writes, localhost-only published
ports and no unintended container/OS autostart. Manual start/stop/update/recovery,
known PIDs/listeners/ownership, own-process cleanup only. Archive legacy after
replacement/equivalence checks, eliminate active old paths and sys.path/module
collisions/workspace references incrementally, preserve unrelated owner data.

Exit: target `dist/Oneiro-Setup.exe` plus actual isolated install/start/reopen/
stop/reinstall/upgrade/restore. New owner data preserved, one shortcut; file names
are final targets, not assertions that these artifacts already exist.

### H — Scientific kernel and automatic improvement (Stage 6)

Recheck retained world/replay/dream/C++/harness/metrics with fixed-record invariant
and equivalence evidence. Exact replay has zero world actions; consistency,
coverage/conflicts protect the judge. Trajectory-changing stochastic policies
require live trials, not replay-only predictions.
Compare OSTIS/context-only/flat store with identical material and traceable run
IDs: recall/order/provenance/contradictions/latency, raw results, frozen controls.
At least three paired stochastic repeats or abstention; never change the control
after seeing results. Determine one real gain without claiming deterministic-world
gain proves GUI-agent improvement.

Protected supervisor/control tests outside candidate write authority. Candidate
-> isolated checks -> acceptance trial -> promotion/rejection -> versioned rollback.
Test bad candidate, restart mid-update and rollback after new owner records;
newer data survives and candidates cannot weaken their own acceptance gate.
SoL-Pi/design resources are sources/possible candidates, not compulsory framework
dependencies or evidence of our own savings. Verify citations before shipping.
Exit: real reproducible gain, comparison, reject/promote/rollback evidence;
no gain leaves scientific acceptance open rather than manufacturing success.

### I — Full local acceptance and bilingual presentation

Apply every checklist row to the installed delivered revision, not just source
unit tests. Fault/recovery/live-model/OSTIS/browser/native/VM/scientific checks
remain distinct. Write final paper/presentation only after current evidence;
preserve historical papers and numbers separately.

Final exact targets relative to the project root:

- `dist/Oneiro-Setup.exe` (installer, unit G).
- `dist/oneiro-delivery/gui-demo.odt`, `gui-demo.pdf` (real GUI outputs).
- `dist/oneiro-delivery/demo.mp4` (actual recorded demonstration).
- `dist/oneiro-delivery/slides-ru.pptx`, `slides-ru.pdf`.
- `dist/oneiro-delivery/slides-en.pptx`, `slides-en.pdf`.
- `dist/oneiro-delivery/talk-ru.md`, `talk-en.md`.
- `dist/oneiro-delivery/acceptance.md`, `SHA256SUMS`.

Names after the first item in a delivery-directory pair remain within that
same `dist/oneiro-delivery/` directory. Keep editable presentation sources in
project docs as well. Do not include secrets, old graph or private account data
in the kit. Russian/English decks/scripts must match numbers and limitations;
a recording supplements, not substitutes for, runnable live demonstration.
Verify PPTX editability, PDF/ODT reopen/content, playable MP4, manifest completeness
and matching hashes. This is local delivery only, not a request to upload files.

Exit: installed reusable product, evidence-backed full acceptance and genuine
local delivery kit, or an explicit list of unfinished requirements. HTTP 200,
foundation/readiness listings and old green counts do not complete the Mission.

### Verification, checkpoints and resource discipline

Each nontrivial slice: focused pytest, configured mypy expanded with integration,
relevant C++ build/live checks, doc-route validator for docs edits, actual user
interface/scenario. Review final edited version; after repairs rerun affected
checks. Preserve tested command exit status through filters. Never weaken/skip/
suppress to obtain green or advertise mocked evidence as live proof.
Deliver a runnable minimal vertical slice early and retain usable checkpoints;
coherent units are hours-days. No invented deadline or one-night completion.
Long jobs run background with PID/lifetime/log/readiness/stop path; inspect
listeners first. Night exclusivity does not remove RAM/disk/load checks or permit
mass-killing, autostart/system/router changes or administrator bypass.

Access blocks only dependent scenarios. Obtain bot credentials/admin/login/2FA
when actually required; do not interview already-settled product requirements
again. Keep evidence/task checkpoints next to the work, own verified hunks only
in local commits, no broad staging/reset/stash/foreign overwrites/publication.
