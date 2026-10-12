"""The self-improvement core: judge a candidate from records, measure it, gate it.

O8 of `docs/READY-2026-10-12.md`. A candidate changes only the layer that decides
what one turn shows the model and how long it may run (`oneiro.dream.policy`); the
judge rebuilds what a candidate would have shown from *records alone* and never
executes the world (`oneiro.dream.replay`); the live leg runs each task at least
three times through the declared providers (`oneiro.dream.measure`), and a run cut
short can be resumed from the payload it wrote; promotion
happens only behind a gate with rollback (`oneiro.dream.gate`); a recorded turn is
read back read-only (`oneiro.dream.episode`).

Nothing here writes to the graph on its own. Reading a turn and judging a candidate
are read-only, `measure` writes only to the demo's own stream, and the two gate
writers (`record_experiment`, `publish_release`) are called explicitly.
"""
from __future__ import annotations

from oneiro.dream.cli import dream_command, main
from oneiro.dream.episode import Episode, EpisodeError, Step, read, recent_turns
from oneiro.dream.gate import (Criteria, Evidence, GateError, Verdict, open_experiment,
                               promote, publish_release, record_experiment, record_repeats,
                               rollback)
from oneiro.dream.measure import (APPLICABLE, DEMO_STREAM, MeasureError, Measurement, Run,
                                  Task, TaskResult, apply_policy, compare, measure,
                                  measure_tasks, missing_repeats, owner_for, seed_settings,
                                  unappliable)
from oneiro.dream.policy import (BASE, FIELDS, KNOBS, VARIANTS, PolicyError, TurnPolicy,
                                 get_policy)
from oneiro.dream.propose import Proposal, candidates, neighbours, propose
from oneiro.dream.replay import (NOT_RECORDED, Context, Estimate, Reconstruction, assemble,
                                 estimate, judge, judged_steps, read_context,
                                 verify_reconstruction)

__all__ = [
    "APPLICABLE", "BASE", "Context", "Criteria", "DEMO_STREAM", "Episode", "EpisodeError",
    "Estimate", "Evidence", "FIELDS", "GateError", "KNOBS", "MeasureError", "Measurement",
    "NOT_RECORDED", "PolicyError", "Proposal", "Reconstruction", "Run", "Step", "Task",
    "TaskResult", "TurnPolicy", "VARIANTS", "Verdict", "apply_policy", "assemble",
    "candidates", "compare", "dream_command", "estimate", "get_policy", "judge",
    "judged_steps", "main", "measure", "measure_tasks", "missing_repeats", "neighbours",
    "open_experiment", "owner_for", "promote", "propose", "publish_release", "read",
    "read_context", "recent_turns", "record_experiment", "record_repeats", "rollback",
    "seed_settings", "unappliable", "verify_reconstruction",
]
