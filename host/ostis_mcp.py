"""What the host gets from us, over the protocol it already speaks.

The host (CowAgent) reads its MCP servers from ``<workspace>/mcp.json`` in the same
format every other tool on this machine uses, so the knowledge graph and the human
question arrive as ordinary tools rather than as a fork of their code.

Three tools, each honest about what it does:

* ``memory_search`` reads the graph and answers with provenance: every line it
  returns names the record it came from and when that record was written.
* ``memory_record`` writes one dated record into the graph. The graph is the
  store; nothing is kept only in the host's own memory files.
* ``ask_human`` sends a question to the owner with two buttons and returns the
  decision, which exists only as a press from his account, recorded in the graph.

Run by the host over stdio:

    python host/ostis_mcp.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve()
PROJECT = HERE.parent.parent
PYTHON_DIR = PROJECT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from mcp.server.fastmcp import FastMCP  # noqa: E402

import approval  # noqa: E402
from bridge import OneiroBridge  # noqa: E402

HOST_SESSION_PREFIX = "host-cowagent"
DEFAULT_WORKSPACE = Path(os.environ.get("ONEIRO_WORKSPACE", Path.home() / ".openclaw" / "workspace"))

server = FastMCP("oneiro")

_bridge: Optional[OneiroBridge] = None


def graph() -> OneiroBridge:
    """One connection per process: the host calls tools in a background thread."""
    global _bridge
    if _bridge is None:
        _bridge = OneiroBridge(
            host=os.environ.get("ONEIRO_HOST", "localhost"),
            port=int(os.environ.get("ONEIRO_PORT", "8090")),
        )
        _bridge.connect()
    return _bridge


def session_id(bridge: OneiroBridge) -> str:
    """The host's own long-lived session, created once and reused after restarts."""
    try:
        for record in reversed(bridge.load_life_sessions()):
            if record.session_id.startswith(HOST_SESSION_PREFIX):
                return record.session_id
    except Exception:
        pass
    created = bridge.start_life_session(
        f"{HOST_SESSION_PREFIX}-life",
        goals=[{"text": "work as the owner's assistant with the graph as its memory",
                "origin": "rule"}],
        self_state={"phase": "host", "origin": "rule"},
    )
    return created.session_id


# Function words that match everything and therefore say nothing. A query made
# only of these is refused rather than answered with noise.
STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "was", "were", "are", "his", "her",
    "its", "from", "into", "about", "what", "when", "where", "who", "how", "did",
    "does", "not", "but", "all", "any", "our", "their", "have", "has", "had", "been",
    "и", "в", "во", "на", "за", "по", "из", "что", "как", "это", "для", "или", "но",
    "не", "мы", "он", "она", "они", "его", "её", "у", "с", "со", "к", "о", "об",
}


def _content_words(query: str) -> list[str]:
    """Words that carry meaning: no function words, nothing shorter than three."""
    words = []
    for raw in (query or "").lower().replace(",", " ").replace(".", " ").split():
        word = raw.strip("-_:;!?()[]{}\"'")
        if len(word) >= 3 and word not in STOPWORDS:
            words.append(word)
    return words


@server.tool()
def memory_search(query: str, limit: int = 5) -> str:
    """Search what the agent already knows, with the record each answer came from.

    Args:
        query: words to look for in the recorded work and notes.
        limit: how many records to return at most.
    """
    bridge = graph()
    terms = [t for t in _content_words(query)]
    found: list[tuple[int, str]] = []
    for record in bridge.load_organization_events():
        blob = f"{record.role} {record.kind} {record.payload}".lower()
        score = sum(1 for term in terms if term in blob)
        if score:
            found.append((score, record))
    if not terms:
        return ("The query is only function words, so it would match everything. "
                "Ask with the words that name the thing (a name, a file, a task).")
    # One shared word is a coincidence, not a memory: require two, or a single
    # term when it is long enough to be a name rather than a common word.
    found = [pair for pair in found
             if pair[0] >= 2 or any(len(t) >= 7 for t in terms if t in str(pair[1].payload).lower())]
    found.sort(key=lambda pair: (-pair[0], -pair[1].recorded_at))
    if not found:
        return (f"Nothing recorded about {query!r}. Say so instead of guessing; "
                f"the graph holds {len(bridge.load_organization_events())} records.")
    lines = [f"{len(found)} records match {query!r}; the closest ones:"]
    for score, record in found[: max(1, int(limit))]:
        payload = str(record.payload)
        if len(payload) > 220:
            payload = payload[:220] + "..."
        lines.append(
            f"- [{record.kind}] {payload}\n"
            f"  recorded: {record.recorded_at} by role {record.role}, "
            f"origin {record.origin}, verified {record.verified}, id {record.record_id}"
        )
    return "\n".join(lines)


