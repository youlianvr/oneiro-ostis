# Oneiro — binding owner decisions

Status: full-project rewrite approved; implementation is incremental, not done.
Authority: current owner conversation and Mission, recovered 2026-10-02.
Delivery plan: [MASTER-PLAN.md](MASTER-PLAN.md).
Evidence/checklist: [REWRITE-BASELINE.md](REWRITE-BASELINE.md).

## Product

One coherent persistent assistant with mandatory OSTIS memory, independent
manager/researcher/executor roles, initiative, Linux computer use and measured
self-improvement. Review all own code, including scientific/kernel/native code.
Use ready libraries/protocols/low-level desktop drivers instead of writing another
agent engine. CowAgent/Hermes/OpenClaw are not product prerequisites.

## Roles and operation

- Three configurable SOUL personalities; no compulsory three-role pipeline.
- Manager converses/plans/delegates/arbitrates, not code edits.
- Researcher researches/reads/shared notes, not installation/project changes.
- Executor implements assigned work/verifies outcomes/reports objections.
- Prompts and SOUL cannot change permanent capabilities.
- Each role owns notes and can read others' memory.
- Initiative comes from owner needs, unfinished work and interests, with opt-in,
  quiet hours, deduplication and finite cycles.
- No OS autostart; a manually started instance may keep working.

## Models, tools and permissions

- Use configured working OmniRoute models, including live development checks;
  leave provider integration extensible, don't hardcode upstream names.
- Working context, selected attachments and VM screenshots may go to configured
  AI APIs without per-request approvals. Credential values stay out of ordinary
  context/logs. This supersedes repetitive outbound-URL/model-media consent in
  older plans; implementation still has to catch up.
- Use scoped permissions for real accounts. Use API scopes where possible;
  GUI access cannot guarantee per-effect restrictions merely by classifying pixels.
- Computer use is confined to a separate Linux desktop VM, not host desktop.
- Local work within approved scope does not require repeated continuation asks.
- Agent may automatically improve/update application code after verification;
  capability grants, secrets, control tests and update supervisor are outside its
  writable authority. Trial/rejection/rollback are mandatory, improvement measured.
- Finite calls/tokens/time/retries prevent accidental loops; price is not invented.
- No permanent destruction: archive/trash/restore; rebuild separate storage.
  This supersedes the old provision allowing irreversible destructive instructions.

## Memory and evidence

OSTIS is required; production cannot silently fall back to SQLite/JSON. Typed
append-only observations, stable IDs, completion/recovery and provenance are
required. Existing graph data/experiments/owner work/published artifacts are kept.
Normal startup never clears existing graph. Migration/snapshot consistency must
be demonstrated on the real pinned stack, not inferred from a copy or mock.
No claim of action, viewing, installation, measurement or test without evidence.

## Delivery and publication

- One desktop shortcut; one origin **http://127.0.0.1:9899**.
- Chat at root, settings/onboarding via relative routes, graph panel at **/oneiro/**.
  No CORS workaround and no manual port discovery.
- Native installer/onboarding/manual lifecycle/upgrade/recovery are product work.
- English UI/code/new docs; Russian dialogue. Keep existing Russian `main` and
  English `v2` split: rewrite intended for `v2`, not translation of `main`.
- Latest Mission authorizes eventual GitHub push after verification. Current
  foundation unit must not publish. Publication is project subtree only to its
  own remote; no workspace publication or broad staging.
- No further architecture/continuation questions after approval. Missing access,
  infrastructure/admin/2FA blocks the affected scenario; independent work continues.

## Acceptance

See all stages/exit conditions in MASTER-PLAN. Offline contracts, typechecking,
live OSTIS/provider/browser/VM/scientific/migration/update checks and clean-install
proof are separate evidence categories. A shell returning HTTP 200 is not a
working assistant. Plans, provider listings and old green counts are not live
acceptance. Reports state changed paths, commits, actual tests and remaining gaps.
