# Oneiro Hybrid Architecture

Status: approved direction, first vertical slice in progress.

## Product direction

Oneiro is a long-lived autonomous agent that can work for days, survive process restarts, learn from its own experience, and keep a verifiable autobiographical record. The project is not another prompt or token optimizer. Its distinctive contribution is the OSTIS-native life record: time, provenance, confidence, consequences, and manual correction remain queryable as a graph.

## Reuse strategy

The project reuses the strongest existing runtime capabilities instead of rebuilding them:

- **OpenClaw** supplies the long-running shell: process lifecycle, scheduling, channels, permissions, and the starting UI language.
- **Hermes Agent** supplies the learning shell: experience-derived skills, learning-loop conventions, and self-improvement proposals.
- **Oneiro** supplies the integration contract and autobiographical memory: sessions, goals, actions, observations, outcomes, self-model entries, validity, provenance, and recovery after restart.

Both upstream projects are MIT-licensed at their main repositories. Their copyright and license notices remain required, and third-party notices, model licenses, provider terms, and MCP licenses remain separate obligations.

## Ownership and data flow

```text
OpenClaw adapter  ─┐
                   ├─> Oneiro Life API ─> OSTIS autobiographical graph
Hermes adapter     ─┘          │
                               ├─> recalled context for the next decision
                               ├─> learning proposals and skill candidates
                               └─> audit trail for every decision

OpenClaw UI <────────────────── read-only projection of the graph + live job state
```

State ownership is deliberately singular:

| Concern | Owner | Rule |
|---|---|---|
| Process, schedules, channels, permissions | OpenClaw runtime | Oneiro does not reimplement a gateway or scheduler |
| Learning proposals and reusable skills | Hermes learning adapter | A proposal is attributed to `origin=hermes` |
| Biography and durable state | Oneiro/OSTIS | Runtime databases are not treated as the project memory |
| Runtime event translation | Oneiro adapters | Adapters are thin and replaceable |
| UI projection | OpenClaw-derived frontend | It reads verified graph projections, not fabricated dashboard state |
| Code changes | isolated worktree | Human approval is required before applying to the main checkout |

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

1. Add session, goal, observation, self-state, origin, confidence, and validity concepts to the existing experience ontology.
2. Extend the Python bridge with explicit append-only session APIs.
3. Add a local life-runner that can execute a bounded self-task in an isolated worktree and record its lifecycle.
4. Add a Hermes adapter against verified local interfaces, not guessed imports.
5. Add an OpenClaw adapter against verified hooks or plugin surfaces.
6. Project the graph into the existing dashboard and then replace its visual shell with the adapted OpenClaw UI where useful.
7. Add long-running scheduling only after one restart-and-recovery run is green.

## Acceptance criteria for the first slice

- A session survives a full process restart through OSTIS.
- The recovered state includes at least one unfinished goal and one self-model claim.
- Every claim carries an origin and no model-originated claim is presented as human-confirmed.
- A self-edit is made only in an isolated worktree and its test result is recorded.
- A second run can explain its first action using a graph record created by the first run.
- Existing Stage 2–6 tests remain green.
- No push, automatic merge, secret mutation, deletion, or unverified runtime API is introduced.

## Deferred until the slice is proven

- Full OpenClaw UI replacement.
- Autonomous main-branch edits.
- Unbounded internet exploration.
- Automatic confidence promotion by the model.
- New token-efficiency or harness optimization rounds.
- Claims of general intelligence or unrestricted self-improvement.

## Known and unknown integration facts

Known: Hermes Agent is installed locally, exposes a Python package and CLI, and is MIT-licensed. Its installed CLI exposes `--worktree`, `journey`/`memory-graph`, `plugins`, and `dashboard`. Its verified plugin seam is `register(ctx)` with lifecycle hooks including `on_session_start`, `post_tool_call`, `on_session_end`, `on_session_finalize`, `pre_llm_call`, `post_llm_call`, and `pre_verify`. Known: OpenClaw runtime/source is present locally and is MIT-licensed at its main repository. Known: Oneiro already has a live OSTIS bridge and dashboard.

Unknown until verified against the installed versions: the exact OpenClaw plugin/event API and whether its UI can be reused without depending on private internals. The Hermes adapter can be built against the verified plugin seam; the OpenClaw adapter must resolve its actual hook or ACP contract before importing or calling it.
