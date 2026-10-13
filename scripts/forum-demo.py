"""Rehearse the local forum demo, preserving artifacts and every command's exit.

Run: python scripts/forum-demo.py
Resume an already-verified W3 run: --w3-root _tmp/oneiro-w3-live-<suffix>
Only test mailbox/bot transports are used. No real account and no owner graph writes.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
TESTS = PROJECT / "tests"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--w3-root", type=Path, help="reuse an already completed W3 check")
    args = parser.parse_args()
    evidence = PROJECT / "_tmp" / ("forum-rehearsal-" + time.strftime("%Y%m%d-%H%M%S"))
    evidence.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8",
               PYTHONPATH=os.pathsep.join((str(PROJECT / "python"), str(TESTS))))
    receipts = []
    started = time.monotonic()

    def run(label: str, command: list[str], child_env: dict[str, str] | None = None) -> int:
        log = evidence / (label + ".log")
        begin = time.monotonic()
        with log.open("w", encoding="utf-8") as output:
            done = subprocess.run(command, cwd=PROJECT, env=child_env or env,
                                  stdout=output, stderr=subprocess.STDOUT, timeout=600)
        row = {"label": label, "exit": done.returncode,
               "seconds": round(time.monotonic() - begin, 2),
               "log": str(log.relative_to(PROJECT))}
        receipts.append(row)
        (evidence / "receipts.json").write_text(json.dumps(receipts, indent=2))
        print(json.dumps(row), flush=True)
        return done.returncode

    if args.w3_root:
        root = args.w3_root.resolve()
    else:
        if run("w3", [sys.executable, "-u", str(TESTS / "live_drafts_check.py"),
                      "--marker", evidence.name]):
            print("W3 failed; see retained log. No later package is claimed complete.")
            return 1
        text = (evidence / "w3.log").read_text(encoding="utf-8")
        marker = "the check's own roots stay for inspection: "
        lines = [line.split(marker, 1)[1].strip() for line in text.splitlines() if marker in line]
        if not lines:
            raise RuntimeError("W3 did not report its isolated root")
        root = Path(lines[-1])
    if root.parent != (PROJECT / "_tmp").resolve() or not root.name.startswith("oneiro-w3-live-"):
        raise ValueError("Only a task-owned W3 root inside this project may be resumed")
    if not (root / "asks" / "calls.jsonl").is_file():
        raise ValueError("The W3 root contains no completed transport evidence")
    graph = "oneiro-w3-" + root.name.removeprefix("oneiro-w3-live-")
    inspected = subprocess.run(["docker", "inspect", graph], capture_output=True,
                               text=True, encoding="utf-8", check=True, timeout=30)
    obj = json.loads(inspected.stdout)[0]
    binding = obj["HostConfig"]["PortBindings"]["8090/tcp"][0]
    if binding["HostIp"] != "127.0.0.1":
        raise ValueError("The demo graph must have a loopback-only binding")
    port = int(binding["HostPort"])
    child_env = {**env, "ONEIRO_LIVE_GRAPH_PORT": str(port), "ONEIRO_PORT": str(port),
                 "ONEIRO_DATA_DIR": str(evidence / "runtime"),
                 "ONEIRO_SETTINGS_FILE": str(evidence / "settings.json"),
                 "ONEIRO_KEYS_FILE": str(evidence / "no-keys.env")}
    (evidence / "runtime").mkdir()
    # Do not name any model/key in the isolated settings: this rehearsal never asks
    # a model or uses a real mailbox. A separate primary verification covers that.
    (evidence / "settings.json").write_text("{}\n")
    graph_started = False
    try:
        if run("graph-start", ["docker", "start", graph]):
            return 1
        graph_started = True
        read = [sys.executable, str(PROJECT / "scripts" / "office-graph-read.py"),
                "--stream", "demo", "--limit", "1"]
        deadline = time.monotonic() + 90
        ready = False
        while time.monotonic() < deadline:
            # Read actual graph records, not just an open socket.
            status = run("graph-readiness", read, child_env)
            if status == 0:
                ready = True
                break
            time.sleep(2)
        if not ready:
            return 1
        hook_code = (
            "from pathlib import Path; import live_hooks_check as c; "
            f"c.WORK=Path({str(evidence / 'hooks')!r}); c.WORK.mkdir(); "
            "raise SystemExit(c.main(['--marker', '" + evidence.name + "']))"
        )
        if run("webhook", [sys.executable, "-u", "-c", hook_code], child_env):
            return 1
        # The product command is exercised unmodified, except its injectable Docker
        # runner preserves this job's container instead of permanently removing it.
        # No fake conversions/records: every non-cleanup command is real Docker.
        office_code = (
            "from oneiro import office_env,cli; "
            "real=office_env._subprocess_runner; "
            "office_env._subprocess_runner=lambda argv,**kw: "
            "real(([argv[0],'stop','--time','20',argv[-1]] if argv[1:2]==['rm'] else argv),**kw); "
            "raise SystemExit(cli.main(['office','run','--topic','Oneiro: локальный форум',"
            f"'--out',{str(evidence / 'office')!r},'--stream','demo','--json']))"
        )
        if run("office", [sys.executable, "-u", "-c", office_code], child_env):
            return 1
        if run("office-readback", read[:-1] + ["30"], child_env):
            return 1
        print("Rehearsal artifacts: " + str(evidence.relative_to(PROJECT)), flush=True)
        return 0
    finally:
        if graph_started:
            if run("graph-stop", ["docker", "stop", "--time", "20", graph]):
                raise RuntimeError("The task-owned graph did not stop; inspect its receipt")
            state = subprocess.run(["docker", "inspect", "--format", "{{.State.Running}}", graph],
                                   capture_output=True, text=True, check=True, timeout=30)
            if state.stdout.strip() != "false":
                raise RuntimeError("The task-owned graph remains running")
        (evidence / "summary.json").write_text(json.dumps({
            "w3_root": str(root.relative_to(PROJECT)), "graph": graph, "graph_port": port,
            "wall_seconds": round(time.monotonic() - started, 2),
            "scope": "synthetic mailbox/bot, signed webhook, predefined office sources",
            "human_speech_timed": False, "receipts": receipts}, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
