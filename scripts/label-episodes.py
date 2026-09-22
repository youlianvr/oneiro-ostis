"""Name every recorded episode's failures, and count them the way the paper does.

    python scripts/label-episodes.py            # all recorded runs
    python scripts/label-episodes.py t07        # only runs whose name contains t07

Nothing is invented here: every label comes from a field the episode itself wrote
(stop reason, solved flag, tool call count), and an episode that does not fit a mode
stays unlabelled.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "python"))

from failure_taxonomy import CATEGORIES, MODE_BY_ID, label_episode, label_tool_trace  # noqa: E402

RUNS = PROJECT / "harness" / "lab" / "runs"


def main() -> int:
    needle = sys.argv[1] if len(sys.argv) > 1 else ""
    records = sorted(RUNS.glob(f"*{needle}*/record.json"))
    if not records:
        print(f"no recorded episodes under {RUNS} matching {needle!r}")
        return 0

    counts: Counter = Counter()
    per_label = Counter()
    unlabelled = []
    for path in records:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"unreadable: {path.name} ({exc})")
            continue
        labels = label_episode(record) + label_tool_trace(record.get("steps") or [])
        if not labels:
            unlabelled.append(record.get("label") or path.parent.name)
        for label in labels:
            counts[label.mode.category] += 1
            per_label[f"{label.mode.mode_id} {label.mode.name}"] += 1

    solved = sum(1 for path in records
                 if json.loads(path.read_text(encoding="utf-8")).get("solved") is True)
    print(f"episodes: {len(records)}  solved: {solved}  unlabelled: {len(unlabelled)}")
    print("\nby category (the paper's three):")
    for category in CATEGORIES:
        print(f"  {category:32s} {counts.get(category, 0)}")
    print("\nby mode:")
    for name, count in per_label.most_common():
        mode = MODE_BY_ID[name.split()[0]]
        print(f"  {count:3d}  {name:44s} share in the paper: {mode.share:.3%}")
    if unlabelled:
        shown = ", ".join(sorted(set(unlabelled))[:6])
        print(f"\nno mode fits (left unlabelled on purpose): {shown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
