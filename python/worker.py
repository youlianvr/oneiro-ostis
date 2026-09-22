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
READ_WINDOW_LINES = 400
LIST_LIMIT = 300
CHECK_TIMEOUT = 600.0
FINISH_GRACE_CALLS = 2
# A worker that declares itself finished without ever running the declared check
# throws away the whole cycle: the packet gate refuses it and the change dies in
# the worktree. So "finish" is refused while the check has not passed, a bounded
# number of times; past that the gate decides, as it always did.
MAX_FINISH_REFUSALS = 3
SHRINK_GUARD_MIN_BYTES = 2_000
SHRINK_GUARD_RATIO = 0.5

SKIP_PARTS = {".git", "__pycache__", ".pytest_cache", "node_modules", ".venv", "venv"}

TOOLS = [
    {"type": "function", "function": {
        "name": "list_files",
        "description": "List project files inside the worktree (relative paths and sizes).",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "read_file",
        "description": ("Read a text file from the worktree as plain text, up to 400 lines "
                        "(continue with start_line). Copy snippets for replace_in_file here."),
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Path relative to the worktree root."},
            "start_line": {"type": "integer", "description": "First line to show, 1-based."},
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
        "name": "replace_in_file",
        "description": ("Replace an exact snippet inside an existing file: old_text must match "
                        "the file byte for byte and appear exactly once. Use this for edits "
                        "instead of rewriting a whole file."),
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
            "old_text": {"type": "string", "description": "Exact text to replace, copied from read_file."},
            "new_text": {"type": "string", "description": "Replacement text."},
        }, "required": ["path", "old_text", "new_text"]},
    }},
    {"type": "function", "function": {
        "name": "run_check",
        "description": "Run the declared check command inside the worktree and return its output.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "finish",
        "description": ("Declare the change complete and give a short summary of what was done. "
                        "The summary is read by a person who is not a programmer: plain "
                        "Russian, no file names, no English, no tool names."),
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
- Edit an existing file with replace_in_file: copy the exact snippet out of read_file and swap it.
  write_file replaces a whole file, so it is for new files or for a rewrite that is really the point.
  Never leave a large file as a stub.
- After changing files, call run_check and iterate until it passes. Calling finish before the
  check has passed once is refused, and you will be told what the check said; run it, fix what it
  names, and only then finish. If the check fails for reasons your change cannot fix, say so
  honestly in the summary and finish anyway.
- Read the files you are about to change before changing them; do not guess their content.
- Never touch .git or anything outside the worktree.
- Work in the project subdirectory named in the task; that is where the code and tests live.
- When the check passes, call finish with a short summary in Russian, one or two sentences, in the
  words a person who is not a programmer would use: no file names, no English words, no tool names.
  That summary is what a human reads later in the record of the work.
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
        self._pending_changes = 0
        self._check_passed = False
        self._last_check = ""
        self._finish_refusals = 0

    @property
    def check_passed(self) -> bool:
        """Whether the declared check has passed at least once in this session."""
        return self._check_passed

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
                                 "Use the tools: edit the files with replace_in_file or write_file, "
                                 "run the check, then call finish."})
                continue
            for call in tool_calls:
                name, arguments = self._parse_call(call)
                if name == "finish":
                    refusal = self._refuse_finish()
                    if refusal:
                        self.actions.append({"step": step, "tool": "finish_refused",
                                             "reason": refusal[:200]})
                        messages.append({"role": "tool",
                                         "tool_call_id": call.get("id") or f"call_{step}",
                                         "content": refusal})
                        continue
                    summary = str(arguments.get("summary") or "").strip() or "finished"
                    self.actions.append({"step": step, "tool": "finish",
                                         "check_passed": self._check_passed,
                                         "summary": summary[:500]})
                    return WorkerOutcome("done", summary, steps=step,
                                         model_calls=model_calls, actions=self.actions)
                result = self._execute(name, arguments)
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("id") or f"call_{step}",
                    "content": result,
                })
        return self._finish_grace(messages, model_calls)

    def _finish_grace(self, messages: list[dict], model_calls: int) -> WorkerOutcome:
        """Out of steps with real edits on disk: one bounded window to call finish.

        A worker that edited files and then ran out of steps has already produced
        the only part worth keeping; the summary is the last cheap piece. Without
        this window the run drops a real change because the model was still
        writing tests when the counter hit zero.
        """
        if not self._pending_changes:
            return WorkerOutcome("gave_up", f"step limit reached ({self.step_limit})",
                                 steps=self.step_limit, model_calls=model_calls,
                                 actions=self.actions)
        messages.append({"role": "user", "content":
                         "You are out of steps. Call finish now: one short summary "
                         "in Russian of what you changed and whether the check passes."})
        for _ in range(FINISH_GRACE_CALLS):
            reply = self.pool.reply(WORKER_ROLE, messages, tools=TOOLS, budget=self.budget)
            model_calls += 1
            message = reply.message
            tool_calls = message.get("tool_calls") or []
            messages.append({
                "role": "assistant",
                "content": message.get("content") or "",
                **({"tool_calls": tool_calls} if tool_calls else {}),
            })
            for call in tool_calls:
                name, arguments = self._parse_call(call)
                if name == "finish":
                    # The same rule holds in the grace window, and it is worth more
                    # here than anywhere: a check that was never run is the one
                    # thing that turns a finished change into a refused packet.
                    refusal = self._refuse_finish()
                    if refusal:
                        self.actions.append({"step": self.step_limit, "tool": "finish_refused",
                                             "reason": refusal[:200]})
                        messages.append({"role": "tool",
                                         "tool_call_id": call.get("id") or "grace",
                                         "content": refusal})
                        continue
                    summary = str(arguments.get("summary") or "").strip() or "finished"
                    self.actions.append({"step": self.step_limit, "tool": "finish",
                                         "check_passed": self._check_passed,
                                         "summary": summary[:500]})
                    return WorkerOutcome("done", summary, steps=self.step_limit,
                                         model_calls=model_calls, actions=self.actions)
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("id") or "grace",
                    "content": self._execute(name, arguments),
                })
        return WorkerOutcome(
            "gave_up",
            f"step limit reached ({self.step_limit}); finish was not called in the grace window",
            steps=self.step_limit, model_calls=model_calls, actions=self.actions,
        )

    def _refuse_finish(self) -> Optional[str]:
        """Refuse a finish the declared check does not back yet.

        Returns the sentence the model reads, or ``None`` when the finish may
        stand (the check passed, or the refusal budget is spent and the packet
        gate should judge the result itself).
        """
        if self._check_passed:
            return None
        if self._finish_refusals >= MAX_FINISH_REFUSALS:
            return None
        self._finish_refusals += 1
        if self._last_check:
            return (
                "[finish refused: the declared check has not passed yet. "
                "Last check output follows.\n"
                f"{self._last_check[:1500]}\n"
                "Fix what it names, call run_check again, and call finish only once "
                "the check passes.]"
            )
        return (
            "[finish refused: you have not run the declared check at all. Call run_check now; "
            "if it fails, fix the failure and run it again. Finish only once it passes.]"
        )

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
                return self._read_file(str(arguments.get("path") or ""),
                                       arguments.get("start_line"))
            if name == "write_file":
                return self._write_file(str(arguments.get("path") or ""),
                                        str(arguments.get("content") or ""))
            if name == "replace_in_file":
                return self._replace_in_file(str(arguments.get("path") or ""),
                                             str(arguments.get("old_text") or ""),
                                             str(arguments.get("new_text") or ""))
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

    def _read_file(self, path: str, start_line: object = 1) -> str:
        """Plain text, never numbered: the worker copies snippets out of this
        window into replace_in_file, and a line-number prefix would make every
        copied snippet un-matchable. Which is also why a read is a window."""
        target = self._resolve(path)
        if not target.is_file():
            return f"[no such file: {path}]"
        try:
            start = max(1, int(start_line))
        except (TypeError, ValueError):
            start = 1
        lines = target.read_text(encoding="utf-8", errors="replace").split("\n")
        window = lines[start - 1: start - 1 + READ_WINDOW_LINES]
        body = "\n".join(window) or "[empty file]"
        end = start - 1 + len(window)
        if end < len(lines):
            body += (f"\n... [showed lines {start}-{end} of {len(lines)}; "
                     "read again with start_line to continue]")
        return self._clip(body)

    def _replace_in_file(self, path: str, old_text: str, new_text: str) -> str:
        if not old_text:
            raise ValueError("old_text is required")
        target = self._resolve(path)
        if not target.is_file():
            return f"[no such file: {path}]"
        text = target.read_text(encoding="utf-8", errors="replace")
        count = text.count(old_text)
        if count == 0:
            return ("[no exact match for old_text. Read the file and copy the snippet exactly, "
                    "without surrounding lines you do not intend to change.]")
        if count > 1:
            return (f"[old_text appears {count} times. Include more surrounding lines so the "
                    "match is unique.]")
        updated = text.replace(old_text, new_text, 1)
        size = len(updated.encode("utf-8"))
        if size > MAX_WRITE_BYTES:
            raise ValueError(f"result too large (limit {MAX_WRITE_BYTES} bytes)")
        target.write_text(updated, encoding="utf-8")
        self.actions.append({"tool": "replace_in_file", "path": path})
        self._pending_changes += 1
        return f"replaced {len(old_text)} chars with {len(new_text)} chars in {path}"

    def _write_file(self, path: str, content: str) -> str:
        size = len(content.encode("utf-8"))
        if size > MAX_WRITE_BYTES:
            raise ValueError(f"write too large (limit {MAX_WRITE_BYTES} bytes)")
        target = self._resolve(path)
        if target.is_file():
            previous = target.stat().st_size
            if previous >= SHRINK_GUARD_MIN_BYTES and size < previous * SHRINK_GUARD_RATIO:
                raise ValueError(
                    f"this would replace a {previous}-byte file with {size} bytes; "
                    "edit it with replace_in_file instead of rewriting it"
                )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        self.actions.append({"tool": "write_file", "path": path, "bytes": size})
        self._pending_changes += 1
        return f"written {size} bytes to {path}"

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
        self._check_passed = completed.returncode == 0
        result = f"exit {completed.returncode}\n{output}"
        self._last_check = result
        self.actions.append({"tool": "run_check", "exit": completed.returncode,
                             "passed": self._check_passed})
        return self._clip(result)


__all__ = ["TOOLS", "WorkerOutcome", "WorkerSession"]
