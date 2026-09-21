"""The worker: a bounded tool loop inside one isolated worktree.

The worker is the only role that touches files, and it can only touch them
inside the worktree the runner created for this cycle. Every write goes
through a path jail; the only command it may run is the cycle's declared
check, which came from the loop's allowlist, never from a model.

The result is evidence for a PR packet a human reviews later. There is no
merge, no push, and no approval anywhere in this module.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

from llm import CallBudget, ModelPool, ProviderError
from swarm import Proposal

WORKER_ROLE = "worker"
MAX_STEPS = 24
MAX_NUDGES = 3
MAX_WRITE_BYTES = 200_000
OBSERVATION_CHARS = 6_000
LIST_LIMIT = 300
CHECK_TIMEOUT = 600.0

SKIP_PARTS = {".git", "__pycache__", ".pytest_cache", "node_modules", ".venv", "venv"}

TOOLS = [
    {"type": "function", "function": {
        "name": "list_files",
        "description": "List project files inside the worktree (relative paths and sizes).",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read one text file from the worktree with line numbers.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Path relative to the worktree root."},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "write_file",
        "description": ("Write a complete text file inside the worktree: creates it or "
                        "replaces its whole content. Keep files small."),
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
        }, "required": ["path", "content"]},
    }},
    {"type": "function", "function": {
        "name": "run_check",
        "description": "Run the declared check command inside the worktree and return its output.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "finish",
        "description": "Declare the change complete and give a short summary of what was done.",
        "parameters": {"type": "object", "properties": {
            "summary": {"type": "string", "description": "What changed and why, in Russian."},
        }, "required": ["summary"]},
    }},
]

WORKER_SYSTEM = """You are the worker of a small autonomous organization that improves the Oneiro
project. You receive one chosen proposal and you implement it inside one isolated git worktree.

Rules:
- Work only inside the worktree. The change you make becomes a PR packet that a human reviews; you
  never merge, push, release, or approve anything.
- Make the smallest change that satisfies the acceptance criteria. Prefer editing existing files
  over creating new ones.
