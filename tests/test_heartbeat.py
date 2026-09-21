"""Compact tests for the full bounded heartbeat wiring."""

from pathlib import Path

from bridge import LifeSession
from heartbeat import HeartbeatRunner
from swarm import ManagerDecision, PRPacket, Proposal
from worktree_runner import CheckResult, Worktree


class FakeBridge:
    def __init__(self):
        self.events = []
        self.sessions = []
        self.closed = False

    def start_life_session(self, session_id, **kwargs):
        session = LifeSession(session_id=session_id, created_at=1, **{})
        self.sessions.append(session)
        return session

    def record_life_event(self, session, event, **kwargs):
        session.events.append({**event, **kwargs})
        return session

    def record_organization_event(self, **event):
        self.events.append(event)

    def finish_life_session(self, session, *, self_state=None, status="finished"):
        session.status = status
        session.self_state = self_state or {}
        return session

    def close(self):
        self.closed = True


class FakeWorktreeRunner:
    def __init__(self):
        self.worktree = Worktree(Path("/preserved/heartbeat"), "agent/heartbeat")
        self.calls = []

    def create(self, path, branch):
        self.calls.append(("create", path, branch))
        return self.worktree

    def run_check(self, worktree, command):
        self.calls.append(("check", tuple(command)))
        return CheckResult(tuple(command), 0, "1 passed")

    def collect_pr_packet(self, worktree, *, pr_id, summary, checks, skill_candidate=None):
        self.calls.append(("packet", pr_id, tuple(check.command for check in checks)))
        return PRPacket(pr_id, worktree.branch, summary, tuple(" ".join(c.command) for c in checks), ("tests/generated.py",))


def make_proposal():
    return Proposal("hb-1", "Add a small regression test", "The path needs coverage", ("test passes",))


def test_heartbeat_wires_storage_roles_and_worker():
    bridge = FakeBridge()
    runner = HeartbeatRunner(
        bridge,
        repository=Path("/repo"),
        worktree_path=Path("/outside/worktree"),
        branch="agent/heartbeat",
        check_command=("python", "-m", "pytest", "tests/generated.py"),
        pr_id="pr-hb-1",
        worker_edit=lambda proposal, worktree: None,
    )
    fake_worktree = FakeWorktreeRunner()
    runner.worktree_runner = fake_worktree

    result = runner.run(
        session_id="hb-session",
        researcher=make_proposal,
        manager=lambda options: ManagerDecision("assign_worker", "small and testable"),
    )
    runner.close()

    assert result.cycle.pr is not None
    assert result.cycle.pr.merged is False
    assert result.worktree.branch == "agent/heartbeat"
    assert [call[0] for call in fake_worktree.calls] == ["create", "check", "packet"]
    assert [event["kind"] for event in bridge.events] == [
        "heartbeat_start",
        "research_options",
        "manager_decision",
        "research_proposal",
        "worktree_created",
        "pr_packet",
        "heartbeat_end",
    ]
    assert result.session.status == "finished"
    assert bridge.closed is True


def test_heartbeat_can_finish_without_worktree_when_manager_stops():
    bridge = FakeBridge()
    runner = HeartbeatRunner(
        bridge,
        repository=Path("/repo"),
        worktree_path=Path("/outside/worktree"),
        branch="agent/review",
        check_command=("pytest",),
        pr_id="pr-review",
        worker_edit=lambda proposal, worktree: None,
    )
    fake_worktree = FakeWorktreeRunner()
    runner.worktree_runner = fake_worktree

    result = runner.run(
        session_id="review-session",
        researcher=make_proposal,
        manager=lambda options: ManagerDecision("external_review", "needs evidence"),
    )

    assert result.worktree is None
    assert result.cycle.stopped_reason == "manager action: external_review"
    assert fake_worktree.calls == []
    assert result.session.status == "finished"


def test_heartbeat_restart_continues_the_same_biography():
    """A restarted heartbeat must continue the same OSTIS biography.

    The loop owns the session (as life_loop does) and hands it to each
    heartbeat. A second heartbeat run after a restart must write into that
    same session instead of starting a fresh one, so the session id is not
    reset and events accumulate on one biography.
    """
    bridge = FakeBridge()
    session = bridge.start_life_session("hb-session", goals=[], self_state={})

    def make_runner(pr_id):
        runner = HeartbeatRunner(
            bridge,
            repository=Path("/repo"),
            worktree_path=Path("/outside/worktree"),
            branch="agent/heartbeat",
            check_command=("python", "-m", "pytest", "tests/generated.py"),
            pr_id=pr_id,
            worker_edit=lambda proposal, worktree: None,
        )
        runner.worktree_runner = FakeWorktreeRunner()
        return runner

    first = make_runner("pr-hb-1").run(
        session_id="hb-session",
        researcher=make_proposal,
        manager=lambda options: ManagerDecision("assign_worker", "small and testable"),
        session=session,
    )
    events_after_first = len(session.events)

    # Second run simulates a restart: same shared bridge/storage, same session.
    second = make_runner("pr-hb-2").run(
        session_id="hb-session",
        researcher=make_proposal,
        manager=lambda options: ManagerDecision("assign_worker", "small and testable"),
        session=session,
    )

    # The biography is continued, not reset: same session object and id.
    assert second.session is session
    assert second.session.session_id == "hb-session"
    # Events accumulate on the same biography across the restart.
    assert len(second.session.events) > events_after_first
    # The loop-owned session is never finished by the heartbeat.
    assert second.session.status == "running"
