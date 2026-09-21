# oneiro-life — the OpenClaw plugin

The gateway is the long-life host: it stays up, so the organization can live
inside it. This plugin gives the gateway two things and nothing else:

- a **service** (`oneiro-life`) that supervises the life process: starts it,
  restarts it after a crash (bounded: 5 s, 30 s, 120 s, then gives up and
  records why), and stops it cleanly when the gateway stops;
- two **gateway lifecycle hooks** (`gateway_start`, `gateway_stop`) that
  record the gateway's own life into OSTIS.

The graph is written by Python only. The plugin shells out to `record.py`,
which uses the project's bridge; Node never speaks to the SC machine directly.

## Enable it (isolated dev profile only)

```bash
openclaw --dev plugins install --link projects/ostis/oneiro-ostis/plugins/oneiro-life --force
openclaw --dev plugins enable oneiro-life
openclaw --dev plugins inspect oneiro-life --runtime --json
```

The owner's live installation is never touched: `--dev` keeps state in
`~/.openclaw-dev` and moves the gateway to port 19001.

## Configuration

Settings live under `plugins.entries.oneiro-life.config` in the dev profile's
`openclaw.json`. Every key has a working default, so enabling the plugin with
no config is valid.

| Key | Default | Meaning |
|---|---|---|
| `autostart` | `false` | Start the life process with the gateway. Off by default: one swarm run at a time is the owner's call, not a side effect of booting a gateway. |
| `projectDir` | the project this plugin ships in | Where `python/life_loop.py` lives. |
| `pythonPath` | `python` | Python used for the recorder and the life process. |
| `cycles` / `intervalSeconds` | `2` / `60` | Passed straight to `life_loop.py`. |
| `host` / `port` | `localhost` / `8090` | OSTIS machine for the bridge. |
| `sessionId` | `oneiro-gateway` | Session id the gateway's own records carry. |

## What lands in OSTIS

Each entry is one organization record with `origin=rule` and `verified=true`,
so a reader can tell machine-enforced facts from model-authored ones:

`gateway_service_start`, `gateway_service_stop`, `gateway_start`,
`gateway_stop`, and, when supervision is on, `life_process_finished` /
`life_process_exit` / `life_process_restart` / `life_process_gave_up`.

## Supervised run logs

The service writes the life process's own output to
`<stateDir>/logs/oneiro-life-<run_tag>.log` (state dir is the dev profile's).
The plugin never rewrites project files and never merges, pushes, or approves
anything: an unmerged PR packet stays a human decision.
