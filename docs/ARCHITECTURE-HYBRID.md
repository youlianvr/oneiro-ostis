# Oneiro Hybrid Architecture

Status: approved direction, first swarm vertical slice in planning.

## Product direction

Oneiro is a long-lived autonomous organization rather than a single general-purpose agent. A small set of persistent agents lives through repeated heartbeat cycles, shares a typed autobiographical graph, proposes and executes work, and accumulates skills that change later behaviour. The organization speaks to the owner through one manager. Every code change ends as a reviewable PR, never as an autonomous merge.

The research claim is deliberately narrow: a persistent graph organization can turn experience into verifiable, transferable skills while preserving who proposed a change, why it was accepted internally, what evidence supports it, and which human decision allowed it into the main line. The project is not another prompt or token optimizer.

## Prior art and boundary of novelty

The closest systems establish that persistent multi-agent life is a meaningful research direction, but they optimize different objects:

- **Project Sid** studies societies from 10 to 1,000+ agents, specialization, collective rules, and cultural transmission in simulated worlds. It is a society-scale simulation, not a governed software organization whose changes pass through human PR review.
- **Agent Hospital** evolves medical agents through repeated simulated cases and reports transfer to MedQA. It provides a strong precedent for experience-driven skill improvement, but the environment and roles are domain-specific and the durable organizational history is not an OSTIS-native, provenance-first biography.
- **AgentVerse** and related multi-agent frameworks show that specialized teams can outperform a single agent on selected tasks. Their central object is task completion, not long-lived role identities with a manager-controlled escalation protocol.
- **Anthropic's Research system** demonstrates an orchestrator-worker architecture and parallel research. It explicitly reports high token consumption and focuses on one research request, not a persistent organization that lives between tasks.
- **Emergence World** studies weeks-long populations, social drift, governance, energy pressure, and cross-model contamination. It is the strongest precedent for long-horizon society research. Oneiro differs by making the organization itself the work object, with auditable skill evolution and a human-owned PR gate instead of an open social world.

Therefore Oneiro must not claim novelty for "multiple agents," "persistent memory," or "agents that write code" separately. Its testable contribution is the combination of persistent role identities, OSTIS-native event and decision provenance, manager-mediated escalation, external review as a separate model context, and skill transfer demonstrated on held-out work before a human accepts the PR.

## Product boundary

The first organization is a three-role company:

| Role | Responsibility | Direct owner contact | Can modify main checkout |
|---|---|---:|---:|
| Researcher | Find problems, investigate evidence, formulate proposals | No | No |
| Manager / critic | Prioritize proposals, reject waste, request external review, escalate important decisions, prepare PR review packets | Yes | No |
| Worker | Implement an approved proposal in an isolated branch/worktree and run checks | No | No |

The manager is not a second owner and cannot accept its own work. "Self-judgement" means an internal review against the recorded project criteria. "External expert" means a separate, more capable model with independent context. "Escalation" means a message to the owner for architecture, risk, or a ready PR.

## Reuse strategy

The project reuses the strongest existing runtime capabilities instead of rebuilding them:

- **OpenClaw** supplies the long-running shell: process lifecycle, scheduling, channels, permissions, and the starting UI language.
- **Hermes Agent** supplies the learning shell: experience-derived skills, learning-loop conventions, and self-improvement proposals.
- **Oneiro** supplies the integration contract and autobiographical memory: sessions, goals, actions, observations, outcomes, self-model entries, validity, provenance, and recovery after restart.

Both upstream projects are MIT-licensed at their main repositories. Their copyright and license notices remain required, and third-party notices, model licenses, provider terms, and MCP licenses remain separate obligations.

## Ownership and data flow

```text
OpenClaw / Hermes heartbeat
            │
            ▼
       Oneiro coordinator
       ├─ researcher ── proposals / evidence
       ├─ manager ───── decisions / escalation / PR packet
       └─ worker ────── branch / tests / skill candidate
            │
            ▼
 OSTIS organization graph
 sessions · messages · tasks · decisions · skills · PR evidence
            │
            ├─ external expert adapter (independent context)
            ├─ owner channel (manager only)
            └─ read-only UI projection
```

A heartbeat is a bounded work cycle, not permission to run forever without accounting. Each cycle has a session id, role identity, budget, current task, emitted events, and an explicit next wake-up. The long-lived process may continue, but every unit remains replayable and stoppable.

State ownership is deliberately singular:

| Concern | Owner | Rule |
|---|---|---|
| Process, schedules, channels, permissions | OpenClaw runtime | Oneiro does not reimplement a gateway or scheduler |
| Learning proposals and reusable skills | Hermes learning adapter | A proposal is attributed to `origin=hermes` |
| Organization state and durable biography | Oneiro/OSTIS | Runtime databases are not treated as the project memory |
| Role orchestration and budgets | Oneiro coordinator | The coordinator owns leases, role handoffs, cycle limits, and stop reasons |
| Runtime event translation | Oneiro adapters | Adapters are thin and replaceable |
| External expert judgement | Separate model adapter | Independent context, no hidden access to the team's private deliberation unless explicitly included |
| Owner communication | Manager only | Researcher and worker cannot send owner-facing messages |
| UI projection | OpenClaw-derived frontend | It reads verified graph projections, not fabricated dashboard state |
| Code changes | isolated branch/worktree | Human approval is required before applying to the main checkout |

