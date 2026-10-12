"""The webhook: one signed local POST becomes a task, and every refusal names its cause.

The door belongs to the console, so most of it is exercised through the console — the
real app, the real middleware, the real store — rather than by calling `hooks.deliver`
in a vacuum. A signature the route cannot reach is tested on the module itself: the
secret's file, rotation, and the size bound.

The four ways a delivery can be wrong are each one test with its own code and sentence,
because the point of the contract is that an integrator can read the answer and know
which half of their script is wrong.
"""
from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from chat_fakes import MemoryLinks, isolate, make_app
from oneiro import hooks, tasks, web
from oneiro.query import GraphQueryError
from oneiro.records import State
from oneiro.runtime import Runtime

PAYLOAD = {"title": "Backup ran with errors", "detail": "three files were skipped"}
BODY = json.dumps(PAYLOAD).encode("utf-8")
STRANGER = b"a-key-that-is-not-the-one-in-force"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)


def secret() -> bytes:
    """The key in force, read the way an integration on this machine reads it."""
    return hooks.secret_path().read_bytes()


def post_hook(client: TestClient, body: bytes = BODY, *, name: str = "mail",
              signed_by: bytes | str | None = "auto", sign_body: bytes | None = None,
              header: str | None = None):
    """POST the exact bytes, signed with a named key, over other bytes, or not at all."""
    headers: dict[str, str] = {}
    if isinstance(signed_by, bytes):                      # a key that is not the owner's
        key: bytes | None = signed_by
    elif signed_by == "auto":
        key = secret()
    else:
        key = None                                        # signed_by=None: no signature
    if key is not None:
        headers[hooks.HEADER] = hooks.sign(key, body if sign_body is None else sign_body)
    if header is not None:
        headers[hooks.HEADER] = header
    return client.post(f"/api/hooks/{name}", content=body, headers=headers)


def stored_tasks(owner) -> list[dict]:
    page = asyncio.run(owner.memory_page(limit=500))
    return [row for row in page["items"] if row["kind"] == "task"]


class DeadGraph:
    """A memory that cannot be written: the delivery must be refused, not lost."""

    async def call(self, operation, **arguments):
        raise GraphQueryError("graph_timeout", "the worker did not answer in time")

    async def close(self) -> None:
        return None


# ---------------------------------------------------------------- the secret


def test_the_secret_is_made_once_and_its_value_is_never_in_the_report(tmp_path):
    first = hooks.ensure_secret()
    value = secret()
    second = hooks.ensure_secret()

    assert first["created"] is True and second["created"] is False
    assert first["path"] == second["path"] == str(hooks.secret_path())
    assert first["length"] == len(value) and first["length"] >= hooks.SECRET_BYTES
    assert first["fingerprint"] == second["fingerprint"]
    # What may be printed names the key. It is not the key, in any form.
    report = json.dumps(hooks.describe(), ensure_ascii=False)
    assert hooks.describe()["present"] is True
    assert value.decode() not in report and value.decode()[:16] not in report


def test_rotating_the_secret_stops_the_old_signature(tmp_path):
    before = hooks.ensure_secret()
    old = secret()
    rotated = hooks.rotate_secret()

    assert rotated["created"] is True and secret() != old
    assert rotated["fingerprint"] != before["fingerprint"]
    with pytest.raises(hooks.HookError, match="does not match"):
        hooks.verify(secret(), BODY, hooks.sign(old, BODY))
    hooks.verify(secret(), BODY, hooks.sign(secret(), BODY))   # the new key is in force


def test_a_missing_secret_is_refused_by_that_name(tmp_path):
    owner = Runtime()
    with pytest.raises(hooks.HookError) as error:
        asyncio.run(hooks.deliver(owner, BODY, "a-signature"))

    assert error.value.code == "secret_absent" and error.value.status == 503
    assert "oneiro hooks key" in error.value.reason          # the reason names the repair


# ------------------------------------------------------ the delivery a script makes


def test_a_signed_delivery_creates_one_task_and_records_it(tmp_path):
    links = MemoryLinks()
    with TestClient(make_app(tmp_path, links)) as client:
        owner = client.app.state.runtime
        answer = post_hook(client)

        assert answer.status_code == 202, answer.text
        body = answer.json()
        assert body["hook"] == "mail" and body["duplicate"] is False
        assert body["title"] == PAYLOAD["title"]
        assert body["task_id"].startswith("task-hook-mail-")

        # Recorded as the owner's own instruction would be, and readable the way the
        # console reads a task: a hook is not a second kind of work.
        stored = stored_tasks(owner)
        assert [row["id"] for row in stored] == [body["task_id"]]
        assert stored[0]["state"] == State.QUEUED.value
        assert stored[0]["provenance"] == "owner_instruction"
        assert stored[0]["assigned_role"] == "executor"
        assert stored[0]["title"] == PAYLOAD["title"]
        assert stored[0]["detail"] == PAYLOAD["detail"]

        history = asyncio.run(tasks.history(owner, body["task_id"]))
        assert history["state"] == State.QUEUED.value and history["runs"] == []


def test_the_same_delivery_twice_is_one_task(tmp_path):
    links = MemoryLinks()
    with TestClient(make_app(tmp_path, links)) as client:
        first = post_hook(client)
        second = post_hook(client)

        assert first.json()["duplicate"] is False and second.status_code == 202
        assert second.json()["duplicate"] is True
        assert second.json()["task_id"] == first.json()["task_id"]
        assert len(stored_tasks(client.app.state.runtime)) == 1


