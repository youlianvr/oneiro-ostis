"""Partial replay over recorded episodes: the judge.

A dream proposes candidate harness policies. To judge them without spending
tokens, we recompute what each candidate *would have been shown* at every step
of an already recorded episode. Three kinds of outcome, kept apart on purpose:

  exact    the context a candidate policy assembles is a deterministic function
           of the recording (prompt text, history window, observation clipping,
           per-step prompt size in characters), so it is recomputed, not guessed;
  abstain  what the *model* would then decide is not replayable: a different
           context means a different decision, and nothing in the recording can
           tell us what it would be. Those steps are marked uncovered;
  honest   the token model (tokens = a + b * characters) is fitted on the
           episode it predicts, and its accuracy is reported separately as
           held-out error: half the steps for fitting, the other half for
           checking, plus leave-one-task-out across episodes.

`verify_reconstruction` is the exactness test: replaying the *recorded* policy
must reproduce the recorded per-step prompt sizes character for character. If
that ever fails, the judge's model of the harness is wrong and every estimate
below it is void.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

import agent
from policy import VARIANTS, HarnessPolicy, get_policy

RUNS_DIR = Path(__file__).resolve().parent / "lab" / "runs"


# ---------- loading ----------


# A run that ended in an error, a timeout or a provider refusal is not evidence
# about the policy that produced it: it says nothing about whether the agent
# could have solved the task, and its token count is a partial one. Such a run
# must not calibrate the judge, because the judge would then predict savings
# against a bar that no honest run ever set.
NORMAL_STOPS = {"finished", "max_steps", "stopped"}


def load_records(label: str | None = None, normal_only: bool = True) -> list[dict]:
    records = []
    for path in sorted(RUNS_DIR.glob("*/record.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not record.get("blocks") or not record.get("steps"):
            continue  # recorded before the judge existed: nothing to replay on
        if label and record.get("label") != label:
            continue
        if normal_only and record.get("stop_reason") not in NORMAL_STOPS:
            continue
        record["_path"] = str(path.parent.name)
        records.append(record)
    return records


# ---------- the assembly model ----------


def system_text(record: dict, policy: HarnessPolicy) -> str:
    """The system prompt this policy would have produced."""
    setup = record.get("setup") or {}
    return agent.system_prompt(
        policy,
        setup.get("file_list") if policy.include_file_list else None,
        setup.get("initial_tests") if policy.include_initial_tests else None,
    )


def clip(text: str, limit: int) -> str:
    if limit and len(text) > limit:
        return text[:limit] + f"\n... [{len(text) - limit} characters truncated]"
    return text


def assemble(record: dict, policy: HarnessPolicy, step_index: int) -> list[dict]:
    """Messages the policy would send when sending step `step_index`."""
    step = record["steps"][step_index]
    blocks = record["blocks"][: step.get("history_len", step_index)]
    if policy.context_mode == "window":
        blocks = blocks[-max(1, policy.window_steps):]
    messages = [
        {"role": "system", "content": system_text(record, policy)},
        {"role": "user", "content": record["user_prompt"]},
    ]
    for block in blocks:
        for message in block:
            copy = dict(message)
            if copy.get("role") == "tool":
                copy["content"] = clip(copy.get("content") or "", policy.observation_chars)
            messages.append(copy)
    return messages


def assembled_chars(messages: list[dict]) -> int:
    return sum(len(m.get("content") or "") for m in messages)


def verify_reconstruction(record: dict) -> dict:
    """Does replaying the recorded policy reproduce the recorded prompt sizes?"""
    policy = HarnessPolicy.from_descriptor(record["policy"])
    expected = [s.get("prompt_chars", 0) for s in record["steps"]]
    rebuilt = [assembled_chars(assemble(record, policy, i))
               for i in range(len(record["steps"]))]
    return {
        "steps": len(rebuilt),
        "chars_match": rebuilt == expected,
        "first_mismatch": next((i for i, (a, b) in enumerate(zip(rebuilt, expected))
                                if a != b), None),
        "rebuilt": rebuilt,
    }


# ---------- the token model ----------


@dataclass
class TokenModel:
    """tokens = intercept + slope * characters."""

    intercept: float = 0.0
    slope: float = 0.0
    fitted_on: int = 0
    in_split_error: float = 0.0

    def predict(self, chars: float) -> float:
        return self.intercept + self.slope * chars


def _least_squares(pairs: list[tuple[int, int]]) -> tuple[float, float]:
    n = len(pairs)
    if n == 0:
        return 0.0, 0.0
    sum_x = sum(x for x, _ in pairs)
    sum_y = sum(y for _, y in pairs)
    sum_xx = sum(x * x for x, _ in pairs)
    sum_xy = sum(x * y for x, y in pairs)
    denominator = n * sum_xx - sum_x * sum_x
    if denominator == 0:
        return (sum_y / n, 0.0)
    slope = (n * sum_xy - sum_x * sum_y) / denominator
    return ((sum_y - slope * sum_x) / n, slope)


def _pairs(record: dict) -> list[tuple[int, int]]:
    return [(s.get("prompt_chars", 0), s.get("tokens", {}).get("input", 0))
            for s in record["steps"] if s.get("tokens", {}).get("input")]


def fit_token_model(record: dict) -> TokenModel:
    """Fit on everything, and report how well it predicts unseen steps."""
    pairs = _pairs(record)
    if not pairs:
        return TokenModel()
    intercept, slope = _least_squares(pairs)
    model = TokenModel(intercept=intercept, slope=slope, fitted_on=len(pairs))

    if len(pairs) >= 3:
        split = len(pairs) // 2
        check_intercept, check_slope = _least_squares(pairs[:split])
        errors = [abs((check_intercept + check_slope * chars) - tokens) / tokens
                  for chars, tokens in pairs[split:] if tokens]
        model.in_split_error = sum(errors) / len(errors) if errors else 0.0
    return model


def cross_validate(records: list[dict]) -> dict:
    """Fit the token model on other tasks, predict this one. The honest error."""
    if len(records) < 2:
        return {"episodes": 0, "mean_relative_error": 0.0, "max_relative_error": 0.0}
    errors: list[float] = []
    for record in records:
        others = [pair for other in records if other is not record for pair in _pairs(other)]
        intercept, slope = _least_squares(others)
        for chars, tokens in _pairs(record):
            if tokens:
                errors.append(abs((intercept + slope * chars) - tokens) / tokens)
    if not errors:
        return {"episodes": 0, "mean_relative_error": 0.0, "max_relative_error": 0.0}
    return {
        "episodes": len(records),
        "mean_relative_error": sum(errors) / len(errors),
        "max_relative_error": max(errors),
    }


# ---------- the estimate ----------


@dataclass
class Estimate:
    task: str
    policy: str
    steps_covered: int = 0
    steps_total: int = 0
    prompt_chars_predicted: int = 0
    prompt_chars_recorded: int = 0
    prompt_tokens_predicted: float = 0.0
    prompt_tokens_recorded: float = 0.0
    dropped_observations: int = 0
    truncation_saved_chars: int = 0
    redundant_reads: int = 0
    repeated_commands: int = 0
    held_out_error: float = 0.0
    notes: list[str] = field(default_factory=list)

    @property
    def saving_ratio(self) -> float:
        if not self.prompt_tokens_recorded:
            return 1.0
        return self.prompt_tokens_predicted / self.prompt_tokens_recorded

    @property
    def decision_replayable(self) -> float:
        return self.steps_covered / self.steps_total if self.steps_total else 0.0


def _redundancy(record: dict) -> tuple[int, int]:
    """Reads of a file with no edit in between, and repeated identical commands."""
    read_before: set[str] = set()
    redundant = 0
    commands: dict[str, int] = {}
    for action in record.get("trajectory") or []:
        tool = action.get("tool")
        args = action.get("args") or {}
        if tool == "read_file":
            path = str(args.get("path"))
            if path in read_before:
                redundant += 1
            read_before.add(path)
        elif tool in ("edit_file", "write_file"):
            read_before = {str(args.get("path"))}
        elif tool in ("run_command", "run_tests"):
            key = str(args.get("command", tool))
            commands[key] = commands.get(key, 0) + 1
    return redundant, sum(count - 1 for count in commands.values() if count > 1)


def estimate(record: dict, policy: HarnessPolicy) -> Estimate:
    """Judge one candidate policy on one recorded episode."""
    result = Estimate(task=record["task"], policy=policy.name)
    result.steps_total = len(record["steps"])
    recorded_policy = HarnessPolicy.from_descriptor(record["policy"])
    model = fit_token_model(record)
    result.held_out_error = model.in_split_error

    for index, step in enumerate(record["steps"]):
        candidate_messages = assemble(record, policy, index)
        recorded_messages = assemble(record, recorded_policy, index)
        chars = assembled_chars(candidate_messages)
        result.prompt_chars_predicted += chars
        result.prompt_chars_recorded += step.get("prompt_chars", 0)
        result.prompt_tokens_predicted += model.predict(chars)
        result.prompt_tokens_recorded += step.get("tokens", {}).get("input", 0)

        if candidate_messages == recorded_messages:
            result.steps_covered += 1

        candidate_history = sum(1 for m in candidate_messages if m.get("role") == "tool")
        recorded_history = sum(1 for m in recorded_messages if m.get("role") == "tool")
        result.dropped_observations += max(0, recorded_history - candidate_history)
        for message in recorded_messages:
            if message.get("role") == "tool":
                content = message.get("content") or ""
                result.truncation_saved_chars += max(
                    0, len(content) - len(clip(content, policy.observation_chars)))

    result.redundant_reads, result.repeated_commands = _redundancy(record)
    if result.dropped_observations:
        result.notes.append(
            f"{result.dropped_observations} observations would be dropped by windowing")
    if result.truncation_saved_chars:
        result.notes.append(
            f"{result.truncation_saved_chars} characters clipped from observations")
    if result.decision_replayable < 1.0:
        result.notes.append(
            f"{result.steps_total - result.steps_covered}/{result.steps_total} steps diverge: "
            f"the model's decisions there are NOT replayable (abstain)")
    return result


def judge(records: list[dict], policies: list[HarnessPolicy]) -> dict[str, list[Estimate]]:
    return {policy.name: [estimate(record, policy) for record in records]
            for policy in policies}


def render(table: dict[str, list[Estimate]], task: str = "") -> str:
    lines = [f"Replay judge over {task or 'all tasks'} (estimates from recordings only)", ""]
    lines.append("| policy | episodes | prompt tok predicted | recorded | ratio | context covered | "
                 "dropped obs | clipped chars | redundant reads | repeated cmds | held-out err |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for name, estimates in table.items():
        predicted = sum(e.prompt_tokens_predicted for e in estimates)
        recorded = sum(e.prompt_tokens_recorded for e in estimates)
        ratio = predicted / recorded if recorded else 1.0
        covered = sum(e.steps_covered for e in estimates)
        total = sum(e.steps_total for e in estimates)
        error = max((e.held_out_error for e in estimates), default=0.0)
        lines.append(
            f"| `{name}` | {len(estimates)} | {predicted:.0f} | {recorded:.0f} | {ratio:.2f}x | "
            f"{covered}/{total} | {sum(e.dropped_observations for e in estimates)} | "
            f"{sum(e.truncation_saved_chars for e in estimates)} | "
            f"{sum(e.redundant_reads for e in estimates)} | "
            f"{sum(e.repeated_commands for e in estimates)} | {error:.1%} |"
        )
    lines.append("")
    lines.append("`context covered` counts steps where the candidate assembles exactly the "
                 "recorded context; everywhere else the model's decision is unreplayable, so the "
                 "judge abstains on capability there and only the cost side is estimated.")
    lines.append("`held-out err` is the token model's error on steps it was not fitted on "
                 "(first half fits, second half checks), per episode, worst case shown.")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="replay-judge recorded episodes")
    parser.add_argument("--policy", action="append", default=None,
                        help="policy name(s); default: all known variants")
    parser.add_argument("--label")
    parser.add_argument("--verify", action="store_true",
                        help="check that replaying the recorded policy reproduces recorded prompt sizes")
    parser.add_argument("--cross-validate", action="store_true",
                        help="fit the token model on other tasks, predict this one")
    args = parser.parse_args()

    records = load_records(args.label)
    if not records:
        print("no replayable records found")
        return

    if args.verify:
        for record in records:
            check = verify_reconstruction(record)
            print(f"{record['task']:<22} chars_match={check['chars_match']} "
                  f"steps={check['steps']} first_mismatch={check['first_mismatch']}")
        return

    if args.cross_validate:
        summary = cross_validate(records)
        print(f"leave-one-task-out token model over {summary['episodes']} episodes: "
              f"mean relative error {summary['mean_relative_error']:.1%}, "
              f"max {summary['max_relative_error']:.1%}")
        return

    names = args.policy or sorted(VARIANTS)
    policies = [get_policy(name) for name in names]
    print(render(judge(records, policies)))


if __name__ == "__main__":
    main()
