"""Rehearse the phone path without inventing the owner's words or his press.

    python scripts/tg-rehearsal.py --text "пробный прогон"

What this does and does not do, because the difference is the whole design:

* it takes a job with **no task record**, so the graph never claims the owner
  handed something in that he did not: the record starts at "work started";
* it runs the real project loop, which costs real model calls, and it sends the
  real question to the owner's Telegram, buttons included;
* it never presses a button. The verdict, when it comes, is a press from his own
  account, recorded by the gateway. Until then the question stays open.

The honest result is a rehearsal: every link of the chain is exercised against
live parts, and the one link only a human can supply stays human.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "python"))

import task_runner as runner_module  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    text = "пробный прогон: посмотри, что можно улучшить в помощнике, и спроси меня"
    if "--text" in args:
        text = args[args.index("--text") + 1]
    runner = runner_module.runner_from_env()
    state = runner_module.TaskState(task_id="rehearsal-1", text=text, update_id=0)
    print(f"[rehearsal] work starts, no task record will be written for it: «{text}»")
    proposal_id = runner.work(state)
    if proposal_id is None:
        print("[rehearsal] no packet: the failure path was exercised, nothing was asked")
        return 2
    print(f"[rehearsal] question sent as {proposal_id}; waiting for the owner's press")
    print(f"[rehearsal] close it after the press: "
          f"python -c \"import task_runner as m; r=m.runner_from_env(); "
          f"print(r.collect(m.TaskState(task_id='rehearsal-1', text='{text}', "
          f"question='{proposal_id}', decision='approve')))\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
