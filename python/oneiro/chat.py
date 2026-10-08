"""One OpenAI-compatible chat call for the chat slice.

Deliberately small and self-contained inside the package: no import of the older
top-level strategy modules. The provider address, key and model come from the
caller (the settings owner), never from a hard-coded provider.

Bounded in time (`timeout`) and in size (`MAX_REPLY_BYTES`). Every failure raises
ChatError with a short reason. The HTTP status is reported; the response body
and the Authorization header are never included, so a key cannot leak through
an error message.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

TIMEOUT = 60.0
MAX_REPLY_BYTES = 64 * 1024


class ChatError(RuntimeError):
    """A chat call failed. The message is safe to show: no key, no provider body."""


def chat_reply(messages: list[dict[str, str]], *, base_url: str, api_key: str, model: str,
               timeout: float = TIMEOUT) -> str:
    """One chat-completions request; returns the assistant text, stripped."""
    if not (base_url and api_key and model):
        raise ChatError("the model is not configured")
    payload = json.dumps({"model": model, "messages": messages}).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_REPLY_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise ChatError(f"the provider answered HTTP {exc.code}") from None
    except (urllib.error.URLError, OSError) as exc:
        raise ChatError(f"the provider is unreachable ({type(exc).__name__})") from None
    if len(raw) > MAX_REPLY_BYTES:
        raise ChatError("the provider reply exceeds the size limit")
    try:
        body: Any = json.loads(raw.decode("utf-8"))
        text = body["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise ChatError("the provider reply has no assistant text") from None
    if not isinstance(text, str) or not text.strip():
        raise ChatError("the provider reply is empty")
    return text.strip()
