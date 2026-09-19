"""One-command demo: live episode -> graph -> dream -> improved behaviour.

    python demo/run_demo.py

Runs against the live oneiro-ostis stack, prints every number it produces and
writes the same transcript to docs/demo-log.md. Deterministic world: the two
measured scores are reproducible; only timestamps change.

What the audience sees:
  1. Day 1 — the agent lives an episode with its current (mediocre) strategy;
     every step is recorded into the OSTIS graph by the C++ agents.
  2. The graph — attempts come back out of the KB with provenance intact.
  3. The dream — candidate strategies proposed, each judged by exact replay
     over the recorded experience (no world execution), winner persisted.
  4. Day 2 — the winner acts online; the score improves.
"""

from __future__ import annotations

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "python"))

from adapter_llm import OfflineStrategyGenerator
from bridge import OneiroBridge
from dream import dream
from episode import run_episode
from strategy import strategy_survey, strategy_survey_reverse, strategy_weak_incumbent

HOST = os.environ.get("ONEIRO_HOST", "localhost")
PORT = int(os.environ.get("ONEIRO_PORT", "8090"))
LOG_PATH = os.path.join(ROOT, "docs", "demo-log.md")

LINES: list[str] = []


def say(line: str = "") -> None:
    print(line)
    LINES.append(line)


def main() -> int:
    bridge = OneiroBridge(HOST, PORT)
    bridge.connect()
    subject = f"demo_{int(time.time())}"

    say("# Oneiro-OSTIS — demo transcript")
    say()
    say(f"Stack: sc-machine at `{HOST}:{PORT}` (C++ agents), sc-web at `http://localhost:8000`.")
    say(f"Subject: `{subject}` · world: deterministic island expedition, seed `oneiro-0`.")
    say()

    # ---------- 0. before ----------
    strategies_before = bridge.load_strategies()
    say("## 0. Before")
    say()
    say(f"- strategy nodes in the graph: {len(strategies_before)}")
    say(f"- attempts recorded for this subject: {len(bridge.retrieve_attempts(subject))}")
    say()

    # ---------- 1. day 1 ----------
    say("## 1. Day 1 — the agent acts (current strategy)")
    say()
    incumbent = strategy_weak_incumbent()
    day1 = run_episode(bridge, subject, incumbent, episode_id=f"{subject}-d1", max_steps=40)
    bridge.mark_strategy_online_score(incumbent.name, day1.total_score)
    say(f"- strategy: `{incumbent.name}` — {incumbent.descriptor()}")
    say(f"- result: **{day1.total_score:.1f}** ({day1.summary()})")
    say()

    # ---------- 2. the graph holds the experience ----------
    say("## 2. The experience lives in the graph")
    say()
    attempts = bridge.retrieve_attempts(subject)
    say(f"- attempts recorded for the subject: **{len(attempts)}**")
    say(f"- retrieval from the KB returns them chronologically with provenance")
    say()
    say("| # | action | object | outcome | score | strategy | episode |")
    say("|---|---|---|---|---|---|---|")
    for i, rec in enumerate(attempts[:4]):
        say(
            f"| {i} | {rec.action} | {rec.object} | {rec.outcome} | "
            f"{rec.score if rec.score is not None else '-'} | {rec.strategy} | {rec.episode} |"
        )
    say(f"| … | ({len(attempts) - 4} more) | | | | | |")
    say()
    say("Open `http://localhost:8000` to browse the same graph in sc-web.")
    say()

    # ---------- 3. exploration ----------
    say("## 3. Exploration day (wider experience for the judge)")
    say()
    for explore_strategy in (strategy_survey(), strategy_survey_reverse()):
        episode = run_episode(
            bridge, subject, explore_strategy, episode_id=f"{subject}-{explore_strategy.name}", max_steps=40
        )
        say(f"- `{explore_strategy.name}`: {episode.total_score:.1f} ({episode.summary()})")
    say()

    # ---------- 4. the dream ----------
    say("## 4. The dream — proposals judged by exact replay")
    say()
    t0 = time.perf_counter()
    result = dream(
        bridge,
        subject,
        round_index=1,
        incumbent=incumbent,
        generator=OfflineStrategyGenerator(limit=24),
        limit=24,
    )
    elapsed = time.perf_counter() - t0
    say(
        f"- the judge replayed **{len(result.results)} candidates** over "
        f"{result.tree_summary['episodes']} recorded episodes "
        f"({result.tree_summary['steps']} steps, {result.tree_summary['transitions']} transitions) "
        f"in {elapsed:.1f}s — zero world executions"
    )
    say(f"- recordings consistent: {len(result.consistency['conflicts'])} conflicts")
    say()
    from replay.engine import REPLAY_HEADER

    say(REPLAY_HEADER)
    ranked = sorted(result.results, key=lambda p: p[1].estimated_score, reverse=True)
    for candidate, replay_result in ranked[:6] + [
        pair for pair in result.results if pair[0].name == incumbent.name
    ]:
        row = replay_result.as_row().rstrip()
        if candidate.name == result.winner.name:
            row += " **WINNER**"
        say(row)
    say()
    say(f"- winner: **`{result.winner.name}`** → {result.winner.descriptor()}")
    say(f"- saved to the graph as `strategy_{result.winner.name}` (class concept_strategy, "
        f"replay score {result.winner_result.estimated_score:.1f})")
    say()

    # ---------- 5. day 2 ----------
    say("## 5. Day 2 — the deployed winner acts online")
    say()
    day2 = run_episode(bridge, subject, result.winner, episode_id=f"{subject}-d2", max_steps=40)
    bridge.mark_strategy_online_score(result.winner.name, day2.total_score)
    say(f"- strategy: `{day2.strategy_name}`")
    say(f"- result: **{day2.total_score:.1f}** ({day2.summary()})")
    say()
    delta = day2.total_score - day1.total_score
    pct = 100.0 * delta / day1.total_score if day1.total_score else 0.0
    say("## 6. Verdict")
    say()
    say(f"| day | strategy | measured score |")
    say(f"|---|---|---|")
    say(f"| 1 | {day1.strategy_name} | {day1.total_score:.1f} |")
    say(f"| 2 | {day2.strategy_name} | {day2.total_score:.1f} |")
    say()
    say(f"**The dream improved the measured online score by {delta:+.1f} ({pct:+.0f}%)** "
        f"— judged only from recordings, proven in the world.")
    say()

    strategies_after = bridge.load_strategies()
    say(f"Graph after the demo: {len(strategies_after)} strategy nodes, "
        f"{len(bridge.retrieve_attempts(subject))} attempts for the subject, "
        f"online scores attached to the deployed strategies.")

    with open(LOG_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(LINES) + "\n")
    print(f"\n[transcript written to {os.path.relpath(LOG_PATH, ROOT)}]")

    bridge.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
