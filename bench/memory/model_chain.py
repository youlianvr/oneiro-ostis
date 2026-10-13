"""The model client the memory stand uses now: `oneiro.chat.chat_call`, nothing else.

The retired `python/llm.py` used to own this, and it is gone. The stand's numbers have to
come from the code the product actually runs, so every call here goes through the one chat
entry point the package owns and never through a second HTTP client of the stand's own.

Two things are kept from the old client on purpose, because the measurement rests on them:

* **The arms and the judge keep their contract.** `client.chat(messages, max_tokens=...)`
  returns `(message, usage)` and `client.model` names the model that served the call, so the
  official LongMemEval prompt assembly (`arms.py`) and its verdict parsing (`judge.py`) stay
  exactly as they were — this file changes where a call goes, not what is asked or judged.
* **A failure is a failure.** A provider that refuses, times out, or answers with no text
  raises `ProviderError`. Nothing is retried into a different number, and the cell that met
  it is recorded as `provider_error` rather than as a wrong answer.

`ModelChain` is the benchmark's own rule in code: a row of results belongs to one logical
model, an ordered chain of routing names, and the call records which one actually served it.
"""

from __future__ import annotations

from typing import Any

from oneiro.chat import ChatError, chat_call

#: How long one call may take. The product's own default is 60 s, which is right for a turn
#: and too tight here: a stage-`s` prompt carries a hundred sessions and can run to tens of
#: thousands of characters, and a single slow answer must not be recorded as a provider
#: failure. Measured on the previous stand: a full answer call took tens of seconds.
TIMEOUT = 180.0

#: What the stand calls itself on the wire. This is not cosmetic. `urllib` sends its own
#: library string when no agent is named, and an endpoint behind a bot-filtering edge answers
#: that with HTTP 403 (`error code: 1010`) before the request ever reaches a model — measured
#: 2026-10-13 against `https://justbash-api.annenkov.me/v1`: the same request answered 403 with
#: the library string and 200 with this one, on every arm of a two-question smoke. A provider
#: that refuses a request for how the client introduced itself must be met with a real name,
#: not with a rewritten result, so the name is sent and a refusal is still recorded as a refusal.
USER_AGENT = "oneiro-bench/1.0 (memory stand)"


class ProviderError(RuntimeError):
    """One provider call did not come back with an answer. Never swallowed."""


class ChatClient:
    """One provider model, called through `oneiro.chat.chat_call`."""

    def __init__(self, model: str, api_key: str, base_url: str,
                 temperature: float = 0.0, timeout: float = TIMEOUT) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.temperature = temperature
        self.timeout = timeout
        #: Set by the last call: the model the provider said actually answered. A routing
        #: alias is not a model, so this is what a record may name. Empty until a call
        #: succeeds.
        self.served = ""

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None,
             max_tokens: int | None = None) -> tuple[dict[str, Any], dict[str, int]]:
        """One call; `(message, usage)` in the shape the arms and the judge already read."""
        try:
            reply = chat_call(messages, base_url=self.base_url, api_key=self.api_key,
                              model=self.model, tools=tools, max_tokens=max_tokens,
                              temperature=self.temperature, timeout=self.timeout,
                              user_agent=USER_AGENT)
        except ChatError as exc:
            # The same kind of failure: a call that did not produce an answer. The message
            # carries the model and a short reason and never the key or the provider's body.
            raise ProviderError(f"{self.model}: {exc}") from None
        self.served = reply.served or self.model
        usage = {
            "prompt_tokens": int(reply.usage.get("prompt_tokens") or 0),
            "completion_tokens": int(reply.usage.get("completion_tokens") or 0),
        }
        return {"content": reply.content}, usage


class ModelChain:
    """One logical model backed by an ordered chain of provider model ids.

    The benchmark's rule is that a row of results belongs to one model; this chain keeps
    that promise by recording which model actually served the call, and by never silently
    mixing a different model into the same cell. The chain is exhausted only when every
    member failed, and then the reasons are all named.
    """

    def __init__(self, models, base_url: str, key: str, temperature: float = 0.0,
                 timeout: float = TIMEOUT) -> None:
        self.models = list(models)
        self.base_url = base_url
        self.key = key
        self.temperature = temperature
        self.timeout = timeout
        self.model = self.models[0]
        self.failures: list[str] = []

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None,
             max_tokens: int | None = None) -> tuple[dict[str, Any], dict[str, int]]:
        problems: list[str] = []
        for model in self.models:
            client = ChatClient(model=model, api_key=self.key, base_url=self.base_url,
                                temperature=self.temperature, timeout=self.timeout)
            try:
                message, usage = client.chat(messages, tools=tools, max_tokens=max_tokens)
            except ProviderError as exc:
                problems.append(str(exc))
                self.failures.append(str(exc)[:300])
                continue
            self.model = client.served or model
            return message, usage
        raise ProviderError("model chain exhausted: " + "; ".join(problems))
