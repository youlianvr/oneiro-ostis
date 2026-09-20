"""Safe worker-side worktree and PR evidence helpers.

The runner creates an isolated git worktree and collects evidence. It never
merges, pushes, publishes, or removes a worktree. Cleanup is an explicit owner
operation, not a hidden side effect of a heartbeat.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from swarm import PRPacket


class WorktreeError(RuntimeError):
    """Raised when the worker cannot establish a safe isolated branch."""


@dataclass(frozen=True)
class Worktree:
    root: Path
    branch: str


@dataclass(frozen=True)
class CheckResult:
    command: tuple[str, ...]
    returncode: int
    output: str

    @property
    def passed(self) -> bool:
        return self.returncode == 0


class WorktreeRunner:
    """Create isolated branches and collect review evidence."""

    def __init__(self, repository: Path):
        self.repository = repository.resolve()

    def create(self, path: Path, branch: str) -> Worktree:
        """Create a new branch worktree at ``path`` without touching main."""
        self._validate_branch(branch)
        target = path.resolve()
        if target.exists():
            raise WorktreeError(f"worktree path already exists: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        self._run(
            ["git", "-C", str(self.repository), "worktree", "add", "-b", branch, str(target), "HEAD"],
            cwd=self.repository,
        )
        return Worktree(root=target, branch=branch)

    def run_check(self, worktree: Worktree, command: Sequence[str]) -> CheckResult:
        """Run one declared check inside the worktree and capture its output."""
        if not command:
            raise WorktreeError("a check command is required")
        completed = subprocess.run(
            list(command),
            cwd=worktree.root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        return CheckResult(tuple(command), completed.returncode, completed.stdout or "")

    def collect_pr_packet(
        self,
        worktree: Worktree,
        *,
        pr_id: str,
        summary: str,
        checks: Sequence[CheckResult],
        skill_candidate: str | None = None,
    ) -> PRPacket:
        """Build a non-merged PR packet from the worktree state."""
        self._validate_branch(worktree.branch)
        if not pr_id or not summary:
            raise WorktreeError("PR evidence requires id and summary")
        if not checks or not all(check.passed for check in checks):
            raise WorktreeError("all declared checks must pass before a PR packet")
        names = self._run(
            ["git", "-C", str(worktree.root), "diff", "--name-only", "HEAD"],
            cwd=worktree.root,
        ).stdout
        changed_paths = tuple(line.strip() for line in names.splitlines() if line.strip())
        if not changed_paths:
            raise WorktreeError("PR packet cannot be empty")
        return PRPacket(
            pr_id=pr_id,
            branch=worktree.branch,
            summary=summary,
            tests=tuple(" ".join(check.command) for check in checks),
            changed_paths=changed_paths,
            skill_candidate=skill_candidate,
            merged=False,
            owner_approved=False,
        )

    @staticmethod
    def _validate_branch(branch: str) -> None:
        if not branch or branch in {"main", "master"} or branch.startswith("main/"):
            raise WorktreeError("worker branches must not target main or master")
        if branch.startswith("-"):
            raise WorktreeError("branch names cannot start with '-'")

    @staticmethod
    def _run(command: Sequence[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
        try:
            completed = subprocess.run(
                list(command),
                cwd=cwd,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
        except OSError as exc:
            raise WorktreeError(f"command failed to start: {command[0]}") from exc
        if completed.returncode != 0:
            raise WorktreeError(
                f"command failed ({completed.returncode}): {' '.join(command)}\n{completed.stdout or ''}"
            )
        return completed
