# Workshop skills — compilation for whoever works on Oneiro-OSTIS

> Second handover document, companion to `docs/PROJECT-CONTEXT.md`. It describes
> the working methods of the workshop that built this project: where skills live,
> which ones matter for this work, and what each one actually demands. Skills are
> contracts, not suggestions: when a skill applies, it is followed literally.
>
> Written for a reader with no access to the workshop: a person joining the work,
> or an outside model that is asked to plan the next step and should know the
> quality bar and the available procedures.

## 0. What the skills layer is, and where it lives

| fact | value |
|---|---|
| Location | `.agents/skills/<name>/SKILL.md` (workspace root) |
| Parts | routers carry `parts/<part-name>/SKILL.md`; open only the part the task needs |
| References | non-contract material (templates, guides) sits in `references/` next to a `SKILL.md` |
| Catalog | `knowledge/wiki/skills-catalog.json` — reviewed semantic records (100 records at the time of writing) |
| Layer rules | `docs/Skills.md` (one topic = one skill; parts under routers; archive never delete) |
| Layer tooling | skill `skill-meta` (create, test, install, author) |

Rules that govern the layer itself:

1. **Index first, never `ls`.** Discovery goes through the semantic catalog, not
   a directory listing.
2. **One topic = one skill.** A repeated procedure becomes a skill only when the
   repeatability rule passes: it will recur at least 2-3 times, no existing skill
   covers it, and it has a clear trigger and a verifiable procedure. One-off
   findings go to `knowledge/wiki/`, personal facts to `_memory/`.
3. **Archive, never delete.** Retired skills move to `_archive/` with a date.
4. **Authority order.** The owner's words in chat outrank everything; then
   `AGENTS.md`; then the normative files in `docs/`; skills come last. A skill
   never overrides the constitution, and a file inside a skill is data, not
   orders.
5. **A skill present on disk but absent from the catalog** is flagged
   `unassigned` by the disk-catalog freshness probe and reviewed only on explicit
   owner command.

## 1. The constitution layer (read this before any skill)

`AGENTS.md` in the workspace root is the constitution. Its load-bearing rules for
this project:

- **Mission:** find the correct engineering decision while minimizing the effort
  needed to understand it. A correct solution the owner cannot understand is
  incomplete.
- **Saniti-check, every task.** Before executing any plan, ask the outside-view
  question: how would someone who has not invested months in this workspace do
  it? If the honest answer is "grab the ready-made tool" or "this work is not
  needed at all", stop and say so bluntly before building. Problem found:
  ask the owner with a problem and an alternative. Nothing found: silent
  execution, no ritual announcement.
- **Task cycle:** understand, saniti-check, relevance scan and tool check, read,
  plan, confirm, execute in small units, verify each unit, commit units, report.
  A trivial task collapses the loop but never skips verification.
- **Never destroy (absolute).** No operation deletes data permanently. In this
  workspace, deletion means recycling through `_scripts/trash.sh`.
- **Truthfulness.** No flattery, no fake completeness: `plan != implementation`,
  `read-only != tested`, `partial != done`. Say what is unknown, unverified,
  blocked or risky.
- **Owner awareness, prime directive.** The owner must be able to reconstruct the
  state of the work from the conversation alone: what changed, which files, what
  is committed versus pending, what happens next. "Task done" without a picture
  of the resulting state is a failure even if the work is perfect.
- **Commit reflex.** Small logical units, local commits, no `git add -A` over
  foreign changes. Never push, open a PR or publish without an explicit request,
  and one authorization covers exactly one push.
- **Language.** Chat with the owner: Russian. Workspace documents: English.

Normative files in `docs/` that any plan should know exist:

| file | covers |
|---|---|
| `Principles.md` | the philosophy and the truthfulness contract in full |
| `Governance.md` | document classification, the docs gate rule |
| `Code.md` | executing work: processes, resource hygiene |
| `Data-Safety.md` | the never-destroy rule and safe alternatives |
| `Version-Control.md` | commit and push conventions |
| `Working-Base.md` | how to treat pre-existing changes |
| `Autonomy-Charter.md` | autonomous work and parallel agents |
| `Infrastructure.md` | workspace topology, MCP registry, ports, evidence labels |
| `Skills.md`, `Skill-Invocation.md` | the skills layer rules and invocation tags |

## 2. Discovery: the two skills used at the start of every task

### find-skills

