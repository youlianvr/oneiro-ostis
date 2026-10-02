"""What happened, when, and what caused it.

A record says what is true now. An event says what happened, and — the part that
matters when several channels are running — what caused it.

`causation_id` is the event that caused this one and `correlation_id` groups every
event belonging to one piece of work. Telegram answering a question the web
channel asked is one conversation: same correlation, different causation. Without
those two fields, a channel can only guess whether a reply belongs to the request
it thinks it sent, which is exactly how stale callbacks end up releasing the
wrong action.

Two properties are deliberate:

- **The envelope never invents certainty.** An event that describes an action
  carries the action's `uncertain` state rather than an optimistic one, so
  subscribers see the same doubt the runtime has.
- **A truncated tail is not a corrupt store.** A crash mid-write can leave a
  partial last line. `read_events` skips a trailing incomplete line and says how
  many it skipped, rather than discarding records that were already durable.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

from oneiro.records import Record, RecordError, SCHEMA_VERSION, decode, new_id

ENVELOPE_VERSION = 1

#: Event names the runtime emits. Declared here so producers and subscribers
#: cannot invent incompatible spellings of the same thing.
EVENTS = (
    "message.recorded",
    "task.created",
    "task.state_changed",
    "run.started",
    "run.state_changed",
    "action.dispatched",
    "action.outcome_observed",
    "decision.made",
    "note.recorded",
    "experience.recorded",
    "experiment.completed",
    "release.promoted",
    "release.rolled_back",
)


@dataclass(frozen=True)
class Event:
    """One occurrence, carrying the record it happened to."""

    event: str
    record: Record
    id: str = field(default_factory=new_id)
    envelope_version: int = ENVELOPE_VERSION
    schema_version: int = SCHEMA_VERSION
    occurred_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    causation_id: str = ""
    correlation_id: str = ""
    channel: str = ""

    def __post_init__(self) -> None:
        if self.event not in EVENTS:
            raise RecordError(f"unknown event {self.event!r}")
        if self.envelope_version != ENVELOPE_VERSION:
            raise RecordError(
                f"envelope version {self.envelope_version}; this build writes {ENVELOPE_VERSION}"
            )
        if not self.correlation_id:
            # Every event belongs to some piece of work; an uncorrelated event
            # cannot be grouped, cancelled or audited later.
            raise RecordError("correlation_id is required")

    @property
    def digest(self) -> str:
        """A stable fingerprint, so a replayed or edited event is detectable.

        Computed over the envelope and the record, never over the stored digest:
        hashing the field that holds the hash would be circular.
        """
        material = json.dumps(self._fingerprint(), sort_keys=True,
                              ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(material).hexdigest()

    def _fingerprint(self) -> dict[str, Any]:
        """The fields the digest covers, without the digest itself."""
        return {
            "event": self.event,
            "id": self.id,
            "envelope_version": self.envelope_version,
            "schema_version": self.schema_version,
            "occurred_at": self.occurred_at,
            "causation_id": self.causation_id,
            "correlation_id": self.correlation_id,
            "channel": self.channel,
            "record": self.record.to_dict(),
        }

    def to_dict(self, *, include_record: bool = True) -> dict[str, Any]:
        data = self._fingerprint()
        data["digest"] = self.digest
        if not include_record:
            data.pop("record")
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)

    def caused_by(self, cause: "Event") -> "Event":
        """The same occurrence, attributed to the event that triggered it."""
        return Event(event=self.event, record=self.record, id=self.id,
                     occurred_at=self.occurred_at, causation_id=cause.id,
                     correlation_id=self.correlation_id or cause.correlation_id,
                     channel=self.channel)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Event":
        for name in ("event", "id", "occurred_at", "correlation_id"):
            if name not in data:
                raise RecordError(f"event envelope is missing {name}")
        payload = data.get("record")
        if not isinstance(payload, dict):
            raise RecordError("event envelope carries no record")
        event = cls(
            event=str(data["event"]),
            record=decode(payload),
            id=str(data["id"]),
            envelope_version=int(data.get("envelope_version", ENVELOPE_VERSION)),
            schema_version=int(data.get("schema_version", SCHEMA_VERSION)),
            occurred_at=str(data["occurred_at"]),
            causation_id=str(data.get("causation_id", "")),
            correlation_id=str(data["correlation_id"]),
            channel=str(data.get("channel", "")),
        )
        claimed = data.get("digest")
        if claimed and claimed != event.digest:
            raise RecordError(
                f"event {event.id} does not match its digest; it was edited or truncated"
            )
        return event


#: The event each record kind produces unless the caller says otherwise.
#: Without this, a record would be wrapped under a name no subscriber expects.
DEFAULT_EVENT_NAMES = {
    "conversation_message": "message.recorded",
    "task": "task.created",
    "run": "run.started",
    "action": "action.dispatched",
    "decision": "decision.made",
    "note": "note.recorded",
    "experience": "experience.recorded",
    "experiment": "experiment.completed",
    "release": "release.promoted",
}


def sequence(records: Iterable[Record], correlation_id: str, channel: str = "",
             names: dict[str, str] | None = None) -> list[Event]:
    """Wrap records in order, each caused by the one before it."""
    table = dict(DEFAULT_EVENT_NAMES)
    table.update(names or {})
    events: list[Event] = []
    previous: Event | None = None
    for record in records:
        name = table.get(record.KIND, "")
        if not name:
            raise RecordError(f"no event name is declared for record kind {record.KIND!r}")
        event = Event(event=name, record=record, correlation_id=correlation_id,
                      channel=channel,
                      causation_id=previous.id if previous else "")
        events.append(event)
        previous = event
    return events


def read_events(text: str) -> tuple[list[Event], int]:
    """Every complete event in a JSON-lines store, and how many were skipped.

    A torn final line is reported rather than raised: a crash during the last
    append leaves earlier records durable and still readable, and losing them
    would be worse than reporting one incomplete line.
    """
    events: list[Event] = []
    skipped = 0
    lines = text.splitlines()
    for number, line in enumerate(lines, start=1):
        line = line.strip()
        if not line:
            continue
        try:
            events.append(Event.from_dict(json.loads(line)))
        except (ValueError, RecordError, KeyError, TypeError):
            skipped += 1
            if number == len(lines):        # a truncated tail, not a bad store
                continue
            raise RecordError(f"event line {number} is unreadable") from None
    return events, skipped