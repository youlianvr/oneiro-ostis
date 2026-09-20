"""Offline tests for worker worktree safety."""

from pathlib import Path

import pytest

from swarm import PRPacket
from worktree_runner import CheckResult, Worktree, WorktreeError, WorktreeRunner


def test_protected_branches_are_rejected(tmp_path):
    runner = WorktreeRunner(tmp_path)
    with pytest.raises(WorktreeError, match="main"):
        runner.create(tmp_path / "main", "main")
    with pytest.raises(WorktreeError, match="main"):
        runner.create(tmp_path / "main2", "main/unsafe")


def test_failed_check_cannot_become_pr_packet(tmp_path):
    runner = WorktreeRunner(tmp_path)
    worktree = Worktree(tmp_path / "agent", "agent/test")
    with pytest.raises(WorktreeError, match="all declared checks"):
        runner.collect_pr_packet(
            worktree,
            pr_id="pr-1",
            summary="change",
            checks=[CheckResult(("pytest",), 1, "failed")],
        )


def test_packet_model_remains_unmerged():
    packet = PRPacket(
        pr_id="pr-2",
        branch="agent/test",
        summary="safe change",
        tests=("pytest",),
    )
    assert packet.merged is False
    assert packet.owner_approved is False