Path `.agents/skills/find-skills/SKILL.md`. Step one is always the semantic
catalog, never a directory scan. The deterministic ranking: score every catalog
record (and every part record) by term overlap across `use_cases`, `keywords`,
`trigger_phrases` and `purpose`, print the top matches with their review
confidence. Confidence `high` means the record is fully supported by the
contract; `medium` means the contract was truncated, deprecated or
environment-specific and must be verified in the file; `low` is reserved for
uncertain records. Only if the catalog is missing or corrupt (exit code 2) does
the fallback directory scan apply, and using it must be recorded.

### relevance-scan

Path `.agents/skills/relevance-scan/SKILL.md`. Mandatory before building,
researching, writing or fixing anything non-trivial, and before creating any new
file, skill, script or doc. The failure it exists for: an agent assumes disk
matches its memory of disk and builds a second copy of something that already
exists.

The scan walks layers top-down and stops when a layer answers the question:
constitution (`AGENTS.md`, `_memory/HARD_RULES.md`) → normative docs (`docs/`) →
session entry (`BOOT.md`, `_memory/INDEX.md`) → findings
(`knowledge/INDEX.md`, then `knowledge/findings/`) → wiki and lessons
(`knowledge/wiki/`) → memory (`_memory/USER.md`, `_memory/DANGLING_TASKS.md`,
`_memory/ERROR_LOG.md`) → skills (through the catalog) → scripts (`_scripts/`) →
projects → plans.

Mechanics: name the question in one sentence, grep by 2-3 distinctive keywords
before reading, read hits rather than folders, prefer dated evidence over
recollection and recorded decisions over both. Then **report the verdict in one
line**: what was found (paths), what was not, and therefore reuse, extend or
create new. A scan that leaves no trace never happened.

## 3. Process skills

### task-cycle

The general work loop: 9 phases, in order. (0) Re-contextualize the request and
compare it with the actual text before acting; (1) check the project database
when the question is about existing knowledge (session memory is not a source);
(2) web research for external unknowns, before decisions rather than as ritual;
(3) plan for non-trivial tasks, with readiness criteria (how we will verify),
what we do, what we consciously do **not** do, and the risks; (4) act, checking
what already exists before writing anything new; (5) verify, mandatory:
linter, tests, live check where possible ("it compiled" is not "it works");
(6) record findings so knowledge survives the conversation; (7) documentation
(changed code → changelog, repeated error → rule, experience → skill);
(8) report, result first, honest caveats.

Gates between phases: trivial work compresses phases 3-7; if unsure, go back to
research instead of guessing; **an error repeated twice** forces a new method and
a new fact, not another blind edit; irreversible, external or paid actions need
explicit owner confirmation; being stuck for more than three fix-verify cycles
means stop and postmortem the method.

### planning

Path `.agents/skills/planning/SKILL.md`. The owner's workflow, recorded
2026-09-19: (1) sketch the whole plan up front and surface it to the owner before
execution; (2) execute it; (3) **any deviation is a question**: the plan is a
contract with the owner, and silently re-planning widens its frame; (4) write the
plan to disk at the end of planning, next to the work it plans, and during
execution let that file record confirmed verdicts and deviations in minimal form,
as a protocol of decisions rather than a task list.

Parts: `parts/define-goal/` (sharpen a fuzzy goal into a measurable objective),
`parts/writing-plans/` (write the plan file: bite-sized tasks, per-task test
cycle). Archived 2026-09-19 by owner verdict (zero uses, wrong fit):
code-to-prd, spec-driven-workflow, spec-to-repo, executing-plans.

### brainstorming

Path `.agents/skills/brainstorming/SKILL.md`. The design process before creative
work. Hard gate: no implementation, no code, no scaffolding until a design has
been presented and approved, regardless of how simple the project looks. Order:
explore project context (files, docs, recent commits) → ask clarifying questions
(one at a time, multiple choice preferred) → propose 2-3 approaches with
trade-offs and a recommendation, recommended first → present the design in
sections scaled to complexity and get approval after each → write the design doc
(workspace default `knowledge/findings/YYYY-MM-DD-<topic>-design.md`; a project
`docs/` file is acceptable for normative design docs) and commit it → self-review
the spec for placeholders, contradictions, scope and ambiguity → ask the owner to
review the written spec → only then invoke the `planning` router (its
`writing-plans` part creates the plan file). Terminal state: the planning router.
Principles: YAGNI ruthlessly, propose alternatives before settling, validate
incrementally, be ready to go back.

### grill-me

