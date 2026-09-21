# oneiro-life — the OpenClaw plugin

The gateway is the long-life host: it stays up, so the organization can live
inside it. This plugin gives the gateway two things and nothing else:

- a **service** (`oneiro-life`) that records its own start and stop;
- two **gateway lifecycle hooks** (`gateway_start`, `gateway_stop`) that
  record the gateway's own life into OSTIS.

## How it records, and why installing needs a flag

Records are written by Python, as everywhere else in the project. The plugin
runs the recorder next to this file (`record.py`) through `execFile` with an
argument array, never a shell string; a test asserts the exact argv.

OpenClaw's install scan flags any plugin that spawns processes:

```
WARNING: Plugin "oneiro-life" contains dangerous code patterns:
Shell command execution detected (child_process)
```

That guardrail is the host's and stays intact. The host also ships the
acknowledgment for it, so the plugin installs with:

```bash
openclaw --dev plugins install --link --dangerously-force-unsafe-install \
  projects/ostis/oneiro-ostis/plugins/oneiro-life
```

The flag covers this one install; nothing in OpenClaw's own code is patched
and no other code runs with that permission.

## Enable it (isolated dev profile only)

```bash
openclaw --dev plugins install --link --dangerously-force-unsafe-install \
  projects/ostis/oneiro-ostis/plugins/oneiro-life
openclaw --dev plugins enable oneiro-life
openclaw --dev plugins inspect oneiro-life --runtime --json
```

The owner's live installation is never touched: `--dev` keeps state in
`~/.openclaw-dev` and moves the gateway to port 19001.

## Configuration

Settings live under `plugins.entries.oneiro-life.config` in the dev profile's
`openclaw.json`. All keys have working defaults.

| Key | Default | Meaning |
|---|---|---|
| `pythonPath` | `python` | Interpreter that runs the recorder. |
| `sessionId` | `oneiro-gateway` | Session id the gateway's own records carry. |
| `ostisPort` | `8090` | Port of the sc-machine the recorder connects to. |

## What lands in OSTIS

Each entry is one organization record with `origin=rule` and `verified=true`,
so a reader can tell machine-enforced facts from model-authored ones:
`gateway_start`, `gateway_stop`, `gateway_service_start`,
`gateway_service_stop`.

## Manual recorder

`record.py` writes one record straight through the bridge, for use from a
shell:

```bash
python plugins/oneiro-life/record.py --kind gateway_start --payload '{"port": 19001}'
```
