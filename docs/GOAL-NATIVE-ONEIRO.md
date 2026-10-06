# Oneiro — binding owner decisions

Status: full-project rewrite approved; implementation is incremental, not done.
Authority: current owner conversation and full local-delivery Mission approved
2026-10-07; this supersedes conflicting 2026-10-02/06 delivery decisions.
Approval is a work grant, not evidence of implementation.
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
- Active initiative comes from owner needs, unfinished work and interests:
  independent reversible work and starting useful discussions, with quiet hours,
  mute, cooldowns, deduplication and finite cycles; not a timed notification loop.
- One conversation across local UI and Telegram; important notifications appear
  in both without creating a second task, event or decision.
- No OS autostart. Closing the native window leaves Oneiro in the tray;
  reopening reuses the instance, and explicit exit safely stops owned processes.

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
- Autonomous file changes are confined to that VM and a separate Oneiro working
  folder. No automatic attachment of the shared workspace or other owner folders.
- Money, publication, host-desktop access and expanded grants require a specific
  owner decision. Permanent destruction stays forbidden even with a request.
- Local work within approved scope does not require repeated continuation asks.
- The owner granted the exclusive overnight computer window for background
  builds/downloads/measurements with logs and a stop path. This does not grant
  administrator access, system changes or stopping unrelated processes, and is
  not a deadline or a promise to finish the entire rewrite in one night.
- Text, images/screenshots and PDF are v1 media. Voice, audio, video analysis,
  a mobile application and training own models are deferred beyond v1.
- Agent may automatically improve/update application code after verification;
  capability grants, secrets, control tests and update supervisor are outside its
  writable authority. Trial/rejection/rollback are mandatory, improvement measured.
- Finite calls/tokens/time/retries prevent accidental loops; price is not invented.
- No permanent destruction: archive/trash/restore; rebuild separate storage.
  This supersedes the old provision allowing irreversible destructive instructions.

## Memory and evidence

OSTIS is required; production cannot silently fall back to SQLite/JSON. Typed
append-only observations, stable IDs, completion/recovery and provenance are
required. **Clean-start override (owner, 2026-10-06; approved 2026-10-07):**
the old graph is not migrated or used as a seed. Preserve one verified archive
outside Git (SHA-256, extraction and complete-file comparison); retain its old
volume stopped and intact, then use a separate clean volume. Existing owner
files, historical experiments, published numbers and school artifacts remain.
Normal startup never clears a graph. New memory/strategies, tasks/intentions,
settings/connections and Telegram intake/outbox must survive supported recovery.
The accepted hard-kill graph-memory loss window is at most 300 seconds, measured
on disposable new storage. A periodic timer or read-back alone is not proof.
Unknown external effects must remain inspectable after recovery; no blind retry.
Ontology upgrades must be additive/idempotent and preserve proper sc-types.
Migration/snapshot consistency must be demonstrated on the real pinned stack,
not inferred from a hot copy or mock.
No claim of action, viewing, installation, measurement or test without evidence.

## Local delivery (publication excluded)

- Fully verified target: Windows 11. Native window and tray around the same
  HTML/CSS/JS and backend, not a second frontend framework or agent system.
- One desktop shortcut; one origin **http://127.0.0.1:9899**.
- Chat at root, settings/onboarding via relative routes, graph panel at **/oneiro/**.
  No CORS workaround and no manual port discovery.
- Native installer/onboarding/manual lifecycle/upgrade/recovery are product work.
- English UI/code/technical docs; Russian dialogue. Preserve historical Russian
  `main` and English `v2`; do not switch branches or translate history implicitly.
- **Local-delivery override (owner, 2026-10-07):** no push, deploy, PR or sending
  materials in this Mission. This supersedes earlier eventual-push authority.
  Small local commits are authorized for own verified changes only.
- A new private owner-allowlisted Telegram bot shares runtime/state with the UI;
  the existing Telegram userbot stays read-only. Unknown delivery is not an
  exactly-once guarantee. Old question callbacks cannot release new actions.
- `/oneiro/` has linked memory-explorer and growing-strategy-tree views. Every
  node/edge/score traces to actual OSTIS records; stable IDs and current graph
  addresses expose provenance. Truncation, failure, cycles and orphan edges are
  visible. Pinned anime.js ships locally with its licence; no CDN/React/Tailwind.
  Static/reduced-motion rendering must remain useful without animation.
- The principal VM demo uses LibreOffice Writer through GUI actions: formatted
  headings, a table and an image; save ODT, export PDF, reopen and independently
  inspect both. Script-generated files cannot substitute for claimed GUI work.
- Live demo plus reusable installed product, not a one-off presentation.
  Russian and English editable slides/PDFs/talk scripts and a real demo recording
  are written at the end from raw evidence, with the same numbers/limitations.
- Scientific acceptance requires real measured improvement on at least one
  preselected scenario. It need not be the GUI task; label deterministic-world
  evidence separately from coding/GUI-agent evidence. Freeze controls/criteria
  before search; at least three paired stochastic repeats, or abstain.
  No measured gain means scientific acceptance remains incomplete.
- Automatic update checks, promotion/rejection and rollback have a journal;
  rollback must preserve newer owner data and candidates cannot weaken the gate.
- No further architecture/continuation questions after approval. Missing access,
  infrastructure/admin/2FA blocks the affected scenario; independent work continues.

## Acceptance

See all stages/exit conditions in MASTER-PLAN. Offline contracts, typechecking,
live OSTIS/provider/browser/VM/scientific/migration/update checks and clean-install
proof are separate evidence categories. A shell returning HTTP 200 is not a
working assistant. Plans, provider listings and old green counts are not live
acceptance. Reports state changed paths, commits, actual tests and remaining gaps.
