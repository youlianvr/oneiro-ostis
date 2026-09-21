# Goal: a live swarm (night run, 2026-09-21)

> Owner verdict, recorded in chat before an overnight autonomous run.
> This file is the contract for the night: what must exist by morning,
> what was decided, what is explicitly out of scope.

## The goal

By morning Oneiro must be a **living organization**, not a protocol:

1. Three roles call real models through the `dahl` provider:
   **researcher** and **worker** on `deepseek-ai/DeepSeek-V4-Flash-0731`,
   **manager** on `zai-org/GLM-5.3-Flash`. When the provider misbehaves, the
   automatic fallback is `MiniMaxAI/MiniMax-M2.7`; anything beyond that is
   recorded, not improvised.
2. The heartbeat runs as **cycles and survives restarts**: stopping the
   process and starting it again continues the biography from OSTIS instead
   of silently beginning a new one.
3. At least one cycle produces a **real PR packet** from an isolated worktree:
   files changed, checks run, `merged=false`, `owner_approved=false`.
   Merging is the owner's decision and stays outside this run.
4. The first work item is a **real weakness of Oneiro itself**, proposed by
   the researcher, chosen by the manager, executed by the worker.

## OpenClaw is the long-life host (owner verdict: reverse it, use it)

The owner chose to spend part of the night reversing OpenClaw rather than
building our own scheduler. Verdict from the installed package (2026.4.21):

- seams that exist and are documented: `definePluginEntry` with
  `registerService` (a long-lived in-process service with start/stop),
  typed hooks via `api.on(...)`, internal hooks via `api.registerHook(...)`
  for coarse events (`session:*`), `registerCommand`, `registerGatewayMethod`,
  `registerHttpRoute`;
- the bundled `diagnostics-otel` extension is a working example of
  `api.registerService(...)`;
- profile isolation is built in: `--dev` keeps state under `~/.openclaw-dev`
  and shifts the gateway to port 19001, so the owner's live installation is
  never touched.

Consequence for this night: Oneiro ships an OpenClaw plugin (`oneiro-life`)
whose **service supervises the life process** (start, restart on crash,
clean stop on gateway shutdown) and whose **hooks record OpenClaw session
lifecycle into OSTIS**. The isolated dev profile is the only instance used.

## Decisions carried from the chat

- **Models per role**: manager `zai-org/GLM-5.3-Flash`; researcher and worker
  `deepseek-ai/DeepSeek-V4-Flash-0731`; automatic fallback `MiniMaxAI/MiniMax-M2.7`;
  if the whole provider is down, the cycle freezes with the reason recorded.
- **First work**: a real Oneiro weakness. The researcher reads the project
  dossier and proposes 2-4 options; the manager picks exactly one with
  acceptance criteria.
- **Budget and failure**: per-cycle caps on model calls and wall time; 429
  and provider hiccups get bounded retries with backoff; after the bounded
  retries the cycle freezes with the reason in OSTIS and the run continues
  with non-model work.
- **Push**: none tonight. Local commits per unit only.
- **Trust boundary**: the worker changes live only inside an isolated
  worktree on an unmerged branch; `main`/`master` are never touched; no
  push, no merge, no approval; the check commands come from a fixed
  allowlist, never from free-form model output.

## Exit criteria (checkable in the morning)

- [ ] `life_loop.py` completes at least two cycles and stops cleanly.
- [ ] A kill during the run, then a restart, resumes the biography from
      OSTIS (restart visible as a record, no silent duplicate work).
- [ ] At least one PR packet with passing checks, `merged=false`,
      `owner_approved=false`, and a real worktree path.
- [ ] The OpenClaw dev gateway boots with the `oneiro-life` plugin loaded
      (`plugins inspect` shows the service and hooks), and OSTIS contains the
      gateway lifecycle records the plugin wrote.
- [ ] The dashboard shows the organization feed: roles, proposals, decision,
      PR packet, freeze reasons, in Russian.
- [ ] All units committed locally; no push.

## Out of scope tonight (deliberately)

- Merging, pushing, approving anything.
- A Telegram channel for the manager, Control UI pages, memory-capability
  registration: these are next steps, not promises.
- Any claim that a learned skill transfers or that the graph beats a flat
  file: that measurement stays on the memory line's own plan.

## Evidence trail

Every cycle writes to OSTIS with `origin` and `verified`: what the models
produced (`origin=model`), what the system enforced (`origin=rule`), what the
worker did (`origin=worker`). The morning report quotes these records, the
run logs, and the tests; nothing is claimed without one of the three.
