"""The standalone surface: `python -m oneiro.dream <command>`.

The kernel is usable on its own, before anything is wired into the live agent:

* `record`  — what one recorded turn is, read back from the demo's own stream;
* `replay`  — how far a candidate can be judged from the records, with the proof;
* `propose` — the candidates the recordings can actually speak about, ordered;
* `measure` — the live leg: three repeats per task, through the providers the settings
  declare, in a root of the demo's own, and resumable from the payload it wrote so a
  measurement cut short by a failed turn is completed rather than bought again;
* `gate`    — the verdict on one measurement, and a promotion only when it passes.

Reads stay in the stream the demo writes to, so no command here can disturb the
records the owner's own work lives in. `measure` is the only command that writes
anything, and it writes to that same stream.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Callable

#: The submodules are imported from their own paths, not from the package: the package
#: rebinds `measure` and `propose` to the functions of those names, so `oneiro.dream.measure`
#: is a function and an alias taken from there would be one too.
from oneiro.dream import episode, gate, replay
from oneiro.dream.measure import (DEFAULT_REPEATS, DEMO_STREAM, TASKS, MeasureError,
                                  Measurement, compare, demo_root, measure_tasks, owner_for,
                                  seed_settings)
from oneiro.dream.policy import BASE, VARIANTS, PolicyError, TurnPolicy, get_policy
from oneiro.dream.propose import propose as propose_candidates
from oneiro.query import GraphQueryError


def _print(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _with_owner(root: Path, stream: str, work: Callable[[Any], Any]) -> Any:
    """Open the demo subject, do the work in one loop, and close it again."""
    owner = owner_for(Path(root), stream=stream)

    async def run() -> Any:
        try:
            return await work(owner)
        finally:
            await owner.close()

    return asyncio.run(run())


def _policy(args: argparse.Namespace) -> TurnPolicy:
    """The candidate named on the command line: a variant, then `--set` on top of it."""
    base = get_policy(args.policy) if getattr(args, "policy", "") else BASE
    overrides: dict[str, Any] = {}
    for item in getattr(args, "set", None) or []:
        name, _, raw = str(item).partition("=")
        if not name or not raw:
            raise PolicyError(f"--set expects knob=value, got {item!r}")
        overrides[name.strip()] = _coerce(raw.strip())
    if not overrides:
        return base
    descriptor = {**base.descriptor(), **overrides,
                  "name": args.set_name or "-".join(f"{k}={v}" for k, v in overrides.items())}
    return TurnPolicy.from_descriptor(descriptor)


def _coerce(raw: str) -> Any:
    lowered = raw.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    try:
        return int(raw)
    except ValueError:
        return raw


async def _episodes(owner: Any, turn: str, limit: int) -> list[episode.Episode]:
    ids = [turn] if turn else await episode.recent_turns(owner, limit=limit)
    found: list[episode.Episode] = []
    for turn_id in ids:
        found.append(await episode.read(owner, turn_id))
    return found


async def _contexts(owner: Any, turns: list[episode.Episode]) -> dict[str, replay.Context]:
    return {item.turn_id: await replay.read_context(owner, item) for item in turns}


# ------------------------------------------------------------------ commands


def record_command(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="oneiro.dream record",
                                     description="read recorded turns back")
    parser.add_argument("--turn", default="", help="one turn ID; default: the newest")
    parser.add_argument("--turns", type=int, default=3, help="how many newest turns")
    parser.add_argument("--stream", default=DEMO_STREAM)
    parser.add_argument("--root", default="")
    args = parser.parse_args(argv)
    root = Path(args.root) if args.root else Path.cwd()

    async def work(owner: Any) -> list[dict[str, Any]]:
        out = []
        for item in await _episodes(owner, args.turn, args.turns):
            context = await replay.read_context(owner, item)
            out.append({**item.to_dict(),
                        "context": {"facts": len(context.facts),
                                    "history": len(context.history)}})
        return out

    try:
        _print(_with_owner(root, args.stream, work))
    except (episode.EpisodeError, GraphQueryError) as exc:
        print(f"error: {exc}")
        return 2
    return 0


def replay_command(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="oneiro.dream replay",
                                     description="judge a candidate from records only")
    parser.add_argument("--turn", default="")
    parser.add_argument("--turns", type=int, default=3)
    parser.add_argument("--policy", default="", help=f"one of {', '.join(sorted(VARIANTS))}")
    parser.add_argument("--stream", default=DEMO_STREAM)
    parser.add_argument("--root", default="")
    args = parser.parse_args(argv)
    root = Path(args.root) if args.root else Path.cwd()

    async def work(owner: Any) -> dict[str, Any]:
        turns = await _episodes(owner, args.turn, args.turns)
        contexts = await _contexts(owner, turns)
        chosen = _policy(args)
        return {"policy": chosen.name,
                "estimates": [replay.estimate(turn, chosen, contexts[turn.turn_id]).to_dict()
                              for turn in turns],
                "reconstruction": [replay.verify_reconstruction(turn, contexts[turn.turn_id])
                                   .to_dict() for turn in turns]}

    try:
        _print(_with_owner(root, args.stream, work))
    except (episode.EpisodeError, PolicyError, GraphQueryError) as exc:
        print(f"error: {exc}")
        return 2
    return 0


def propose_command(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="oneiro.dream propose",
                                     description="the candidates the records can speak about")
    parser.add_argument("--turn", default="")
    parser.add_argument("--turns", type=int, default=5)
    parser.add_argument("--minimum-coverage", type=float, default=0.0)
    parser.add_argument("--stream", default=DEMO_STREAM)
    parser.add_argument("--root", default="")
    args = parser.parse_args(argv)
    root = Path(args.root) if args.root else Path.cwd()

    async def work(owner: Any) -> dict[str, Any]:
        turns = await _episodes(owner, args.turn, args.turns)
        contexts = await _contexts(owner, turns)
        found = propose_candidates(turns, contexts,
                                   minimum_coverage=args.minimum_coverage)
        return {"turns": [turn.turn_id for turn in turns],
                "candidates": [item.to_dict() for item in found]}

    try:
        _print(_with_owner(root, args.stream, work))
    except (episode.EpisodeError, GraphQueryError) as exc:
        print(f"error: {exc}")
        return 2
    return 0


def _resumed(args: argparse.Namespace) -> dict[str, Measurement]:
    """The runs a payload already holds, one measurement per side.

    A payload that cannot be read is refused before anything is spent, and a payload
    from another candidate is refused by `measure` itself, where the policy is known.
    """
    if not args.resume:
        return {}
    path = Path(args.resume)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise MeasureError(f"the measurement to resume from cannot be read: {exc}") from None
    sides = {side: Measurement.from_dict(payload[side])
             for side in ("control", "candidate")
             if isinstance(payload.get(side), dict)}
    if not sides:
        raise MeasureError(f"{str(path)!r} holds neither a control nor a candidate measurement")
    return sides


def measure_command(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="oneiro.dream measure",
                                     description="run every task three times under a candidate, "
                                                 "or finish a run that was cut short")
    parser.add_argument("--policy", default="", help=f"one of {', '.join(sorted(VARIANTS))}")
    parser.add_argument("--set", action="append", default=[],
                        help="knob=value, repeatable, on top of --policy")
    parser.add_argument("--set-name", default="")
    parser.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
    parser.add_argument("--task", action="append", default=[],
                        help="only these tasks, repeatable")
    parser.add_argument("--resume", default="", help="a payload written by --save: keep its "
                        "runs and run only the repeats that failed")
    parser.add_argument("--save", default="", help="write the payload here, so a measurement "
                        "that was cut short can be resumed")
    parser.add_argument("--stream", default=DEMO_STREAM)
    parser.add_argument("--root", default="", help="where the demo's own root goes")
    args = parser.parse_args(argv)

    chosen = _policy(args)
    tasks = tuple(task for task in TASKS
                  if not args.task or task.name in args.task)
    root = Path(args.root) if args.root else demo_root()
    workspace = root / "workspace"
    settings = seed_settings(root, workspace)
    print(f"root: {root}")
    print(f"settings: {settings}")
    print(f"stream: {args.stream}  repeats: {args.repeats}  tasks: "
          f"{', '.join(task.name for task in tasks)}")
    try:
        resumed = _resumed(args)
    except MeasureError as exc:
        print(f"error: {exc}")
        return 2
    if resumed:
        print("resumed: " + ", ".join(
            f"{side} keeps {item.runs} runs recorded, measured ("
            + ", ".join(f"{task.task}={len(task.measured)}" for task in item.tasks) + ")"
            for side, item in sorted(resumed.items())))

    async def run() -> dict[str, Any]:
        control = await measure_tasks(
            BASE, data_root=root, repeats=args.repeats, stream=args.stream, tasks=tasks,
            reuse=resumed.get("control"))
        payload: dict[str, Any] = {"control": control.to_dict()}
        if chosen.name != BASE.name:
            candidate = await measure_tasks(
                chosen, data_root=root, repeats=args.repeats, stream=args.stream, tasks=tasks,
                reuse=resumed.get("candidate"))
            payload["candidate"] = candidate.to_dict()
            payload["comparison"] = compare(control, candidate)
        return payload

    try:
        payload = asyncio.run(run())
    except (MeasureError, GraphQueryError) as exc:
        print(f"error: {exc}")
        return 2
    if args.save:
        Path(args.save).write_text(json.dumps(payload, ensure_ascii=False, indent=2,
                                              default=str), encoding="utf-8")
        print(f"saved: {args.save}")
    _print(payload)
    return 0


def gate_command(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="oneiro.dream gate",
                                     description="the verdict on one measurement")
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--control", default=BASE.name)
    parser.add_argument("--name", default="dream-measurement")
    parser.add_argument("--hypothesis", default="a smaller assembled context costs fewer tokens")
    parser.add_argument("--coverage", type=float, required=True)
    parser.add_argument("--saving", type=float, required=True)
    parser.add_argument("--repeats", type=int, required=True)
    parser.add_argument("--regressions", type=int, default=0)
    parser.add_argument("--coverage-floor", type=float, default=gate.Criteria().coverage_floor)
    parser.add_argument("--saving-threshold", type=float,
                        default=gate.Criteria().saving_threshold)
    parser.add_argument("--min-repeats", type=int, default=gate.Criteria().min_repeats)
    parser.add_argument("--max-regressions", type=int, default=gate.Criteria().max_regressions)
    parser.add_argument("--promote-version", default="")
    args = parser.parse_args(argv)

    criteria = gate.Criteria(coverage_floor=args.coverage_floor,
                             saving_threshold=args.saving_threshold,
                             min_repeats=args.min_repeats,
                             max_regressions=args.max_regressions)
    try:
        experiment = gate.record_repeats(gate.open_experiment(
            name=args.name, hypothesis=args.hypothesis, control=args.control,
            candidate=args.candidate, criteria=criteria), args.repeats)
        evidence = gate.Evidence(policy=args.candidate, coverage=args.coverage,
                                 saving=args.saving, repeats=args.repeats,
                                 regressions=args.regressions)
        verdict = gate.gate(experiment, criteria, evidence)
        payload: dict[str, Any] = {"experiment": experiment.to_dict(),
                                   "evidence": {"policy": evidence.policy,
                                                "coverage": evidence.coverage,
                                                "saving": evidence.saving,
                                                "repeats": evidence.repeats},
                                   "verdict": verdict.to_dict()}
        if args.promote_version and verdict.passed:
            release = gate.promote(experiment, criteria, evidence,
                                   version=args.promote_version)
            payload["release"] = release.to_dict()
            payload["rolled_back"] = gate.rollback(release, reason="cli dry run").to_dict()
    except gate.GateError as exc:
        print(f"error: {exc}")
        return 2
    _print(payload)
    return 0 if payload["verdict"]["passed"] else 2


COMMANDS: dict[str, Callable[[list[str]], int]] = {
    "record": record_command, "replay": replay_command, "propose": propose_command,
    "measure": measure_command, "gate": gate_command,
}


def main(argv: list[str] | None = None) -> int:
    """`oneiro.dream` on the command line. Returns the exit status."""
    parser = argparse.ArgumentParser(
        prog="oneiro.dream",
        description="the self-improvement core: judge a candidate from records, measure it, "
                    "and gate it")
    parser.add_argument("command", nargs="?", default="", choices=("", *COMMANDS))
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    if not args.command:
        parser.print_help()
        return 0
    return COMMANDS[args.command](args.arguments)


def dream_command(argv: list[str]) -> int:
    """The one agreed line: `oneiro.dream.main`, under the name `cli.py` calls."""
    return main(argv)


if __name__ == "__main__":                       # pragma: no cover - module entry
    sys.exit(main())
