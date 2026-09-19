"""Our own coding agent: the harness we own, measure and search over.

    python harness/run.py --task t01-start-total --agent ours --policy baseline

The loop is deliberately small and fully observed: a policy decides what the
model is shown, the model picks a tool, the tool acts on a scratch copy of the
task repository, and every step is measured. Nothing the policy does is hidden
from the record, because the record is what the judge replays.

The only network dependency is the OpenAI-compatible chat endpoint; the tools
themselves are local and deterministic.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import runner
from policy import HarnessPolicy, get_policy

# The provider is any OpenAI-compatible endpoint; the key comes from the
# environment (see runner.api_key). dahl serves three tool-capable models:
#   deepseek-ai/DeepSeek-V4-Flash-0731  (fastest, default)
#   MiniMaxAI/MiniMax-M2.7              (fallback)
#   zai-org/GLM-5.3-Flash               (slow, chatty about tool calls)
DEFAULT_MODEL = "deepseek-ai/DeepSeek-V4-Flash-0731"
BASE_URL = os.environ.get("ONEIRO_BASE_URL", "https://inference.dahl.global/v1")
REQUEST_TIMEOUT = 180.0
MAX_PLACEHOLDER_RETRIES = 8

# The provider answers instantly with this text while it boots a cold model;
# it is not a model answer and must never enter the trajectory.
PLACEHOLDER_MARKER = "model is starting up"


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List the files in the repository.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a text file from the repository, with line numbers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "path relative to the repository root"},
                    "start": {"type": "integer", "description": "first line (1-based), optional"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a file with the given content.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace an exact string in a file. old_string must occur exactly once.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_string": {"type": "string"},
                    "new_string": {"type": "string"},
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_tests",
            "description": "Run the repository test suite with pytest and return its output.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run a shell command in the repository root and return its output.",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    },
]


# ---------- provider ----------


class Provider:
    """Minimal OpenAI-compatible chat client with tool calling."""

    def __init__(self, model: str, api_key: str, temperature: float, base_url: str = BASE_URL):
        self.model = model
        self.api_key = api_key
        self.temperature = temperature
        self.base_url = base_url.rstrip("/")

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> tuple[dict, dict]:
        """Return (message, usage); retries while the provider is booting."""
        payload: dict = {"model": self.model, "messages": messages,
                         "temperature": self.temperature}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        for attempt in range(MAX_PLACEHOLDER_RETRIES):
            request = urllib.request.Request(
                f"{self.base_url}/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json",
                         "Authorization": f"Bearer {self.api_key}"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                    body = json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:300]
                raise RuntimeError(f"HTTP {exc.code} from provider: {detail}") from exc

            choice = body["choices"][0]
            message = choice["message"]
            usage = body.get("usage") or {}
            content = message.get("content") or ""
            if PLACEHOLDER_MARKER in content and not message.get("tool_calls"):
                time.sleep(15)
                continue
            return message, usage

        raise RuntimeError(
            f"provider kept answering with the cold-start placeholder after "
            f"{MAX_PLACEHOLDER_RETRIES} tries ({self.model} is not warm)"
        )


# ---------- tools ----------


class ToolBox:
    """Executes the agent's tools inside one repository and reports what happened."""

    def __init__(self, repo: Path, policy: HarnessPolicy):
        self.repo = repo
        self.policy = policy
        self.actions: list[dict] = []

    # -- helpers --

    def _resolve(self, path: str) -> Path:
        target = (self.repo / str(path)).resolve()
        if self.repo.resolve() not in target.parents and target != self.repo.resolve():
            raise ValueError(f"path escapes the repository: {path}")
        return target

    def _clip(self, text: str) -> str:
        limit = self.policy.observation_chars
        if limit and len(text) > limit:
            return text[:limit] + f"\n... [{len(text) - limit} characters truncated]"
        return text

    def _shell(self, command: str, timeout: float = 180.0) -> str:
        bash = shutil.which("bash")
        argv = [bash, "-lc", command] if bash else ["cmd", "/c", command]
        try:
            proc = subprocess.run(argv, cwd=str(self.repo), capture_output=True, text=True,
                                  timeout=timeout, encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            return f"[command timed out after {timeout:.0f}s]"
        out = (proc.stdout or "") + (proc.stderr or "")
        return out.strip() or f"[exit {proc.returncode}, no output]"

    # -- tools --

    def list_files(self) -> str:
        skip = {".git", "__pycache__", ".pytest_cache", "opencode.json"}
        rows = []
        for path in sorted(self.repo.rglob("*")):
            if any(part in skip for part in path.parts):
                continue
            if path.is_file():
                rows.append(f"{path.relative_to(self.repo).as_posix()} "
                            f"({path.stat().st_size} bytes)")
        return "\n".join(rows) or "[empty repository]"

    def read_file(self, path: str, start: int = 1) -> str:
        target = self._resolve(path)
        if not target.exists():
            return f"[no such file: {path}]"
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(1, int(start or 1))
        window = lines[start - 1:start - 1 + max(1, self.policy.read_lines)]
        numbered = [f"{start + i:>4} | {line}" for i, line in enumerate(window)]
        tail = "" if start - 1 + len(window) >= len(lines) else \
            f"\n... [{len(lines) - (start - 1 + len(window))} more lines]"
        return "\n".join(numbered) + tail

    def write_file(self, path: str, content: str) -> str:
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"[wrote {len(content)} characters to {path}]"

    def edit_file(self, path: str, old_string: str, new_string: str) -> str:
        target = self._resolve(path)
        if not target.exists():
            return f"[no such file: {path}]"
        text = target.read_text(encoding="utf-8", errors="replace")
        count = text.count(old_string)
        if count != 1:
            return f"[old_string occurs {count} times in {path}; need exactly one]"
        target.write_text(text.replace(old_string, new_string, 1), encoding="utf-8")
        return f"[edited {path}]"

    def run_tests(self) -> str:
        return self._shell("python -m pytest -q -p no:cacheprovider")

    def run_command(self, command: str) -> str:
        return self._shell(str(command))

    def execute(self, name: str, args: dict) -> str:
        fn = getattr(self, name, None)
        if fn is None or name not in {t["function"]["name"] for t in TOOLS}:
            return f"[unknown tool: {name}]"
        try:
            observation = fn(**args) if isinstance(args, dict) else fn()
        except TypeError as exc:
            observation = f"[bad arguments for {name}: {exc}]"
        except ValueError as exc:
            observation = f"[refused: {exc}]"
        except Exception as exc:  # a broken tool must not kill the episode
            observation = f"[tool {name} failed: {exc.__class__.__name__}: {exc}]"

        self.actions.append({"tool": name, "args": args, "observation": observation})
        return self._clip(observation)


# ---------- prompt ----------


def system_prompt(policy: HarnessPolicy, file_list: str | None, tests: str | None) -> str:
    parts = [
        "You are a coding agent working in a small repository.",
        "Fix the task by editing files with the tools; then run the tests and make them pass.",
        "Work in the repository root; paths are relative to it. Keep edits minimal and correct.",
    ]
    if policy.include_file_list and file_list:
        parts.append(f"Files in the repository:\n{file_list}")
    if policy.include_initial_tests and tests:
        parts.append(f"The test suite currently reports:\n{tests}")
    return "\n\n".join(parts)


# ---------- the episode ----------


def _usage_tokens(usage: dict) -> dict:
    """Token counts in the same shape the opencode runner records."""
    details = usage.get("prompt_tokens_details") or {}
    prompt = usage.get("prompt_tokens", 0)
    completion = usage.get("completion_tokens", 0)
    return {
        "input": prompt,
        "output": completion,
        "reasoning": usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0),
        "cache_read": details.get("cached_tokens", 0) or usage.get("cache_read_tokens", 0) or 0,
        "cache_write": 0,
        "total": usage.get("total_tokens", 0) or prompt + completion,
    }


