"""Drafts: a reply that leaves only when the owner presses send.

The rule this module exists for: **a draft is a call that is already written down and
has not been made.** Nothing here puts a message on the wire by itself.

How the rule is kept, in three parts that do not depend on each other's goodwill:

* A draft is an `Action` record in state `WAITING`, decision `ask`, whose arguments are
  the exact call that would go out, plus the pending `Approval` naming that call. So the
  owner reads the real bytes and not a summary of them.
* Sending requires an **owner's grant for exactly those arguments**. `approvals.decide`
  refuses any actor but the owner and binds the grant to a digest of the arguments, so a
  grant can never release a different text, and a text edited after the press is a
  different call that has not been pressed. The agent has no tool that decides an
  approval, so a turn can produce a draft and can never release one.
* The declared permissions are boundaries on top: `permissions.send_publish` refusing
  sending, or the role boundary of the tool, are refusals an approval cannot open — the
  same rule the rest of the product follows.

The one outbound message that needs no press is the notice to the owner themselves, and
it is safe by construction rather than by permission: `notify` has **no recipient
parameter**. The address comes from the bot's own `get_updates`, which can only report
the person who wrote to it — there is no argument through which a caller, a model or a
stored file could name somebody else.

Reads are not sends: `read_incoming` asks the mailbox for its newest messages and keeps
what came back, and it neither needs nor asks for the owner's press.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, cast

from oneiro import approvals, i18n, mcp, recall
from oneiro.records import Action, Effect, EffectOutcome, Note, Provenance, State
from oneiro.tools import Policy, Tool, ToolError, arguments_digest

#: The label every draft carries, so one query finds them all.
DRAFT_LABEL = "draft"
#: The role a sent draft runs as. The executor may use the send effect; the manager and
#: the researcher may not, which is a boundary and not a preference.
ROLE = "executor"

NOT_THE_OWNER = "not_the_owner"
UNKNOWN_DRAFT = "unknown_draft"
UNKNOWN_TOOL = "unknown_tool"
BAD_ARGUMENTS = "bad_arguments"
ALREADY_SETTLED = "already_settled"
NOT_PRESSED = "not_pressed"
PERMISSION_DENIED = "permission_denied"
NO_CHAT = "no_chat"

#: The reason a pending draft carries, in the product's one language for records: a screen
#: renders its own wording from the state, and a person reading the graph reads this.
WAITING_REASON = "nothing is sent until the owner presses send for exactly this call"

MAX_TEXT = 8000
MAX_NOTICE_CHARS = 2000
EXCERPT_CHARS = 400


class DraftError(ValueError):
    """A draft request that cannot be carried out, with a short machine-readable reason."""

    def __init__(self, reason: str, message: str = "") -> None:
        super().__init__(message or reason)
        self.reason = reason


def draft_id(tool: str, arguments: dict[str, Any]) -> str:
    """The record ID of one draft: the tool and the exact arguments, hashed.

    Nothing else takes part, so the same reply written twice is one draft, and the
    approval that names this id can only ever release these bytes.
    """
    return "draft-" + arguments_digest(arguments)[:24]


def _policy(policy: Policy | None) -> Policy:
    from oneiro import agent        # the product's own policy, built once, in one place

    return policy if policy is not None else agent.default_policy()


async def offered(key: str) -> Tool:
    """The MCP tool this key names, or a refusal that says why it is not there.

    A tool is offered only when its server is declared, enabled and open, so a draft
    cannot be written against a capability that this build does not have right now.
    """
    hub = mcp.hub()
    try:
        server, tool = mcp.split_tool_key(key)
    except mcp.McpError as exc:
        raise DraftError(UNKNOWN_TOOL, str(exc)) from None
    if server not in hub.sessions:
        report = await hub.open(server)
        if not report.get("opened"):
            raise DraftError(UNKNOWN_TOOL,
                             f"the server {server} did not come up: "
                             f"{report.get('reason') or 'no reason was given'}")
    tool_object = hub.registry().get(key)
    if tool_object is None:
        raise DraftError(UNKNOWN_TOOL, f"the server {server} offers no tool named {tool}")
    return tool_object


def target_of(arguments: dict[str, Any]) -> str:
    """Who a call addresses, for the effect on the record. Never a permission."""
    for name in ("to", "recipient", "chat_id", "channel", "address"):
        value = arguments.get(name)
        if isinstance(value, (str, int)) and str(value).strip():
            return str(value).strip()
    return ""


def _labels(key: str, extra: tuple[str, ...]) -> tuple[str, ...]:
    server, tool = mcp.split_tool_key(key)
    parts = [DRAFT_LABEL, f"server:{server}" if server else "", f"tool:{tool}" if tool else "",
             *extra]
    return tuple(dict.fromkeys(item for item in parts if item))


def _draft_action(key: str, arguments: dict[str, Any], *, identity: str,
                  labels: tuple[str, ...] = ()) -> Action:
    return Action(id=identity, run_id="draft-" + identity[7:], tool=key, arguments=dict(arguments),
                  decision="ask",
                  effect=Effect(kind="send", target=target_of(arguments), outcome=EffectOutcome.NONE),
                  state=State.WAITING, provenance=Provenance.SYSTEM,
                  labels=_labels(key, labels))


def stored_action(stored: dict[str, Any]) -> Action:
    """The typed record for a stored row. The kind and the label are checked, not assumed."""
    record = Action.from_dict(stored)
    if not isinstance(record, Action) or DRAFT_LABEL not in record.labels:
        raise DraftError(UNKNOWN_DRAFT, "that record is not a draft")
    return record


def shape(stored: dict[str, Any], *, approval: dict[str, Any] | None = None) -> dict[str, Any]:
    """One draft as every surface reads it: the call, its state, and why it stands there."""
    action = stored_action(stored)
    why = {
        State.WAITING: "waiting for your press",
        State.RUNNING: "the send is in flight",
        State.COMPLETED: "sent",
        State.FAILED: "the send failed",
        State.UNCERTAIN: "the send may or may not have happened",
        State.CANCELLED: "discarded",
    }.get(action.state, action.state.value)
    return {"id": action.id, "tool": action.tool, "arguments": dict(action.arguments),
            "target": target_of(action.arguments), "state": action.state.value,
            "decision": action.decision, "why": why, "result": action.result,
            "labels": list(action.labels), "created_at": stored.get("created_at", ""),
            "updated_at": stored.get("updated_at", ""),
            "effect": {"kind": action.effect.kind, "target": action.effect.target,
                       "outcome": action.effect.outcome.value},
            "may_retry": action.effect.outcome.permits_blind_retry,
            "approval": None if approval is None else {
                "id": str(approval.get("id") or ""), "state": str(approval.get("state") or ""),
                "granted": bool(approval.get("granted")),
                "pressed": bool(approval.get("granted")) and not approval.get("consumed_action_id")}}


async def _approval_of(owner: Any, action: Action) -> dict[str, Any] | None:
    return await approvals.lookup(owner, action.tool, action.arguments)


async def get(owner: Any, draft_id_value: str) -> dict[str, Any]:
    """One draft by id, with the owner's decision about it, or a named refusal."""
    stored = await recall.latest(owner, Action.KIND, draft_id_value)
    if stored is None:
        raise DraftError(UNKNOWN_DRAFT, f"there is no record with the id {draft_id_value}")
    action = stored_action(stored)
    return shape(stored, approval=await _approval_of(owner, action))


