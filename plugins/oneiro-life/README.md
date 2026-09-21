# oneiro-life — the OpenClaw plugin

The gateway is the long-life host: it stays up, so the organization can live
inside it. This plugin gives the gateway two things and nothing else:

- a **service** (`oneiro-life`) that records its own start and stop;
- two **gateway lifecycle hooks** (`gateway_start`, `gateway_stop`) that
  record the gateway's own life into OSTIS.

## Why it records over HTTP instead of spawning Python

The first version of this plugin spawned the life process and shelled out to a
Python recorder. OpenClaw's install scan refused it:

```
WARNING: Plugin "oneiro-life" contains dangerous code patterns:
Shell command execution detected (child_process)
Plugin "oneiro-life" installation blocked: dangerous code patterns detected
```

That guardrail is the host's, and it is a good one, so the design moved to the
host's terms:

- the plugin posts records over **loopback HTTP** to the project dashboard
  (`POST http://127.0.0.1:8130/api/gateway-record`), which owns the bridge;
- the graph is still written by Python only;
- the plugin spawns nothing, so it installs without an acknowledgment;
- the endpoint accepts an allowlist of lifecycle kinds and a small JSON body,
  and the dashboard listens on loopback only.

Running the life process is therefore the host's job, not the plugin's: start
it manually, from a scheduler, or from OpenClaw's own cron once that wiring is
chosen. Supervision inside the plugin is deliberately out until the host
offers a blessed process surface.

## Enable it (isolated dev profile only)

```bash
openclaw --dev plugins install --link projects/ostis/oneiro-ostis/plugins/oneiro-life
openclaw --dev plugins enable oneiro-life
openclaw --dev plugins inspect oneiro-life --runtime --json
```

The owner's live installation is never touched: `--dev` keeps state in
`~/.openclaw-dev` and moves the gateway to port 19001.

## Configuration

Settings live under `plugins.entries.oneiro-life.config` in the dev profile's
`openclaw.json`. Both keys have working defaults.

| Key | Default | Meaning |
|---|---|---|
| `dashboardUrl` | `http://127.0.0.1:8130` | The dashboard that owns the bridge. |
| `sessionId` | `oneiro-gateway` | Session id the gateway's own records carry. |

## What lands in OSTIS

Each entry is one organization record with `origin=rule` and `verified=true`,
so a reader can tell machine-enforced facts from model-authored ones:

`gateway_start`, `gateway_stop`, `gateway_service_start`, `gateway_service_stop`
(and the `life_process_*` kinds the endpoint also accepts, for whoever runs
the loop).

## Manual recorder

`record.py` writes one record straight through the bridge, for use from a
shell when the dashboard is not running:

```bash
python plugins/oneiro-life/record.py --kind gateway_start --payload '{"port": 19001}'
```
