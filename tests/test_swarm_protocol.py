"""Offline tests for the bounded Oneiro organization protocol."""

import pytest

from swarm import (
    ManagerDecision,
    PRPacket,
    Proposal,
    SwarmCoordinator,
    SwarmProtocolError,
)


def proposal() -> Proposal:
    return Proposal(
        proposal_id="p-memory-test",
        title="Add a restart regression test",
        rationale="The last session exposed an untested restart path.",
        acceptance=("the test survives a fresh bridge connection",),
        evidence=("tests/test_core_loop.py",),
    )


def packet() -> PRPacket:
    return PRPacket(
        pr_id="pr-memory-test",
        branch="agent/p-memory-test",
        summary="Adds the restart regression test.",
        tests=("pytest tests/test_core_loop.py",),
        changed_paths=("tests/test_core_loop.py",),
        skill_candidate="restart-check",
    )


def test_manager_can_stop_without_worker():
    calls = []
    coordinator = SwarmCoordinator(
        session_id="s1",
        event_sink=lambda **event: calls.append(event),
    )

    result = coordinator.run_cycle(
        researcher=proposal,
        manager=lambda _: ManagerDecision("external_review", "Novel protocol boundary"),
        worker=lambda _: pytest.fail("worker must not run"),
    )

    assert result.pr is None
    assert result.stopped_reason == "manager action: external_review"
    assert [event["kind"] for event in calls] == [
        "research_proposal",
        "manager_decision",
        "external_review",
    ]


def test_worker_result_is_a_non_merged_pr_packet():
    result = SwarmCoordinator(session_id="s2").run_cycle(
        researcher=proposal,
        manager=lambda _: ManagerDecision("assign_worker", "Acceptance criteria are testable"),
        worker=lambda _: packet(),
    )

    assert result.pr is not None
    assert result.pr.branch == "agent/p-memory-test"
    assert result.pr.merged is False
    assert result.pr.owner_approved is False
    assert result.events[-1]["kind"] == "pr_packet"


def test_worker_cannot_return_main_or_approved_pr():
    with pytest.raises(SwarmProtocolError, match="main branch"):
        SwarmCoordinator(session_id="s3").run_cycle(
            researcher=proposal,
            manager=lambda _: ManagerDecision("assign_worker", "Proceed"),
            worker=lambda _: PRPacket(
                pr_id="bad",
                branch="main",
                summary="bad",
                tests=("pytest",),
            ),
        )

    with pytest.raises(SwarmProtocolError, match="approve"):
        SwarmCoordinator(session_id="s4").run_cycle(
            researcher=proposal,
            manager=lambda _: ManagerDecision("assign_worker", "Proceed"),
            worker=lambda _: PRPacket(
                pr_id="bad-approval",
                branch="agent/bad-approval",
                summary="bad",
                tests=("pytest",),
                owner_approved=True,
            ),
        )
