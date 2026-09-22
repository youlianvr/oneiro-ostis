# Goal: a live swarm (night run, 2026-09-21)

> Owner verdict, recorded in chat before an overnight autonomous run.
> This file is the contract for the night: what must exist by morning,
> what was decided, what is explicitly out of scope.

## The goal

By morning Oneiro must be a **living organization**, not a protocol:

1. Three roles call real models through the local OmniRoute proxy:
   **researcher** and **worker** on `auto/coding`,
   **manager** on `main`. When the proxy misbehaves, the
   automatic fallback is `auto/coding:reliable`; anything beyond that is
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

### The journal effect (`live4`, after `91f4a20d9`)

The dossier now carries the organization's own journal (the last 14 journal
lines read from OSTIS, across lives), and tells the researcher not to propose
what the journal already shows. What actually happened:

- the researcher still listed the old marker fix as its first option, so a
  paragraph of instruction does not by itself stop a small model from
  repeating itself;
- the journal changed the **decision**: the manager picked the second option,
  "add a test that the heartbeat continues the biography after a restart",
  citing the night goal's own open item, and the worker delivered it
  (`pr-live-live4-a050037-c1`, 49 lines in `tests/test_heartbeat.py`, check
  passed, unmerged). The swarm's first work item that no earlier cycle had
  produced.
- cycle two did not complete, and the record says exactly why: the provider
  answered `HTTP 524` for the manager's model after four attempts, the
  fallback model returned no JSON twice, and the cycle was skipped as
  `cycle_schema_error` with no freeze and no crash (`cycles_done: 1`,
  `status: finished`, `freeze_reason: null`).

Conclusion to carry forward: deduplication needs a mechanical guard (refuse
or re-rank an option whose subject an earlier PR packet already delivered),
not only an instruction in the dossier. That guard is the next step, and it
is a design choice the owner should shape.

### The OpenClaw host: the block and the host's own key

The approved plan had the plugin's service spawning the recorder process.
OpenClaw's install scan refused it:

```
WARNING: Plugin "oneiro-life" contains dangerous code patterns:
Shell command execution detected (child_process)
Plugin "oneiro-life" installation blocked: dangerous code patterns detected
```

Night fallback: records went over loopback HTTP to the project dashboard
(`POST /api/gateway-record`) and the plugin spawned nothing.

Morning verdict (owner): do not live with the limitation, and do not patch
OpenClaw; use the acknowledgment the host itself ships:

```
openclaw plugins install --dangerously-force-unsafe-install <path>
```

The plan's shape is back and the fallback is gone: the plugin runs `record.py`
through `execFile` with an argument array (never a shell string), Python stays
the only writer of the graph, and the dashboard endpoint was removed. The
host's own code is untouched: the flag covers this one install.

Verified live: `plugins list` shows `Oneiro Life / oneiro-life / loaded` with
the recorder path, the dev gateway boot left `gateway_service_start` (state
dir, project dir) and `gateway_start` (port 19001) records in OSTIS with
`origin=rule, verified=true`, and `tests/test_gateway_plugin.py` asserts the
exact argv through node.

Still open: graceful-stop records. Stopping an unmanaged gateway kills the
process before its shutdown path runs, so no `gateway_stop` or
`gateway_service_stop` record appeared. That needs the gateway installed as a
managed service (`openclaw gateway install` creates a Windows scheduled task),
which is the owner's decision.

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
  `agent/live-live3-a041541-c1` and `agent/live-live4-a050037-c1` hold the real
  changes (the last one adds the restart-continuity test);
  `agent/live-live1-c1` holds the broken stub that exposed the missing edit
  tool, and `agent/live-live3-c1` holds a partial edit from the killed
  attempt. None of them is merged, pushed, or deleted.
- Decide whether the life loop should run continuously (OpenClaw cron, or
  plugin supervision once the host offers a blessed process surface).

## Morning verdicts (owner, 2026-09-21)

Three decisions settled at the start of the day; the rest stay open.

- **Two live packets merged.** The restart-continuity test and the named
  marker list came onto master by cherry-pick (`ae52fe869`, `70572d02e`); the
  offline suite is 84 passing. The draft marker fix, the broken stub and the
  interrupted attempt stay unmerged branches.
- **Packets live as branches, working copies are gone.** Every uncommitted
  change in the eight run worktrees was committed into its own branch first
  (`agent/heartbeat-20260921014748`, `agent/heartbeat-proof-20260921020147`,
  `agent/live-live1-c1`, `agent/live-live2-c1`, `agent/live-live2-c2`,
  `agent/live-live3-a041541-c1`, `agent/live-live3-c1`,
  `agent/live-live4-a050037-c1`), then the working copies went to the Recycle
  Bin (`_scripts/trash.sh`) and the worktree metadata was pruned. Nothing was
  destroyed; the branches hold every change.
- **The duplicate gate is hard and graph-checked.** A candidate whose essence
  matches work already delivered is refused before the manager sees it, and the
  refusal is recorded in OSTIS. The check reads the graph's own record of past
  proposals and packets, not only the current session's journal.
- **The swarm keeps running by hand.** No schedule, no service, no plugin
  supervision for now; a run starts on the owner's word.

Still open for the owner: the next stage's target. Settled later the same
morning: the two live packets were merged (see below) and the OpenClaw plugin
came back to spawning the recorder (see "the host's own key").

## Evidence trail

Every cycle writes to OSTIS with `origin` and `verified`: model-authored
records carry the role that produced them (`origin=researcher|manager|worker`)
and stay unverified; system-enforced records carry `origin=rule` and are
marked verified. The morning report quotes these records, the run logs, and
the tests; nothing is claimed without one of the three.
