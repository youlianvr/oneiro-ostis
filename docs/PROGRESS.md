# PROGRESS

## 2026-09-17

- Repo created: `youlianvr/oneiro-ostis` (private; subtree-push per projects/README.md rule).
- `.gitignore` workspace updated: `/projects/ostis/*` with `!/projects/ostis/oneiro-ostis/` — vendor stack stays out, project tracked.
- Old `consciousness-research-*.md` plans moved to `projects/ostis/_archive/` (superseded, kept).
- PLAN.md and README.md written.

## 2026-09-18

- Stage 1 stack work (owner confirmed network was the blocker: VPN throttled docker.io to ~10 KB/s; switched off):
  - Measured direct docker.io at ~12 KB/s even after VPN off; `mirror.gcr.io` fast for `library/` images (alpine 3.4s).
  - Non-`library/` mirrors (`docker.m.daocloud.io`, `dockerpull.org`, `docker.1ms.run`) cannot serve ostis images from cache — they hang proxying to the slow upstream.
  - `registry-mirrors` (mirror.gcr.io + docker.m.daocloud.io) added to `~/.docker/daemon.json` (backup at `Temp/daemon.json.bak`); daemon restarted; library pulls now seconds.
  - `ostis/sc-web:0.9.0` pulled via `docker.1ms.run` (worked slowly but completed) and retagged.
  - `ostis/sc-machine:0.10.0` from Docker Hub turned out to be the **generic sc-machine image** — no `/example-app/install`, container exit 127. The compose `image:` name is just what a local build would tag; local build of `machine` is mandatory. Lesson recorded.
  - Local build of `machine` running via schtasks (survives tool timeouts); base images cached; apt downloads at usable speed.
- Added `scripts/smoke-test.sh` — stage-1 acceptance test (containers up, healthcheck, HTTP probes :8000/:8090).
- Added `docs/ONTOLOGY-DRAFT.md` — draft sc-ontology of experience events (episode template, nrel dictionary, SCs example) for Stage 2.

### Gotchas (for future sessions)

- Long-running docker commands die with the tool's job object when the client is killed — run them via `schtasks /Create ... /Run` with a bat file; that survives everything.
- `docker compose up` with `image:` + `build:` pulls the named image first even when a local build is intended; use `docker compose build <service>` explicitly.
- containerd image store (`io.containerd.snapshotter.v1`) does NOT honor daemon registry-mirrors for build-time pulls; left enabled anyway (switching the store would wipe existing images — maigret/dnstwist kept intact).
- Windows + Git Bash: `MSYS_NO_PATHCONV=1` needed for `schtasks /Create /TN ...`; schtasks output is cp866 — pipe through `iconv -f cp866 -t utf-8`.
