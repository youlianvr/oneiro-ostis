"""Model access for the living roles: one provider, bounded waits, one budget.

Owner decision (2026-09-22): every model call goes to the local OmniRoute
proxy (``http://127.0.0.1:20128/v1``), not to a single vendor endpoint. The
proxy holds the provider keys, fails over between upstreams, and answers with
the id of the model that actually served the call; that id is recorded, so a
result row can never be attributed to a model that did not produce it.

The role aliases below are the proxy's routing names, not upstream model ids:
they stay valid while the relays behind them change, which is exactly what
made the previous fixed-vendor setup stop working (the vendor answered
``model_concurrency`` and every call waited).

This module owns exactly three things:

* the request itself, with the provider failure modes actually observed in
  this project (cold-start placeholder, 429 with Retry-After, 5xx, dropped
  connections, truncated JSON);
* the fallback chain for one call;
* a per-cycle call budget so a runaway cycle freezes instead of spending on.

No prompts, no role logic, no OSTIS code: those live beside this module.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

DEFAULT_BASE_URL = "http://127.0.0.1:20128/v1"
API_KEY_ENV = "OMNIROUTE_API_KEY"
REQUEST_TIMEOUT = 180.0
MAX_REQUEST_ATTEMPTS = 4
MAX_PLACEHOLDER_RETRIES = 8
PLACEHOLDER_WAIT = 15.0
PLACEHOLDER_MARKER = "model is starting up"

ROLE_MODELS = {
    "researcher": "auto/coding",
    "worker": "auto/coding",
    "manager": "main",
}
FALLBACK_MODEL = "auto/coding:reliable"

RETRYABLE_ERRORS = (urllib.error.URLError, TimeoutError, ConnectionError,
                    json.JSONDecodeError, KeyError)


class ProviderError(RuntimeError):
    """A provider failure that survived the bounded retries."""


class ProviderDown(ProviderError):
    """The model chain could not answer; the cycle must freeze, not improvise."""


class RateLimited(ProviderError):
    """429 survived every bounded wait."""


class BudgetExhausted(ProviderError):
    """The per-cycle model-call budget is spent; the cycle freezes."""


def _retry_after(exc: urllib.error.HTTPError) -> float:
    """The provider's own wait, when it sends one (never longer than 120 s)."""
    try:
        value = exc.headers.get("Retry-After") if exc.headers else None
        return min(120.0, float(value)) if value else 0.0
    except (TypeError, ValueError, AttributeError):
        return 0.0


def load_api_key(env_path_hint: Optional[Path] = None) -> str:
    """Find the provider key: environment first, then a nearby ``.env``.

    The KeyError message is the first thing a morning reader sees when the
    key moved, so it names the exact variable and both places searched.
    """
    for name in ("ONEIRO_API_KEY", API_KEY_ENV):
        value = os.environ.get(name)
        if value:
            return value.strip()
    start = env_path_hint or Path(__file__).resolve()
    for parent in list(start.parents)[:8]:
        env_file = parent / ".env"
        if not env_file.is_file():
            continue
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith(API_KEY_ENV + "="):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                if value:
                    return value
    raise ProviderError(
        f"no provider key: set {API_KEY_ENV} in the environment or keep it in a "
        f".env above {start}"
    )