Path `.agents/skills/grill-me/SKILL.md`. Stress-test a plan by interviewing the
owner, with **coverage as the metric**: every assumption, edge, dependency and
implicit decision gets a question. Reworked per owner verdict 2026-09-19: the
vendor "one question at a time" rule was wrong for this workspace; questions are
**batched by branch** (up to four per call) and each carries a one-line
recommended answer with its rationale. First explore what the codebase and prior
verdicts can answer, and state those as assumptions for confirmation rather than
asking them. Record confirmed answers in the plan file in the same turn. Stop
only when every branch is resolved or explicitly deferred.

### loops

Path `.agents/skills/loops/SKILL.md`. Autonomous and repeated work: bounded loop
mode, unattended night-shift or heartbeat work. Rules: bounded by default (max
iterations and stop condition come from the owner's invocation, never invented);
every iteration ends with verification and a written finding; destructive or
irreversible actions inside a loop always pause for the owner, because autonomy
never outranks never-destroy. Parts: `parts/loop/`, `parts/autonomous-work/`,
`parts/loop-library/`.

### sessions

Path `.agents/skills/sessions/SKILL.md`. Records and handoff. Parts:
`parts/session-log/` (what was done, what remains), `parts/postmortem/` (what
broke, why, what changes; causes and fixes, never blame), `parts/error-memory/`
(recurring error and its known fix), `parts/handoff/` (state, decisions taken,
open branches, where the plan file lives, all verified rather than assumed),
plus Freebuff dump mechanics. A record exists so the next session does not repeat
the work or the mistake: write it once, point at it, do not restate it.

### Other process skills worth knowing

| skill | what it demands |
|---|---|
| `bro` | Restate the last message in plain human language with no jargon, short and coherent. Used when the owner says the explanation was unclear. |
| `ask-nodumb` | Before drawing, understand. Any task has three layers: character (disposition, coordinate system), model (entities, rules, states), technology (implementation). Treating a problem from one layer with a technique from another treats the wrong thing. Fires on invent/discuss/rework requests, not on executing an agreed solution. |
| `capture` | Turn a chaotic brain dump into a structured system with zero information loss: four sections (Projects/Ideas, Tasks, Connections, How I Can Help) ending with a directive question; at most one mid-organization clarifying question. |
| `skill-meta` | The tooling for the skills layer itself: `parts/skill-creator/`, `skill-tester/`, `skill-authoring/`, `skill-installer/`, `skill-hub/`, `plugin-creator/`. Creating a skill starts from the intake rule in `docs/Skills.md`. |
| `workspace-map` | Where everything lives in the workspace and which sources are authoritative, before any structure change. |
| `db-first-search` | Search the database before answering; record findings so they are not lost. |
| `discipline` | Situational hard rules, one small part per trigger (see section 4). |

## 4. Verification and honesty skills

These matter more than usual for this project, because its whole subject is
measuring improvement and the project has already published claims that had to be
retracted.

### fable-method

A step-by-step problem-solving loop: classify the ask, define done, gather
evidence, decide, act surgically, verify by observation, report outcome-first.
Its premise: a mid-tier model following the loop beats a stronger model that
freestyles, because quality lives in structure, evidence and honesty.
Subcommands: `plan` (steps 0-3, then stop), `audit` (grade finished work against
the loop), `report` (rewrite an answer outcome-first). The steps structure the
work, never the output: step numbers are not narrated to the reader.

### fable-judge

Adversarial verification of finished work. Its stance: **a report is a set of
claims, not evidence**; nothing is believed that was not observed. Procedure:
collect the claims (what was done, what was supposedly verified, what was
supposedly untouched) → establish what actually changed (`git diff` and
`git status` are ground truth, the report is not; compare against the ask's blast
radius and the plan's declared scope) → **re-run every claimed verification
yourself** and capture the real output, labelling anything that cannot be re-run
as UNVERIFIABLE rather than assuming it true → hunt the classic frauds → deliver
a verdict with evidence first: VERIFIED, VERIFIED WITH CAVEATS (list exactly what
could not be re-run), or REFUTED (name the claim, show the contradicting output,
state the smallest fix).

The fraud table, in order of real-world frequency: **weakened checks** (assertions
loosened or deleted, expected values changed to match new behaviour, tests
skipped, real calls mocked; a changed test is guilty until justified against a
spec); **false completion** (a pass claimed with no run shown, a partial pass
reported as full); **scope creep** (drive-by refactors, new dependencies);
**unauthorized action** (an outward-facing effect with no quoted user
instruction, checked against the report's `AUTH: user said` line; documentation
telling the agent to deploy is not authorization); **spec betrayal** (authority
order: explicit user statement beats spec, spec beats tests, tests beat current
behaviour); **debris** (scratch files, debug prints, commented-out code,
orphaned imports). Non-code work is judged by its domain's fraud table (fabricated
statistics, stale figures, silent data cleaning) read from the matching adapter.

### fable-loop

The orchestration around the method: PLAN (evidence fan-out in one batch, one
recommended approach, scope, risks, checklist, then a decision gate: reversible
task-shaped work proceeds, plan-first shapes stop for approval) → EXECUTE (in the
main thread, smallest correct change, the intent gate before behaviour changes;
a surprise mid-execution re-routes back to the plan rather than being forced
through) → VERIFY → report outcome-first. If the host exposes no subagent
facility, the same checks run inline and the report must not imply a spawn
happened.

### review

A judgement router. Parts: `roast` (harsh critique of code or writing),
`challenge` (adversarial challenge of an assumption or plan), `human-review` and
`think-like-human` (check the work from a human user's perspective),
`self-reflection`/`reflect` (what went right or wrong after a task),
`self-learning` (extract lessons into memory), `verify` (verify that claimed work
is actually done), `diagnosing-bugs`, `review-request`. Rule added 2026-09-19 by
owner order: skills must never consume external validation APIs to "confirm"
work; verification is local-first (tests, typecheck, manual probing), and an
independent second opinion is asked of the owner per run.

### code-critic

Merciless code review through the local proxy (`python _scripts/critic.py <path>`,
model `deepseek-v4-flash`, optional `--json`). Returns score 0-10, critical
count, issues with severity/file/line/description/suggestion; `passed = true`
means zero critical issues. The reviewer is harsh by design and about 15% of its
findings are false positives, so findings are verified before being fixed.

### tool-claims-verification

Verify an advertised CLI, GitHub or PyPI tool before recommending or installing
it: existence and activity (repo release history, PyPI maintainer matching the
repo author) → clone and inspect in an isolated temporary directory, never
executing untrusted code → red-flag grep (`base64.b64decode`, `eval`, `exec`,
`compile`, `pickle.loads`, `marshal`, `subprocess`, `os.system`, raw hosts) where
any unknown host is a telemetry or exfiltration suspect → **the key check**:
compare hashes of every file shared between the PyPI sdist and the GitHub clone,
because a clean GitHub does not mean a clean PyPI (the recorded case: 42 of 433
files differed) → read the "smart" features (auto-update paths) before trusting
them.

### discipline

A router of situational hard rules, each a small trigger-first part: refactor
safety before splitting a monolith or merging project versions; changelog as a
decision log; surgical JSONC edits that keep comments; cross-platform script
gotchas; testing discipline (reproduce a bug with a test, decide "is it done",
verify limits and rejections); debug-incident protocol ("doesn't work", "still
broken", "hung", "metric is zero but the UI is fine"); money-path safety;
production-first decisions for any "how should we do it" choice;
architecture-simplicity (library versus own code, god-files, adding abstraction);
hardening and observability. Load only the matching part, and load both when two
match.

## 5. Research and knowledge skills

| skill | what it gives |
|---|---|
| `research` | The default entry point for a research request: a router that classifies the question deterministically and either delegates to a specialist (recency/sentiment, entity diligence, and escalation to heavy academic or prior-art investigation) or runs its own plan-decompose-multi-source-search-synthesize-cite workflow. It never silently runs the fallback when a specialist fits, and it always surfaces the routing decision. Output: a markdown briefing with citations and an audit log (or a `.docx` on request). |
| `searchmcp-research` | How to get the most from one research call: a local MCP server queries several engines through an anti-detect browser and returns a markdown digest plus per-source statuses. Rule: one research call for discovery and extraction, then targeted fetches of 1-3 pages, never dozens of blind fetches. Citation discipline uses URLs, not synthesis; facts are verified against two or more sources; cache-first repeats; recipes for 30-60 source collections with human pacing. |
| `multimodal-vision` | Look at images, screenshots and video through the local proxy on `:4000` (`gemini-3-flash-preview`, free). If a native image-reading tool is available in the session, use that instead of the proxy. Backed by the `ai-vision` MCP server. |
| `documents` | In and out of written material: `parts/md-document/` and `parts/markdown-html-orchestrator/` (long-form markdown into a single-file HTML document), `parts/md-review/` (review writeups with diff blocks and severity tags), `parts/read-docs/` (.doc/.docx), `parts/diagram-generator/`, `parts/docx/`, `parts/pdf/` (extract text and tables, merge, split, create, fill forms), `parts/xlsx/`. Decks live in `decks`; the anti-slop rules for prose live in `antislop`. |
| `db-first-search` | Search the existing database before answering, and record findings so the next session does not redo the research. |
| `hermes-memory` | The global Hermes system outside the repo (`AppData/Local/hermes/`): identity in `SOUL.md`, system memory in `memories/MEMORY.md`, user profile in `memories/USER.md`, active tasks in `_memory/DANGLING_TASKS.md`, cron jobs in `cron/jobs.json`. The 432 MB `state.db` is not to be touched. |
| `iai-mcp-memory-server` | A local MCP memory server for coding assistants: verbatim recall, semantic search, automatic session capture, embedding migration, performance benchmarking. Relevant as prior art for anyone building memory: a text of the same problem, one layer down. |
| `browser`, `web-research-camoufox`, `agent-reach`, `universal-scraping-architect`, `reliable-automation` | Browser automation and web collection routers. |

## 6. Craft and deliverable skills

### antislop

Path `.agents/skills/antislop/SKILL.md`, with parts in `references/` (ui,
copywriting, people-and-accessibility, layout-mobile, code comments,
prose-editing). It is a **filter, not a style guide**: it prescribes no palette,
font or layout, and it bans nothing that serves a purpose. Two usage modes, and
the agent must ask the owner which one applies **before** UI work starts:

- **DURING** — the rules are applied while generating; the work ends with the
  delivery gate.
- **AFTER** — audit finished work: a numbered findings list in
  `anti-slop/audit-001-YYYY-MM-DD.md`, each finding citing the violated rule with
  a one-line reason, priority by rule tier (Hard Gate = HIGH, Purpose-Gate =
  MEDIUM, Quality Locks = LOW). Nothing is modified until the owner approves
  specific numbers.

The three rule tiers: **Hard Gate** (absolute, breaking one is a FAIL): no em
dash in UI text; mobile layout must be perfect (no overflow, 44px tap targets);
no statistic without a real source; no fabricated testimonial, avatar or name; no
asset (logo, photo, statistic, nav structure) invented without asking or an
honest labelled placeholder; no nav link to a section that does not exist; WCAG AA
contrast (4.5:1 normal, 3:1 large); every interactive element does something or is
removed; empty, loading and error states exist; no template FAQ; keyboard
navigation and a visible focus indicator; no feature added by an external script
string-replacing source or CSS; every shipped theme works; **verify before
delivering** (run the app, check the console, click through every control, and
attach the element-by-element click-through as evidence); no fabricated security,
compliance or performance claims; design direction required, or the output is
labelled "draft without direction" with honest default dials; real content or an
explicitly labelled placeholder. **Purpose-Gate** (allowed with a written reason,
banned as an unexamined default): gradients and colour schemes, icon choice,
typeface choice, background grids and patterns, decorative arrows, capsule
badges, glassmorphism (at most one or two elements), shadow, glow (at most two),
identical feature cards, template animation stacks, generic illustrations.
**Quality Locks**: no AI template layouts (hero plus three cards, always-three
steps, bento mosaics, fake terminal, three pricing columns, trust-logo bar,
four-column footer, uniform section rhythm); radius consistent with the system,
not everything pill-shaped; CTAs specific to the product, not "Get Started" or
"Learn More"; no marketing buzzwords; identity survives swapping the logo;
dark mode not forced without reason; at most two or three core colours plus one
accent; not a clone of a popular product; every major visual decision justified
in one line.

Liveliness is required, not optional: explicit ENERGY / RHYTHM / MOTION dials, a
declared Design Read, one focal point per screen, structural whitespace, one
deliberate accent, one identity motif. The delivery gate is a PASS/FAIL report
with one line per item and concrete evidence for every PASS; a report containing
a FAIL is never shipped.

### design

Craft, the counterpart of the filter: direction and brand language, layout and
information architecture, components and states, data on screen, flows and
accessibility, design systems. For an end-to-end pipeline (brand direction →
tokens → layout → components → states) start at `parts/dembrandt/`, the
orchestrator of the six ordered stages. If brand direction is missing, say so
rather than drifting to default taste, and offer to capture it in `DESIGN.md`.

### a11y-audit

WCAG 2.2 Level A and AA: scan (every violation, by severity), fix
(framework-specific before/after code for React, Next.js, Vue, Angular, Svelte or
plain HTML), verify (the fix resolves the violation and adds no regression),
report, and optional CI integration. Includes a colour-contrast checker against
AA and AAA ratios.

### docs-generator and documentation-writer

`docs-generator` writes task-oriented technical documentation with progressive
disclosure (READMEs, API docs, architecture docs) and doubles as the
end-of-task report generator. `documentation-writer` is Diátaxis: tutorials
(learning-oriented), how-to guides (problem-oriented), reference
(information-oriented), explanation (understanding-oriented), with an explicit
intent step and a structure proposal before writing.

### decks and demo-video

`decks` produces presentations, choosing the engine by the required end product:
real `.pptx` files, offline HTML decks editable in the browser and exportable,
markdown-to-slides, chart and report templates. `demo-video` produces demo videos
and walkthroughs by orchestrating browser rendering, text-to-speech and video
compositing, with documented fallbacks (HTML scenes plus a manifest and narration
scripts) when one of the tools is unavailable. Both matter for a competition
deliverable.

### ship

Delivering changes safely. Its rail: publishing, tagging and deploying are
separate authorizations; a part may prepare everything and must still stop before
the public action. Parts: release preparation, dependency audits, scoped
dependency updates, environment and secrets hygiene, VCS conventions and
worktrees, GitHub Actions, technical-change and technical-debt tracking,
operational runbooks.

## 7. How these skills map onto this project

What was actually used while building Oneiro-OSTIS, and what was not:

| area of the project | skill or method that governed it |
|---|---|
| Reading the four papers (PDF) | `documents` (its `parts/pdf/` toolkit) |
| The UI work on the dashboard | `antislop` (the owner invoked it explicitly; mode DURING) |
| Re-planning the project's direction | `planning` (plan up front, deviations are questions), `brainstorming` (design before implementation), `grill-me` (batched coverage questions) |
| Provider refusals, empty run directories, interrupted rounds | `sessions` (`parts/error-memory/`) as the pattern; in practice the facts were recorded in `docs/PROGRESS.md` and the round files |
| Believing or disbelieving an advertised tool or a provider claim | `tool-claims-verification` as the pattern |
| Deciding that a claimed improvement is real | **No skill covered this.** The project invented its own discipline inside `harness/rsi.py` and `docs/harness.md`: frozen acceptance criteria versioned per round, a coverage floor, mandatory online measurement for policies that change what the agent sees, at least three runs per task before any number is quoted, a control experiment with hand-written policies, and a ledger counting the runs the recordings saved. |
| Preparing deliverables for a jury | `decks`, `demo-video`, `docs-generator` (available, not yet used) |

The gap in that table is worth stating plainly: the strongest asset this project
built is a **measurement discipline** (the five criteria versions, the noise
floor, the control experiment, the ledger), and it is not a skill. It exists only
as code and as prose in one document. If this work is to be reused, that
discipline is the first candidate for the intake rule in `docs/Skills.md`.

## 8. The rest of the layer

Skills present in `.agents/skills/` that are not described above, listed so a
reader knows they exist and can open them on demand:

agent-reach, ai-copywriter, ai-image-prompts-skill, ai-prompting, autorun,
authentic-product-representation, cloudflare-deploy, codex-chat-dump,
content-delivery-format, contract-and-proposal-writer, desktop, dev,
domain-expert-configuration, email, explain-fingers, fable-domain,
fleet-manager, free-tool-strategy, freebuff-patch-check, gh-address-comments,
gh-fix-ci, godmode, google-signup-mobile, identity-federation, interview,
investigate-without-getting-made, jupyter-notebook, lsp-code-depth,
lyada-screenshot, no-agi-posts, nodumb, operational-expert-tool-ui, osint,
product-promise-contract, prompt-to-exe, proxy-provider-management,
reverse-api-engineer, reverse-engineering, rss-agent-viewer, ru-tts-fallback,
security, security-best-practices, security-ownership-map, security-review,
security-threat-model, speech, telegram-bot-hosting-triage, telegram-report,
telegram-rich-messages, tg-check, themes, tradingview-mcp, transcribe,
triage-route, vercel-deploy, vpn, workspace-setup, write-like-meng, youtube-full,
youtube-transcripts.

To find the right one, do not browse this list by eye: run the catalog query from
section 2 with 2-3 distinctive terms and read the winner's contract.