async def listing(owner: Any, *, limit: int = 50) -> dict[str, Any]:
    """The drafts still open, then what became of the last few that are not.

    Two reads, not one per draft: the actions that carry the label, and the approvals,
    joined by the id an approval derives from the call it names.
    """
    found = await recall.scan(owner, lambda row: DRAFT_LABEL in (row.get("labels") or []))
    decisions = await recall.scan(owner, lambda row: row.get("kind") == approvals.KIND)
    newest_decision: dict[str, dict[str, Any]] = {}
    for row in decisions.rows:                       # newest first
        newest_decision.setdefault(str(row["id"]), row)
    seen: set[str] = set()
    open_drafts: list[dict[str, Any]] = []
    settled: list[dict[str, Any]] = []
    for row in found.rows:                           # newest first
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        action = stored_action(row)
        item = shape(row, approval=newest_decision.get(approvals.approval_id(
            action.tool, action.arguments)))
        if row.get("state") == State.WAITING.value:
            open_drafts.append(item)
        elif len(settled) < limit:
            settled.append(item)
    return {"drafts": open_drafts[:limit], "settled": settled, "waiting": len(open_drafts),
            "scanned": found.scanned, "complete": found.complete}


# ---------------------------------------------------------------- the mailbox


def _messages(text: str) -> list[dict[str, Any]]:
    """The messages in a mailbox answer, when it answers with the shape this build reads.

    A server that answers with one blob of text is not a failure: it is kept whole as one
    record. What is never done is inventing rows out of text that did not parse.
    """
    try:
        parsed = json.loads(text)
    except ValueError:
        return []
    if isinstance(parsed, dict):
        for key in ("messages", "items", "results", "result"):
            if isinstance(parsed.get(key), list):
                parsed = parsed[key]
                break
        else:
            return []
    if not isinstance(parsed, list):
        return []
    return [row for row in parsed if isinstance(row, dict)]