@server.tool()
def memory_record(text: str, kind: str = "note", subject: str = "") -> str:
    """Record one dated fact into the graph so it survives this conversation.

    Args:
        text: what is worth remembering, in one or two sentences.
        kind: a short label such as note, letter, list, decision.
        subject: whose work this belongs to, if it belongs to someone.
    """
    bridge = graph()
    record = bridge.record_organization_event(
        session_id=session_id(bridge),
        role="agent",
        kind=kind or "note",
        payload={"text": text, "subject": subject, "origin": "model"},
        origin="model",
        verified=False,
    )
    return f"recorded as {record.record_id} at {record.recorded_at}"


@server.tool()
def memory_tail(limit: int = 8) -> str:
    """The most recent things recorded, newest last, to see where the work stands.

    Args:
        limit: how many records to show.
    """
    bridge = graph()
    records = bridge.load_organization_events()
    lines = []
    for record in records[-max(1, int(limit)):]:
        payload = str(record.payload)
        if len(payload) > 160:
            payload = payload[:160] + "..."
        lines.append(f"{record.recorded_at} {record.role}/{record.kind}: {payload}")
    return "\n".join(lines) or "the graph is empty"


def _channel(state_path: Optional[Path] = None) -> approval.TelegramApprovalChannel:
    owner = approval._walk_env(None, approval.TELEGRAM_OWNER_ENV)
    if not owner:
        raise approval.ApprovalError(
            f"no owner id: set {approval.TELEGRAM_OWNER_ENV} in the environment or a .env above {PROJECT}"
        )
    bridge = graph()

    def record(kind: str, payload: dict) -> None:
        bridge.record_organization_event(
            session_id=session_id(bridge),
            role="human" if kind == "proposal_decided" else "agent",
            kind=kind,
            payload=payload,
            origin="human" if kind == "proposal_decided" else "rule",
            verified=True,
        )

    return approval.TelegramApprovalChannel(
        owner_user_id=int(owner),
        state_path=state_path or (PROJECT / "state" / "approvals.json"),
        recorder=record,
    )


@server.tool()
def ask_human(title: str, found: str, proposed: str, needed: str,
              target: str, proposal_id: str, wait_seconds: int = 0) -> str:
    """Ask the owner before doing something that leaves the machine.

    Use it for anything that writes outside this conversation: sending a letter,
    adding rows to a register, moving or deleting documents, changing its own code.

    Args:
        title: one line the owner sees first.
        found: what you actually found, with the file or message it came from.
        proposed: the concrete action you want to take.
        needed: what you need from him, in his own words.
        target: where the effect lands, such as a register, file or mailbox.
        proposal_id: a short slug, unique for this question.
        wait_seconds: how long to wait for the press before returning unanswered.
    """
    channel = _channel()
    proposal = approval.Proposal.action(
        proposal_id=proposal_id,
        title=title,
        found=found,
        proposed=proposed,
        needed=needed,
        target=target,
    )
    channel.send(proposal)
    if wait_seconds and int(wait_seconds) > 0:
        import time

        deadline = time.time() + min(600, int(wait_seconds))
        while time.time() < deadline:
            result = channel.poll()
            for decision in result.decisions:
                if decision.proposal_id == proposal_id:
                    return f"{decision.verdict}: {decision.proposal_id}"
            time.sleep(2)
    return (f"question sent as {proposal_id}; the button decides it, nothing is done "
            f"until then. Ask again with check_answer to read the verdict.")


@server.tool()
def check_answer(proposal_id: str) -> str:
    """Read the owner's answer to a question that was already sent.

    Args:
        proposal_id: the slug returned by ask_human.
    """
    channel = _channel()
    result = channel.poll()
    for decision in result.decisions:
        if decision.proposal_id == proposal_id:
            return f"{decision.verdict}: {proposal_id}"
    if channel.is_approved(proposal_id):
        return f"approve: {proposal_id}"
    if proposal_id in channel.decided:
        return f"{channel.decided[proposal_id]['verdict']}: {proposal_id}"
    refusals = [r for r in result.refusals if r.get("proposal_id") == proposal_id]
    if refusals:
        return f"refused ({refusals[0]['reason']}): {proposal_id}"
    return f"no answer yet: {proposal_id}"


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
