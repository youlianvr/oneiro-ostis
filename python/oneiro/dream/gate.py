"""The gate: a candidate advances only on evidence, and a promotion can be undone.

This is the graph's own vocabulary used as a process. An `Experiment` is frozen
before anything is run (`frozen_before_run`) and carries the minimum number of
repeats a conclusion needs (`min_repeats`, three by default); `may_conclude` refuses
to speak until both hold. A `Release` is the only thing a promotion produces, and a
rollback is a **new revision of that same release**, never a deletion: the promoted
revision stays in the graph, so undoing a promotion cannot erase owner data that
was written after it.

Two protections are real rather than declared:

* **A candidate cannot promote itself.** Promotion takes an `Experiment` that was
  frozen before the run and an `Evidence` whose `policy` names that experiment's
  candidate, so evidence gathered about one candidate cannot carry another one
  through the gate, and a candidate created after the fact has nothing to ride on.
* **A verdict is not a judgement call.** Every check is a comparison against a
  threshold frozen in `Criteria`, and a refusal names the check that failed, so the
  same evidence always gives the same answer.

Writing to the graph is a separate, explicit step (`record_experiment`,
`publish_release`), and it is the caller's: deciding is pure, so a gate can be
re-run against stored evidence without publishing anything.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from oneiro.records import Experiment, Provenance, Release, State, now

#: The default number of repeats a conclusion needs. Three is the minimum the plan
#: sets, and the recorded noise floor is the reason: two measurements of the same
#: policy can land tens of percent apart.
MIN_REPEATS = 3


class GateError(ValueError):
    """A promotion or a rollback the gate refuses, with the reason named."""


@dataclass(frozen=True)
class Criteria:
    """The acceptance rules, frozen before a run so a later reading cannot move them."""

    coverage_floor: float = 0.5
    saving_threshold: float = 0.15
    min_repeats: int = MIN_REPEATS
    max_regressions: int = 0


@dataclass(frozen=True)
class Evidence:
    """What was measured about one candidate. Every field is supplied, none is inferred."""

    policy: str
    coverage: float
    saving: float
    repeats: int
    regressions: int = 0


@dataclass(frozen=True)
class Verdict:
    """The gate's answer, with every check kept so a refusal can be read back."""

    passed: bool
    checks: dict[str, bool] = field(default_factory=dict)
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "checks": dict(self.checks), "reasons": list(self.reasons)}


def open_experiment(*, name: str, hypothesis: str, control: str, candidate: str,
                    criteria: Criteria, seeds: tuple[int, ...] = ()) -> Experiment:
    """An experiment with its rules already frozen. Nothing may be run before this.

    An experiment whose candidate equals its control has nothing to measure, so it is
    refused here rather than silently producing a verdict about no change.
    """
    if control == candidate:
        raise GateError("an experiment needs a candidate that differs from its control")
    return Experiment(name=name, hypothesis=hypothesis, control=control, candidate=candidate,
                      seeds=tuple(seeds), repeats=0, min_repeats=criteria.min_repeats,
                      frozen_before_run=True, state=State.RUNNING, labels=("dream-gate",))


def record_repeats(experiment: Experiment, repeats: int) -> Experiment:
    """Count more repeats. A count never goes down; a new experiment is the way back."""
    return experiment.with_repeats(repeats)


def gate(experiment: Experiment, criteria: Criteria, evidence: Evidence) -> Verdict:
    """Compare one measurement against the frozen rules, naming every failed check."""
    checks = {
        "frozen_before_run": bool(experiment.frozen_before_run),
        "enough_repeats": experiment.has_enough_repeats() and evidence.repeats >= criteria.min_repeats,
        "coverage": evidence.coverage >= criteria.coverage_floor,
        "saving": evidence.saving >= criteria.saving_threshold,
        "no_regression": evidence.regressions <= criteria.max_regressions,
    }
    reasons: list[str] = []
    if not checks["frozen_before_run"]:
        reasons.append("the acceptance rules were not frozen before the run")
    if not checks["enough_repeats"]:
        reasons.append(f"at least {criteria.min_repeats} repeats are needed; "
                       f"{evidence.repeats} were run")
    if not checks["coverage"]:
        reasons.append(f"coverage {evidence.coverage:.2f} is below the floor "
                       f"{criteria.coverage_floor:.2f}: the saving is an extrapolation")
    if not checks["saving"]:
        reasons.append(f"saving {evidence.saving:+.2f} is below the threshold "
                       f"{criteria.saving_threshold:.2f}")
    if not checks["no_regression"]:
        reasons.append(f"{evidence.regressions} regression(s) against a limit of "
                       f"{criteria.max_regressions}")
    return Verdict(passed=all(checks.values()), checks=checks, reasons=tuple(reasons))


def promote(experiment: Experiment, criteria: Criteria, evidence: Evidence, *,
            version: str) -> Release:
    """The only path a candidate has to being deployed. Refuses without evidence.

    The evidence must be about this experiment's candidate, the experiment must be
    able to conclude, and every frozen check must pass; otherwise the refusal names
    the check. The release records the checks themselves, so what was believed at
    promotion time is readable later.
    """
    if evidence.policy != experiment.candidate:
        raise GateError(f"the evidence is about {evidence.policy!r}; this experiment is about "
                        f"{experiment.candidate!r}")
    if not experiment.may_conclude():
        raise GateError(f"experiment {experiment.name!r} cannot conclude: "
                        f"frozen={experiment.frozen_before_run}, "
                        f"{experiment.repeats}/{experiment.min_repeats} repeats")
    verdict = gate(experiment, criteria, evidence)
    if not verdict.passed:
        raise GateError("a candidate is promoted only on evidence; it was refused: "
                        + "; ".join(verdict.reasons))
    return Release(version=version, artifact=experiment.candidate, checks=dict(verdict.checks),
                   promoted=True, state=State.COMPLETED, provenance=Provenance.SYSTEM,
                   labels=("dream-gate", f"experiment:{experiment.name}"))


def rollback(release: Release, *, reason: str) -> Release:
    """A new revision of the same release that undoes the promotion and nothing else.

    The promoted revision is left in the graph, no other record is touched, and the
    reason is written onto the revision, so owner data written after the promotion
    cannot be lost by an undo. A release that was never promoted has nothing to undo.
    """
    if not reason.strip():
        raise GateError("a rollback names its reason")
    if release.rolled_back:
        raise GateError(f"release {release.version} was already rolled back")
    if not release.promoted:
        raise GateError(f"release {release.version} was never promoted, so there is nothing "
                        f"to roll back")
    return replace(release, promoted=False, rolled_back=True, updated_at=now(),
                   labels=release.labels + (f"rollback:{reason.strip()}",))


async def record_experiment(owner: Any, experiment: Experiment) -> dict[str, Any]:
    """Write the experiment, frozen rules and all. Once per ID."""
    return await owner.publish(experiment.to_dict(), "dream-experiment-" + experiment.id)


async def publish_release(owner: Any, release: Release, *,
                          expected_revision: int = 0) -> dict[str, Any]:
    """Write one release revision, naming the revision it replaces.

    A promotion is published against revision 0; a rollback is published against the
    revision the promotion returned, so a rollback cannot quietly overwrite a newer
    revision written in between.
    """
    operation = f"dream-release-{release.id}-{expected_revision}"
    return await owner.publish(release.to_dict(), operation, expected_revision=expected_revision)
