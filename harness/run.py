"""Run one task and record the episode.

    python harness/run.py --task t01-start-total
    python harness/run.py --task t01-start-total --policy cautious --label ablation
    python harness/run.py --task t01-start-total --agent opencode   # external reference

Our own agent is the default: it is the harness this project owns, and the one
the RSI loop will search over.
"""

from __future__ import annotations

import argparse

import agent
import runner
from policy import VARIANTS, get_policy


def main() -> None:
    parser = argparse.ArgumentParser(description="run one task, record one episode")
    parser.add_argument("--task", required=True)
    parser.add_argument("--agent", choices=["ours", "opencode"], default="ours")
    parser.add_argument("--policy", default="baseline", choices=sorted(VARIANTS))
    parser.add_argument("--model", default=None)
    parser.add_argument("--label", default=None)
    parser.add_argument("--timeout", type=float, default=900.0)
    args = parser.parse_args()

    runner.RUNS_DIR.mkdir(parents=True, exist_ok=True)

    if args.agent == "ours":
        policy = get_policy(args.policy)
        record = agent.run_task(
            args.task,
            model=args.model or agent.DEFAULT_MODEL,
            label=args.label or "ours",
            policy=policy,
            timeout=args.timeout,
        )
    else:
        record = runner.run_task(
            args.task,
            model=args.model or runner.DEFAULT_MODEL,
            label=args.label or "opencode",
            timeout=args.timeout,
        )

    print(runner.summary_line(record))
    if record.get("error"):
        print(f"error: {record['error']}")
    print(f"record: {record['scratch']}/record.json")


if __name__ == "__main__":
    main()
