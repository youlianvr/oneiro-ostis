"""The owner's permission, kept as records in the graph.

The rule this module exists for: an approval authorises **one exact call** and it
comes from the owner, never from a model, a prompt or a stored text.

* `approval_id(tool, arguments)` is derived from the call itself, so a grant for
  one call can never be looked up as a grant for another.
* `granted_for` requires `Provenance.OWNER_INSTRUCTION`, so a record the agent
  wrote about itself cannot release anything.
* A grant is released once (`consume`), so a button pressed for one action does
  not quietly authorise the same call a week later.
* A refusal and a free-text answer are decisions too, and neither is a grant:
  the owner's words stay words unless the decision was an approval.

The Telegram channel and the console are transports over these records; the
decisions themselves live here, so every channel sees the same truth.
"""
from __future__ import annotations

from typing import Any

from oneiro import recall
from oneiro.records import Approval, Provenance, State
from oneiro.tools import arguments_digest

KIND = Approval.KIND
NOT_THE_OWNER = "not_the_owner"
ALREADY_DECIDED = "already_decided"
UNKNOWN_PROPOSAL = "unknown_proposal"
EMPTY_REASON = "empty_reason"


class ApprovalError(ValueError):
    """A decision that cannot be made, with a short machine-readable reason."""

    def __init__(self, reason: str, message: str = "") -> None:
        super().__init__(message or reason)
        self.reason = reason


def stored_approval(stored: dict[str, Any]) -> Approval:
    """The typed record for a stored row. The kind is checked, not assumed."""
    record = Approval.from_dict(stored)
    if not isinstance(record, Approval):
        raise ApprovalError(UNKNOWN_PROPOSAL, "the stored record is not an approval")
    return record


def approval_id(tool: str, arguments: dict[str, Any]) -> str:
    """The record ID for one exact call: the tool and its arguments, hashed."""
    return f"approval-{tool}-{arguments_digest(arguments)[:24]}"


async def request(owner: Any, *, action_id: str, tool: str, arguments: dict[str, Any],
                  reason: str = "", task_id: str = "") -> dict[str, Any]:
    """Record that this exact call is waiting for the owner. Nothing is run."""
    record = Approval(id=approval_id(tool, arguments), action_id=action_id, tool=tool,
                      arguments_digest=arguments_digest(arguments), granted=False,
                      reason=reason, task_id=task_id, state=State.WAITING,
                      provenance=Provenance.SYSTEM)
    stored = await recall.latest(owner, KIND, record.id)
    if stored is not None:
        # The same call already has a decision: asking again would overwrite it.
        return stored
    return (await owner.publish(record.to_dict(), record.id))["record"]


async def decide(owner: Any, approval_id_value: str, *, granted: bool, actor: str = "owner",
                 reason: str = "") -> dict[str, Any]:
    """The owner's decision about one pending proposal.

    Only the owner decides: a decision from any other actor is refused by name
    and nothing is written. A second decision on the same proposal is refused
    rather than overwriting the first.
    """
    if actor != "owner":
        raise ApprovalError(NOT_THE_OWNER, "only the owner can decide an approval")
    stored = await recall.latest(owner, KIND, approval_id_value)
    if stored is None:
        raise ApprovalError(UNKNOWN_PROPOSAL, "there is no such proposal")
    current = stored_approval(stored)
    if current.state is not State.WAITING or current.consumed_action_id:
        raise ApprovalError(ALREADY_DECIDED, "this proposal already has a decision")
    decided = current.with_state(State.COMPLETED if granted else State.CANCELLED,
                                 granted=bool(granted), reason=reason.strip(),
                                 provenance=Provenance.OWNER_INSTRUCTION)
    # A new revision, so its own operation ID, naming the revision it follows.
    return (await owner.publish(decided.to_dict(), "decision-" + current.id,
                                expected_revision=int(stored["__revision__"])))["record"]


async def lookup(owner: Any, tool: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
    """The newest record for exactly this call, whatever its state."""
    return await recall.latest(owner, KIND, approval_id(tool, arguments))


async def granted_for(owner: Any, tool: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
    """The owner's unspent grant for exactly this call, or None.

    Both conditions are the point: the digest matches this call, and the record
    is an available owner grant. A pending proposal, a refusal, a consumed grant
    and a grant for different arguments all answer None.
    """
    stored = await lookup(owner, tool, arguments)
    if stored is None:
        return None
    approval = stored_approval(stored)
    return stored if approval.covers(tool, approval.arguments_digest) else None


async def consume(owner: Any, stored: dict[str, Any], action_id: str) -> dict[str, Any]:
    """Mark a grant as spent on the action it released. Records, not deletion."""
    used = stored_approval(stored).consumed_by(action_id)
    return (await owner.publish(used.to_dict(), "used-" + action_id,
                                expected_revision=int(stored["__revision__"])))["record"]


async def pending(owner: Any, *, limit: int = 50) -> list[dict[str, Any]]:
    """Proposals waiting for the owner, newest first, one row per proposal."""
    found = await recall.scan(owner, lambda row: row.get("kind") == KIND)
    seen: set[str] = set()
    waiting: list[dict[str, Any]] = []
    for row in found.rows:                      # newest first
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        if row.get("state") == State.WAITING.value and not row.get("granted"):
            waiting.append(row)
        if len(waiting) >= limit:
            break
    return waiting
