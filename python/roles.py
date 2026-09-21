"""The three living roles: prompts, strict reply schemas, validation.

A role's whole contract: it receives JSON context, it must answer with one
JSON object matching the documented schema. Anything else is a schema error
that gets exactly one corrective retry and then fails the cycle. Free-form
prose never leaks into the organization records.

Human-readable fields (title, rationale, reason) are written in Russian so the
dashboard and the owner's morning reading need no translation; keys, ids and
check names stay in English.
"""

from __future__ import annotations

import json
from typing import Any, Optional, Sequence

from llm import CallBudget, ModelPool, ProviderError
from swarm import ManagerDecision, Proposal

RESEARCHER_ROLE = "researcher"
MANAGER_ROLE = "manager"

MANAGER_ACTIONS = ("assign_worker", "reject", "external_review", "escalate")


class SchemaError(RuntimeError):
    """The model answered with something the role contract does not accept."""


def extract_json(text: str) -> dict:
    """Pull the first complete JSON object out of a model answer."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if "```" in cleaned:
            cleaned = cleaned.split("```", 1)[0]
    start = cleaned.find("{")
    if start < 0:
        raise SchemaError(f"no JSON object in the answer: {text[:200]!r}")
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(cleaned)):
        char = cleaned[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                try:
                    data = json.loads(cleaned[start:index + 1])
                except json.JSONDecodeError as exc:
                    raise SchemaError(f"invalid JSON in the answer: {exc}") from exc
                if not isinstance(data, dict):
                    raise SchemaError("the answer must be a JSON object")
                return data
    raise SchemaError("unterminated JSON object in the answer")


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SchemaError(f"field {field_name!r} must be a non-empty string")
    return value.strip()


def _text_list(value: Any, field_name: str, minimum: int = 0) -> tuple[str, ...]:
    if value is None:
        value = []
    if not isinstance(value, list):
        raise SchemaError(f"field {field_name!r} must be a list of strings")
    items = tuple(_text(item, f"{field_name}[]") for item in value)
    if len(items) < minimum:
        raise SchemaError(f"field {field_name!r} needs at least {minimum} item(s)")
    return items


RESEARCHER_SYSTEM = """You are the researcher of a small autonomous organization that improves one software
project, Oneiro. Your job in this cycle: study the dossier and propose 2 to 4 alternative pieces of
work, each small enough for one isolated worktree and one test run.

Rules:
- Every proposal must fix a real weakness visible in the dossier (cite file paths or records).
- "acceptance" lists concrete, testable criteria for the change.
- "check_id" must be one of the offered check ids; it is the only command the worker may run.
- "risk" is "low" or "medium"; anything larger is not a first task.
- Do not propose merges, pushes, releases, or changes outside the project.
- Write title, rationale, acceptance and evidence in Russian. Keep JSON keys and ids in English.
- Answer with a single JSON object and nothing else, exactly this shape:
{"proposals":[{"title":"...","rationale":"...","acceptance":["..."],"evidence":["path:line — ..."],"check_id":"unit-tests","risk":"low"}]}
"""

MANAGER_SYSTEM = """You are the manager-critic of a small autonomous organization that improves one
software project, Oneiro. The researcher offers alternative proposals; you decide what happens next.

Decide with this priority: usefulness for the project's real goals, honesty of evidence, then cost.
You may stop the cycle when nothing is worth doing — that is a valid, respected outcome.

Actions:
- "assign_worker": exactly one proposal id in "chosen"; it must be one of the offered ids.
- "reject": the proposals are weak; say why.
- "external_review": the decision needs a stronger independent model than the team has.
- "escalate": the choice belongs to the owner (architecture, risk, or a ready change for review).

