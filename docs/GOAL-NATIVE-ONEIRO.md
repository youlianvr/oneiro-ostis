# Native Oneiro — global delivery goal

Status: implementation in progress, replacing the product control plane on `v2`.
This document supersedes the old rigid product-loop decisions in PLAN-V2 and
ARCHITECTURE-HYBRID. The research/replay experiments and their evidence remain valid.

## Goal

Deliver a coherent, persistent personal assistant which the owner can actually
use: a configurable manager as the conversational counterpart, an independent
researcher and executor, proactive work, OSTIS memory and enforced permissions.
CowAgent, Hermes and OpenClaw are not the product's control plane. Reusable
libraries, protocols and external tools are welcome when they fit seamlessly.
Implementation proceeds without repeated requests to continue. Missing credentials
and unavailable infrastructure must be reported, never replaced by claimed success.

## Owner decisions

- Priority: a continuously living, proactive personal assistant; both technical
  work and everyday assistance. Research initially, useful product eventually.
- No mandatory researcher -> manager -> executor ceremony on every message.
- Three configurable personalities, maintained in individual SOUL.md profiles.
  A personality is a behavioural configuration, not a claim of consciousness.
- Manager talks, reads, plans, delegates and arbitrates; does not write code.
- Researcher can read anything, research the web, maintain personal notes and
  share findings; cannot install programs or modify working projects.
- Executor works within its task, may read documentation directly, reports
  objections and unexpected consequences. Permanent role boundaries cannot be
  relaxed by a prompt, a SOUL change or the manager's insistence.
- Each role owns its memory and may freely read the other roles' memory.
  Research does not require permission from the manager or immediate reporting.
- Interests can emerge from discoveries or unfinished work. Independent interest
  exploration is configurable. Owner pain points may also motivate research.
- Manager can revise a plan, escalate consequences or insist within the owner's
  authorised scope. Confirmed destructive instructions should be executable,
  not silently vetoed for lack of a backup.
- Internet requests, reading private sources and registration are possible;
  no unsolicited messages, publication, private-repository exposure, diagnostic
  uploads or local-data transfer. Remote LLM context and VirusTotal file uploads
  are explicit exceptions. Antivirus results are not proof of safety.
- Configuration changes need separate permission. Autostart is unwanted.
  Applying changes to an external/working database requires a button confirmation;
  this does not mean confirming every write to Oneiro's own autobiographical graph.
- A direct instruction can authorise its specified action, not unrelated side
  effects. Pending decisions pause dependent work, not the entire system.
- Language is not fixed here.

## Target architecture

```text
Native web / Telegram
          |
Conversation + task service / initiative scheduler
          |
Manager | Researcher | Executor (one model/tool runtime, distinct profiles)
          |
Trusted tool registry -> role gate -> effect gate -> exact approval -> handler
          |
OSTIS event memory + semantic relations / local artifacts
```

One process owns coordination. Channels translate inputs and deliver outputs;
they do not have their own agent, task queue or approval truth. A reviewed tool
registry, not tool-name heuristics, determines effects. Unrestricted host shell
and unreviewed MCP tools must not bypass policy. Risky execution belongs in a
network-disabled container, not a git worktree masquerading as a sandbox.

OSTIS is required for durable operation. No silent flat-file/SQLite replacement
when the graph is unavailable. A test-only in-memory adapter exercises contracts.
The first migration preserves existing graph records and research code; normal
startup must never rebuild an existing graph with `--clear`.

## Acceptance and verification

- Casual chat does not automatically create a coding task.
- Delegation is optional and produces recoverable, independently scheduled tasks.
- Tool effects and actual outcomes are recorded; claims do not substitute for tools.
- An exact pending action survives restart; only the authenticated owner's button
  releases sensitive effects. Text replies remain conversation, not rejection.
- Role restrictions are enforced in the dispatcher as well as tool schemas.
- SOUL is editable without changing capability restrictions.
- Initiative has an opt-in, interval and bounded call budgets; waiting tasks do
  not stop research or conversation. No fixed briefing masquerades as personality.
- UI, Telegram and scheduler consume the same service and memory.
- Missing model, graph, sandbox or API keys are visible and prevent affected work.
- Offline tests cover policy, replay/recovery, channels and native conversation.
  Live integrations are only labelled verified after real calls succeed.

## Migration boundaries

Legacy launcher, installer, console overlay and research panel remain available
for existing installations, but are no longer prerequisites of the native entrypoint.
Delete or archive legacy product paths only after equivalent native scenarios and
migration checks pass. Do not discard existing owner data or scientific results.

## Known external prerequisites

This workspace currently has no Docker binary, OSTIS Python dependencies, pytest
or configured environment keys. Native offline tests will use stdlib unittest.
A live OSTIS + LLM + Telegram + VirusTotal test cannot be claimed until the actual
services/credentials exist. The managed Node-only static hosting is not a host for
this local Python/Docker product.
