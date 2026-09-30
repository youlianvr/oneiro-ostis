"""Bounded organization protocol for the Oneiro swarm.

This module deliberately does not call a model or a git command. It owns the
small, testable contract between role adapters:

    researcher -> manager -> worker -> PR packet

Runtime adapters may later provide Hermes or OpenClaw callbacks. Every state
transition is emitted through an event sink, which the OSTIS bridge can back
with ``record_organization_event``. A cycle can stop at rejection, external
review, or owner escalation without pretending that work happened.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal, Optional, Sequence

Role = Literal["researcher", "manager", "worker"]
ManagerAction = Literal["reject", "external_review", "escalate", "assign_worker"]
EventSink = Callable[..., object]


@dataclass(frozen=True)
class Proposal:
    """A researcher's bounded proposal for one piece of work."""

    proposal_id: str
    title: str
    rationale: str
    acceptance: tuple[str, ...]
    evidence: tuple[str, ...] = ()
    check_id: str = ""


@dataclass(frozen=True)
class ManagerDecision:
    """A manager's decision, never a merge approval."""

    action: ManagerAction
    reason: str
    evidence: tuple[str, ...] = ()
    chosen: Optional[str] = None


@dataclass(frozen=True)
class PRPacket:
    """Evidence returned by a worker for owner review."""

    pr_id: str
    branch: str
    summary: str
    tests: tuple[str, ...]
    changed_paths: tuple[str, ...] = ()
    skill_candidate: Optional[str] = None
    merged: bool = False
    owner_approved: bool = False


@dataclass
class CycleResult:
    """Observable result of one bounded heartbeat cycle."""

    proposal: Proposal
    decision: ManagerDecision
    pr: Optional[PRPacket] = None
    stopped_reason: Optional[str] = None
    events: list[dict] = field(default_factory=list)


class SwarmProtocolError(ValueError):
    """Raised when a role violates the organization contract."""


class SwarmCoordinator:
    """Run one bounded role cycle and emit every transition.

    ``event_sink`` can be a thin adapter around ``OneiroBridge``. Keeping it as
    a callback makes the state machine testable without a live OSTIS stack and
    prevents the coordinator from owning storage.
    """

    def __init__(
        self,
        *,
        session_id: str,
        event_sink: Optional[EventSink] = None,
    ) -> None:
        if not session_id:
            raise ValueError("session_id is required")
        self.session_id = session_id
        self.event_sink = event_sink

    def run_cycle(
        self,
        researcher: Callable[[], "Proposal | Sequence[Proposal]"],
        manager: Callable[[Sequence[Proposal]], ManagerDecision],
        worker: Optional[Callable[[Proposal], PRPacket]] = None,
    ) -> CycleResult:
        """Execute exactly one proposal-to-PR cycle.

        The researcher may offer several options; the manager receives the
        whole sequence and picks exactly one (``chosen``) or stops the cycle
        with ``reject``, ``external_review``, or ``escalate``. No worker is
        called unless the manager returned ``assign_worker`` with a valid
        choice; external review and escalation are terminal for the cycle.
        """
        offered = researcher()
        options: tuple[Proposal, ...] = (
            (offered,) if isinstance(offered, Proposal) else tuple(offered)
        )
        if not options:
            raise SwarmProtocolError("researcher returned no proposals")
        for option in options:
            self._validate_proposal(option)
        events: list[dict] = []
        self._emit(events, "research_options", "researcher", {
            "options": [
                {"proposal_id": p.proposal_id, "title": p.title, "check_id": p.check_id}
                for p in options
            ],
        })

        decision = manager(options)
        self._validate_decision(decision, options)
        chosen = self._chosen_proposal(decision, options)
        self._emit(events, "manager_decision", "manager", {
            "proposal_id": chosen.proposal_id if chosen else None,
            "action": decision.action,
            "reason": decision.reason,
            "evidence": list(decision.evidence),
        })

        if decision.action != "assign_worker" or chosen is None:
            reason = f"manager action: {decision.action}"
            self._emit(events, decision.action, "manager", {
                "proposal_id": None,
                "reason": decision.reason,
            })
            return CycleResult(options[0], decision, stopped_reason=reason, events=events)

        self._emit(events, "research_proposal", "researcher", chosen.__dict__)
        if worker is None:
            raise SwarmProtocolError("assign_worker requires a worker callback")
        pr = worker(chosen)
        self._validate_pr(pr)
        self._emit(events, "pr_packet", "worker", {
            "proposal_id": chosen.proposal_id,
            "pr_id": pr.pr_id,
            "branch": pr.branch,
            "summary": pr.summary,
            "tests": list(pr.tests),
            "changed_paths": list(pr.changed_paths),
            "skill_candidate": pr.skill_candidate,
            "merged": pr.merged,
            "owner_approved": pr.owner_approved,
        })
        return CycleResult(chosen, decision, pr=pr, events=events)

    def _emit(self, events: list[dict], kind: str, role: Role, payload: dict) -> None:
        event = {
            "session_id": self.session_id,
            "kind": kind,
            "role": role,
            "payload": payload,
            "origin": role,
            "verified": False,
        }
        events.append(event)
        if self.event_sink is not None:
            self.event_sink(
                session_id=self.session_id,
                role=role,
                kind=kind,
                payload=payload,
                origin=role,
                verified=False,
            )

    @staticmethod
    def _validate_proposal(proposal: Proposal) -> None:
        if not proposal.proposal_id or not proposal.title or not proposal.rationale:
            raise SwarmProtocolError("proposal needs id, title, and rationale")
        if not proposal.acceptance:
            raise SwarmProtocolError("proposal needs at least one acceptance criterion")

    @staticmethod
    def _validate_decision(decision: ManagerDecision,
                           options: Sequence[Proposal]) -> None:
        if not decision.reason:
            raise SwarmProtocolError("manager decision needs a reason")
        if decision.action != "assign_worker":
            return
        ids = {option.proposal_id for option in options}
        if decision.chosen is None:
            if len(options) != 1:
                raise SwarmProtocolError(
                    "assign_worker needs an explicit chosen proposal"
                )
            return
        if decision.chosen not in ids:
            raise SwarmProtocolError(
                f"chosen proposal {decision.chosen!r} was not offered: {sorted(ids)}"
            )

    @staticmethod
    def _chosen_proposal(decision: ManagerDecision,
                         options: Sequence[Proposal]) -> Optional[Proposal]:
        if decision.action != "assign_worker":
            return None
        wanted = decision.chosen or options[0].proposal_id
        for option in options:
            if option.proposal_id == wanted:
                return option
        return None

    @staticmethod
    def _validate_pr(pr: PRPacket) -> None:
        if not pr.pr_id or not pr.summary or not pr.tests:
            raise SwarmProtocolError("PR packet needs id, summary, and test evidence")
        if pr.branch in {"main", "master"} or pr.branch.startswith("main/"):
            raise SwarmProtocolError("worker cannot return a main branch")
        if pr.merged or pr.owner_approved:
            raise SwarmProtocolError("worker cannot merge or approve its own PR")