def _field(row: dict[str, Any], *names: str) -> str:
    """One text field out of a message, tolerating the spellings servers use."""
    for name in names:
        value = row.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            nested = _field(value, "email", "address", "name")
            if nested:
                return nested
    return ""


async def read_incoming(owner: Any, *, tool: str, arguments: dict[str, Any] | None = None,
                        limit: int = 10) -> dict[str, Any]:
    """Read the mailbox through a declared MCP tool and keep what came back.

    Reading is not sending: it changes nothing outside the machine except asking the
    mailbox for its newest messages, so it needs no press. What came back is stored as
    `Note` records with observation provenance — the assistant saw them, which is not the
    same as the owner saying them.
    """
    tool_object = await offered(tool)
    call_arguments = dict(arguments or {})
    try:
        tool_object.validate(call_arguments)
    except ToolError as exc:
        raise DraftError(BAD_ARGUMENTS, str(exc)) from None
    outcome = await mcp.hub().call(tool, call_arguments)
    if not outcome["ok"]:
        return {"tool": tool, "ok": False, "state": str(outcome.get("state") or "failed"),
                "reason": str(outcome.get("reason") or "the read did not finish"),
                "notes": [], "read": 0, "text": ""}
    text = str(outcome.get("text") or "")
    notes: list[dict[str, Any]] = []
    for row in (_messages(text) or [{}])[:limit]:
        subject = _field(row, "subject", "title", "topic") or f"incoming mail via {tool}"
        body = _field(row, "body", "text", "snippet", "preview") or text
        sender = _field(row, "from", "sender", "author")
        message_id = _field(row, "id", "message_id", "uid", "thread_id")
        digest = hashlib.sha256(f"{tool}\n{message_id}\n{sender}\n{subject}\n{body}"
                                .encode("utf-8")).hexdigest()
        note = Note(id="mail-" + digest[:24], topic=subject[:300], body=body[:MAX_TEXT],
                    sources=tuple(item for item in (sender, message_id, tool) if item),
                    state=State.COMPLETED, provenance=Provenance.OBSERVATION, labels=("mail",))
        # A letter already on record is **not** written again. Its identity is the digest of
        # what arrived, so a second read of the same letter is the same note; writing it a
        # second time with a fresh timestamp is the same operation id with different
        # content, which the graph refuses as a collision (measured on the live graph
        # 2026-10-12: `operation_collision: operation ID already has different content`,
        # HTTP 503 on `POST /api/mail/read` for a letter read a second time). A read is
        # idempotent here, and the stored note is what the answer carries back.
        stored_note = await recall.latest(owner, Note.KIND, note.id)
        notes.append(stored_note if stored_note is not None
                     else (await owner.publish(note.to_dict(), note.id))["record"])
    return {"tool": tool, "ok": True, "state": State.COMPLETED.value, "reason": "",
            "notes": notes, "read": len(notes), "text": text}


# ---------------------------------------------------------------- the draft


