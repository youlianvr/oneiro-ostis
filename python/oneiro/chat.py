"""One OpenAI-compatible chat call for the chat slice.

Deliberately small and self-contained inside the package: no import of the older
top-level strategy modules. The provider address, key and model come from the
caller (the settings owner), never from a hard-coded provider.

Bounded in time (`timeout`) and in size (`MAX_REPLY_BYTES`). Every failure raises
ChatError with a short reason. The HTTP status is reported; the response body
and the Authorization header are never included, so a key cannot leak through
an error message. A failure that is worth repeating says so (`retryable`), so the
caller that owns the retry policy does not have to read a sentence to decide, and
the reply carries what the provider reported about the call — tokens, the model
that actually answered, its upstream and its own cost — without inventing any of it.

`chat_call` is the same request with tool declarations, returning the assistant
text *and* the tool calls the model asked for. What the model asks for is a
request, not an effect: the caller decides whether a call may run. Arguments that
are not valid JSON are reported as malformed instead of being guessed at.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

TIMEOUT = 60.0
MAX_REPLY_BYTES = 64 * 1024
MAX_TOOL_CALLS = 8


class ChatError(RuntimeError):
    """A chat call failed. The message is safe to show: no key, no provider body.

    `status` is the HTTP status when the provider sent one, and `retryable` says whether
    another attempt of the same request could succeed: a dropped connection, a 429 or a
    5xx is worth repeating, while a 4xx is the provider's own answer about this request
    and is never retried. `retry_after` carries the provider's own wait when it sends one.
    """

    def __init__(self, message: str, *, status: int = 0, retryable: bool = False,
                 retry_after: float = 0.0) -> None:
        super().__init__(message)
        self.status = status
        self.retryable = retryable
        self.retry_after = retry_after


@dataclass(frozen=True)
class ToolCall:
    """One tool the model asked to run.

    `arguments` is empty and `malformed` is set when the provider sent arguments
    that are not a JSON object, so a broken request is refused rather than run
    against guessed arguments.
    """

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    malformed: str = ""


@dataclass(frozen=True)
class ModelReply:
    """One assistant turn: text, tool calls, or both — and what the provider said of it.

    `usage`, `served`, `upstream` and `cost` are what the provider itself reported: the
    tokens it billed, the model that actually answered (a routing alias is not a model,
    so `served` is what a record may name), the upstream that served it and its own cost
    string. Each is empty when the provider says nothing about it, and nothing here is
    ever guessed: an absent number is absent.
    """

    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    usage: dict[str, Any] = field(default_factory=dict)
    served: str = ""
    upstream: str = ""
    cost: str = ""

    @property
    def wants_tools(self) -> bool:
        return bool(self.tool_calls)


def _tool_calls(message: dict[str, Any]) -> tuple[ToolCall, ...]:
    """Parse the provider's tool-call list without trusting its shape."""
    raw = message.get("tool_calls")
    if not isinstance(raw, list):
        return ()
    calls: list[ToolCall] = []
    for index, item in enumerate(raw[:MAX_TOOL_CALLS]):
        if not isinstance(item, dict):
            continue
        function = item.get("function")
        function = function if isinstance(function, dict) else {}
        name = function.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        call_id = item.get("id")
        call_id = call_id if isinstance(call_id, str) and call_id else f"call-{index}"
        text = function.get("arguments")
        text = text if isinstance(text, str) else ""
        try:
            arguments = json.loads(text) if text.strip() else {}
        except ValueError:
            calls.append(ToolCall(call_id, name.strip(), {},
                                  "the arguments are not valid JSON"))
            continue
        if not isinstance(arguments, dict):
            calls.append(ToolCall(call_id, name.strip(), {},
                                  "the arguments are not a JSON object"))
            continue
        calls.append(ToolCall(call_id, name.strip(), arguments))
    return tuple(calls)


def _retry_after(exc: urllib.error.HTTPError) -> float:
    """The provider's own wait, when it sends one (never longer than two minutes)."""
    try:
        value = exc.headers.get("Retry-After") if exc.headers else None
        return min(120.0, float(value)) if value else 0.0
    except (TypeError, ValueError, AttributeError):
        return 0.0


def _usage(answer: Any, headers: dict[str, str]) -> dict[str, Any]:
    """The tokens the provider reported: its body first, its headers when the body is bare.

    A proxy that answers without a `usage` object usually still counts the call in its
    own headers, and a ledger that recorded nothing there would understate a turn.
    """
    reported = answer.get("usage") if isinstance(answer, dict) else None
    if isinstance(reported, dict) and reported:
        return dict(reported)
    counted = {}
    for key, header in (("prompt_tokens", "x-omniroute-tokens-in"),
                        ("completion_tokens", "x-omniroute-tokens-out")):
        raw = headers.get(header, "")
        if str(raw).strip().isdigit():
            counted[key] = int(raw)
    return counted


def chat_call(messages: list[dict[str, Any]], *, base_url: str, api_key: str, model: str,
              tools: list[dict[str, Any]] | None = None,
              timeout: float = TIMEOUT) -> ModelReply:
    """One chat-completions request with optional tool declarations."""
    if not (base_url and api_key and model):
        raise ChatError("the model is not configured")
    body: dict[str, Any] = {"model": model, "messages": messages}
    if tools:
        body["tools"] = tools
    payload = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_REPLY_BYTES + 1)
            headers = {str(name).lower(): str(value)
                       for name, value in (response.headers or {}).items()}
    except urllib.error.HTTPError as exc:
        # The status is worth repeating for 429 and 5xx and nothing else; the body is
        # still not read, so a provider echo cannot travel into an error message.
        raise ChatError(f"the provider answered HTTP {exc.code}", status=exc.code,
                        retryable=exc.code == 429 or exc.code >= 500,
                        retry_after=_retry_after(exc)) from None
    except (urllib.error.URLError, OSError) as exc:
        raise ChatError(f"the provider is unreachable ({type(exc).__name__})",
                        retryable=True) from None
    if len(raw) > MAX_REPLY_BYTES:
        raise ChatError("the provider reply exceeds the size limit")
    try:
        answer: Any = json.loads(raw.decode("utf-8"))
        message = answer["choices"][0]["message"]
        text = message.get("content")
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        raise ChatError("the provider reply has no assistant text") from None
    calls = _tool_calls(message)
    content = text.strip() if isinstance(text, str) else ""
    if not content and not calls:
        raise ChatError("the provider reply is empty")
    served = answer.get("model") if isinstance(answer, dict) else ""
    return ModelReply(content, calls, usage=_usage(answer, headers),
                      served=str(served or headers.get("x-omniroute-model", "")),
                      upstream=headers.get("x-omniroute-provider", ""),
                      cost=headers.get("x-omniroute-response-cost", ""))


def chat_reply(messages: list[dict[str, str]], *, base_url: str, api_key: str, model: str,
               timeout: float = TIMEOUT) -> str:
    """One chat-completions request; returns the assistant text, stripped."""
    reply = chat_call(messages, base_url=base_url, api_key=api_key, model=model, timeout=timeout)
    if not reply.content:
        raise ChatError("the provider reply has no assistant text")
    return reply.content
