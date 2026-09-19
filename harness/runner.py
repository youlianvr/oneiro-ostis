"""Task runner: one agent run = one recorded episode.

    python harness/runner.py --task t01-start-total
    python harness/runner.py --task t01-start-total --label baseline

A task lives in `harness/tasks/<id>/`:

    repo/        starting code the agent sees (with its visible failing test)
    hidden/      tests the agent never sees, copied in only for evaluation
    task.json    {"id", "title", "kind", "prompt"}

The runner copies `repo/` into a scratch directory under `harness/lab/runs/`,
makes it a git repository (opencode snapshots projects through git), drops in
the provider config, runs `opencode run --format json`, then evaluates the
result with both the visible and the hidden tests. Everything measured ends up
in `record.json`: steps, tool calls, tokens per step, wall time, test outcome.

The record is the unit our graph, judge and RSI loop consume; nothing here
talks to the network except the agent itself.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import shutil
import subprocess
import string
import time
from collections import Counter
from pathlib import Path

HARNESS_DIR = Path(__file__).resolve().parent
PROJECT_DIR = HARNESS_DIR.parent
WORKSPACE_DIR = PROJECT_DIR.parents[2]
TASKS_DIR = HARNESS_DIR / "tasks"
RUNS_DIR = HARNESS_DIR / "lab" / "runs"
PROVIDER_TEMPLATE = HARNESS_DIR / "opencode.template.json"

DEFAULT_MODEL = "deepseek-ai/DeepSeek-V4-Flash-0731"
API_KEY_ENV = "INFERENCE_DAHL_GLOBAL_KEY"
AGENT_TIMEOUT = 600.0

# On Windows opencode installs as a .cmd shim, which CreateProcess cannot
# launch directly: route it through cmd.exe when that is what we find.
OPENCODE = shutil.which("opencode") or "opencode"


def opencode_cmd(args: list[str]) -> list[str]:
    if OPENCODE.lower().endswith((".cmd", ".bat")):
        return ["cmd", "/c", OPENCODE, *args]
    return [OPENCODE, *args]


# ---------- environment ----------


def api_key(name: str = API_KEY_ENV) -> str:
    """A provider key, from the environment or the workspace .env."""
    key = os.environ.get(name)
    if key:
        return key
    env_file = WORKSPACE_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit(f"{name} not found (environment or workspace .env)")


# ---------- scratch setup ----------


def _run(cmd: list[str], cwd: Path, timeout: float = 120.0, env: dict | None = None):
    return subprocess.run(
        cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout,
        encoding="utf-8", errors="replace", env=env,
    )


def make_scratch(task: dict, label: str) -> Path:
    """A fresh copy of the task repo, git-initialised, with provider config."""
    slug = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
    stamp = time.strftime("%Y%m%d-%H%M%S")
    scratch = RUNS_DIR / f"{task['id']}-{label}-{stamp}-{slug}"
    if scratch.exists():
        raise SystemExit(f"scratch already exists: {scratch}")
    (scratch / "repo").mkdir(parents=True)
    shutil.copytree(TASKS_DIR / task["id"] / "repo", scratch / "repo", dirs_exist_ok=True)
    shutil.copy(PROVIDER_TEMPLATE, scratch / "repo" / "opencode.json")

    repo = scratch / "repo"
    git = ["git", "-c", "user.email=oneiro@lab", "-c", "user.name=oneiro"]
    _run(git + ["init", "-q"], repo)
    _run(git + ["add", "-A"], repo)
    _run(git + ["commit", "-q", "-m", "task start"], repo)
    return scratch


# ---------- the agent run ----------


def parse_events(events_path: Path) -> dict:
    """Turn the `--format json` stream into the measurements we record."""
    steps: list[dict] = []
    tools: Counter = Counter()
    tokens = {"input": 0, "output": 0, "reasoning": 0, "cache_read": 0, "cache_write": 0}
    files_touched: list[str] = []
    texts: list[str] = []

    for line in events_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = event.get("type")
        part = event.get("part") or {}

        if kind == "tool_use":
            tool = part.get("tool") or "?"
            state = part.get("state") or {}
            data = state.get("input") or {}
            detail = data.get("filePath") or data.get("command") or data.get("pattern") or ""
            tools[tool] += 1
            if tool in ("edit", "write") and detail:
                files_touched.append(str(detail))
            steps.append({"index": len(steps), "kind": "tool", "tool": tool,
                          "detail": str(detail)[:400], "status": state.get("status")})
        elif kind == "text":
            text = (part.get("text") or "").strip()
            if text:
                texts.append(text)
                steps.append({"index": len(steps), "kind": "text", "detail": text[:400]})
        elif kind == "step_finish":
            usage = part.get("tokens") or {}
            cache = usage.get("cache") or {}
            entry = {"index": len(steps) - 1, "kind": "step_finish",
                     "reason": part.get("reason"),
                     "input": usage.get("input", 0), "output": usage.get("output", 0),
                     "reasoning": usage.get("reasoning", 0),
                     "cache_read": cache.get("read", 0), "cache_write": cache.get("write", 0),
                     "total": usage.get("total", 0)}
            steps.append(entry)
            tokens["input"] += usage.get("input", 0)
            tokens["output"] += usage.get("output", 0)
            tokens["reasoning"] += usage.get("reasoning", 0)
            tokens["cache_read"] += cache.get("read", 0)
            tokens["cache_write"] += cache.get("write", 0)

    return {"steps": steps, "tools": dict(tools), "tokens": tokens,
            "files_touched": files_touched, "texts": texts}


TEST_LINE = re.compile(r"(\d+) (passed|failed|error)")


def evaluate(scratch: Path, task_id: str) -> dict:
    """Run the visible tests, then the hidden ones, in the finished repo."""
    repo = scratch / "repo"
    hidden = TASKS_DIR / task_id / "hidden"
    result: dict = {}

    visible = _run(["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"], repo, timeout=300)
    result["visible"] = {"exit": visible.returncode, "tail": visible.stdout.strip().splitlines()[-1:]}

    if hidden.exists():
        target = repo / "_hidden_tests"
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(hidden, target)
        run = _run(["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "_hidden_tests"],
                   repo, timeout=300)
        result["hidden"] = {"exit": run.returncode, "tail": run.stdout.strip().splitlines()[-1:]}
        shutil.rmtree(target, ignore_errors=True)

    counts = {"passed": 0, "failed": 0}
    for block in ("visible", "hidden"):
        for line in result.get(block, {}).get("tail", []):
            for number, word in TEST_LINE.findall(line):
                if word in counts:
                    counts[word] += int(number)
    result["counts"] = counts
    result["solved"] = bool(
        result["visible"]["exit"] == 0
        and (result.get("hidden", {}).get("exit", 0) == 0)
    )
    return result


def run_task(task_id: str, model: str = DEFAULT_MODEL, label: str = "run",
             timeout: float = AGENT_TIMEOUT) -> dict:
    task_file = TASKS_DIR / task_id / "task.json"
    if not task_file.exists():
        raise SystemExit(f"no such task: {task_id}")
    task = json.loads(task_file.read_text(encoding="utf-8"))

    scratch = make_scratch(task, label)
    events_path = scratch / "events.jsonl"
    env = dict(os.environ, **{API_KEY_ENV: api_key()})

    started = time.time()
    timed_out = False
    with events_path.open("w", encoding="utf-8") as out:
        try:
            proc = subprocess.run(
                opencode_cmd(["run", "--format", "json", "--model", model, task["prompt"]]),
                cwd=str(scratch / "repo"), stdout=out, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace", timeout=timeout, env=env,
            )
            exit_code = proc.returncode
            stderr = proc.stderr or ""
        except subprocess.TimeoutExpired:
            exit_code, stderr, timed_out = -1, "timeout", True
    wall = round(time.time() - started, 2)

    (scratch / "stderr.log").write_text(stderr, encoding="utf-8")
    parsed = parse_events(events_path)
    result = evaluate(scratch, task_id)

    record = {
        "schema": 1,
        "task": task["id"],
        "title": task.get("title", ""),
        "kind": task.get("kind", ""),
        "label": label,
        "model": model,
        "prompt": task["prompt"],
        "wall_seconds": wall,
        "timed_out": timed_out,
        "exit_code": exit_code,
        "scratch": str(scratch),
        "solved": result["solved"],
        "tests": result,
        "tools": parsed["tools"],
        "tool_calls": sum(parsed["tools"].values()),
        "tokens": parsed["tokens"],
        "files_touched": parsed["files_touched"],
        "steps": parsed["steps"],
        "final_text": parsed["texts"][-1][:1200] if parsed["texts"] else "",
    }
    (scratch / "record.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def summary_line(record: dict) -> str:
    tokens = record["tokens"]
    return (
        f"{record['task']:<22} solved={str(record['solved']):<5} "
        f"steps={len(record['steps']):<3} tools={record['tool_calls']:<2} "
        f"in={tokens['input']:<6} out={tokens['output']:<5} cache={tokens['cache_read']:<6} "
        f"{record['wall_seconds']:>6}s"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="run one agent task and record it")
    parser.add_argument("--task", required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--label", default="run")
    parser.add_argument("--timeout", type=float, default=AGENT_TIMEOUT)
    args = parser.parse_args()

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    record = run_task(args.task, args.model, args.label, args.timeout)
    print(summary_line(record))
    print(f"record: {record['scratch']}/record.json")


if __name__ == "__main__":
    main()
