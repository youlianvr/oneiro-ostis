"""Aggregate episode records into a results table.

    python harness/report.py                      # every record on disk
    python harness/report.py --policy baseline
    python harness/report.py --label baseline > docs/rsi-results.md

One row per episode, one summary per (policy, model) group. Nothing here is
computed by hand; the numbers come from `record.json` files written by the
runner.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

RUNS_DIR = Path(__file__).resolve().parent / "lab" / "runs"


def load_records(label: str | None = None, policy: str | None = None) -> list[dict]:
    records = []
    for path in sorted(RUNS_DIR.glob("*/record.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if label and record.get("label") != label:
            continue
        if policy and (record.get("policy") or {}).get("name") != policy:
            continue
        record["_path"] = str(path.parent.name)
        records.append(record)
    return records


def group_key(record: dict) -> str:
    policy = (record.get("policy") or {}).get("name")
    agent = record.get("agent", "opencode")
    return policy or agent


def mean(values: list[float]) -> str:
    return f"{statistics.mean(values):.1f}" if values else "-"


def render(records: list[dict]) -> str:
    if not records:
        return "_no records yet_"

    lines: list[str] = []
    groups: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        groups[group_key(record)].append(record)

    for name in sorted(groups):
        rows = sorted(groups[name], key=lambda r: r["task"])
        solved = sum(1 for r in rows if r.get("solved"))
        lines.append(f"### harness policy: `{name}`")
        lines.append("")
        lines.append("| task | kind | solved | steps | tool calls | input tok | output tok | total tok | seconds |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for record in rows:
            tokens = record.get("tokens") or {}
            lines.append(
                f"| `{record['task']}` | {record.get('kind', '')} | "
                f"{'yes' if record.get('solved') else '**no**'} | "
                f"{len(record.get('steps') or [])} | {record.get('tool_calls', 0)} | "
                f"{tokens.get('input', 0)} | {tokens.get('output', 0)} | "
                f"{tokens.get('total', 0)} | {record.get('wall_seconds', 0)} |"
            )
            if record.get("error"):
                lines.append(f"| | | error | {record['error'][:80]} | | | | | |")
        lines.append("")
        totals = [sum((r.get("tokens") or {}).get(k, 0) for k in ("input", "output", "total"))
                  for r in rows]
        lines.append(
            f"- solved: **{solved}/{len(rows)}**; "
            f"mean total tokens {mean(totals)}; "
            f"mean wall {mean([r.get('wall_seconds', 0) for r in rows])}s; "
            f"model `{rows[0].get('model', '?')}`"
        )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="results table from recorded episodes")
    parser.add_argument("--label")
    parser.add_argument("--policy")
    args = parser.parse_args()
    print(render(load_records(args.label, args.policy)))


if __name__ == "__main__":
    main()