async def create(owner: Any, *, tool: str, arguments: dict[str, Any], labels: tuple[str, ...] = (),
                 source_id: str = "") -> dict[str, Any]:
    """Write down a call that is ready to go, and do not make it.

    The arguments are checked against the tool's own declared schema, so a draft that
    could never be sent is refused here and names the field that is missing, instead of
    sitting in the list looking sendable.
    """
    tool_object = await offered(tool)
    call_arguments = dict(arguments or {})
    try:
        tool_object.validate(call_arguments)
    except ToolError as exc:
        raise DraftError(BAD_ARGUMENTS, str(exc)) from None
    if not call_arguments:
        raise DraftError(BAD_ARGUMENTS, "a draft needs the arguments of the call it would make")
    identity = draft_id(tool, call_arguments)
    stored = await recall.latest(owner, Action.KIND, identity)
    if stored is not None and stored.get("state") != State.WAITING.value:
        # This exact call already went out, or was called off: asking again would
        # overwrite the answer with a new question.
        return shape(stored)
    extra = tuple(labels) + (("source:" + source_id,) if source_id else ())
    record = _draft_action(tool, call_arguments, identity=identity, labels=extra)
    published = stored if stored is not None else (
        await owner.publish(record.to_dict(), identity))["record"]
    await approvals.request(owner, action_id=identity, tool=tool, arguments=call_arguments,
                            reason=WAITING_REASON)
    return shape(published, approval=await _approval_of(owner, stored_action(published)))


async def revise(owner: Any, draft_id_value: str, *, arguments: dict[str, Any]) -> dict[str, Any]:
    """Edit a pending draft. The edit is a different call and needs its own press.

    The grant, if the owner already pressed for the old text, is bound to the old
    arguments and cannot release this one: the digest is part of the approval's identity.
    """
    stored, current = await _open_draft(owner, draft_id_value)
    tool_object = await offered(current.tool)
    call_arguments = dict(arguments or {})
    try:
        tool_object.validate(call_arguments)
    except ToolError as exc:
        raise DraftError(BAD_ARGUMENTS, str(exc)) from None
    if call_arguments == dict(current.arguments):
        # The edit asks for what the draft already says: this is the same call, so no
        # revision is written and nothing about it changes. A command repeated after a
        # graph failure therefore answers with the draft as it stands instead of writing
        # the same revision under the same operation id — which the graph would refuse as
        # a collision, since a revision carries its own timestamp.
        return shape(stored, approval=await _approval_of(owner, current))
    revised = cast(Action, Action.from_dict({
        **current.to_dict(), "arguments": call_arguments, "effect":
        Effect(kind="send", target=target_of(call_arguments),
               outcome=EffectOutcome.NONE).to_dict()}))
    published = await owner.publish(revised.to_dict(), "revise-" + current.id,
                                    expected_revision=int(stored["__revision__"]))
    await approvals.request(owner, action_id=current.id, tool=current.tool,
                            arguments=call_arguments, reason=WAITING_REASON)
    return shape(published["record"], approval=await _approval_of(owner, revised))


async def _open_draft(owner: Any, draft_id_value: str) -> tuple[dict[str, Any], Action]:
    """A draft that is still waiting, or a refusal naming why it is not."""
    stored = await recall.latest(owner, Action.KIND, draft_id_value)
    if stored is None:
        raise DraftError(UNKNOWN_DRAFT, f"there is no record with the id {draft_id_value}")
    current = stored_action(stored)
    if current.state is not State.WAITING:
        raise DraftError(ALREADY_SETTLED, f"this draft is {current.state.value}")
    return stored, current


async def discard(owner: Any, draft_id_value: str, *, reason: str = "") -> dict[str, Any]:
    """Call a pending draft off. The refusal is the owner's own decision, on record.

    Calling off a draft that is already called off, with the same words, is the same
    decision: it is answered with the record that stands instead of a second revision.
    """
    latest = await recall.latest(owner, Action.KIND, draft_id_value)
    if latest is not None:
        standing = stored_action(latest)
        if standing.state is State.CANCELLED \
                and str(standing.result or "") == (reason or "the draft was called off"):
            return shape(latest, approval=await _approval_of(owner, standing))
    stored, current = await _open_draft(owner, draft_id_value)
    pending = await _approval_of(owner, current)
    if pending is not None and pending.get("state") == State.WAITING.value:
        await approvals.decide(owner, str(pending["id"]), granted=False, actor="owner",
                               reason=reason or "the draft was called off")
    cancelled = cast(Action, current.with_state(State.CANCELLED, decision="deny",
                                               result=reason or "the draft was called off"))
    published = await owner.publish(cancelled.to_dict(), "discard-" + current.id,
                                    expected_revision=int(stored["__revision__"]))
    return shape(published["record"], approval=await _approval_of(owner, cancelled))