@dataclass
class ChatClient:
    """Minimal OpenAI-compatible chat client with the project's retry policy."""

    model: str
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    temperature: float = 0.2
    # What the proxy says actually answered: the routing alias is what we ask
    # for, the provider id is what we can show.
    served_provider: str = ""

    def _post(self, payload: dict) -> tuple[dict, dict]:
        request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8")), dict(response.headers)

    def chat(self, messages: list[dict], tools: list[dict] | None = None,
             max_tokens: int | None = None) -> tuple[dict, dict]:
        """Return (message, usage), retrying transient provider failures."""
        payload: dict = {"model": self.model, "messages": messages,
                         "temperature": self.temperature}
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        placeholder_waits = 0
        rate_limited = False
        last_failure = "no attempt made"
        for attempt in range(MAX_REQUEST_ATTEMPTS):
            try:
                body, headers = self._post(payload)
                choice = body["choices"][0]
                message = choice["message"]
                self.served_provider = (headers.get("x-omniroute-provider")
                                        or headers.get("X-Omniroute-Provider") or "")
            except urllib.error.HTTPError as exc:
                if exc.code == 429:
                    # The provider's own wait outlives a one-second ladder; a
                    # cycle that dies here would waste what it already paid for.
                    rate_limited = True
                    last_failure = "HTTP 429"
                    time.sleep(_retry_after(exc) or min(60.0, 5 * 2 ** attempt))
                    continue
                if exc.code >= 500:
                    last_failure = f"HTTP {exc.code}"
                    time.sleep(2 ** attempt)
                    continue
                detail = exc.read().decode("utf-8", errors="replace")[:300]
                raise ProviderError(f"HTTP {exc.code} from {self.model}: {detail}") from exc
            except RETRYABLE_ERRORS as exc:
                last_failure = repr(exc)
                time.sleep(2 ** attempt)
                continue

            usage = body.get("usage") or {}
            content = message.get("content") or ""
            if PLACEHOLDER_MARKER in content and not message.get("tool_calls"):
                if placeholder_waits >= MAX_PLACEHOLDER_RETRIES:
                    raise ProviderDown(
                        f"{self.model} is not warm: still booting after "
                        f"{placeholder_waits} checks"
                    )
                placeholder_waits += 1
                time.sleep(PLACEHOLDER_WAIT)
                continue
            return message, usage

        failure = RateLimited if rate_limited else ProviderDown
        raise failure(f"{self.model} failed after {MAX_REQUEST_ATTEMPTS} attempts: {last_failure}")


@dataclass
class CallBudget:
    """Per-cycle model-call budget; charging past the cap freezes the cycle."""

    max_calls: int
    calls: int = 0

    def charge(self, note: str = "") -> None:
        if self.calls >= self.max_calls:
            tail = f" ({note})" if note else ""
            raise BudgetExhausted(
                f"model-call budget exhausted: {self.calls}/{self.max_calls}{tail}"
            )
        self.calls += 1


@dataclass
class CallRecord:
    """One line of the run's model evidence, quoted by the morning report."""

    role: str
    model: str
    ok: bool
    detail: str = ""
    served: str = ""            # upstream that actually answered, when named


@dataclass
class ModelReply:
    message: dict
    usage: dict
    model: str


@dataclass
class ModelPool:
    """Role-aware model access with the owner-approved fallback chain."""

    api_key: str = ""
    base_url: str = ""
    roles: dict = field(default_factory=lambda: dict(ROLE_MODELS))
    fallback: Optional[str] = FALLBACK_MODEL
    client_factory: Callable[..., ChatClient] = ChatClient
    calls: list[CallRecord] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.api_key:
            self.api_key = load_api_key()
        if not self.base_url:
            self.base_url = os.environ.get("ONEIRO_BASE_URL", DEFAULT_BASE_URL)

    def reply(
        self,
        role: str,
        messages: list[dict],
        *,
        tools: list[dict] | None = None,
        budget: Optional[CallBudget] = None,
        temperature: Optional[float] = None,
    ) -> ModelReply:
        """Ask one role's model chain; every attempt lands in ``calls``."""
        if budget is not None:
            budget.charge(role)
        chain = [self.roles.get(role) or self.roles["worker"]]
        if self.fallback and self.fallback not in chain:
            chain.append(self.fallback)
        problems: list[str] = []
        for model in chain:
            client = self.client_factory(
                model=model,
                api_key=self.api_key,
                base_url=self.base_url,
                temperature=0.2 if temperature is None else temperature,
            )
            try:
                message, usage = client.chat(messages, tools=tools)
            except ProviderError as exc:
                problems.append(f"{model}: {exc}")
                self.calls.append(CallRecord(role, model, False, str(exc)[:300]))
                continue
            self.calls.append(CallRecord(role, model, True,
                                         served=getattr(client, "served_provider", "")))
            return ModelReply(message=message, usage=usage, model=model)
        raise ProviderDown("; ".join(problems))

    def evidence(self) -> list[dict]:
        """The call log in JSON-ready form, for organization records."""
        return [record.__dict__ for record in self.calls]
