"""Multi-seed series: does the dream improve reliably, and how honest is the judge?

Runs the recursive loop over several world seeds of a domain and aggregates:

  - per seed: day-1 measured score, final measured score, delta and ratio,
    the winning strategies along the way, tree growth;
  - calibration: every deployed winner's per-episode replay estimate (from the
    dream that chose it) against its measured online score on the next day —
    the judge's bias and mean absolute error are reported, per domain, without
    dressing.

Usage (one domain per process — a full run takes minutes):

    PYTHONPATH=python python -m series island      > /tmp/series-island.md
    PYTHONPATH=python python -m series workshop    > /tmp/series-workshop.md
"""

from __future__ import annotations

import os
import statistics
import sys
from dataclasses import dataclass, field
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "python"))

from bridge import OneiroBridge
from loop import run_loop
from loop_workshop import run_workshop_loop

HOST = os.environ.get("ONEIRO_HOST", "localhost")
PORT = int(os.environ.get("ONEIRO_PORT", "8090"))


@dataclass
class RoundRow:
    round_index: int
    strategy: str
    online_score: float
    winner: Optional[str] = None
    winner_est_per_episode: Optional[float] = None
    coverage: Optional[float] = None
    tree_steps: Optional[int] = None
    conflicts: Optional[int] = None


@dataclass
class SeedRun:
    domain: str
    seed: str
    rows: list[RoundRow] = field(default_factory=list)

    @property
    def day1(self) -> float:
        return self.rows[0].online_score

    @property
    def final(self) -> float:
        return self.rows[-1].online_score

    @property
    def delta(self) -> float:
        return self.final - self.day1

    @property
    def ratio(self) -> float:
        return self.final / self.day1 if self.day1 else float("inf")

    def calibration_pairs(self) -> list[tuple[float, float]]:
        """(replay per-episode estimate, measured online score of that same
        strategy on the next day) — only when the winner was actually deployed."""
        pairs: list[tuple[float, float]] = []
        for current, nxt in zip(self.rows, self.rows[1:]):
            if current.winner and nxt.strategy == current.winner and current.winner_est_per_episode is not None:
                pairs.append((current.winner_est_per_episode, nxt.online_score))
        return pairs


def run_island_seed(bridge, seed: str, rounds: int, limit: int) -> SeedRun:
    subject = f"series_island_{seed}_{int(__import__('time').time())}"
    report = run_loop(bridge, subject=subject, rounds=rounds, world_seed=seed, limit=limit)
    run = SeedRun(domain="island", seed=seed)
    for log in report.rounds:
        dr = log.dream_result
        run.rows.append(
            RoundRow(
                round_index=log.round_index,
                strategy=log.online.strategy_name,
                online_score=log.online.total_score,
                winner=dr.winner.name if dr else None,
                winner_est_per_episode=dr.winner_result.mean_score if dr else None,
                coverage=dr.winner_result.coverage if dr else None,
                tree_steps=dr.tree_summary.get("steps") if dr else None,
                conflicts=len(dr.consistency["conflicts"]) if dr else None,
            )
        )
    return run


def run_workshop_seed(bridge, seed: str, rounds: int, limit: int) -> SeedRun:
    subject = f"series_workshop_{seed}_{int(__import__('time').time())}"
    report = run_workshop_loop(bridge, subject=subject, rounds=rounds, world_seed=seed, limit=limit)
    run = SeedRun(domain="workshop", seed=seed)
    for log in report.rounds:
        dr = log.dream_result
        run.rows.append(
            RoundRow(
                round_index=log.round_index,
                strategy=log.online.strategy_name,
                online_score=log.online.total_score,
                winner=dr.winner.name if dr else None,
                winner_est_per_episode=dr.winner_result.mean_score if dr else None,
                coverage=dr.winner_result.coverage if dr else None,
                tree_steps=dr.tree_summary.get("steps") if dr else None,
                conflicts=len(dr.consistency["conflicts"]) if dr else None,
            )
        )
    return run


def summarise(runs: list[SeedRun]) -> str:
    lines: list[str] = []
    domain = runs[0].domain if runs else "?"
    lines.append(f"### {domain} — {len(runs)} seeds")
    lines.append("")
    lines.append("| seed | day 1 | final | delta | ratio | winners (by round) | replay est. per ep → measured next day | judge error |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for run in runs:
        winners = " → ".join(row.winner or "-" for row in run.rows)
        pairs = run.calibration_pairs()
        calib = "; ".join(f"{est:.1f} → {meas:.1f}" for est, meas in pairs) or "—"
        errors = ", ".join(f"{est - meas:+.1f}" for est, meas in pairs) or "—"
        lines.append(
            f"| `{run.seed}` | {run.day1:.1f} | {run.final:.1f} | **{run.delta:+.1f}** | {run.ratio:.2f}x "
            f"| {winners} | {calib} | {errors} |"
        )
    lines.append("")

    deltas = [run.delta for run in runs]
    ratios = [run.ratio for run in runs]
    improved = sum(1 for d in deltas if d > 1e-9)
    lines.append(
        f"- improved seeds: **{improved}/{len(runs)}**; "
        f"delta mean {statistics.mean(deltas):+.1f}, median {statistics.median(deltas):+.1f}, "
        f"min {min(deltas):+.1f}, max {max(deltas):+.1f}; "
        f"ratio mean {statistics.mean(ratios):.2f}x"
    )

    all_pairs = [pair for run in runs for pair in run.calibration_pairs()]
    if all_pairs:
        errs = [est - meas for est, meas in all_pairs]
        abs_errs = [abs(e) for e in errs]
        rel = [abs(e) / m * 100 for e, (_, m) in zip(errs, all_pairs) if m]
        lines.append(
            f"- judge calibration ({len(all_pairs)} deployed winners): bias {statistics.mean(errs):+.1f} "
            f"(replay − measured), MAE {statistics.mean(abs_errs):.1f}, "
            f"mean relative error {statistics.mean(rel):.1f}%"
        )
    else:
        lines.append("- judge calibration: no deployed winner was measured on a following day")
    lines.append("")
    conflicts = [row.conflicts for run in runs for row in run.rows if row.conflicts is not None]
    lines.append(f"- recording conflicts across all dream trees: {sum(conflicts)}")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    domain = argv[1] if len(argv) > 1 else "island"
    bridge = OneiroBridge(HOST, PORT)
    bridge.connect()

    if domain == "island":
        seeds = [f"oneiro-{i}" for i in range(int(os.environ.get("ONEIRO_SEEDS", "5")))]
        runs = [run_island_seed(bridge, s, rounds=int(os.environ.get("ONEIRO_ROUNDS", "3")), limit=24) for s in seeds]
    elif domain == "workshop":
        seeds = [f"workshop-{i}" for i in range(int(os.environ.get("ONEIRO_SEEDS", "3")))]
        runs = [run_workshop_seed(bridge, s, rounds=int(os.environ.get("ONEIRO_ROUNDS", "3")), limit=24) for s in seeds]
    else:
        print(f"unknown domain {domain!r}", file=sys.stderr)
        return 2

    print(summarise(runs), end="")
    bridge.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
