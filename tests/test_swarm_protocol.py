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
        manager=lambda _options: ManagerDecision("external_review", "Novel protocol boundary"),
        worker=lambda _: pytest.fail("worker must not run"),
    )

    assert result.pr is None
    assert result.stopped_reason == "manager action: external_review"
    assert [event["kind"] for event in calls] == [
        "research_options",
        "manager_decision",
        "external_review",
    ]


def test_worker_result_is_a_non_merged_pr_packet():
    result = SwarmCoordinator(session_id="s2").run_cycle(
        researcher=proposal,
        manager=lambda _options: ManagerDecision("assign_worker", "Acceptance criteria are testable"),
        worker=lambda _: packet(),
    )

    assert result.pr is not None
    assert result.pr.branch == "agent/p-memory-test"
    assert result.pr.merged is False
    assert result.pr.owner_approved is False
    assert [event["kind"] for event in result.events] == [
        "research_options",
        "manager_decision",
        "research_proposal",
        "pr_packet",
    ]


def test_manager_picks_one_of_several_offered_options():
    first = proposal()
    second = Proposal(
        proposal_id="p-cheaper",
        title="A smaller alternative",
        rationale="Needs one file and one test.",
        acceptance=("the check passes",),
        evidence=("python/roles.py",),
        check_id="unit-tests",
    )
    result = SwarmCoordinator(session_id="s-multi").run_cycle(
        researcher=lambda: [first, second],
        manager=lambda options: ManagerDecision(
            "assign_worker", "Second is cheaper", chosen="p-cheaper"),
        worker=lambda chosen: PRPacket(
            pr_id=f"pr-{chosen.proposal_id}",
            branch=f"agent/{chosen.proposal_id}",
            summary=chosen.title,
            tests=("pytest",),
        ),
    )

    assert result.pr is not None
    assert result.pr.branch == "agent/p-cheaper"
    options_event = result.events[0]
    assert options_event["kind"] == "research_options"
    assert [item["proposal_id"] for item in options_event["payload"]["options"]] == [
        "p-memory-test", "p-cheaper",
    ]
    proposal_event = result.events[2]
    assert proposal_event["kind"] == "research_proposal"
    assert proposal_event["payload"]["proposal_id"] == "p-cheaper"


def test_manager_cannot_pick_an_unoffered_option():
    with pytest.raises(SwarmProtocolError, match="was not offered"):
        SwarmCoordinator(session_id="s-bad").run_cycle(
            researcher=lambda: [proposal()],
            manager=lambda options: ManagerDecision(
                "assign_worker", "pick", chosen="p-nope"),
            worker=lambda _: packet(),
        )


def test_worker_cannot_return_main_or_approved_pr():
    with pytest.raises(SwarmProtocolError, match="main branch"):
        SwarmCoordinator(session_id="s3").run_cycle(
            researcher=proposal,
            manager=lambda _options: ManagerDecision("assign_worker", "Proceed"),
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
            manager=lambda _options: ManagerDecision("assign_worker", "Proceed"),
            worker=lambda _: PRPacket(
                pr_id="bad-approval",
                branch="agent/bad-approval",
                summary="bad",
                tests=("pytest",),
                owner_approved=True,
            ),
        )