async def _granted(owner: Any, current: Action, *, policy: Policy) -> tuple[dict[str, Any], str]:
    """Whether this exact call may go out now, and the owner's grant that says so.

    Two independent things must hold: the declared permissions must not refuse sending,
    and the owner must have pressed for exactly these arguments. A "deny" is a boundary
    that an approval cannot open, and the absence of a press is not a permission at all.
    """
    if policy.decision("send") == "deny":
        raise DraftError(PERMISSION_DENIED,
                         "sending is refused by permissions.send_publish; an approval cannot "
                         "open a refusal you set")
    tool_object = await offered(current.tool)
    try:
        decision, reason = policy.check(tool_object, ROLE, current.arguments)
    except ToolError as exc:
        raise DraftError(BAD_ARGUMENTS, str(exc)) from None
    if decision == "deny":
        raise DraftError(PERMISSION_DENIED, reason)
    grant = await approvals.granted_for(owner, current.tool, current.arguments)
    if grant is None:
        raise DraftError(NOT_PRESSED,
                         "this draft has not been pressed: nothing goes out until you press "
                         "send for exactly these arguments")
    return grant, policy.check(tool_object, ROLE, current.arguments, approved=True)[1]


async def send(owner: Any, draft_id_value: str, *, actor: str = "owner",
               policy: Policy | None = None, dry_run: bool = False) -> dict[str, Any]:
    """Send a draft the owner has pressed for. The one place where a message goes out.

    The order is the rule, and it is the same order the turn path uses: the grant is spent
    **before** the call, and the action is recorded as RUNNING before the call is made, so
    a crash in the middle cannot leave a reusable grant behind or leave a send with
    nothing to show for it. `dry_run` answers the same question, spends nothing and sends
    nothing — it is what a screen asks before it offers the button.
    """
    if actor != "owner":
        raise DraftError(NOT_THE_OWNER, "only the owner's press sends a draft")
    stored, current = await _open_draft(owner, draft_id_value)
    decided = _policy(policy)
    grant, reason = await _granted(owner, current, policy=decided)
    if dry_run:
        return {"ok": True, "dry_run": True, "state": current.state.value,
                "why": reason, "grant": str(grant["id"]),
                "draft": shape(stored, approval=grant)}
    await approvals.consume(owner, grant, current.id)
    in_flight = current.with_state(State.RUNNING, decision="allow", result=reason)
    published = await owner.publish(in_flight.to_dict(), "send-" + current.id,
                                    expected_revision=int(stored["__revision__"]))
    outcome = await mcp.hub().call(current.tool, current.arguments)
    ok = bool(outcome["ok"])
    state = (State.COMPLETED if ok
             else State.UNCERTAIN if outcome.get("state") == "uncertain" else State.FAILED)
    effect = (EffectOutcome.SUCCEEDED if ok
              else EffectOutcome.UNCERTAIN if state is State.UNCERTAIN else EffectOutcome.FAILED)
    text = str(outcome.get("text") or "")
    final = in_flight.with_state(
        state, effect=Effect(kind="send", target=target_of(current.arguments), outcome=effect),
        provenance=(Provenance.VERIFIED_TOOL_OUTCOME if ok else Provenance.SYSTEM),
        result=(f"{reason}\n{text}" if ok
                else f"{outcome.get('reason') or 'it did not finish'}")[:4000])
    recorded = True
    try:
        await owner.publish(final.to_dict(), f"{'sent' if ok else 'tried'}-{current.id}",
                            expected_revision=int(published.get("revision") or 0))
    except Exception:                    # the call happened; say so instead of hiding it
        recorded = False
    return {"ok": ok, "dry_run": False, "state": state.value, "effect": effect.value, "text": text,
            "reason": str(outcome.get("reason") or ""), "draft": shape(final.to_dict()),
            "recorded": recorded, "may_retry": effect.permits_blind_retry}


async def press(owner: Any, draft_id_value: str, *, policy: Policy | None = None) -> dict[str, Any]:
    """The owner's press: one decision, then one send, in that order.

    This is what a button and the command line both call. Nothing else in the product
    decides an approval, and `approvals.decide` refuses any actor but the owner, so a draft
    can only be released by the person it belongs to.
    """
    stored, current = await _open_draft(owner, draft_id_value)
    pending = await _approval_of(owner, current)
    if pending is not None and pending.get("state") == State.WAITING.value:
        await approvals.decide(owner, str(pending["id"]), granted=True, actor="owner",
                               reason="the owner pressed send for this exact call")
    return await send(owner, draft_id_value, actor="owner", policy=policy)