def run_task(task_id: str, model: str = DEFAULT_MODEL, label: str = "ours",
             policy: HarnessPolicy | None = None, timeout: float = 900.0) -> dict:
    """Run one episode and return its record (same shape as the opencode runner)."""
    policy = policy or get_policy("baseline")
    task_file = runner.TASKS_DIR / task_id / "task.json"
    if not task_file.exists():
        raise SystemExit(f"no such task: {task_id}")
    task = json.loads(task_file.read_text(encoding="utf-8"))

    scratch = runner.make_scratch(task, f"{label}-{policy.name}")
    repo = scratch / "repo"
    provider = Provider(model, runner.api_key(), policy.temperature)
    toolbox = ToolBox(repo, policy)

    file_list = toolbox.list_files() if policy.include_file_list else None
    initial_tests = toolbox.run_tests() if policy.include_initial_tests else None
    toolbox.actions.clear()  # the setup probes are not part of the trajectory

    messages: list[dict] = [
        {"role": "system", "content": system_prompt(policy, file_list, initial_tests)},
        {"role": "user", "content": task["prompt"]},
    ]
    turns: list[list[dict]] = []          # history in unit-sized chunks
    steps: list[dict] = []
    tokens = {"input": 0, "output": 0, "reasoning": 0, "cache_read": 0,
              "cache_write": 0, "total": 0}
    nudges = 0
    started = time.time()
    stop_reason = "max_steps"
    error = None

    try:
        for index in range(max(1, policy.max_steps)):
            if time.time() - started > timeout:
                stop_reason = "timeout"
                break
            request_messages = list(messages)
            if policy.context_mode == "window":
                keep = policy.window_steps
                flat = [m for turn in turns[-keep:] for m in turn]
                request_messages = messages[:2] + flat

            call_started = time.time()
            message, usage = provider.chat(request_messages, TOOLS)
            latency = round(time.time() - call_started, 2)
            step_tokens = _usage_tokens(usage)
            for key in tokens:
                tokens[key] += step_tokens[key]

            calls = message.get("tool_calls") or []
            turn: list[dict] = [message]
            step = {"index": len(steps), "latency": latency, "tokens": step_tokens}
            if calls:
                step["kind"] = "tool"
                step["tools"] = [c["function"]["name"] for c in calls]
            else:
                step["kind"] = "text"
                step["text"] = (message.get("content") or "")[:400]

            for call in calls:
                name = call["function"]["name"]
                try:
                    args = json.loads(call["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                observation = toolbox.execute(name, args)
                turn.append({"role": "tool", "tool_call_id": call.get("id"),
                             "content": observation})
                step.setdefault("observations", []).append(observation[:400])

            steps.append(step)
            turns.append(turn)
            messages.extend(turn)

            if not calls:
                tail = toolbox.run_tests()
                if policy.verify_before_finish and nudges < policy.max_verify_nudges:
                    nudges += 1
                    nudge = ("The tests still fail. Here is the current output:\n"
                             f"{toolbox._clip(tail)}\nContinue until they pass.")
                    steps.append({"index": len(steps), "kind": "nudge",
                                  "text": "verify_before_finish", "tokens": {}})
                    turns.append([{"role": "user", "content": nudge}])
                    messages.append({"role": "user", "content": nudge})
                    continue
                stop_reason = "finished"
                break
        else:
            stop_reason = "max_steps"
    except Exception as exc:  # record the failure, never lose the episode
        error = f"{exc.__class__.__name__}: {exc}"
        stop_reason = "error"

    wall = round(time.time() - started, 2)
    result = runner.evaluate(scratch, task_id)

    record = {
        "schema": 1,
        "task": task["id"],
        "title": task.get("title", ""),
        "kind": task.get("kind", ""),
        "label": label,
        "agent": "ours",
        "policy": policy.descriptor(),
        "model": model,
        "prompt": task["prompt"],
        "wall_seconds": wall,
        "stop_reason": stop_reason,
        "error": error,
        "solved": result["solved"],
        "tests": result,
        "tools": {},
        "tool_calls": len([s for s in steps if s.get("kind") == "tool"]),
        "tokens": tokens,
        "steps": steps,
        "trajectory": [
            {"tool": a["tool"], "args": a["args"], "observation": a["observation"][:400]}
            for a in toolbox.actions
        ],
        "scratch": str(scratch),
        "final_text": (steps[-1].get("text") if steps else "") or "",
    }
    counts: dict = {}
    for action in toolbox.actions:
        counts[action["tool"]] = counts.get(action["tool"], 0) + 1
    record["tools"] = counts

    (scratch / "record.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record
