"""Naming failures the way the field already names them.

MAST is the Multi-Agent System Failure Taxonomy from "Why Do Multi-Agent LLM Systems
Fail?" (Cemri, Pan, Yang and others, arXiv 2503.13657, NeurIPS 2025 Datasets and
Benchmarks track): 14 modes in 3 categories, derived from 1600+ annotated traces over
7 frameworks, with kappa = 0.88 between annotators. The frequencies below are theirs.

We adopt their names for one reason: a failure we cannot name cannot be counted, and a
count is the only thing that tells us whether our organisation is worth its cost. A
refusal we cannot classify honestly stays unlabelled instead of being forced into a
mode, because a wrong label is worse than no label.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

CITATION = "Cemri et al., Why Do Multi-Agent LLM Systems Fail?, arXiv 2503.13657"

FC1 = "FC1 System Design Issues"
FC2 = "FC2 Inter-Agent Misalignment"
FC3 = "FC3 Task Verification"

CATEGORIES = (FC1, FC2, FC3)


@dataclass(frozen=True)
class Mode:
    """One failure mode, with the share of traces it accounted for in the paper."""

    mode_id: str
    category: str
    name: str
    share: float
    meaning: str


MODES: tuple[Mode, ...] = (
    # FC1
    Mode("FM-1.1", FC1, "Disobey task specification", 0.118,
         "the system ignored a requirement it was given"),
    Mode("FM-1.2", FC1, "Disobey role specification", 0.015,
         "an agent did not act as its role says it should"),
    Mode("FM-1.3", FC1, "Step repetition", 0.157,
         "the same step was taken again instead of advancing"),
    Mode("FM-1.4", FC1, "Loss of conversation history", 0.028,
         "earlier context was dropped and the work restarted from nothing"),
    Mode("FM-1.5", FC1, "Unaware of termination conditions", 0.124,
         "the run kept going, or stopped, without meeting the stopping rule"),
    # FC2
    Mode("FM-2.1", FC2, "Conversation reset", 0.022,
         "the exchange restarted and lost the thread of work"),
    Mode("FM-2.2", FC2, "Fail to ask for clarification", 0.068,
         "the agent guessed where it should have asked"),
    Mode("FM-2.3", FC2, "Task derailment", 0.074,
         "the work drifted away from the task it was given"),
    Mode("FM-2.4", FC2, "Information withholding", 0.0085,
         "something known was not passed on to the other agent"),
    Mode("FM-2.5", FC2, "Ignored other agent's input", 0.019,
         "an instruction or correction was received and not used"),
    Mode("FM-2.6", FC2, "Reasoning-action mismatch", 0.132,
         "the stated plan and the action taken do not agree"),
    # FC3
    Mode("FM-3.1", FC3, "Premature termination", 0.062,
         "the task was declared finished before the work was done"),
    Mode("FM-3.2", FC3, "No or incomplete verification", 0.082,
         "the check performed was too shallow to catch the defect"),
    Mode("FM-3.3", FC3, "Incorrect verification", 0.091,
         "the check passed something that was in fact wrong"),
)

MODE_BY_ID = {mode.mode_id: mode for mode in MODES}


@dataclass(frozen=True)
class Label:
    mode: Mode
    reason: str

    def as_payload(self) -> dict:
        return {
            "mode_id": self.mode.mode_id,
            "category": self.mode.category,
            "name": self.mode.name,
            "reason": self.reason,
            "taxonomy": CITATION,
        }


def label_episode(record: dict) -> list[Label]:
    """Name what went wrong in one harness episode, from its own recorded fields.

    The rules read only what the episode actually recorded: how it stopped, whether
    the hidden checks passed, and how many steps it spent. Text the agent wrote is
    never treated as evidence, because claiming success is exactly what one of these
    modes is about.
    """
    labels: list[Label] = []
    if not isinstance(record, dict):
        return labels
    solved = record.get("solved")
    stop = str(record.get("stop_reason") or "")
    steps = int(record.get("tool_calls") or 0)
    final_text = str(record.get("final_text") or "")

    if stop == "max_steps":
        labels.append(Label(
            MODE_BY_ID["FM-1.5"],
            f"ran out of the step budget ({steps} calls) without meeting the stopping rule",
        ))
        if steps >= 12:
            labels.append(Label(
                MODE_BY_ID["FM-1.3"],
                f"{steps} tool calls with no passing result suggests repeating steps",
            ))
    if solved is False and stop == "finished":
        if final_text.strip():
            labels.append(Label(
                MODE_BY_ID["FM-3.3"],
                "declared the work done and the hidden checks still failed",
            ))
        else:
            labels.append(Label(
                MODE_BY_ID["FM-3.1"],
                "stopped without a passing result and without explanation",
            ))
    if solved is False and not final_text.strip() and stop == "":
        labels.append(Label(MODE_BY_ID["FM-1.5"], "episode ended with no recorded reason"))
    return labels


def label_judge_refusal(reason: str) -> Optional[Label]:
    """A candidate the judge sent back, in the taxonomy's terms.

    Ours is a verification decision, so the honest reading is a verification failure:
    either the check could not reach far enough, or it saw something that does not
    hold. Anything else stays unlabelled.
    """
    text = (reason or "").lower()
    if "coverage" in text or "not recovered" in text or "unrecoverable" in text:
        return Label(MODE_BY_ID["FM-3.2"], f"coverage rule refused it: {reason}")
    if "regress" in text or "worse" in text or "fails" in text:
        return Label(MODE_BY_ID["FM-3.3"], f"measured worse than the record it replaced: {reason}")
    return None


def label_tool_trace(steps: list[dict]) -> list[Label]:
    """Name failures visible in a recorded tool trace."""
    labels: list[Label] = []
    seen: dict[str, int] = {}
    for step in steps or []:
        if not isinstance(step, dict):
            continue
        signature = f"{step.get('name')}::{step.get('arguments')}"
        seen[signature] = seen.get(signature, 0) + 1
    repeats = {sig: n for sig, n in seen.items() if n >= 3}
    if repeats:
        signature = max(repeats, key=lambda key: repeats[key])
        labels.append(Label(
            MODE_BY_ID["FM-1.3"],
            f"the same call was made {repeats[signature]} times: {signature[:80]}",
        ))
    return labels


def summarize(labels: list[Label]) -> dict:
    """Count labels by category, the way the paper counts its traces."""
    counts = {category: 0 for category in CATEGORIES}
    for label in labels:
        counts[label.mode.category] = counts.get(label.mode.category, 0) + 1
    return counts
