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
        if cursor is None:
            return Scan(rows, scanned, skipped, complete=True)
        if want is not None and len(rows) >= want:
            return Scan(rows[:want], scanned, skipped, complete=False)
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

    def to_dict(self) -> dict[str, Any]:
        return {"facts": self.facts, "used_chars": self.used_chars,
                "limit_chars": CURATED_CHARS, "complete": self.complete,
                "skipped": self.skipped}


def _is_fact(row: dict[str, Any]) -> bool:
    return row.get("kind") == FACT_KIND


async def current_facts(source: PageSource) -> FactSet:
    """Facts in force: the newest revision of each id, removed ones excluded."""
    found = await scan(source, _is_fact)
    seen: set[str] = set()
    facts: list[dict[str, Any]] = []
    for row in found.rows:            # newest first: the first sighting is current
        fact_id = row["id"]
        if fact_id in seen:
            continue
        seen.add(fact_id)
        if row["state"] == State.COMPLETED.value:
            facts.append({"id": fact_id, "text": row["text"],
                          "revision": row["__revision__"],
                          "created_at": row["created_at"],
                          "updated_at": row["updated_at"]})
    facts.reverse()                   # oldest first, so the list reads as it was written
    used = sum(len(fact["text"]) for fact in facts)
    return FactSet(facts, used, found.complete, found.skipped)


async def latest_fact(source: PageSource, fact_id: str) -> dict[str, Any] | None:
    """The current revision of one fact, whatever its state. None if never written.

    Raises `ValueError` when an unreadable record sits above the answer, because
    then the current revision is unknown and must not be acted on.
    """
    found = await scan(source, lambda row: _is_fact(row) and row["id"] == fact_id, want=1)
    if found.skipped:
        raise ValueError("a newer stored revision could not be read")
    if not found.rows:
        return None
    return found.rows[0]


def fact_text_error(text: object) -> str | None:
    if not isinstance(text, str) or not text.strip():
        return "text must be a non-empty string"
    if len(text.strip()) > CURATED_CHARS:
        return f"a fact may be at most {CURATED_CHARS} characters"
    return None


def budget_error(used: int, replacing: int, text: str) -> str | None:
    """Refuse a write that would push the curated set past its limit."""
    if used - replacing + len(text.strip()) > CURATED_CHARS:
        return (f"curated memory is limited to {CURATED_CHARS} characters; "
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