def test_a_different_body_is_a_different_task(tmp_path):
    links = MemoryLinks()
    with TestClient(make_app(tmp_path, links)) as client:
        first = post_hook(client)
        second = post_hook(client, json.dumps({"title": "Another alert"}).encode("utf-8"))

        assert first.json()["task_id"] != second.json()["task_id"]
        assert len(stored_tasks(client.app.state.runtime)) == 2


def test_the_task_carries_the_payloads_own_words(tmp_path):
    body = json.dumps({"subject": "Disk almost full", "message": "83% used"},
                      ensure_ascii=False).encode("utf-8")
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        answer = post_hook(client, body)

        assert answer.json()["title"] == "Disk almost full"
        assert stored_tasks(client.app.state.runtime)[0]["detail"] == "83% used"


def test_a_payload_without_words_keeps_itself_as_the_detail(tmp_path):
    body = json.dumps({"host": "db-1", "state": "down"}).encode("utf-8")
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        answer = post_hook(client, body, name="monitor")
        task = stored_tasks(client.app.state.runtime)[0]

        assert answer.json()["title"] == "вебхук: monitor"
        assert json.loads(task["detail"]) == {"host": "db-1", "state": "down"}


def test_the_signature_header_is_taken_in_any_case(tmp_path):
    links = MemoryLinks()
    with TestClient(make_app(tmp_path, links)) as client:
        # Headers are case-insensitive, and the digest is hex: a caller that writes
        # either of them in capitals is not refused for that.
        answer = client.post("/api/hooks/mail", content=BODY,
                             headers={"X-Oneiro-Signature": hooks.sign(secret(), BODY)})
        assert answer.status_code == 202
        second = json.dumps({"title": "Second"}).encode("utf-8")
        again = post_hook(client, second, header=hooks.sign(secret(), second).upper())
        assert again.status_code == 202
        assert len(stored_tasks(client.app.state.runtime)) == 2


# --------------------------------------------------------------- each refusal


def test_each_refusal_names_its_cause(tmp_path):
    """A missing signature, a stranger's, other bytes, and a body that is not an object."""
    links = MemoryLinks()
    other = json.dumps({"title": "Something else"}).encode("utf-8")
    with TestClient(make_app(tmp_path, links)) as client:
        cases = [
            ("no signature at all",
             post_hook(client, signed_by=None), 401, "signature_absent"),
            ("a stranger's signature",
             post_hook(client, signed_by=STRANGER), 401, "signature_mismatch"),
            ("a signature over other bytes",
             post_hook(client, sign_body=other), 401, "signature_mismatch"),
            ("a signed body that is not JSON",
             post_hook(client, b"not json at all"), 400, "body_not_json"),
            ("a signed body that is not an object",
             post_hook(client, b"[1, 2, 3]"), 400, "body_not_object"),
            ("a signed empty body",
             post_hook(client, b""), 400, "body_empty"),
            ("an unknown hook name",
             post_hook(client, name="Mail-2"), 400, "unknown_hook"),
            ("a title the task layer will not take",
             post_hook(client, json.dumps({"title": "t" * 500}).encode("utf-8")),
             400, "task_refused"),
        ]
        for what, answer, status, code in cases:
            assert answer.status_code == status, f"{what}: {answer.status_code} {answer.text}"
            body = answer.json()
            assert body["code"] == code, f"{what}: {body}"
            assert isinstance(body["error"], str) and len(body["error"]) > 10, what
            assert body["hook"] == ("Mail-2" if code == "unknown_hook" else "mail")

        # Nothing was written by any of them, and the refusals named their own reasons.
        assert stored_tasks(client.app.state.runtime) == []


def test_the_page_token_is_not_a_substitute_for_a_signature(tmp_path):
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        token = client.get("/api/session").json()["csrf"]
        answer = client.post("/api/hooks/mail", content=BODY,
                             headers={"X-Oneiro-CSRF": token})

        assert answer.status_code == 401 and answer.json()["code"] == "signature_absent"


def test_every_other_write_still_needs_the_page_token(tmp_path):
    """The exemption is the hook route, and nothing else became open with it."""
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        answer = client.post("/api/tasks", json={"title": "x", "client_id": "client-0001-aaaa"})

        assert answer.status_code == 403
        assert answer.json() == {"error": "Invalid owner request token"}


def test_a_body_over_the_limit_is_refused_before_it_is_read(tmp_path):
    big = b'{"title": "' + b"x" * (hooks.MAX_BODY + 1) + b'"}'
    links = MemoryLinks()
    with TestClient(make_app(tmp_path, links)) as client:
        answer = post_hook(client, big)

        assert answer.status_code == 413 and answer.json()["code"] == "body_too_large"
        assert stored_tasks(client.app.state.runtime) == []
    # The module refuses it on its own as well, for a caller that is not the route.
    with pytest.raises(hooks.HookError) as error:
        asyncio.run(hooks.deliver(Runtime(), b"x" * (hooks.MAX_BODY + 1), "a-signature"))
    assert error.value.code == "body_too_large"


def test_a_delivery_that_cannot_be_written_is_refused_not_lost(tmp_path):
    with TestClient(web.create_app(runtime=Runtime(graph=DeadGraph()),
                                   scheduler=False)) as client:
        answer = post_hook(client)

        assert answer.status_code == 503
        assert "Nothing was changed" in answer.json()["error"]
        assert answer.json()["detail"].startswith("graph_timeout")
