"""One bounded researcher-manager-worker heartbeat.

The runner is orchestration only. OSTIS owns durable session and organization
records, SwarmCoordinator owns role transitions, and WorktreeRunner owns the
isolated branch and PR evidence. No model, OpenClaw, merge, push, or approval
is performed here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence, Union

from bridge import LifeSession, OneiroBridge
from swarm import (
    CycleResult,
    ManagerDecision,
    PRPacket,
    Proposal,
    SwarmCoordinator,
)
from worktree_runner import CheckResult, Worktree, WorktreeRunner


WorkerEdit = Callable[[Proposal, Worktree], None]


@dataclass
class HeartbeatResult:
    """Result of one bounded heartbeat, including its preserved worktree."""

    session: LifeSession
    cycle: CycleResult
    worktree: Optional[Worktree]
    checks: tuple[CheckResult, ...]


class HeartbeatRunner:
    """Run one deterministic organization heartbeat against real boundaries."""

    def __init__(
        self,
        bridge: OneiroBridge,
        *,
        repository: Path,
        worktree_path: Path,
        branch: str,
        check_command: Sequence[str],
        pr_id: str,
        worker_edit: WorkerEdit,
    ) -> None:
        self.bridge = bridge
        self.worktree_runner = WorktreeRunner(repository)
        self.worktree_path = worktree_path
        self.branch = branch
        self.check_command = tuple(check_command)
        self.pr_id = pr_id
        self.worker_edit = worker_edit
        self._worktree: Optional[Worktree] = None
        self._checks: list[CheckResult] = []

    def run(
        self,
        *,
        session_id: str,
        researcher: Callable[[], Union[Proposal, Sequence[Proposal]]],
        manager: Callable[[Sequence[Proposal]], ManagerDecision],
        session: Optional[LifeSession] = None,
    ) -> HeartbeatResult:
        """Run one cycle and close the LifeSession on every outcome.

        A caller that owns a longer life (the loop) passes its existing
        session; the heartbeat then writes into it instead of starting a
        separate one, so one restart-visible biography covers both. A session
        the heartbeat started itself is also finished by the heartbeat.
        """
        self._active_session_id = session_id
        own_session = session is None
        if session is None:
            session = self.bridge.start_life_session(
                session_id,
                goals=[{"text": "complete one bounded organization heartbeat", "origin": "rule"}],
                self_state={"phase": "heartbeat", "origin": "rule"},
            )
        self.bridge.record_life_event(
            session,
            {"kind": "heartbeat_start", "branch": self.branch},
            origin="rule",
            verified=True,
        )
        self.bridge.record_organization_event(
            session_id=session_id,
            role="manager",
            kind="heartbeat_start",
            payload={"branch": self.branch, "check": list(self.check_command)},
            origin="rule",
            verified=True,
            record_id=f"heartbeat_start_{session_id}_{self.branch}",
        )

        coordinator = SwarmCoordinator(
            session_id=session_id,
            event_sink=lambda **event: self.bridge.record_organization_event(**event),
        )
        try:
            cycle = coordinator.run_cycle(
                researcher=researcher,
                manager=manager,
                worker=self._worker,
            )
            summary = {
                "status": "finished",
                "stopped_reason": cycle.stopped_reason,
                "pr_id": cycle.pr.pr_id if cycle.pr else None,
                "branch": cycle.pr.branch if cycle.pr else None,
                "checks": [list(check.command) for check in self._checks],
            }
            self.bridge.record_life_event(
                session,
                {"kind": "heartbeat_result", **summary},
                origin="rule",
                verified=True,
            )
            self.bridge.record_organization_event(
                session_id=session_id,
                role="manager",
                kind="heartbeat_end",
                payload=summary,
                origin="rule",
                verified=True,
                record_id=f"heartbeat_end_{session_id}_{self.branch}",
            )
            if own_session:
                self.bridge.finish_life_session(
                    session,
                    self_state={"phase": "finished", "pr_id": summary["pr_id"], "origin": "rule"},
                )
            return HeartbeatResult(session, cycle, self._worktree, tuple(self._checks))
        except Exception as exc:
            error = {"status": "failed", "error": str(exc), "branch": self.branch}
            self.bridge.record_life_event(
                session,
                {"kind": "heartbeat_error", **error},
                origin="rule",
                verified=True,
            )
            self.bridge.record_organization_event(
                session_id=session_id,
                role="manager",
                kind="heartbeat_error",
                payload=error,
                origin="rule",
                verified=True,
                record_id=f"heartbeat_error_{session_id}_{self.branch}",
            )
            if own_session:
                self.bridge.finish_life_session(
                    session,
                    self_state={"phase": "failed", "error": str(exc), "origin": "rule"},
                    status="failed",
                )
            raise

    def close(self) -> None:
        """Close the OSTIS connection; intentionally preserve the worktree."""
        self.bridge.close()

    def _worker(self, proposal: Proposal) -> PRPacket:
        if self._worktree is not None:
            raise RuntimeError("one heartbeat may create only one worktree")
        self._worktree = self.worktree_runner.create(self.worktree_path, self.branch)
        self.bridge.record_organization_event(
            session_id=self._session_id_from_path(),
            role="worker",
            kind="worktree_created",
            payload={"path": str(self._worktree.root), "branch": self._worktree.branch},
            origin="worker",
            verified=False,
            record_id=f"worktree_{self.pr_id}",
        )
        self.worker_edit(proposal, self._worktree)
        check = self.worktree_runner.run_check(self._worktree, self.check_command)
        self._checks.append(check)
        return self.worktree_runner.collect_pr_packet(
            self._worktree,
            pr_id=self.pr_id,
            summary=proposal.title,
            checks=self._checks,
        )

    def _session_id_from_path(self) -> str:
        """The coordinator passes the active id through the runner instance."""
        # Set by run before the callback can execute; keeping this private avoids
        # adding session ownership to WorktreeRunner.
        return self._active_session_id

    _active_session_id: str = ""
