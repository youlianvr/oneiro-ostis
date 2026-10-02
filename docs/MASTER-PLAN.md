# Oneiro — full-project rewrite

Authority: owner-approved Mission in the current conversation, recovered on
2026-10-02. This plan replaces the earlier limited product-plane rewrite and
waiting for the missing cloud PR. Approval is not implementation evidence.
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

Latest Mission adds production delivery: onboarding, installation, **one desktop
shortcut**, and **one address http://127.0.0.1:9899** for chat, relative settings
routes and graph panel **/oneiro/**, without CORS or manual port discovery.
Eventually publish the verified project to its own GitHub repository. Publication
is deferred until acceptance; preserve Russian `main` / English `v2`, publish
only the project subtree, never the workspace. The present foundation step does
not publish. A report distinguishes real live verification from remaining gaps.

## Confirmed owner decisions

- Preserve scientific meaning and accumulated data; implementations are reviewed
  and rewritten wherever needed, including existing native code.
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

Preserve graph history, owner files, unfinished work, experimental records,
published results and school-paper artifacts. Never silently replace historical
numbers. Keep old paths until replacements pass relevant scenarios, then archive;
no active imports, launch commands or installation dependencies may use legacy.

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
must be verified on the actual stack. Major migrations run on a consistent copied
graph before promotion, not the live storage.

## Implementation checklist

Only checked items have current evidence. Historical native/cloud green counts
are not completion of these phases.

- [x] Recover complete approved requirements and preserve delivery additions.
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
      Remaining in this stage: load_memory_sessions cannot read back what
      save_memory_sessions writes (payload arc is findable by address; reader
      searches the relation keynode instead) - localised, undiagnosed. Other bridge
      writers and the dream-cycle writers are untested across a restart.
      See REWRITE-BASELINE.md.
- [ ] 3: concurrent, recoverable runtime/tasks/initiative.
- [ ] 4: shared model/research/media adapters and live capabilities.
- [ ] 5: isolated executor/tools and Linux desktop integration.
- [ ] 6: scientific equivalence and measured automatic updates/rollback.
- [ ] 7: unified production web/Telegram/chat/settings/graph.
- [ ] 8: installer/onboarding/one shortcut/migration/legacy retirement.
- [ ] Full acceptance, production readiness and scoped GitHub publication.

## Stages and exit conditions

### 0 — Baseline, inventory and decision record

Inspect Git status/branch, foreign changes, ownership, services and data. Do not
stop unrelated processes or overwrite foreign work. Update this plan/goal and
supersede the PR wait. Inventory imports, entrypoints, settings, graph schemas,
datasets and artifacts. Run old tests, distinguishing failures/prerequisites.
Establish a consistent snapshot and isolated restore; a hot file copy is not
assumed consistent.

Exit: written decisions/disposition map/reproducible baseline/identified data;
verified recovery before production migration.

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

Exit: old data queryable; new records survive restart; no duplicate logical events
on retries; partial operations detectable; restored/migrated counts/content pass.

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
search key. Web/Telegram attachments: image/text/PDF and available audio/video;
bound bytes/pages/frames/context and label uninspected/unsupported media.

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

Exit: real VM task verified, host untouched, stop/takeover/restoration functional,
account actions within available grants.

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

Exit: known replay correct, uncertainty prevents unsupported promotion, scientific
comparison reproducible, update/reject/rollback work without weakening own gate.

### 7 — Unified web and Telegram

API/UI over typed records: streaming chat/media/conversations/tasks/evidence/
memory/roles/providers/live status. Separate liveness/readiness/integration checks.
Telegram same core, attachment-only intake, stable question/reply mapping,
restart-safe updates and outbox recovery. Unknown send outcomes remain unknown:
no impossible exactly-once promise. Cross-channel cancel/decide; stale callbacks
can't release new actions. Desktop observation/stop/takeover; small-screen checks.

Exit: same state in both channels; chat/delegation/answers survive restart;
attachments aren't dropped; no parallel channel agent logic. One origin/routes.

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

Exit: clean and migrated installs pass; old planes unnecessary, data preserved;
chat/settings/graph share 9899. Production acceptance precedes publication.

## Acceptance matrix and verification

1. Clean install/start outside workspace.
2. Casual conversation without mandatory tasks/delegation.
3. Sourced research/retrievable notes.
4. Actual executor changes/tests/outcomes.
5. Initiative from all three sources without repetition.
6. Live text/tools/vision via router and honest capability failures.
7. Real Linux VM completion/result/owner interruption.
8. Fault/restart during models/writes/effects/delivery.
9. Data-preserving migration/snapshot restore/ontology upgrade.
10. Determinism/replay equivalence/coverage/conflict/scientific comparisons.
11. Actual candidate validation/promotion/reject/rollback.
12. No active legacy dependency.
13. Onboarding, one shortcut, same-origin chat/settings/graph on 9899.
14. Production checklist and project-only GitHub publication, preserving branches.

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

Preserve foreign changes; commit only owned hunks. Publication waits for
verification and targets the project subtree/English v2, not Russian main.
Each stage persists current work/checks/blockers/next step in owning docs and task
memory. Report paths, committed vs pending, evidence, gaps and decision reasons.
Only required live evidence completes the task; partial implementation is partial.
