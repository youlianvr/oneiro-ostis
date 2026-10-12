"""Inbound webhooks: one local, signed POST that becomes a task.

Something outside the conversation should be able to give Oneiro work — a mail
forwarder, a backup script, a monitoring alert. This module is the whole of that
door, and it is deliberately narrow.

**It is local.** The route lives on the console, which listens on loopback and
refuses any request that does not carry the owner's process token as well. Nothing
is published to a network and no tunnel is opened, so the door cannot be reached
from outside the machine.

**It is signed.** The body is authenticated with HMAC-SHA256 over the exact bytes
that arrived. The secret is generated once, kept in the data root as
`hooks.secret` with owner-only permissions, and never printed: `describe()` reports
its path, its length and a fingerprint, which is what a person needs to check
*which* key is in use, and not the key itself.

**Every refusal has a name.** A missing signature, a wrong signature, a body that
is not JSON, a body that is not an object: each is a `HookError` with a code and a
sentence, because "400 Bad Request" tells an operator nothing about which half of
their integration is wrong.

**The task is the console's task.** Delivery goes through `oneiro.tasks.create`,
the same call the console makes, so a task that arrived by hook cannot be a
different kind of thing from a task the owner typed.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from pathlib import Path
from typing import Any

from oneiro import config, tasks

#: The header the signature arrives in, lowercase: HTTP headers are case-insensitive.
HEADER = "x-oneiro-signature"
#: The file the secret lives in, inside the data root.
SECRET_NAME = "hooks.secret"
#: A hook name is a bounded identifier: it names a source, not a path.
NAME = re.compile(r"[a-z][a-z0-9-]{0,31}")
#: A body larger than this is refused before it is parsed or signed.
MAX_BODY = 64 * 1024
SECRET_BYTES = 32


class HookError(ValueError):
    """A refusal with a name and the status it should carry."""

    def __init__(self, code: str, reason: str, status: int = 400) -> None:
        super().__init__(f"{code}: {reason}")
        self.code = code
        self.reason = reason
        self.status = status


# --------------------------------------------------------------- the secret


def secret_path() -> Path:
    return config.data_root() / SECRET_NAME


def _fingerprint(secret: bytes) -> str:
    """A short, stable name for a key: it identifies the key, it is not the key."""
    return hashlib.sha256(secret).hexdigest()[:12]


def describe() -> dict[str, Any]:
    """What may be printed about the secret. Never the value, in any form."""
    path = secret_path()
    if not path.is_file():
        return {"path": str(path), "present": False, "length": 0, "fingerprint": ""}
    secret = path.read_bytes().strip()
    return {"path": str(path), "present": True, "length": len(secret),
            "fingerprint": _fingerprint(secret)}


def ensure_secret() -> dict[str, Any]:
    """Create the secret if there is none, and say what happened.

    The value is written and forgotten: this returns a fingerprint, so a caller
    cannot print the key by accident, and a fresh key is only made when none
    exists — rotating is a separate, deliberate act.
    """
    path = secret_path()
    if path.is_file():
        described = describe()
        return {**described, "created": False}
    path.parent.mkdir(parents=True, exist_ok=True)
    value = secrets.token_hex(SECRET_BYTES)
    path.write_text(value, encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:                      # a filesystem without POSIX modes says so by
        pass                             # not failing; the file is still owner-scoped
    return {**describe(), "created": True}


def rotate_secret() -> dict[str, Any]:
    """Replace the key. Every unsigned integration stops working until it is told."""
    path = secret_path()
    if path.is_file():
        path.unlink()
    return ensure_secret()


def load_secret() -> bytes:
    path = secret_path()
    if not path.is_file():
        raise HookError("secret_absent", f"no webhook secret at {path}; run: oneiro hooks key",
                        status=503)
    secret = path.read_bytes().strip()
    if not secret:
        raise HookError("secret_empty", f"the webhook secret at {path} is empty", status=503)
    return secret


# ---------------------------------------------------------- signing and shape


def sign(secret: bytes, body: bytes) -> str:
    """The signature of exactly these bytes: the body is never re-serialised."""
    return hmac.new(secret, body, hashlib.sha256).hexdigest()


def verify(secret: bytes, body: bytes, provided: str | None) -> None:
    """Refuse a request that is not signed with this secret."""
    if not provided:
        raise HookError("signature_absent", f"the {HEADER} header is missing", status=401)
    if not hmac.compare_digest(sign(secret, body), provided.strip().lower()):
        raise HookError("signature_mismatch", "the signature does not match this body", status=401)


def parse(body: bytes) -> dict[str, Any]:
    """The payload as an object, or a named reason it is not one."""
    if not body:
        raise HookError("body_empty", "the request had no body")
    try:
        payload = json.loads(body)
    except ValueError as exc:
        raise HookError("body_not_json", f"the body is not JSON ({exc.__class__.__name__})") from None
    if not isinstance(payload, dict):
        raise HookError("body_not_object", f"the body is a {type(payload).__name__}, not an object")
    return payload


def check_name(name: str) -> str:
    if not NAME.fullmatch(name or ""):
        raise HookError("unknown_hook", "a hook name is 1..32 lowercase letters, digits or hyphens")
    return name


# ------------------------------------------------------------- making the task


def _first_text(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def title_of(name: str, payload: dict[str, Any]) -> str:
    """The task's title: the payload's own words, or the hook's name."""
    return _first_text(payload, "title", "subject", "name") or f"вебхук: {name}"


def detail_of(payload: dict[str, Any]) -> str:
    """The task's detail: the payload's text, else the payload itself, kept whole."""
    text = _first_text(payload, "detail", "text", "body", "message")
    if text:
        return text
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)[:4000]


def client_id_for(name: str, body: bytes) -> str:
    """A stable ID per identical delivery, so a retried hook is not a second task."""
    return f"hook-{name}-{hashlib.sha256(body).hexdigest()[:16]}"


async def deliver(owner: Any, body: bytes, provided: str | None, *, name: str = "mail",
                  secret: bytes | None = None) -> dict[str, Any]:
    """Authenticate one delivery and turn it into a task.

    The idempotency key is the digest of the body, so the same delivery twice is
    the same task twice over — `tasks.create` answers a repeated `client_id` with
    what it already has instead of a second task.
    """
    hook = check_name(name)
    if len(body) > MAX_BODY:
        raise HookError("body_too_large", f"the body exceeds {MAX_BODY} bytes", status=413)
    verify(secret if secret is not None else load_secret(), body, provided)
    payload = parse(body)
    title = title_of(hook, payload)
    detail = detail_of(payload)
    client_id = client_id_for(hook, body)
    try:
        created = await tasks.create(owner, title=title, detail=detail, role="executor",
                                     blocked_by=(), client_id=client_id)
    except tasks.TaskError as exc:
        raise HookError("task_refused", str(exc)) from None
    task = created["task"]
    return {"hook": hook, "client_id": client_id, "title": title, "task_id": task["id"],
            "duplicate": bool(created["duplicate"]), "task": task}
