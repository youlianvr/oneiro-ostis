"""The long-lived loop: bounded cycles of the organization, restart-aware.

    python life_loop.py --cycles 2 --interval 60

The loop owns exactly four things: session continuity across restarts (the
biography lives in OSTIS, not in this process), the check allowlist, the
per-cycle budget, and the freeze records when something upstream breaks.

It does not own git (the worktree runner does), role logic (roles.py), model
access (llm.py), or storage (bridge.py). There is no merge, push, or approval
anywhere in this file.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Optional

from bridge import LifeSession, OneiroBridge
from heartbeat import HeartbeatRunner
from llm import BudgetExhausted, CallBudget, ModelPool, ProviderError
from roles import SchemaError, manager as manager_role, researcher as researcher_role
from swarm import Proposal
from worker import WorkerSession

PROJECT_SUBDIR = "projects/ostis/oneiro-ostis"
RUNNING_STATUSES = {"running", "interrupted"}

# The only commands a worker (or a manager's choice) may reach. They are
# fixed here, on purpose: model output selects an id, never a shell string.
ALLOWED_CHECKS: dict[str, tuple[tuple[str, ...], str]] = {
    "unit-tests": ((
        "python", "-m", "pytest", "-q", "-p", "no:cacheprovider",
        f"{PROJECT_SUBDIR}/tests/test_swarm_protocol.py",
        f"{PROJECT_SUBDIR}/tests/test_worktree_runner.py",
        f"{PROJECT_SUBDIR}/tests/test_heartbeat.py",
        f"{PROJECT_SUBDIR}/tests/test_hermes_plugin.py",
        f"{PROJECT_SUBDIR}/tests/test_llm.py",
        f"{PROJECT_SUBDIR}/tests/test_roles.py",
        f"{PROJECT_SUBDIR}/tests/test_worker.py",
        f"{PROJECT_SUBDIR}/tests/test_life_loop.py",
        f"{PROJECT_SUBDIR}/tests/test_bridge_vocabulary.py",
    ), "the organization layer and its adapters stay green"),
    "offline-suite": ((
        "python", "-m", "pytest", "-q", "-p", "no:cacheprovider",
        f"{PROJECT_SUBDIR}/tests/test_llm.py",
        f"{PROJECT_SUBDIR}/tests/test_roles.py",
        f"{PROJECT_SUBDIR}/tests/test_worker.py",
        f"{PROJECT_SUBDIR}/tests/test_life_loop.py",
        f"{PROJECT_SUBDIR}/tests/test_bridge_vocabulary.py",
        f"{PROJECT_SUBDIR}/tests/test_swarm_protocol.py",
        f"{PROJECT_SUBDIR}/tests/test_worktree_runner.py",
        f"{PROJECT_SUBDIR}/tests/test_heartbeat.py",
        f"{PROJECT_SUBDIR}/tests/test_hermes_plugin.py",
        f"{PROJECT_SUBDIR}/tests/test_replay_offline.py",
        f"{PROJECT_SUBDIR}/tests/test_metrics.py",
    ), "the whole offline suite stays green"),
}

DOSSIER_LIMIT = 9000


@dataclass
class LoopConfig:
    """Everything the loop needs to run; nothing it can invent."""

    repo_root: Path
    project_root: Path
    worktrees_root: Path
    cycles: int = 2
    interval_seconds: float = 60.0
    model_calls_per_cycle: int = 36
    worker_steps: int = 24
    host: str = "localhost"
    port: int = 8090
    run_tag: str = ""
    attempt: str = ""
    checks: Mapping[str, tuple[tuple[str, ...], str]] = field(
        default_factory=lambda: dict(ALLOWED_CHECKS)
    )

    def __post_init__(self) -> None:
        if not self.run_tag:
            self.run_tag = time.strftime("%Y%m%d%H%M%S")
        if not self.attempt:
            self.attempt = time.strftime("%H%M%S")
        self.repo_root = Path(self.repo_root).resolve()
        self.project_root = Path(self.project_root).resolve()
        self.worktrees_root = Path(self.worktrees_root).resolve()


def locate_paths() -> tuple[Path, Path]:
    """Project root from this file; repository root by walking to ``.git``."""
    project_root = Path(__file__).resolve().parents[1]
    for candidate in project_root.parents:
        if (candidate / ".git").exists():
            return candidate, project_root
    raise SystemExit("no .git above this file: run inside the workspace checkout")


def build_dossier(config: LoopConfig) -> str:
    """Real project material for the researcher: files, markers, open items."""
    parts: list[str] = []
    python_dir = config.project_root / "python"
    modules = sorted(python_dir.glob("*.py"))
    module_lines = [
        f"- python/{path.name} ({len(path.read_text(encoding='utf-8', errors='replace').splitlines())} lines)"
        for path in modules
    ]
    parts.append("## python modules\n" + "\n".join(module_lines))

    tests_dir = config.project_root / "tests"
    test_files = sorted(tests_dir.glob("test_*.py"))
    parts.append("## tests\n" + "\n".join(f"- tests/{p.name}" for p in test_files))

    markers: list[str] = []
    for path in list(modules) + list(test_files):
        for index, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
        ):
            if "TODO" in line or "FIXME" in line:
                markers.append(
                    f"{path.relative_to(config.repo_root).as_posix()}:{index} — {line.strip()[:110]}"
                )
    parts.append("## TODO/FIXME markers\n" + ("\n".join(markers[:20]) if markers else "[none found]"))

    plan = config.project_root / "docs" / "PLAN-MEMORY.md"
    if plan.is_file():
        text = plan.read_text(encoding="utf-8", errors="replace")
        excerpt = text[:1800]
        parts.append("## known open items (docs/PLAN-MEMORY.md, head)\n" + excerpt)

    goal = config.project_root / "docs" / "GOAL-LIVE-SWARM.md"
    if goal.is_file():
        parts.append("## current night goal (docs/GOAL-LIVE-SWARM.md)\n" + goal.read_text(
            encoding="utf-8", errors="replace")[:1500])

    checks = "\n".join(f"- {cid}: {argv[1] if len(argv) > 1 else ''} ({desc})"
                       for cid, (argv, desc) in config.checks.items())
    parts.append("## offered check ids\n" + checks)

    parts.append(
        "## how this cycle works\n"
        "One proposal becomes one change in an isolated worktree; the check must pass; "
        "the result is an unmerged PR packet a human reviews. Prefer a small, real, "
        "self-contained improvement that the offered checks can verify."
    )
    return "\n\n".join(parts)[:DOSSIER_LIMIT]


def attempt_names(config: LoopConfig, cycle_tag: str) -> tuple[Path, str, str]:
    """Worktree path, branch, and PR id for one attempt of one cycle.

    The attempt tag is what lets a restarted process run while the worktree
    and branch a killed process already left behind still exist; without it
    the restart would collide with its own debris and the biography would
    stall exactly when the resume matters.
    """
    stem = f"live-{config.run_tag}-a{config.attempt}-{cycle_tag}"
    return (config.worktrees_root / f"oneiro-{stem}", f"agent/{stem}", f"pr-{stem}")


def run_loop(
    config: LoopConfig,
    *,
    bridge: Optional[OneiroBridge] = None,
    pool: Optional[ModelPool] = None,
    sleep: Callable[[float], None] = time.sleep,
    echo: Callable[[str], None] = print,
) -> dict:
    """Run bounded cycles; write every outcome to OSTIS; freeze on real failure."""
    owns_bridge = bridge is None
    if bridge is None:
        bridge = OneiroBridge(host=config.host, port=config.port)
        bridge.connect()
    outcome: dict = {
        "run_tag": config.run_tag,
        "cycles_planned": config.cycles,
        "cycles_done": 0,
        "status": "running",
        "session_id": None,
        "prs": [],
        "freeze_reason": None,
    }

    def system_record(session_id: str, kind: str, payload: dict, record_id: str) -> None:
        bridge.record_organization_event(
            session_id=session_id, role="manager", kind=kind, payload=payload,
            origin="rule", verified=True, record_id=record_id,
        )

    session: Optional[LifeSession] = None
    try:
        latest = bridge.load_latest_life_session()
        if latest is not None and latest.status in RUNNING_STATUSES:
            session = latest
            bridge.record_life_event(
                session,
                {"kind": "process_restart", "run_tag": config.run_tag},
                origin="rule", verified=True,
            )
            system_record(session.session_id, "loop_resumed",
                          {"run_tag": config.run_tag},
                          f"loop_resume_{config.run_tag}")
            echo(f"[loop] resumed session {session.session_id} after a restart")
        else:
            session = bridge.start_life_session(
                f"life-{config.run_tag}",
                goals=[{"text": "run bounded organization cycles toward one real PR packet",
                        "origin": "rule"}],
                self_state={"phase": "loop", "origin": "rule"},
            )
            system_record(session.session_id, "loop_start",
                          {"run_tag": config.run_tag, "cycles": config.cycles},
                          f"loop_start_{config.run_tag}")
        outcome["session_id"] = session.session_id

        if pool is None:
            try:
                pool = ModelPool()
            except ProviderError as exc:
                _freeze(bridge, session, outcome, "provider_key", str(exc), echo, config)
                return outcome

        dossier = build_dossier(config)

        for index in range(1, config.cycles + 1):
            cycle_tag = f"c{index}"
            budget = CallBudget(config.model_calls_per_cycle)
            echo(f"[loop] cycle {index}/{config.cycles} ({cycle_tag})")

            try:
                proposals = researcher_role(
                    pool, dossier, list(config.checks), budget=budget,
                    prefix=f"{config.run_tag}-{cycle_tag}-p",
                )
            except BudgetExhausted as exc:
                _freeze(bridge, session, outcome, "budget", str(exc), echo, config)
                break
            except ProviderError as exc:
                _freeze(bridge, session, outcome, "provider_down", str(exc)[:600], echo, config)
                break
            except SchemaError as exc:
                system_record(session.session_id, "cycle_schema_error",
                              {"cycle": cycle_tag, "error": str(exc)[:600],
                               "model_calls": pool.evidence()},
                              f"schema_{config.run_tag}_{cycle_tag}")
                echo(f"[loop] researcher schema error in {cycle_tag}: {exc}")
                continue

            try:
                decision = manager_role(pool, proposals, dossier, budget=budget)
            except BudgetExhausted as exc:
                _freeze(bridge, session, outcome, "budget", str(exc), echo, config)
                break
            except ProviderError as exc:
                _freeze(bridge, session, outcome, "provider_down", str(exc)[:600], echo, config)
                break
            except SchemaError as exc:
                system_record(session.session_id, "cycle_schema_error",
                              {"cycle": cycle_tag, "error": str(exc)[:600],
                               "model_calls": pool.evidence()},
                              f"schema_{config.run_tag}_{cycle_tag}")
                echo(f"[loop] manager schema error in {cycle_tag}: {exc}")
                continue

            system_record(session.session_id, "model_evidence",
                          {"cycle": cycle_tag, "calls": pool.evidence(),
                           "proposals": [p.proposal_id for p in proposals]},
                          f"evidence_{config.run_tag}_{cycle_tag}")

            if decision.action != "assign_worker":
                echo(f"[loop] manager chose {decision.action}: {decision.reason[:160]}")
                if decision.action in ("escalate", "external_review"):
                    outcome["status"] = "waiting_owner"
                    outcome["freeze_reason"] = f"manager action: {decision.action}"
                    break
                continue

            chosen = next(
                (p for p in proposals if p.proposal_id == (decision.chosen or proposals[0].proposal_id)),
                None,
            )
            if chosen is None or chosen.check_id not in config.checks:
                system_record(session.session_id, "cycle_failed",
                              {"cycle": cycle_tag, "error": "chosen proposal has an unusable check id"},
                              f"cycle_failed_{config.run_tag}_{cycle_tag}")
                echo("[loop] chosen proposal has an unusable check id; cycle skipped")
                continue

            check_command, _ = config.checks[chosen.check_id]
            worktree_path, branch, pr_id = attempt_names(config, cycle_tag)

            outcome_box: dict = {}

            def worker_edit(proposal: Proposal, worktree, _outcome=outcome_box,
                            _command=check_command, _budget=budget) -> None:
                worker_session = WorkerSession(
                    pool=pool, proposal=proposal, worktree_root=worktree.root,
                    check_command=_command, budget=_budget,
                    scope=PROJECT_SUBDIR, step_limit=config.worker_steps,
                )
                _outcome["worker"] = worker_session.run()

            heartbeat = HeartbeatRunner(
                bridge=bridge, repository=config.repo_root,
                worktree_path=worktree_path, branch=branch,
                check_command=check_command, pr_id=pr_id, worker_edit=worker_edit,
            )
            try:
                result = heartbeat.run(
                    session_id=session.session_id,
                    researcher=lambda: proposals,
                    manager=lambda _options: decision,
                    session=session,
                )
            except Exception as exc:  # noqa: BLE001 - recorded, never swallowed
                system_record(session.session_id, "cycle_failed",
                              {"cycle": cycle_tag, "error": str(exc)[:600],
                               "worker": outcome_box.get("worker", {}) and
                               outcome_box["worker"].__dict__},
                              f"cycle_failed_{config.run_tag}_{cycle_tag}")
                echo(f"[loop] cycle {cycle_tag} failed: {exc}")
                continue

            pr = result.cycle.pr
            worker_outcome = outcome_box.get("worker")
            if pr is not None:
                outcome["prs"].append({
                    "pr_id": pr.pr_id, "branch": pr.branch,
                    "changed_paths": list(pr.changed_paths), "tests": list(pr.tests),
                })
            system_record(session.session_id, "cycle_finished",
                          {"cycle": cycle_tag,
                           "pr": pr.__dict__ if pr else None,
                           "worker": worker_outcome.__dict__ if worker_outcome else None,
                           "model_calls": pool.evidence()},
                          f"cycle_finished_{config.run_tag}_{cycle_tag}")
            outcome["cycles_done"] = index
            if pr is not None:
                echo(f"[loop] PR packet {pr.pr_id} on {pr.branch}: "
                     f"{len(pr.changed_paths)} changed path(s), tests: {'; '.join(pr.tests)}")
            else:
                echo(f"[loop] cycle {cycle_tag} stopped at: {result.cycle.stopped_reason}")

            if index < config.cycles:
                sleep(config.interval_seconds)

    except KeyboardInterrupt:
        outcome["status"] = "interrupted"
        if session is not None:
            bridge.record_life_event(session, {"kind": "loop_interrupted"},
                                     origin="rule", verified=True)
            system_record(session.session_id, "loop_interrupted", {},
                          f"loop_interrupted_{config.run_tag}")
    finally:
        if session is not None and outcome["status"] in ("running", "interrupted", "waiting_owner"):
            if outcome["status"] == "running":
                outcome["status"] = "finished"
            bridge.record_life_event(
                session,
                {"kind": "loop_end", "status": outcome["status"],
                 "prs": [item["pr_id"] for item in outcome["prs"]]},
                origin="rule", verified=True,
            )
            system_record(session.session_id, "loop_end",
                          {"status": outcome["status"],
                           "prs": [item["pr_id"] for item in outcome["prs"]]},
                          f"loop_end_{config.run_tag}")
            bridge.finish_life_session(
                session,
                self_state={"phase": outcome["status"],
                            "prs": [item["pr_id"] for item in outcome["prs"]],
                            "origin": "rule"},
                status=outcome["status"],
            )
        if owns_bridge:
            bridge.close()
    return outcome


def _freeze(
    bridge: OneiroBridge,
    session: LifeSession,
    outcome: dict,
    kind: str,
    reason: str,
    echo: Callable[[str], None],
    config: LoopConfig,
) -> None:
    """Stop the run with the reason recorded; nothing is retried forever."""
    payload = {"kind": kind, "reason": reason, "run_tag": config.run_tag}
    bridge.record_life_event(session, {"kind": "loop_frozen", **payload},
                             origin="rule", verified=True)
    bridge.record_organization_event(
        session_id=session.session_id, role="manager", kind="loop_frozen",
        payload=payload, origin="rule", verified=True,
        record_id=f"loop_frozen_{config.run_tag}_{kind}",
    )
    bridge.finish_life_session(
        session,
        self_state={"phase": "frozen", "reason": reason, "origin": "rule"},
        status="frozen",
    )
    outcome["status"] = "frozen"
    outcome["freeze_reason"] = reason
    echo(f"[loop] frozen ({kind}): {reason}")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="One bounded run of the Oneiro swarm")
    parser.add_argument("--cycles", type=int, default=2)
    parser.add_argument("--interval", type=float, default=60.0)
    parser.add_argument("--model-calls-per-cycle", type=int, default=36)
    parser.add_argument("--worker-steps", type=int, default=24)
    parser.add_argument("--host", default=os.environ.get("ONEIRO_HOST", "localhost"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("ONEIRO_PORT", "8090")))
    parser.add_argument("--worktrees-root", type=Path,
                        default=Path.home() / ".openclaw" / "worktrees")
    parser.add_argument("--run-tag", default="")
    args = parser.parse_args(argv)

    repo_root, project_root = locate_paths()
    config = LoopConfig(
        repo_root=repo_root, project_root=project_root,
        worktrees_root=args.worktrees_root, cycles=args.cycles,
        interval_seconds=args.interval,
        model_calls_per_cycle=args.model_calls_per_cycle,
        worker_steps=args.worker_steps, host=args.host, port=args.port,
        run_tag=args.run_tag,
    )
    outcome = run_loop(config)
    print(json.dumps(outcome, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