- After changing files, call run_check and iterate until it passes.
- Read the files you are about to change before changing them; do not guess their content.
- Never touch .git or anything outside the worktree.
- Work in the project subdirectory named in the task; that is where the code and tests live.
- When the check passes, call finish with a short summary in Russian.
"""


@dataclass
class WorkerOutcome:
    """What the worker did, kept as evidence for the cycle record."""

    status: str  # "done" | "gave_up"
    summary: str
    steps: int = 0
    model_calls: int = 0
    actions: list[dict] = field(default_factory=list)


class WorkerSession:
    """One bounded tool loop over one worktree."""

    def __init__(
        self,
        *,
        pool: ModelPool,
        proposal: Proposal,
        worktree_root: Path,
        check_command: Sequence[str],
        budget: Optional[CallBudget] = None,
        scope: str = ".",
        step_limit: int = MAX_STEPS,
    ) -> None:
        self.pool = pool
        self.proposal = proposal
        self.root = Path(worktree_root).resolve()
        self.check_command = tuple(check_command)
        self.budget = budget
        self.scope = scope
        self.step_limit = step_limit
        self.actions: list[dict] = []

    # ---------- the loop ----------

    def run(self) -> WorkerOutcome:
        messages: list[dict] = [
            {"role": "system", "content": WORKER_SYSTEM},
            {"role": "user", "content": self._task_text()},
        ]
        nudges = 0
        model_calls = 0
        for step in range(1, self.step_limit + 1):
            reply = self.pool.reply(WORKER_ROLE, messages, tools=TOOLS, budget=self.budget)
            model_calls += 1
            message = reply.message
            tool_calls = message.get("tool_calls") or []
            messages.append({
                "role": "assistant",
                "content": message.get("content") or "",
                **({"tool_calls": tool_calls} if tool_calls else {}),
            })
            if not tool_calls:
                if nudges >= MAX_NUDGES:
                    return WorkerOutcome("gave_up", "the model stopped calling tools",
                                         steps=step, model_calls=model_calls,
                                         actions=self.actions)
                nudges += 1
                messages.append({"role": "user", "content":
                                 "Use the tools: edit the files and run the check. "
                                 "Call finish only after the check passes."})
                continue
            for call in tool_calls:
                name, arguments = self._parse_call(call)
                if name == "finish":
                    summary = str(arguments.get("summary") or "").strip() or "finished"
                    self.actions.append({"step": step, "tool": "finish", "summary": summary[:500]})
                    return WorkerOutcome("done", summary, steps=step,
                                         model_calls=model_calls, actions=self.actions)
                result = self._execute(name, arguments)
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("id") or f"call_{step}",
                    "content": result,
                })
        return WorkerOutcome("gave_up", f"step limit reached ({self.step_limit})",
                             steps=self.step_limit, model_calls=model_calls,
                             actions=self.actions)

    def _task_text(self) -> str:
        return (
            f"Project subdirectory: {self.scope}\n"
            f"Declared check command: {' '.join(self.check_command)}\n\n"
            f"Proposal: {self.proposal.title}\n"
            f"Rationale: {self.proposal.rationale}\n"
            f"Acceptance criteria:\n" +
            "\n".join(f"- {item}" for item in self.proposal.acceptance) +
            "\n\nStart by listing the files, then read what you will change."
        )

    # ---------- tool execution ----------

    @staticmethod
    def _parse_call(call: dict) -> tuple[str, dict]:
        function = call.get("function") or {}
        name = str(function.get("name") or "")
        raw = function.get("arguments") or "{}"
        try:
            arguments = json.loads(raw) if isinstance(raw, str) else dict(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            arguments = {}
        if not isinstance(arguments, dict):
            arguments = {}
        return name, arguments

    def _execute(self, name: str, arguments: dict) -> str:
        try:
            if name == "list_files":
                return self._list_files()
            if name == "read_file":
                return self._read_file(str(arguments.get("path") or ""))
            if name == "write_file":
                return self._write_file(str(arguments.get("path") or ""),
                                        str(arguments.get("content") or ""))
            if name == "run_check":
                return self._run_check()
            return f"[unknown tool: {name}]"
        except ValueError as exc:
            return f"[refused: {exc}]"
        except OSError as exc:
            return f"[tool failed: {exc}]"

    def _clip(self, text: str) -> str:
        if len(text) > OBSERVATION_CHARS:
            return text[:OBSERVATION_CHARS] + f"\n... [{len(text) - OBSERVATION_CHARS} chars cut]"
        return text

    def _resolve(self, path: str) -> Path:
        if not path:
            raise ValueError("a path is required")
        target = (self.root / path).resolve()
        if target != self.root and self.root not in target.parents:
            raise ValueError(f"path escapes the worktree: {path}")
        if ".git" in target.parts:
            raise ValueError("the worker never touches .git")
        return target

    def _list_files(self) -> str:
        base = self._resolve(self.scope)
        if not base.exists():
            return f"[no such directory in the worktree: {self.scope}]"
        rows: list[str] = []
        for path in sorted(base.rglob("*")):
            if any(part in SKIP_PARTS for part in path.parts):
                continue
            if path.is_file():
                rows.append(f"{path.relative_to(self.root).as_posix()} "
                            f"({path.stat().st_size} bytes)")
            if len(rows) >= LIST_LIMIT:
                rows.append(f"... [listing stopped at {LIST_LIMIT} files]")
                break
        return self._clip("\n".join(rows) or "[no files in scope]")

    def _read_file(self, path: str) -> str:
        target = self._resolve(path)
        if not target.is_file():
            return f"[no such file: {path}]"
        text = target.read_text(encoding="utf-8", errors="replace")
        numbered = "\n".join(f"{index:>4} {line}"
                             for index, line in enumerate(text.splitlines(), start=1))
        return self._clip(numbered or "[empty file]")

    def _write_file(self, path: str, content: str) -> str:
        if len(content.encode("utf-8")) > MAX_WRITE_BYTES:
            raise ValueError(f"write too large (limit {MAX_WRITE_BYTES} bytes)")
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        self.actions.append({"tool": "write_file", "path": path,
                             "bytes": len(content.encode("utf-8"))})
        return f"written {len(content.encode('utf-8'))} bytes to {path}"

    def _run_check(self) -> str:
        try:
            completed = subprocess.run(
                list(self.check_command),
                cwd=str(self.root),
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=CHECK_TIMEOUT,
                check=False,
            )
        except subprocess.TimeoutExpired:
            self.actions.append({"tool": "run_check", "exit": None, "timeout": True})
            return f"[check timed out after {CHECK_TIMEOUT:.0f}s]"
        output = (completed.stdout or "").strip() or "[no output]"
        self.actions.append({"tool": "run_check", "exit": completed.returncode})
        return self._clip(f"exit {completed.returncode}\n{output}")


__all__ = ["TOOLS", "WorkerOutcome", "WorkerSession"]