# ---------------------------------------------------------------- the notice


def _chat_in(text: str) -> int | None:
    """The newest private chat id in a bot updates answer, whatever nesting it uses."""
    try:
        parsed = json.loads(text)
    except ValueError:
        return None
    found: list[int] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            chat = node.get("chat")
            if isinstance(chat, dict) and isinstance(chat.get("id"), int) \
                    and str(chat.get("type") or "private") == "private":
                found.append(int(chat["id"]))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(parsed)
    return found[0] if found else None


async def owner_chat(owner: Any, *, updates_tool: str) -> int:
    """The chat the owner wrote to the bot from, asked of the bot itself.

    The owner's decision, and a safety property rather than a courtesy: the address of a
    notice is discovered from the bot's own inbox, so no argument anywhere in this product
    names a recipient for it.
    """
    await offered(updates_tool)
    outcome = await mcp.hub().call(updates_tool, {})
    if not outcome["ok"]:
        raise DraftError(NO_CHAT, f"the bot did not answer: "
                                  f"{outcome.get('reason') or 'no reason was given'}")
    chat = _chat_in(str(outcome.get("text") or ""))
    if chat is None:
        raise DraftError(NO_CHAT, "the bot reports no message from you yet; write to it once "
                                  "so the notice knows where to go")
    return chat


async def notify(owner: Any, text: str, *, tool: str, updates_tool: str,
                 policy: Policy | None = None) -> dict[str, Any]:
    """Send one message to the owner, and to nobody else.

    There is no recipient argument: the address is discovered from the bot's own
    `get_updates`, so the one outbound message that needs no press is also the one that
    cannot be addressed to a stranger. The declared send permission still governs it — a
    machine that may send nothing sends nothing, its owner included.
    """
    if not text.strip():
        raise DraftError(BAD_ARGUMENTS, "a notice needs text")
    decided = _policy(policy)
    if decided.decision("send") == "deny":
        raise DraftError(PERMISSION_DENIED,
                         "sending is refused by permissions.send_publish, so Oneiro sends you "
                         "nothing until you allow it here")
    chat = await owner_chat(owner, updates_tool=updates_tool)
    arguments = {"chat_id": chat, "text": text[:MAX_NOTICE_CHARS]}
    tool_object = await offered(tool)
    try:
        tool_object.validate(arguments)
    except ToolError as exc:
        raise DraftError(BAD_ARGUMENTS, str(exc)) from None
    decision, reason = decided.check(tool_object, ROLE, arguments)
    if decision == "deny":
        raise DraftError(PERMISSION_DENIED, reason)
    outcome = await mcp.hub().call(tool, arguments)
    return {"ok": bool(outcome["ok"]), "chat_id": chat, "state": str(outcome.get("state")),
            "reason": str(outcome.get("reason") or ""),
            "delivered": str(outcome.get("text") or "") if outcome["ok"] else ""}


def notice(draft: dict[str, Any], *, lang: str | None = None) -> str:
    """The words of the notice: the exact call, in the owner's own language."""
    arguments = draft.get("arguments") or {}
    subject = str(arguments.get("subject") or arguments.get("title") or "").strip()
    body = str(arguments.get("body") or arguments.get("text") or "").strip()
    excerpt = " ".join(body.split())
    if len(excerpt) > EXCERPT_CHARS:
        excerpt = excerpt[:EXCERPT_CHARS] + i18n.t("draft.notice.truncated", lang,
                                                   rest=str(len(body) - EXCERPT_CHARS))
    draft_id_value = str(draft.get("id") or "")
    lines = [i18n.t("draft.notice.head", lang),
             i18n.t("draft.notice.to", lang, to=str(draft.get("target") or "—"))]
    if subject:
        lines.append(i18n.t("draft.notice.subject", lang, subject=subject))
    if excerpt:
        lines.append(i18n.t("draft.notice.body", lang, body=excerpt))
    lines.append(i18n.t("draft.notice.id", lang, draft=draft_id_value))
    lines.append(i18n.t("draft.notice.press", lang, draft=draft_id_value))
    return "\n".join(lines)


def notice_for(owner: Any, draft: dict[str, Any], *, lang: str | None = None) -> str:
    """`notice` with the language taken from the setting that owns it."""
    return notice(draft, lang=lang or i18n.current_language())