## Memory record model

Every durable record is a typed graph node or relation with:

- session and event identifiers;
- creation time and validity window;
- source/origin: `model`, `hermes`, `openclaw`, `tool`, `human`, `rule`, or `experiment`;
- confidence and verification state;
- causal links to the action and its result;
- optional manual correction without erasing the earlier record.

A model may write immediately, but its record remains visibly model-originated. The model cannot silently raise its confidence, close a contradiction, or delete history. Rules and a human may confirm, downgrade, close, or cancel a record.

## First vertical slice

The first slice is intentionally CLI-first. It must prove the core life cycle before UI work:

1. Start a session with an explicit session id.
2. Read the latest self-state and unfinished goals from OSTIS.
3. Give the agent one local, self-directed task in the Oneiro repository.
4. Allow changes only in an isolated working copy.
5. Run the declared tests and record the result.
6. Record the session summary, decisions, attempted changes, and self-model update in OSTIS.
7. Stop the process completely.
8. Start a new process and recover the previous state from OSTIS, not Python memory or a local JSON cache.
9. Produce a plain audit trail answering: what was remembered, what was attempted, what changed, and why the next action was chosen.

The first self-directed task may modify only the agent's own project code and must not push, merge, touch secrets, or mutate Hermes `state.db`, `.env`, or `auth.json`.

## Integration order

1. Add organization concepts to the existing experience ontology: role, heartbeat, proposal, task lease, message, decision, escalation, skill candidate, validation run, branch, PR, and review verdict.
2. Extend the Python bridge with append-only APIs for organization events and manager-only owner messages.
3. Add a bounded coordinator that runs the three persistent roles through one heartbeat and records every handoff.
4. Add the worker's isolated branch/worktree runner and produce a PR packet without merge rights.
5. Add skill validation: a candidate must change behaviour on held-out work, not merely create a file.
6. Add an external-expert adapter with independent context and explicit cost, timeout, and disagreement records.
7. Connect the verified Hermes plugin seam and then the verified OpenClaw lifecycle seam.
8. Project the organization graph into the dashboard and add the OpenClaw-derived UI only after the graph tells a complete story.
9. Run the long-lived heartbeat only after bounded replay and restart tests are green.

## Acceptance criteria for the first slice

- A session survives a full process restart through OSTIS.
- The recovered state includes at least one unfinished goal and one self-model claim.
- Every claim carries an origin and no model-originated claim is presented as human-confirmed.
- A self-edit is made only in an isolated worktree and its test result is recorded.
- A second run can explain its first action using a graph record created by the first run.
- Existing Stage 2–6 tests remain green.
- No push, automatic merge, secret mutation, deletion, or unverified runtime API is introduced.

## Skill acceptance contract

A skill candidate is accepted as learned only when all of these are present:

1. a versioned artifact with role, scope, prerequisites, limits, and origin;
2. a source episode showing the failure or repeated pattern that motivated it;
3. a validation run on work not used to propose the skill;
4. an observed behavioural change attributable to the skill;
5. a manager decision explaining why it is useful and what alternatives were rejected;
6. a PR packet with diff, tests, validation evidence, and risk statement;
7. owner approval before merge.

A generated skill file without transferred behaviour is a proposal, not learning.

## Deferred until the slice is proven

- Full OpenClaw UI replacement.
- Autonomous main-branch edits or merges.
- Unbounded internet exploration.
- Automatic confidence promotion by the model.
- New token-efficiency or harness optimization rounds.
- Claims of general intelligence, civilization, or unrestricted self-improvement.

## Known and unknown integration facts

Known: Hermes Agent is installed locally, exposes a Python package and CLI, and is MIT-licensed. Its installed CLI exposes `--worktree`, `journey`/`memory-graph`, `plugins`, and `dashboard`. Its verified plugin seam is `register(ctx)` with lifecycle hooks including `on_session_start`, `post_tool_call`, `on_session_end`, `on_session_finalize`, `pre_llm_call`, `post_llm_call`, and `pre_verify`. Known: OpenClaw runtime/source is present locally and is MIT-licensed at its main repository. Known: Oneiro already has a live OSTIS bridge and dashboard. Prior-art sources checked for this revision: Project Sid (arXiv:2411.00114), Agent Hospital (arXiv:2405.02957), Anthropic's multi-agent research system, and Emergence World (2026 platform description). AgentVerse was found but its OpenReview page was browser-gated during this pass, so no detailed claim is made here.

Unknown until verified against the installed versions: the exact OpenClaw plugin/event API and whether its UI can be reused without depending on private internals. The Hermes adapter can be built against the verified plugin seam; the OpenClaw adapter must resolve its actual hook or ACP contract before importing or calling it.
