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

## Night log (2026-09-21, agent run)

### What the runs left behind

- **`live2`**: two cycles, two PR packets, `status=finished`, no freeze.
  `pr-live-live2-c1` and `pr-live-live2-c2`, both `merged=false`,
  `owner_approved=false`, worker `done` after 12 and 14 steps. Both cycles
  converged on the same weakness (the dossier's TODO/FIXME scan matching its
  own code). That is a real observation, not a bug in the loop: the
  researcher has no memory of what earlier cycles already proposed.
- **`live3`**: killed mid-heartbeat on purpose, then restarted with the same
  run tag. The biography recorded `process_restart`, the journal recorded
  `loop_resumed`, and the restarted cycle produced
  `pr-live-live3-a041541-c1` (two changed paths) without colliding with the
  worktree the killed attempt had left on disk.
- The first live attempt (`live1`) failed because the worker had no way to
  edit a large file: `read_file` returned numbered text clipped at 6000
  chars and `write_file` replaced whole files, so the model stubbed a
  430-line module down to 15 lines. Fixed in `9fb40f674`: `replace_in_file`,
  plain-text windowed reads, a shrink guard, and a bounded finish window.
- `0473db98c` gave every attempt its own worktree, branch, and PR id. That
  is what made the `live3` restart work while the debris of the killed
  attempt was still on disk.

### The OpenClaw host: one deviation, recorded

The approved plan had the plugin's service spawning and supervising the life
process. OpenClaw's install scan refused it:

```
WARNING: Plugin "oneiro-life" contains dangerous code patterns:
Shell command execution detected (child_process)
Plugin "oneiro-life" installation blocked: dangerous code patterns detected
```

Deviation, with the reason: the plugin now records over loopback HTTP to the
project dashboard (`POST /api/gateway-record`, allowlisted kinds, small
bodies); the graph stays written by Python only and the plugin spawns
nothing. Verified live: `openclaw --dev plugins inspect oneiro-life` shows
`Status: loaded`, typed hooks `gateway_start` and `gateway_stop`, service
`oneiro-life`; the gateway boot left `gateway_service_start` and
`gateway_start` (port 19001) records in OSTIS with `origin=rule`.

Still open: graceful-stop records. Stopping an unmanaged gateway kills the
process before its shutdown path runs, so no `gateway_stop` or
`gateway_service_stop` record appeared. Verifying that needs the gateway
installed as a managed service (`openclaw gateway install` creates a Windows
scheduled task), which is the owner's decision, not the agent's.

### Exit criteria, checked

- [x] `life_loop.py` completes at least two cycles and stops cleanly (`live2`).
- [x] A kill during the run, then a restart, resumes the biography from OSTIS
      (`live3`: `process_restart` plus `loop_resumed`).
- [x] PR packets with passing checks, `merged=false`, `owner_approved=false`,
      and real worktree paths (three of them).
- [x] The dev gateway boots with `oneiro-life` loaded, and OSTIS holds the
      gateway lifecycle records the plugin wrote.
- [x] The dashboard shows the organization feed (`/api/swarm`; verified in
      the running page: 53 rows, no console errors).
- [x] All units committed locally; no push.

### Artifacts and open items for the owner

- Branches awaiting a verdict (worktrees under `~/.openclaw/worktrees/`):
  `agent/live-live2-c1`, `agent/live-live2-c2`,
  `agent/live-live3-a041541-c1` hold the real changes;
  `agent/live-live1-c1` holds the broken stub that exposed the missing edit
  tool, and `agent/live-live3-c1` holds a partial edit from the killed
  attempt. None of them is merged, pushed, or deleted.
- Decide whether the life loop should run continuously (OpenClaw cron, or
  plugin supervision once the host offers a blessed process surface).

## Evidence trail

Every cycle writes to OSTIS with `origin` and `verified`: model-authored
records carry the role that produced them (`origin=researcher|manager|worker`)
and stay unverified; system-enforced records carry `origin=rule` and are
marked verified. The morning report quotes these records, the run logs, and
the tests; nothing is claimed without one of the three.
