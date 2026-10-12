"""The standalone surface: `python -m oneiro.dream <command>`.

The kernel has to be usable on its own, before anything is wired into the live agent, so
these tests drive the real entry point: a parser, its exit status, and one run of the
module as a separate process.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from chat_fakes import isolate
from oneiro.dream import cli
from oneiro.dream.cli import COMMANDS
from oneiro.dream.policy import PolicyError

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)


def test_the_surface_offers_the_five_commands_and_help_is_not_an_error(capsys):
    assert set(COMMANDS) == {"record", "replay", "propose", "measure", "gate"}

    assert cli.main([]) == 0
    assert "oneiro.dream" in capsys.readouterr().out


def test_the_gate_passes_or_refuses_with_its_exit_status(capsys):
    passed = cli.main(["gate", "--candidate", "windowed", "--coverage", "0.9",
                       "--saving", "0.3", "--repeats", "3"])
    verdict = json.loads(capsys.readouterr().out)["verdict"]

    assert passed == 0 and verdict["passed"] is True

    refused = cli.main(["gate", "--candidate", "windowed", "--coverage", "0.9",
                        "--saving", "0.01", "--repeats", "3"])
    verdict = json.loads(capsys.readouterr().out)["verdict"]

    assert refused == 2 and verdict["passed"] is False
    assert verdict["reasons"], "a refusal names the check that failed"


def test_the_gate_can_promote_and_then_undo_the_promotion(capsys):
    status = cli.main(["gate", "--candidate", "windowed", "--coverage", "0.9",
                       "--saving", "0.3", "--repeats", "3", "--promote-version", "1.1.0"])
    payload = json.loads(capsys.readouterr().out)

    assert status == 0
    assert payload["release"]["version"] == "1.1.0" and payload["release"]["promoted"] is True
    assert payload["rolled_back"]["rolled_back"] is True
    assert payload["rolled_back"]["promoted"] is False
    assert "rollback:cli dry run" in payload["rolled_back"]["labels"]


def test_a_candidate_is_a_variant_with_set_overrides_on_top():
    policy = cli._policy(argparse.Namespace(policy="windowed", set=["context_chars=2000"],
                                            set_name=""))

    assert policy.history_messages == 4, "the variant's own knob survives"
    assert policy.context_chars == 2000, "the override lands on top of it"
    assert policy.name == "context_chars=2000"


def test_an_override_that_is_not_a_knob_is_refused_by_name():
    with pytest.raises(PolicyError):
        cli._policy(argparse.Namespace(policy="", set=["nonsense=1"], set_name=""))

    with pytest.raises(PolicyError):
        cli._policy(argparse.Namespace(policy="", set=["history_messages"], set_name=""))


def test_the_measure_command_reports_a_graph_failure_cleanly(tmp_path, monkeypatch, capsys):
    """A busy graph is an error with an exit status, not a traceback."""
    from oneiro.query import GraphQueryError

    async def broken(*_args, **_kwargs):
        raise GraphQueryError("graph_timeout", "graph deadline exceeded")

    monkeypatch.setattr(cli, "measure_tasks", broken)
    status = cli.main(["measure", "--repeats", "3", "--root", str(tmp_path / "root")])

    printed = capsys.readouterr()
    assert status == 2
    assert "graph_timeout" in printed.out and "Traceback" not in printed.out


def test_the_measure_command_resumes_a_payload_and_saves_the_merged_one(tmp_path, monkeypatch,
                                                                       capsys):
    """`--resume` hands each side what it already holds; `--save` writes the result back."""
    from oneiro.dream import Measurement

    seen: list[tuple[str, object]] = []

    async def fake(policy, **kwargs):
        seen.append((policy.name, kwargs.get("reuse")))
        return Measurement(policy=policy.name, repeats=3, tasks=(), session=policy.name)

    monkeypatch.setattr(cli, "measure_tasks", fake)
    recorded = Measurement(policy="recorded", repeats=3, tasks=(), session="old")
    resume = tmp_path / "payload.json"
    resume.write_text(json.dumps({"control": recorded.to_dict()}), encoding="utf-8")
    saved = tmp_path / "merged.json"

    status = cli.main(["measure", "--policy", "windowed", "--root", str(tmp_path / "root"),
                       "--resume", str(resume), "--save", str(saved)])

    printed = capsys.readouterr().out
    assert status == 0, printed
    assert "resumed:" in printed
    assert seen[0][0] == "recorded", "the control is measured first, as the floor"
    assert seen[0][1].session == "old", "and it is handed what the payload holds"
    assert seen[1][1] is None, "this payload holds no candidate side yet"
    assert json.loads(saved.read_text(encoding="utf-8"))["control"]["policy"] == "recorded"


def test_the_measure_command_refuses_a_payload_it_cannot_resume(tmp_path, monkeypatch, capsys):
    """A payload that is not one is an error with a status, before anything is spent."""
    broken = tmp_path / "broken.json"
    broken.write_text("{ not json", encoding="utf-8")
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"control": "not a measurement"}), encoding="utf-8")

    status = cli.main(["measure", "--repeats", "3", "--root", str(tmp_path / "root"),
                       "--resume", str(broken)])
    printed = capsys.readouterr()
    assert status == 2 and "cannot be read" in printed.out
    assert "Traceback" not in printed.out

    status = cli.main(["measure", "--repeats", "3", "--root", str(tmp_path / "root"),
                       "--resume", str(empty)])
    printed = capsys.readouterr()
    assert status == 2 and "neither a control nor a candidate" in printed.out


def test_the_module_runs_as_a_separate_process():
    env = {**os.environ, "PYTHONPATH": str(ROOT / "python")}
    done = subprocess.run([sys.executable, "-m", "oneiro.dream", "gate", "--candidate",
                           "windowed", "--coverage", "0.9", "--saving", "0.3",
                           "--repeats", "3"],
                          cwd=str(ROOT), env=env, capture_output=True, text=True)

    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)["verdict"]["passed"] is True