Rules:
- Never approve a merge, a push, or a release; the owner does that outside this system.
- Never pick more than one proposal.
- Write "reason" and "concerns" in Russian. Keep JSON keys and ids in English.
- Answer with a single JSON object and nothing else, exactly this shape:
{"action":"assign_worker","chosen":"r1","reason":"...","concerns":["..."]}
"""


def _researcher_messages(dossier: str, check_ids: Sequence[str]) -> list[dict]:
    checks = ", ".join(check_ids)
    return [
        {"role": "system", "content": RESEARCHER_SYSTEM},
        {"role": "user", "content": (
            f"Offered check ids: {checks}.\n\nDossier:\n{dossier}"
        )},
    ]


def _manager_messages(proposals: Sequence[Proposal], dossier: str) -> list[dict]:
    options = [{"proposal_id": p.proposal_id, "title": p.title, "rationale": p.rationale,
                "acceptance": list(p.acceptance), "evidence": list(p.evidence),
                "check_id": p.check_id} for p in proposals]
    return [
        {"role": "system", "content": MANAGER_SYSTEM},
        {"role": "user", "content": (
            "Proposals:\n" + json.dumps(options, ensure_ascii=False, indent=1) +
            "\n\nDossier excerpt:\n" + dossier
        )},
    ]


def researcher(
    pool: ModelPool,
    dossier: str,
    allowed_checks: Sequence[str],
    budget: Optional[CallBudget] = None,
    *,
    prefix: str = "r",
) -> list[Proposal]:
    """Ask the researcher for 2-4 proposals; one corrective retry on schema."""
    messages = _researcher_messages(dossier, allowed_checks)
    last_error: Optional[Exception] = None
    for attempt in range(2):
        reply = pool.reply(RESEARCHER_ROLE, messages, budget=budget)
        text = reply.message.get("content") or ""
        try:
            data = extract_json(text)
            raw = data.get("proposals")
            if not isinstance(raw, list) or not raw:
                raise SchemaError("field 'proposals' must be a non-empty list")
            if len(raw) > 4:
                raw = raw[:4]
            proposals: list[Proposal] = []
            for index, item in enumerate(raw):
                if not isinstance(item, dict):
                    raise SchemaError("every proposal must be a JSON object")
                check_id = _text(item.get("check_id"), "check_id")
                if check_id not in allowed_checks:
                    raise SchemaError(
                        f"check_id {check_id!r} is not one of {list(allowed_checks)}"
                    )
                risk = item.get("risk", "low")
                if risk not in ("low", "medium"):
                    raise SchemaError("risk must be 'low' or 'medium'")
                proposals.append(Proposal(
                    proposal_id=f"{prefix}{index + 1}",
                    title=_text(item.get("title"), "title"),
                    rationale=_text(item.get("rationale"), "rationale"),
                    acceptance=_text_list(item.get("acceptance"), "acceptance", minimum=1),
                    evidence=_text_list(item.get("evidence"), "evidence"),
                    check_id=check_id,
                ))
            return proposals
        except SchemaError as exc:
            last_error = exc
            messages = messages + [
                {"role": "assistant", "content": text[:2000]},
                {"role": "user", "content": (
                    f"Your answer was rejected: {exc}. Answer again with the exact "
                    "JSON shape, nothing else."
                )},
            ]
    raise SchemaError(f"researcher failed the schema twice: {last_error}")


def manager(
    pool: ModelPool,
    proposals: Sequence[Proposal],
    dossier: str,
    budget: Optional[CallBudget] = None,
) -> ManagerDecision:
    """Ask the manager to choose, stop, escalate, or ask for external review."""
    messages = _manager_messages(proposals, dossier)
    ids = [p.proposal_id for p in proposals]
    last_error: Optional[Exception] = None
    for attempt in range(2):
        reply = pool.reply(MANAGER_ROLE, messages, budget=budget)
        text = reply.message.get("content") or ""
        try:
            data = extract_json(text)
            action = _text(data.get("action"), "action")
            if action not in MANAGER_ACTIONS:
                raise SchemaError(f"action {action!r} is not one of {list(MANAGER_ACTIONS)}")
            chosen: Optional[str] = None
            if action == "assign_worker":
                chosen = _text(data.get("chosen"), "chosen")
                if chosen not in ids:
                    raise SchemaError(f"chosen {chosen!r} is not one of {ids}")
            return ManagerDecision(
                action=action,  # type: ignore[arg-type]
                reason=_text(data.get("reason"), "reason"),
                evidence=_text_list(data.get("concerns"), "concerns"),
                chosen=chosen,
            )
        except SchemaError as exc:
            last_error = exc
            messages = messages + [
                {"role": "assistant", "content": text[:2000]},
                {"role": "user", "content": (
                    f"Your answer was rejected: {exc}. Answer again with the exact "
                    "JSON shape, nothing else."
                )},
            ]
    raise SchemaError(f"manager failed the schema twice: {last_error}")


__all__ = [
    "MANAGER_ACTIONS",
    "SchemaError",
    "extract_json",
    "manager",
    "researcher",
]
