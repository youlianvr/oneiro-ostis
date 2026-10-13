"""Bounded reads over the stored record stream: facts, conversations, search.

The graph worker serves pages newest-first, not predicates, so every read here
walks pages and filters in this process. A walk stops at MAX_SCANNED records or
when the stream ends. Each answer says whether the whole stream was read
(`complete`) and how many stored records could not be decoded (`skipped`). A
capped or partly unreadable answer is never presented as a full one, so "not
found" is only ever claimed for a stream that was read completely.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from oneiro.query import GraphQueryError
from oneiro.records import CuratedFact, Provenance, State, now, new_id

PAGE = 500
MAX_SCANNED = 2000
CURATED_CHARS = 2000
FACT_KIND = CuratedFact.KIND
MESSAGE_KIND = "conversation_message"


class PageSource(Protocol):
    async def memory_page(self, *, cursor: str | None = None,
                          limit: int | None = None) -> dict[str, Any]: ...


@dataclass(frozen=True)
class Scan:
    rows: list[dict[str, Any]]
    scanned: int
    skipped: int
    complete: bool


async def scan(source: PageSource, keep: Callable[[dict[str, Any]], bool], *,
               want: int | None = None, max_scanned: int | None = None) -> Scan:
    """Newest-first matching revisions, reading at most `max_scanned` records.

    `complete` is True only when the stream ended inside the bound. Stopping
    early on `want` is not a completed read, even though the rows are real.
    """
    bound = MAX_SCANNED if max_scanned is None else max_scanned
    rows: list[dict[str, Any]] = []
    scanned = 0
    skipped = 0
    cursor: str | None = None
    while True:
        page = await source.memory_page(cursor=cursor, limit=PAGE)
        items = list(page.get("items") or [])
        scanned += int(page.get("scanned") or len(items))
        skipped += len(page.get("skipped") or [])
        rows.extend(row for row in items if keep(row))
        cursor = page.get("cursor")
        # Rows are newest first, so the first `want` are the ones to keep. More
        # matches than `want` means the answer is not complete, even when the
        # stream has ended inside this page.
        if want is not None and len(rows) > want:
            return Scan(rows[:want], scanned, skipped, complete=False)
        if cursor is None:
            return Scan(rows, scanned, skipped, complete=True)
        if want is not None and len(rows) == want:
            return Scan(rows, scanned, skipped, complete=False)
        if scanned >= bound:
            return Scan(rows, scanned, skipped, complete=False)


def _record_out(row: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if not k.startswith("__")}


# ---------- curated facts ----------


@dataclass(frozen=True)
class FactSet:
    facts: list[dict[str, Any]]
    used_chars: int
    complete: bool
    skipped: int
    #: The budget this set was read under. It comes from the owner's declared
    #: `memory.facts_budget`; the constant is only the default for callers that
    #: have no settings to read.
    limit_chars: int = CURATED_CHARS
    #: Whether every earlier revision of these facts was read. The walk stops at a
    #: bound, so a caller that shows earlier values must be able to say whether it
    #: saw all of them; `complete` covers the facts themselves, this covers history.
    history_complete: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"facts": self.facts, "used_chars": self.used_chars,
                "limit_chars": self.limit_chars, "complete": self.complete,
                "skipped": self.skipped, "history_complete": self.history_complete}


def _is_fact(row: dict[str, Any]) -> bool:
    return row.get("kind") == FACT_KIND


def _revision_view(row: dict[str, Any]) -> dict[str, Any]:
    """One stored revision as a screen reads it: the text, when it changed, and its source.

    The source is the record's own `provenance` — a curated fact is an owner
    instruction, and the field is kept rather than assumed, so a record written by
    another writer would be shown with the source it actually carries.
    """
    return {"revision": row["__revision__"], "text": row["text"],
            "created_at": row["created_at"], "updated_at": row["updated_at"],
            "provenance": str(row.get("provenance") or "")}


async def current_facts(source: PageSource, *, limit_chars: int = CURATED_CHARS) -> FactSet:
    """Facts in force: the newest revision of each id, removed ones excluded.

    An updated fact does not lose what it said before. Every earlier revision that was
    read comes back under `superseded`, each with its own date and source, so a screen
    can show the value that is no longer in force instead of letting it disappear. Only
    revisions the walk actually read are listed, and `history_complete` says whether the
    walk reached the end of the stream.
    """
    found = await scan(source, _is_fact)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in found.rows:            # newest first, so each id's newest revision is first
        grouped.setdefault(row["id"], []).append(row)
    facts: list[dict[str, Any]] = []
    for fact_id, revisions in grouped.items():
        newest = revisions[0]
        if newest["state"] != State.COMPLETED.value:
            continue                  # removed, so it is not in force
        view = _revision_view(newest)
        view["id"] = fact_id
        view["superseded"] = [
            _revision_view(row) for row in revisions[1:]
            if row["state"] == State.COMPLETED.value and row["text"] != newest["text"]]
        facts.append(view)
    facts.reverse()                   # oldest first, so the list reads as it was written
    used = sum(len(fact["text"]) for fact in facts)
    return FactSet(facts, used, found.complete, found.skipped, limit_chars,
                   history_complete=found.complete)


async def latest(source: PageSource, kind: str, record_id: str) -> dict[str, Any] | None:
    """The newest stored revision of one record, or None if it was never written.

    Raises `ValueError` when an unreadable record sits above the answer, because
    then the current revision is unknown and must not be acted on.
    """
    found = await scan(source, lambda row: row.get("kind") == kind and row["id"] == record_id,
                       want=1)
    if found.skipped:
        raise ValueError("a newer stored revision could not be read")
    if not found.rows:
        return None
    return found.rows[0]


async def latest_fact(source: PageSource, fact_id: str) -> dict[str, Any] | None:
    """The current revision of one fact, whatever its state. None if never written."""
    return await latest(source, FACT_KIND, fact_id)


def fact_text_error(text: object) -> str | None:
    if not isinstance(text, str) or not text.strip():
        return "text must be a non-empty string"
    if len(text.strip()) > CURATED_CHARS:
        return f"a fact may be at most {CURATED_CHARS} characters"
    return None


def budget_error(used: int, replacing: int, text: str,
                 limit: int = CURATED_CHARS) -> str | None:
    """Refuse a write that would push the curated set past its declared budget.

    `limit` is the owner's `memory.facts_budget`, passed in by the caller that can
    read the settings, so the sentence in the refusal names the limit in force.
    """
    if used - replacing + len(text.strip()) > limit:
        return (f"curated memory is limited to {limit} characters; "
                f"it holds {used - replacing} without this fact")
    return None


def new_fact(fact_id: str, text: str, created_at: str | None = None,
             state: State = State.COMPLETED) -> CuratedFact:
    stamp = now()
    return CuratedFact(id=fact_id or new_id(), text=text.strip(),
                       created_at=created_at or stamp, updated_at=stamp,
                       provenance=Provenance.OWNER_INSTRUCTION, state=state)


# ---------- conversations ----------


async def history(source: PageSource, conversation_id: str, *, limit: int,
                  exclude_id: str | None = None) -> Scan:
    """The newest `limit` messages of one conversation, returned oldest first."""
    found = await scan(source, lambda row: row.get("kind") == MESSAGE_KIND
                       and row.get("conversation_id") == conversation_id
                       and row.get("id") != exclude_id, want=limit)
    return Scan(list(reversed(found.rows)), found.scanned, found.skipped, found.complete)


async def conversation_list(source: PageSource) -> dict[str, Any]:
    """One summary per conversation seen in the window, most recently active first."""
    found = await scan(source, lambda row: row.get("kind") == MESSAGE_KIND)
    summaries: dict[str, dict[str, Any]] = {}
    for row in found.rows:            # newest first
        summary = summaries.get(row["conversation_id"])
        if summary is None:
            summary = summaries[row["conversation_id"]] = {
                "conversation_id": row["conversation_id"], "last_at": row["updated_at"],
                "messages": 0, "title": ""}
        summary["messages"] += 1
        if not summary["title"] and row["role"] == "owner":
            summary["title"] = row["text"][:80]
    return {"conversations": list(summaries.values()), "scanned": found.scanned,
            "skipped": found.skipped, "complete": found.complete}


# ---------- model context ----------


async def reply_context(source: PageSource, conversation_id: str, *, exclude_id: str,
                        history_limit: int, char_budget: int) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Messages to put before the owner's new message, and an honest report.

    The facts come first, as a system message the owner wrote. Earlier messages
    follow oldest first: the newest `history_limit` of this conversation, then
    trimmed from the oldest end until they fit `char_budget`. Every omission is
    named in `notes`. If the stored records cannot be read, the reply is still
    produced without them, and the report says memory was unavailable.
    """
    notes: list[str] = []
    status = "complete"
    fact_texts: list[str] = []
    try:
        facts = await current_facts(source)
    except GraphQueryError as exc:
        status = "memory_unavailable"
        notes.append(f"Curated facts were not read ({exc.reason}); this reply does not use them.")
    else:
        fact_texts = [fact["text"] for fact in facts.facts]
        if not facts.complete or facts.skipped:
            status = "limited"
            notes.append("Curated facts could not be read completely; some may be missing.")

    rows: list[dict[str, Any]] = []
    try:
        found = await history(source, conversation_id, limit=history_limit, exclude_id=exclude_id)
    except GraphQueryError as exc:
        status = "memory_unavailable"
        notes.append(f"Earlier messages were not read ({exc.reason}); this reply does not use them.")
    else:
        if not found.complete:
            status = "limited"
            notes.append(f"Only the newest {history_limit} earlier messages are sent.")
        used = 0
        kept: list[dict[str, Any]] = []
        for row in reversed(found.rows):          # newest first, so the budget keeps the recent
            if used + len(row["text"]) > char_budget:
                status = "limited"
                notes.append(f"Older messages were left out: the limit is {char_budget} characters.")
                break
            used += len(row["text"])
            kept.append(row)
        rows = list(reversed(kept))

    messages: list[dict[str, str]] = []
    if fact_texts:
        messages.append({"role": "system", "content":
                         "Facts the owner stated and asked you to keep in mind. They are the "
                         "owner's own statements, not verified observations:\n"
                         + "\n".join(f"- {text}" for text in fact_texts)})
    for row in rows:
        messages.append({"role": "user" if row["role"] == "owner" else "assistant",
                         "content": row["text"]})
    report = {"status": status, "facts": len(fact_texts), "history": len(rows), "notes": notes}
    return messages, report


# ---------- search ----------


def snippet(text: str, needle: str, radius: int = 60) -> str:
    """A short excerpt around the first occurrence of `needle` (case-insensitive)."""
    at = text.casefold().find(needle.casefold())
    if at < 0:
        return text[: 2 * radius]
    start = max(0, at - radius)
    end = min(len(text), at + len(needle) + radius)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return prefix + text[start:end] + suffix


async def search_messages(source: PageSource, tokens: list[str], *, limit: int) -> Scan:
    """Messages containing every token (case-insensitive), newest first."""
    folded = [token.casefold() for token in tokens]
    return await scan(source, lambda row: row.get("kind") == MESSAGE_KIND
                      and all(token in row.get("text", "").casefold() for token in folded),
                      want=limit)
