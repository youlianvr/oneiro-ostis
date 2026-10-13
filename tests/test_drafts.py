"""W3: mail in, a draft out, and the press that alone lets it go.

Every test here runs a **real** MCP server: a child process speaking line-delimited
JSON-RPC over stdio, started by the product's own `mcp.LocalSession`, exactly as a server
on this machine starts. Nothing about the transport is faked, and the server writes down
every call that actually arrived — which is what makes the central claim measurable rather
than asserted:

    without the owner's press, the mailbox server receives no send at all.

The rules under test, one at a time:

* an incoming letter is read and kept, with observation provenance, and a read needs no
  press because it is not a send;
* a draft is an `Action` in `WAITING` plus a pending `Approval` naming exactly that call:
  the owner reads the real bytes, not a summary;
* sending without the owner's grant is refused by name, and the server's own log shows the
  call never left the machine;
* the owner's press decides the approval and releases exactly one call; a second press is
  refused and sends nothing again;
* editing a draft after a press makes it an unpressed call again, because the grant is
  bound to the arguments it was given for;
* a boundary (`send_publish: deny`) cannot be opened by any number of presses;
* a turn can write a draft and can never release one: the model has no way to decide an
  approval, and the log stays empty while the turn asks;
* the notice to the owner has no recipient parameter at all — its address is discovered
  from the bot's own updates, so no caller can name somebody else;
* the console's routes are the owner's press, and the page token is what stands in front
  of them.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from chat_fakes import GraphStub, MemoryLinks, csrf_of, isolate, make_app, post
from oneiro import approvals, drafts, i18n, mcp
from oneiro.agent import default_registry, run_turn
from oneiro.chat import ModelReply, ToolCall
from oneiro.records import EffectOutcome, Provenance, State
from oneiro.tools import Policy
from oneiro.runtime import Runtime

CLIENT = "draft-test-0001"
MAIL = "mailbox.send_message"
READ = "mailbox.list_messages"
NOTICE = "bot.send_message"
UPDATES = "bot.get_updates"
CALL = {"to": "curator@example.org", "subject": "Отчёт о приёме",
        "body": "Отчёт подготовлю к пятнице."}

#: A real MCP server on stdio, in the shape the ecosystem speaks. It writes down every
#: call that reached it, which is the evidence the tests measure.
FAKE_SERVER = r'''
import json, sys

LOG, ROLE = sys.argv[1], sys.argv[2]

TOOLS = {
    "mailbox": [
        {"name": "list_messages", "description": "The newest incoming mail.",
         "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}}},
        {"name": "send_message", "description": "Send one message.",
         "inputSchema": {"type": "object", "required": ["to", "subject", "body"],
                         "properties": {"to": {"type": "string"}, "subject": {"type": "string"},
                                        "body": {"type": "string"}}}},
    ],
    "bot": [
        {"name": "get_updates", "description": "What was written to the bot.",
         "inputSchema": {"type": "object", "properties": {}}},
        {"name": "send_message", "description": "Send one message to a chat.",
         "inputSchema": {"type": "object", "required": ["chat_id", "text"],
                         "properties": {"chat_id": {"type": "integer"},
                                        "text": {"type": "string"}}}},
    ],
}[ROLE]

INBOX = {"messages": [{
    "id": "m-1",
    "from": "Куратор <curator@example.org>",
    "subject": "Отчёт о приёме в десятый класс",
    "body": "Прошу подготовить отчёт к пятнице."}]}
UPDATES = {"ok": True, "result": [
    {"update_id": 1, "message": {"chat": {"id": 424242, "type": "private"}, "text": "привет"}}]}


def note(tool, arguments):
    with open(LOG, "a", encoding="utf-8") as stream:
        stream.write(json.dumps({"server": ROLE, "tool": tool, "arguments": arguments},
                                ensure_ascii=False) + "\n")


def send(message):
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    request = json.loads(line)
    method = request.get("method")
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": request["id"],
              "result": {"protocolVersion": "2024-11-05", "capabilities": {},
                         "serverInfo": {"name": ROLE, "version": "1"}}})
    elif method == "notifications/initialized":
        continue
    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": request["id"], "result": {"tools": TOOLS}})
    elif method == "tools/call":
        params = request.get("params") or {}
        name, arguments = params.get("name"), params.get("arguments") or {}
        note(name, arguments)
        if name == "list_messages":
            text = json.dumps(INBOX, ensure_ascii=False)
        elif name == "get_updates":
            text = json.dumps(UPDATES, ensure_ascii=False)
        else:
            text = "ok: " + json.dumps(arguments, ensure_ascii=False)
        send({"jsonrpc": "2.0", "id": request["id"],
              "result": {"content": [{"type": "text", "text": text}]}})
'''


@pytest.fixture()
def servers(tmp_path: Path, monkeypatch) -> Path:
    """Isolated settings, data root and MCP list, with two real servers behind them."""
    isolate(tmp_path, monkeypatch)
    script = tmp_path / "fake_server.py"
    script.write_text(FAKE_SERVER, encoding="utf-8")
    log = tmp_path / "calls.jsonl"
    # The reviewed default refuses sending; the owner in these tests has allowed it, which
    # is what a person does once before the mailbox may answer anybody.
    (tmp_path / "settings.json").write_text(
        json.dumps({"permissions.send_publish": "ask"}), encoding="utf-8")
    (tmp_path / "mcp.json").write_text(json.dumps({"mcp": {
        "mailbox": {"type": "local", "enabled": True,
                    "command": [sys.executable, str(script), str(log), "mailbox"]},
        "bot": {"type": "local", "enabled": True,
                "command": [sys.executable, str(script), str(log), "bot"]}}}), encoding="utf-8")
    mcp.set_hub(mcp.Hub())
    yield log
    mcp.hub().close()
    mcp.set_hub(None)


def calls(log: Path) -> list[dict]:
    """What the servers were actually asked to do, in the order it arrived."""
    if not log.is_file():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]


def owner_for(tmp_path: Path) -> Runtime:
    """The real store over the in-memory link graph, with both servers behind it."""
    return Runtime(graph=GraphStub(MemoryLinks(), tmp_path / "graph-writer.lock"))


def stored(owner, kind: str) -> list[dict]:
    page = asyncio.run(owner.memory_page(limit=500))
    return [row for row in page["items"] if row["kind"] == kind]


async def _turn_with(owner, text: str, client_id: str, policy: Policy, replies: list) -> dict:
    """One turn whose model answers from a script, so the path is the production one."""
    script = list(replies)

    def call(messages, **_kwargs):
        return script.pop(0)(messages)

    return await run_turn(owner, text, client_id, "main",
                          registry=default_registry(owner, "main"), policy=policy, call=call)


# ----------------------------------------------------------- the letter, and the draft


def test_an_incoming_letter_is_read_and_kept_as_an_observation(servers: Path, tmp_path: Path):
    owner = owner_for(tmp_path)

    read = asyncio.run(drafts.read_incoming(owner, tool=READ, arguments={"query": "is:unread"}))

    assert read["ok"] is True and read["read"] == 1
    note = read["notes"][0]
    assert note["topic"] == "Отчёт о приёме в десятый класс"
    assert "к пятнице" in note["body"]
    assert note["provenance"] == Provenance.OBSERVATION.value
    assert any("curator@example.org" in source for source in note["sources"]), \
        "the letter names who it came from"
    assert [row["tool"] for row in calls(servers)] == ["list_messages"], "a read is a read"


def test_a_read_that_is_asked_again_does_not_duplicate_the_letter(servers: Path, tmp_path: Path):
    """A second read of the same letter writes nothing: the record stands as it is.

    Falsified where it hurt, on the live graph (2026-10-12): the note's id is the digest of
    what arrived, so writing it again with a fresh timestamp is one operation id with
    different content — the graph refuses that as a collision and `POST /api/mail/read`
    answered 503 for a letter read a second time. The second read is now a read.
    """
    owner = owner_for(tmp_path)
    written: list[str] = []
    standing = owner.publish

    async def watching(record, operation_id, **kwargs):
        written.append(operation_id)
        return await standing(record, operation_id, **kwargs)

    owner.publish = watching

    first = asyncio.run(drafts.read_incoming(owner, tool=READ))
    second = asyncio.run(drafts.read_incoming(owner, tool=READ))

    assert [row["id"] for row in first["notes"]] == [row["id"] for row in second["notes"]]
    assert first["notes"][0]["created_at"] == second["notes"][0]["created_at"]
    assert len(stored(owner, "note")) == 1, "the same letter is one record"
    assert [op for op in written if op.startswith("mail-")] == [first["notes"][0]["id"]], \
        "the second read writes nothing at all"
    assert [row["tool"] for row in calls(servers)] == ["list_messages", "list_messages"]


def test_an_edit_that_changes_nothing_is_not_a_revision(servers: Path, tmp_path: Path):
    """Asking for the words the draft already has writes nothing and asks nothing new.

    A command repeated after a graph failure would otherwise write the same revision under
    the same operation id with a new timestamp, which the graph refuses as a collision.
    """
    owner = owner_for(tmp_path)
    created = asyncio.run(drafts.create(owner, tool=MAIL, arguments=CALL))
    before = asyncio.run(drafts.get(owner, created["id"]))
    rows = len(stored(owner, "action"))

    again = asyncio.run(drafts.revise(owner, created["id"], arguments=dict(CALL)))

    assert again == before, "the same words are the same draft, timestamps and all"
    assert len(stored(owner, "action")) == rows, "no revision was written"
    assert len(stored(owner, "approval")) == 1, "no second approval was asked for"
    assert calls(servers) == []


def test_calling_a_draft_off_twice_is_the_same_decision(servers: Path, tmp_path: Path):
    """The owner's no, said twice in the same words, is one decision on record.

    A different reason is a different question and is refused, not rewritten: the refusal
    already stands.
    """
    owner = owner_for(tmp_path)
    created = asyncio.run(drafts.create(owner, tool=MAIL, arguments=CALL))

    first = asyncio.run(drafts.discard(owner, created["id"], reason="не нужно"))
    rows = len(stored(owner, "action"))
    again = asyncio.run(drafts.discard(owner, created["id"], reason="не нужно"))

    assert first["state"] == State.CANCELLED.value and again == first
    assert len(stored(owner, "action")) == rows, "the second no wrote nothing"
    with pytest.raises(drafts.DraftError) as settled:
        asyncio.run(drafts.discard(owner, created["id"], reason="другая причина"))
    assert settled.value.reason == drafts.ALREADY_SETTLED


def test_a_draft_is_written_down_and_nothing_leaves(servers: Path, tmp_path: Path):
    owner = owner_for(tmp_path)

    draft = asyncio.run(drafts.create(owner, tool=MAIL, arguments=CALL))

    assert draft["state"] == State.WAITING.value and draft["decision"] == "ask"
    assert draft["why"] == "waiting for your press"
    assert draft["arguments"] == CALL, "the record holds the exact call, not a summary"
    assert draft["effect"]["kind"] == "send" and draft["target"] == CALL["to"]
    assert draft["approval"]["state"] == State.WAITING.value
    assert draft["approval"]["pressed"] is False
    assert calls(servers) == [], "writing a draft puts nothing on the wire"
    recorded = stored(owner, "action")
    assert [row["state"] for row in recorded] == [State.WAITING.value]
    assert drafts.DRAFT_LABEL in recorded[0]["labels"]


def test_the_same_reply_written_twice_is_one_draft(servers: Path, tmp_path: Path):
    owner = owner_for(tmp_path)

    first = asyncio.run(drafts.create(owner, tool=MAIL, arguments=CALL))
    second = asyncio.run(drafts.create(owner, tool=MAIL, arguments=CALL))

    assert first["id"] == second["id"] and len(stored(owner, "action")) == 1


def test_a_draft_the_server_would_refuse_is_refused_here_with_the_field_named(servers: Path,
                                                                            tmp_path: Path):
    owner = owner_for(tmp_path)

    with pytest.raises(drafts.DraftError) as missing:
        asyncio.run(drafts.create(owner, tool=MAIL, arguments={"to": "a@b.c", "subject": "s"}))
    assert missing.value.reason == drafts.BAD_ARGUMENTS and "body" in str(missing.value)

    with pytest.raises(drafts.DraftError) as extra:
        asyncio.run(drafts.create(owner, tool=MAIL, arguments={**CALL, "cc": "x@y.z"}))
    assert "cc" in str(extra.value)

    with pytest.raises(drafts.DraftError) as unknown:
        asyncio.run(drafts.create(owner, tool="nosuch.tool", arguments={}))
    assert unknown.value.reason == drafts.UNKNOWN_TOOL
    assert calls(servers) == []


# ------------------------------------------------------------- the press, and the gate


def test_without_the_press_nothing_is_sent_and_the_reason_is_named(servers: Path, tmp_path: Path):
    owner = owner_for(tmp_path)
    draft = asyncio.run(drafts.create(owner, tool=MAIL, arguments=CALL))

    with pytest.raises(drafts.DraftError) as refused:
        asyncio.run(drafts.send(owner, draft["id"]))

    assert refused.value.reason == drafts.NOT_PRESSED
    assert "press" in str(refused.value)
    assert calls(servers) == [], "the mailbox saw nothing"
    assert asyncio.run(approvals.granted_for(owner, MAIL, CALL)) is None
    # The draft is still there, still waiting: a refusal is not an outcome.
    assert asyncio.run(drafts.get(owner, draft["id"]))["state"] == State.WAITING.value


def test_a_model_cannot_release_a_draft_by_asking_to(servers: Path, tmp_path: Path):
    owner = owner_for(tmp_path)
    draft = asyncio.run(drafts.create(owner, tool=MAIL, arguments=CALL))

    with pytest.raises(approvals.ApprovalError) as refused:
        asyncio.run(approvals.decide(owner, draft["approval"]["id"], granted=True,
                                    actor="model"))

    assert refused.value.reason == approvals.NOT_THE_OWNER
    assert calls(servers) == []


def test_the_press_sends_exactly_once_and_the_grant_is_spent(servers: Path, tmp_path: Path):
    owner = owner_for(tmp_path)
    draft = asyncio.run(drafts.create(owner, tool=MAIL, arguments=CALL))

    sent = asyncio.run(drafts.press(owner, draft["id"]))

    assert sent["ok"] is True and sent["state"] == State.COMPLETED.value
    assert sent["effect"] == "succeeded" and sent["draft"]["why"] == "sent"
    assert calls(servers) == [{"server": "mailbox", "tool": "send_message", "arguments": CALL}]
    assert asyncio.run(approvals.granted_for(owner, MAIL, CALL)) is None, "one press, one send"

    with pytest.raises(drafts.DraftError) as again:
        asyncio.run(drafts.press(owner, draft["id"]))
    assert again.value.reason == drafts.ALREADY_SETTLED
    assert len(calls(servers)) == 1, "a second press sends nothing again"


def test_the_press_may_be_asked_for_without_being_given(servers: Path, tmp_path: Path):
    owner = owner_for(tmp_path)
    draft = asyncio.run(drafts.create(owner, tool=MAIL, arguments=CALL))

    with pytest.raises(drafts.DraftError) as unpressed:
        asyncio.run(drafts.send(owner, draft["id"], dry_run=True))
    assert unpressed.value.reason == drafts.NOT_PRESSED

    asyncio.run(approvals.decide(owner, draft["approval"]["id"], granted=True, actor="owner"))
    asked = asyncio.run(drafts.send(owner, draft["id"], dry_run=True))

    assert asked["dry_run"] is True and asked["ok"] is True
    assert "approved" in asked["why"]
    assert calls(servers) == [], "a dry run sends nothing and spends nothing"
    assert asyncio.run(approvals.granted_for(owner, MAIL, CALL)) is not None


def test_an_edited_draft_is_an_unpressed_call_again(servers: Path, tmp_path: Path):
    owner = owner_for(tmp_path)
    draft = asyncio.run(drafts.create(owner, tool=MAIL, arguments=CALL))
    asyncio.run(approvals.decide(owner, draft["approval"]["id"], granted=True, actor="owner"))

    edited = asyncio.run(drafts.revise(owner, draft["id"], arguments={**CALL,
                                                                    "body": "Отчёт к среде."}))

    assert edited["arguments"]["body"] == "Отчёт к среде."
    assert edited["approval"]["granted"] is False and edited["approval"]["pressed"] is False
    with pytest.raises(drafts.DraftError) as refused:
        asyncio.run(drafts.send(owner, draft["id"]))
    assert refused.value.reason == drafts.NOT_PRESSED, \
        "the grant was for the old text and cannot release the new one"
    assert calls(servers) == []


def test_a_refused_permission_cannot_be_opened_by_any_press(servers: Path, tmp_path: Path):
    owner = owner_for(tmp_path)
    draft = asyncio.run(drafts.create(owner, tool=MAIL, arguments=CALL))
    asyncio.run(approvals.decide(owner, draft["approval"]["id"], granted=True, actor="owner"))
    boundary = Policy({"decisions": {"send": "deny"}})

    with pytest.raises(drafts.DraftError) as refused:
        asyncio.run(drafts.send(owner, draft["id"], policy=boundary))

    assert refused.value.reason == drafts.PERMISSION_DENIED
    assert "send_publish" in str(refused.value)
    assert calls(servers) == [], "a boundary is not a thing a press can open"


def test_a_discarded_draft_is_called_off_on_record(servers: Path, tmp_path: Path):
    owner = owner_for(tmp_path)
    draft = asyncio.run(drafts.create(owner, tool=MAIL, arguments=CALL))

    off = asyncio.run(drafts.discard(owner, draft["id"], reason="not needed"))

    assert off["state"] == State.CANCELLED.value and off["why"] == "discarded"
    assert off["approval"]["granted"] is False
    assert [row["id"] for row in asyncio.run(approvals.pending(owner))] == []
    assert calls(servers) == []


def test_a_turn_that_asks_to_send_records_the_ask_and_sends_nothing(servers: Path, tmp_path: Path):
    """The model may ask; the mailbox is the evidence that asking is all it did."""
    mcp.set_hub(mcp.Hub())
    asyncio.run(mcp.hub().open("mailbox"))
    owner = owner_for(tmp_path)

    def asking(_messages, **_kwargs):
        return ModelReply("", (ToolCall("call-1", MAIL, CALL),))

    def answering(_messages, **_kwargs):
        return ModelReply("I wrote it down and asked you first.")

    result = asyncio.run(_turn_with(owner, "answer the curator", "turn-send-0001",
                                    Policy({"decisions": {"mcp_call": "ask"}}),
                                    [asking, answering]))

    assert result["steps"][0]["decision"] == "ask"
    assert result["reply"]["text"] == "I wrote it down and asked you first."
    assert calls(servers) == [], "the turn asked; it did not send"
    pending = asyncio.run(approvals.pending(owner))
    assert [row["tool"] for row in pending] == [MAIL]
    waited = [row for row in stored(owner, "action") if row["tool"] == MAIL]
    assert [row["state"] for row in waited] == [State.WAITING.value]
    assert [row["effect"]["outcome"] for row in waited] == [EffectOutcome.NONE.value], \
        "nothing ran while the call waited for the owner"


# ------------------------------------------------------------------ the notice


def test_the_notice_has_no_recipient_parameter():
    """The address of a notice is not something any caller can name."""
    names = set(inspect.signature(drafts.notify).parameters)
    assert names == {"owner", "text", "tool", "updates_tool", "policy"}
    assert not names & {"to", "chat", "chat_id", "recipient", "user", "address", "channel",
                        "target", "peer", "conversation"}


def test_the_notice_goes_to_the_chat_the_bot_reports(servers: Path, tmp_path: Path):
    owner = owner_for(tmp_path)
    draft = asyncio.run(drafts.create(owner, tool=MAIL, arguments=CALL))

    sent = asyncio.run(drafts.notify(owner, drafts.notice_for(owner, draft),
                                     tool=NOTICE, updates_tool=UPDATES))

    assert sent["ok"] is True and sent["chat_id"] == 424242
    asked = calls(servers)
    assert [row["tool"] for row in asked] == ["get_updates", "send_message"]
    assert asked[1]["arguments"]["chat_id"] == 424242
    assert "Отчёт о приёме" in asked[1]["arguments"]["text"]
    assert draft["id"] in asked[1]["arguments"]["text"], "the notice names the draft to press"


def test_the_notice_speaks_the_owners_language(servers: Path, tmp_path: Path):
    owner = owner_for(tmp_path)
    draft = asyncio.run(drafts.create(owner, tool=MAIL, arguments=CALL))

    russian = drafts.notice(draft, lang="ru")
    english = drafts.notice(draft, lang="en")

    assert russian.startswith(i18n.t("draft.notice.head", "ru")) and "«" not in english
    assert "Кому: curator@example.org" in russian and "To: curator@example.org" in english
    assert russian != english and i18n.t("draft.notice.head", "ru") in russian


def test_an_owner_who_refuses_sending_is_told_so_by_the_notice_route(servers: Path,
                                                                     tmp_path: Path):
    owner = owner_for(tmp_path)
    draft = asyncio.run(drafts.create(owner, tool=MAIL, arguments=CALL))
    boundary = Policy({"decisions": {"send": "deny"}})

    with pytest.raises(drafts.DraftError) as refused:
        asyncio.run(drafts.notify(owner, "hello", tool=NOTICE, updates_tool=UPDATES,
                                  policy=boundary))

    assert refused.value.reason == drafts.PERMISSION_DENIED
    assert calls(servers) == []


# ------------------------------------------------------------------ the console


def test_the_console_offers_the_draft_and_the_press_releases_exactly_it(servers: Path,
                                                                       tmp_path: Path):
    links = MemoryLinks()
    with TestClient(make_app(tmp_path, links)) as client:
        owner = client.app.state.runtime
        csrf = csrf_of(client)

        read = post(client, "/api/mail/read", {"tool": READ, "limit": 5}, csrf)
        assert read.status_code == 200 and read.json()["read"] == 1

        created = post(client, "/api/drafts", {"tool": MAIL, "arguments": CALL}, csrf)
        assert created.status_code == 201, created.text
        draft_id = created.json()["id"]
        assert created.json()["why"] == "waiting for your press"

        listed = client.get("/api/drafts").json()
        assert [row["id"] for row in listed["drafts"]] == [draft_id]

        asked = post(client, f"/api/drafts/{draft_id}/send", {"dry_run": True}, csrf)
        assert asked.status_code == 409 and asked.json()["reason"] == drafts.NOT_PRESSED
        assert [row["tool"] for row in calls(servers)] == ["list_messages"], \
            "the console asked; the mailbox was not written to"

        sent = post(client, f"/api/drafts/{draft_id}/send", {"dry_run": False}, csrf)
        assert sent.status_code == 200, sent.text
        assert sent.json()["state"] == State.COMPLETED.value

        again = post(client, f"/api/drafts/{draft_id}/send", {"dry_run": False}, csrf)
        assert again.status_code == 409 and again.json()["reason"] == drafts.ALREADY_SETTLED

        notice = post(client, "/api/telegram/notice",
                      {"draft_id": draft_id, "tool": NOTICE, "updates_tool": UPDATES}, csrf)
        assert notice.status_code == 200 and notice.json()["chat_id"] == 424242

        without_token = client.post("/api/drafts", json={"tool": MAIL, "arguments": CALL})
        assert without_token.status_code == 403
        assert "Invalid owner request token" in without_token.text

    reached = calls(servers)
    assert [(row["server"], row["tool"]) for row in reached] == [
        ("mailbox", "list_messages"), ("mailbox", "send_message"),
        ("bot", "get_updates"), ("bot", "send_message")], \
        "one read, one send, one notice, in that order"
    assert reached[1]["arguments"] == CALL
    assert reached[3]["arguments"]["chat_id"] == 424242
    assert draft_id in reached[3]["arguments"]["text"], "the notice names the draft to press"
