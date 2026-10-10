"""The registry: the providers Oneiro may call, the model each role uses, what a model
proved it can do, and what every call cost.

The shape is the one OpenCode and Hermes already use, because there is no reason to
invent a second one: a provider is a record with `name`, `base_url`, the *name* of an
environment variable holding its key (`key_env`, never the key), `discover_models`, and
the models the owner names. Discovery is a real `GET /models`; the fallback list is a list
of `model` or `provider/model` references.

Five decisions are load-bearing.

**A routing alias is not a model.** `auto/coding` is what gets asked for; the provider
answers with the id of the model that actually served the call, and that id is what the
ledger and the records name. A result can therefore never be attributed to a model that
did not produce it.

**Capability is seen, not believed.** A provider's model list advertises things
(`tool_calling`, `vision`), and none of that is proof. Anything this module claims about
what a model can do comes from a real call: whether it asked for a tool when one was
offered, whether it accepted an image. The advertised hints are reported as what the
provider says, beside what was seen.

**A fallback is entered only where a real call showed it can do the job.** The model a
role uses is the owner's own choice and is called as it is; a fallback model may only
answer a call whose needs it was *seen* to cover, and a candidate that cannot be checked
is skipped with the reason, never tried and never silently swapped in.

**No call goes uncounted.** Discovery, probes and turns all reach the provider through one
seam that writes the ledger entry *before* the request is dialled and fills it in
afterwards, so a call that never comes back is still a call on the record — which is the
only way "no uncounted calls" can be more than a sentence.

**An unreadable value is the cautious one, and it is said out loud.** A blank or malformed
provider list, a provider whose address carries credentials, a model nobody lists: each is
a refusal naming the key and the record, not a guess.

The ledger lives with the running process (Oneiro is one process, held by the runtime
lease) and is readable through `oneiro verify-model` and `/api/status`. Writing it to disk
is deliberately not part of this package.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Iterable

from oneiro import config
from oneiro.chat import ChatError, ModelReply, chat_call

#: The roles § 4 gives a model of their own. Any other role — the model check itself, a
#: probe — reads the default.
ROLES = ("manager", "researcher", "executor")
#: What a call can need beyond plain text, and therefore what a fallback must have been
#: seen to do before it may answer.
CAPABILITIES = ("tools", "vision")

#: The provider the previous build called, which keeps the pre-registry address and key.
SHIPPED_PROVIDER = "local"

MAX_ATTEMPTS = 3            # one attempt and at most two repeats of the same request
BACKOFF_BASE = 1.0
BACKOFF_CAP = 8.0
MIN_ATTEMPT = 1.0           # no try is started with less time than this left in the call
WAIT_SLACK = 2.0            # what a caller waits past the limit for this layer to give up
MAX_FALLBACK = 3
MAX_LEDGER = 500
MAX_DISCOVERED = 2000
MAX_DISCOVERY_BYTES = 2 * 1024 * 1024
MODEL_TIMEOUT = 60.0
DISCOVER_TIMEOUT = 20.0
PROBE_TIMEOUT = 45.0
MAX_PROBLEM = 600

#: A one-pixel PNG, sent as the whole of the vision probe's question.
VISION_PIXEL = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
                "AAAADUlEQVR4nGP4z8DwHwAFAAH/iZk9HQAAAABJRU5ErkJggg==")
PROBE_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "oneiro_probe",
        "description": "Report that the tool channel of this model works.",
        "parameters": {"type": "object", "properties": {"text": {"type": "string"}},
                       "required": ["text"]},
    },
}
PROBE_TOOLS_ASK = "Call the oneiro_probe tool with the text \"ready\" and nothing else."
PROBE_VISION_ASK = "What colour is this pixel? Answer with one word."

#: Refusals that are an answer about the request rather than a bad moment: a provider that
#: answers one of these will not answer better on a second try, and for a probe it is a
#: verdict about the capability.
REFUSAL_STATUSES = (400, 404, 405, 406, 415, 422)
#: The provider's own names for the two capabilities, mapped to ours.
DECLARED_NAMES = {"tool_calling": "tools", "tools": "tools", "function_calling": "tools",
                  "vision": "vision", "supports_vision": "vision", "image": "vision"}


class ModelError(ChatError):
    """The whole chain failed. It is a `ChatError` because it is the same kind of failure.

    A caller that already answers a provider failure — the turn reports it, the web channel
    turns it into a 503 — needs nothing else to know what happened.
    """


class NoProvider(ModelError):
    """The provider list cannot be used, and the reason names which part of it."""


class NoModel(ModelError):
    """A model reference names nothing that can be resolved."""


class Canceled(ModelError):
    """The owner stopped the call.

    A request already on the wire may have been served: this says so rather than pretending
    the provider was never asked.
    """


@dataclass(frozen=True)
class Provider:
    """One provider record: an address, the name of a variable holding its key, its models."""

    name: str
    base_url: str
    key_env: str = ""
    discover_models: bool = True
    models: tuple[str, ...] = ()
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "base_url": self.base_url, "key_env": self.key_env,
                "discover_models": self.discover_models, "models": list(self.models),
                "enabled": self.enabled}


@dataclass(frozen=True)
class Discovered:
    """What a provider's own model list said, and what it advertised about each model."""

    provider: str
    models: tuple[str, ...] = ()
    #: Capabilities the provider advertises for a model, and those it denies. A capability
    #: it does not mention at all is in neither, which is a third and different answer.
    declared: dict[str, tuple[str, ...]] = field(default_factory=dict)
    denied: dict[str, tuple[str, ...]] = field(default_factory=dict)
    truncated: bool = False
    at: float = 0.0

    def says(self, model: str, capability: str) -> bool | None:
        """What the provider advertises about one model. `None` means it did not say.

        This is a claim by the provider, not a measurement; nothing in this module decides
        anything from it, and the report prints it beside what a real call showed.
        """
        if capability in self.declared.get(model, ()):
            return True
        if capability in self.denied.get(model, ()):
            return False
        return None

    def to_dict(self) -> dict[str, Any]:
        return {"provider": self.provider, "models": len(self.models),
                "truncated": self.truncated, "at": self.at,
                "named": list(self.models[:20])}


@dataclass(frozen=True)
class Capability:
    """What a model was actually seen to do, and what the attempts to find out said.

    `answers` holds only what a real call established: a capability that could not be
    established is absent rather than `False`, so "it failed" can never be read as "it
    cannot".
    """

    provider: str
    model: str
    answers: dict[str, bool] = field(default_factory=dict)
    notes: tuple[str, ...] = ()
    probed: bool = False        # something came back, a refusal included
    answered: bool = False      # a reply came back, which is what "it works" means
    at: float = 0.0

    def says(self, capability: str) -> bool | None:
        return self.answers.get(capability)

    def covers(self, needs: Iterable[str]) -> bool:
        """Whether every need was seen to be met, not merely unrefused."""
        return all(self.answers.get(need) is True for need in needs)

    def to_dict(self) -> dict[str, Any]:
        return {"provider": self.provider, "model": self.model, "probed": self.probed,
                "answered": self.answered,
                "tools": self.answers.get("tools"), "vision": self.answers.get("vision"),
                "notes": list(self.notes), "at": self.at}


@dataclass
class Call:
    """One line of the ledger. Written when the request is dialled, filled when it ends."""

    at: float
    role: str
    provider: str
    model: str
    attempt: int = 1
    ok: bool = False
    outcome: str = "in flight"
    ms: int = 0
    served: str = ""
    upstream: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    cost: str = ""
    error: str = ""
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"at": self.at, "role": self.role, "provider": self.provider, "model": self.model,
                "attempt": self.attempt, "ok": self.ok, "outcome": self.outcome, "ms": self.ms,
                "served": self.served, "upstream": self.upstream, "tokens_in": self.tokens_in,
                "tokens_out": self.tokens_out, "cost": self.cost, "error": self.error,
                "detail": self.detail}


def _own_model(role: str) -> str:
    """The model a role declares for itself. Empty means "use the default".

    Written out per role rather than built from the role's name: three keys, three lines,
    and the settings check can see that each key reaches behaviour.
    """
    if role == "manager":
        return str(config.value("models.roles.manager") or "").strip()
    if role == "researcher":
        return str(config.value("models.roles.researcher") or "").strip()
    if role == "executor":
        return str(config.value("models.roles.executor") or "").strip()
    return ""


def needs_of(messages: list[dict[str, Any]],
             tools: list[dict[str, Any]] | None = None) -> tuple[str, ...]:
    """What a call needs beyond plain text, read from the request itself.

    Offering tools needs a model that can call them; a message carrying an image needs one
    that can see it. Reading it here means a caller cannot forget to declare it.
    """
    needs: list[str] = []
    if tools:
        needs.append("tools")
    for message in messages:
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, list) and any(
                isinstance(part, dict) and part.get("type") == "image_url" for part in content):
            needs.append("vision")
            break
    return tuple(needs)


def _headers(key: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _outcome(exc: ChatError) -> str:
    """How one failed attempt is recorded: refused, failed, or refused by the provider."""
    if not exc.retryable:
        return "refused"
    return "failed"


class Registry:
    """The providers, the models per role, the probe cache and the ledger of one process."""

    def __init__(self, *, transport: Callable[..., ModelReply] | None = None) -> None:
        #: A transport override, used by a turn that was handed one and by tests. `None`
        #: means the module-level seam, read at call time so a patch is seen.
        self.transport = transport
        self._lock = threading.RLock()
        #: Cached answers, keyed by the provider's name *and* its address: the owner can edit
        #: an address while the process runs, and an answer about the old one must not be
        #: served as though it were about the new one.
        self._discovered: dict[tuple[str, str], Discovered] = {}
        self._capabilities: dict[tuple[str, str, str], Capability] = {}
        self.records: list[Call] = []
        self.dropped = 0

    # ---------------------------------------------------------------- the providers

    def providers(self) -> tuple[Provider, ...]:
        """The provider records the settings declare, in order, validated one by one."""
        try:
            raw, source = config.resolve("models.providers")
        except ValueError as exc:
            raise NoProvider(f"models.providers cannot be read: {exc}") from None
        records = [item for item in raw if isinstance(item, dict)] \
            if isinstance(raw, list) else []
        if not records:
            raise NoProvider(
                "models.providers names no provider, so there is nothing to call: name at "
                "least one with a name and a base_url")
        found = [self._provider(record) for record in records]
        found = [provider for provider in found if provider.enabled]
        if not found:
            raise NoProvider("every provider in models.providers is disabled")
        if source == "default":
            # The pre-registry address still decides where the shipped provider points, so
            # an install that never wrote a provider list is not asked to enter it twice.
            address, address_source = config.resolve("llm.base_url")
            if address_source != "default" and str(address).strip():
                found = [replace(provider, base_url=str(address).strip().rstrip("/"))
                         if provider.name == SHIPPED_PROVIDER else provider
                         for provider in found]
        return tuple(found)

    @staticmethod
    def _provider(record: dict[str, Any]) -> Provider:
        name = str(record.get("name", "")).strip()
        address = str(record.get("base_url", "")).strip()
        if not name or not address:
            raise NoProvider("every provider in models.providers needs a name and a base_url")
        parts = urllib.parse.urlsplit(address)
        if parts.scheme not in ("http", "https") or not parts.hostname or parts.username \
                or parts.password or parts.query or parts.fragment:
            raise NoProvider(
                f"{name}: base_url must be an HTTP(S) address without credentials, a query "
                f"or a fragment; a key is named by key_env and never travels in the address")
        declared = record.get("models") or []
        if isinstance(declared, dict):
            declared = list(declared)
        if not isinstance(declared, list):
            raise NoProvider(f"{name}: models must be a list of model names")
        return Provider(
            name=name, base_url=address.rstrip("/"),
            key_env=str(record.get("key_env", "") or "").strip(),
            discover_models=bool(record.get("discover_models", True)),
            models=tuple(str(item).strip() for item in declared if str(item).strip()),
            enabled=bool(record.get("enabled", True)))

    def key_for(self, provider: Provider) -> str:
        """The key of one provider: the variable it names, else the pre-registry secret.

        The second answer exists for exactly one provider — the first in the list, which is
        the one the previous build called — because that install keeps its key under the old
        name and must not be asked to paste it again. No other provider ever borrows it.
        """
        found = config.env_value(provider.key_env) if provider.key_env else ""
        if found:
            return found
        try:
            default = self.providers()[0]
        except ModelError:
            return ""
        if provider.name != default.name:
            return ""
        return str(config.value("llm.api_key") or "").strip()

    # ------------------------------------------------------------------- the models

    def model_for(self, role: str) -> str:
        """The model a role uses: its own, else the default, else the pre-registry name.

        All three act. The default model wins when the owner set it in this build; the
        pre-registry `llm.model` answers when the owner set only that one, which is how an
        install keeps working across the change; and the declared default answers otherwise.
        """
        own = _own_model(role)
        if own:
            return own
        default, default_source = config.resolve("models.default")
        legacy, legacy_source = config.resolve("llm.model")
        if default_source != "default" and str(default).strip():
            return str(default).strip()
        if legacy_source != "default" and str(legacy).strip():
            return str(legacy).strip()
        return str(default).strip() or str(legacy).strip() or ""

    def resolve(self, reference: str) -> tuple[Provider, str]:
        """Which provider and which model id a reference names.

        `provider/model` is explicit when the head is a declared provider name (a model id
        may itself contain a slash, so an unknown head is left whole). A plain name is
        looked for in what the providers declare and in any list already discovered; a name
        nobody lists goes to the first provider, which is where a routing alias lives.
        """
        text = str(reference or "").strip()
        if not text:
            raise NoModel("no model was named")
        providers = self.providers()
        head, slash, tail = text.partition("/")
        if slash and tail and head in {provider.name for provider in providers}:
            return next(provider for provider in providers if provider.name == head), tail
        for provider in providers:
            if text in provider.models:
                return provider, text
        with self._lock:
            cached = [(provider, self._discovered.get(self._place(provider)))
                      for provider in providers]
        for provider, found in cached:
            if found is not None and text in found.models:
                return provider, text
        return providers[0], text

    def fallback_chain(self, role: str) -> list[tuple[Provider | None, str, str]]:
        """The model the role uses, then the fallback list, in order, each with why.

        A reference that cannot be resolved stays in the chain as a named problem rather
        than being dropped quietly, so a typo in `models.fallback` is visible instead of
        inert: the entry is reported, with the reason, and the call goes on without it.
        """
        chain: list[tuple[Provider | None, str, str]] = []
        model = self.model_for(role)
        if model:
            provider, name = self.resolve(model)
            chain.append((provider, name, f"the model the {role} role uses"))
        try:
            entries = config.value("models.fallback") or []
        except ValueError as exc:                        # a hand-edited list that cannot be read
            chain.append((None, "", f"models.fallback cannot be read: {exc}"))
            return chain
        for entry in list(entries)[:MAX_FALLBACK]:
            try:
                provider, name = self.resolve(str(entry))
            except ModelError as exc:
                chain.append((None, "", f"models.fallback cannot use {entry!r}: {exc}"))
                continue
            chain.append((provider, name, f"a fallback for {role}"))
        return chain

    @staticmethod
    def _place(provider: Provider) -> tuple[str, str]:
        """What a cached answer is keyed by: which provider, at which address."""
        return (provider.name, provider.base_url)

    def describe(self, provider: Provider) -> dict[str, Any]:
        """One provider as every surface reports it: what it declares, and whether a key was
        found for it. `/api/status` and `verify-model` both use this, so the two cannot
        describe the same provider differently."""
        return {**provider.to_dict(), "key_found": bool(self.key_for(provider))}

    # ------------------------------------------------------------------ discovery

    def discover(self, provider: Provider, *, timeout: float = DISCOVER_TIMEOUT,
                 refresh: bool = False) -> Discovered:
        """Ask the provider for its model list — a real call, counted like every other."""
        key = self._place(provider)
        with self._lock:
            cached = self._discovered.get(key)
        if cached is not None and not refresh:
            return cached
        entry = self._open("discover", provider.name, "", detail="the model list")
        started = time.monotonic()
        try:
            entries = self._list_models(provider, self.key_for(provider), timeout)
        except NoModel as exc:
            self._close(entry, ok=False, outcome="refused", error=str(exc),
                        ms=int((time.monotonic() - started) * 1000))
            raise
        names: list[str] = []
        seen: set[str] = set()
        declared: dict[str, tuple[str, ...]] = {}
        denied: dict[str, tuple[str, ...]] = {}
        for item in entries:
            name = str(item.get("id", "") if isinstance(item, dict) else item).strip()
            if not name or name in seen:
                continue
            seen.add(name)
            names.append(name)
            advertised = item.get("capabilities") if isinstance(item, dict) else None
            if not isinstance(advertised, dict):
                continue
            yes: list[str] = []
            no: list[str] = []
            for key, value in advertised.items():
                (yes if value else no).append(DECLARED_NAMES.get(str(key), str(key)))
            if yes:
                declared[name] = tuple(sorted(yes))
            if no:
                denied[name] = tuple(sorted(no))
        found = Discovered(provider=provider.name, models=tuple(names[:MAX_DISCOVERED]),
                           declared=declared, denied=denied,
                           truncated=len(names) > MAX_DISCOVERED, at=time.time())
        with self._lock:
            self._discovered[key] = found
        self._close(entry, ok=True, outcome="completed",
                    ms=int((time.monotonic() - started) * 1000),
                    detail=f"{len(found.models)} models listed")
        return found

    def _list_models(self, provider: Provider, key: str, timeout: float) -> list[Any]:
        request = urllib.request.Request(f"{provider.base_url}/models", headers=_headers(key))
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read(MAX_DISCOVERY_BYTES + 1)
        except urllib.error.HTTPError as exc:
            raise NoModel(f"{provider.name} answered HTTP {exc.code} for its model list"
                          + self._key_hint(provider, exc.code, key)) from None
        except (urllib.error.URLError, OSError) as exc:
            raise NoModel(f"{provider.name} is unreachable for its model list "
                          f"({type(exc).__name__})") from None
        if len(raw) > MAX_DISCOVERY_BYTES:
            raise NoModel(f"{provider.name}: the model list is larger than "
                          f"{MAX_DISCOVERY_BYTES // (1024 * 1024)} MB")
        try:
            answer: Any = json.loads(raw.decode("utf-8"))
        except ValueError:
            raise NoModel(f"{provider.name}: the model list is not valid JSON") from None
        entries = answer.get("data") if isinstance(answer, dict) else answer
        if not isinstance(entries, list) or not entries:
            raise NoModel(f"{provider.name} did not list any models in the OpenAI shape")
        return entries

    @staticmethod
    def _key_hint(provider: Provider, status: int, key: str) -> str:
        """A refusal about the key says which variable was looked for, never the value."""
        if status not in (401, 403) or key:
            return ""
        named = f"`{provider.key_env}`" if provider.key_env else "the provider key setting"
        return f": it refused the key, and no value was found for {named}"

    # --------------------------------------------------------------------- probes

    def probe(self, provider: Provider, model: str, *, needs: tuple[str, ...] = CAPABILITIES,
              timeout: float = PROBE_TIMEOUT,
              cancel: threading.Event | None = None) -> Capability:
        """Find out what a model really does, by asking it — never by believing a list.

        One real call per capability. A model that answers without asking for the offered
        tool is recorded as not having used it; an image the provider refuses is recorded as
        a refusal by that provider; a failure that is neither leaves the capability
        unestablished, which is a third answer and is kept as one.
        """
        keyed = self._place(provider) + (model,)
        with self._lock:
            known = self._capabilities.get(keyed)
        if known is not None and all(known.says(need) is not None for need in needs):
            return known
        answers: dict[str, bool] = dict(known.answers) if known else {}
        notes: list[str] = list(known.notes) if known else []
        probed = bool(known.probed) if known else False
        answered = bool(known.answered) if known else False
        for need in needs:
            if answers.get(need) is not None:
                continue
            if cancel is not None and cancel.is_set():
                raise Canceled("the check was stopped before it asked the model anything")
            if need == "tools":
                messages: list[dict[str, Any]] = [{"role": "user", "content": PROBE_TOOLS_ASK}]
                tools = [PROBE_TOOL]
            else:
                messages = [{"role": "user", "content": [
                    {"type": "text", "text": PROBE_VISION_ASK},
                    {"type": "image_url", "image_url": {"url": VISION_PIXEL}}]}]
                tools = None
            entry = self._open("probe", provider.name, model, detail=f"the {need} probe")
            started = time.monotonic()
            try:
                reply = self._ask(provider, model, self.key_for(provider), messages, tools,
                                  timeout, self.transport)
            except Canceled:
                raise
            except ChatError as exc:
                self._close(entry, ok=False, outcome=_outcome(exc), error=str(exc),
                            ms=int((time.monotonic() - started) * 1000))
                if exc.status:
                    probed = True
                if exc.status in REFUSAL_STATUSES:
                    # The provider answered about this request: it will not do this.
                    answers[need] = False
                    notes.append(f"the provider refused the {need} probe (HTTP {exc.status})")
                else:
                    notes.append(f"the {need} probe did not establish anything: {exc}")
                continue
            established = bool(reply.tool_calls) if need == "tools" else True
            answers[need] = established
            probed = True
            answered = True
            if need == "tools" and not established:
                notes.append("the model answered without asking for the tool, so tool use "
                             "is unproven")
            self._close(entry, ok=True, outcome="completed",
                        ms=int((time.monotonic() - started) * 1000),
                        served=reply.served, upstream=reply.upstream, cost=reply.cost,
                        tokens_in=_tokens(reply, "prompt_tokens"),
                        tokens_out=_tokens(reply, "completion_tokens"),
                        detail=f"the {need} probe")
        found = Capability(provider=provider.name, model=model, answers=answers,
                           notes=tuple(notes), probed=probed, answered=answered,
                           at=time.time())
        if probed:
            with self._lock:
                self._capabilities[keyed] = found
        return found

    def capabilities(self) -> list[Capability]:
        """What was probed so far, for a report that claims nothing beyond it."""
        with self._lock:
            return sorted(self._capabilities.values(), key=lambda item: (item.provider, item.model))

    def verdict(self, provider: Provider, model: str, needs: tuple[str, ...], *,
                timeout: float = PROBE_TIMEOUT) -> str:
        """Whether a model may serve a call with these needs, and why not when it may not.

        It is the same rule a fallback is held to during a turn, exposed so the report can
        show the very evidence a real call would act on rather than a second opinion.
        """
        return self._not_eligible(provider, model, needs, timeout, None)

    # ---------------------------------------------------------------------- calls

    def call(self, role: str, messages: list[dict[str, Any]], *,
             tools: list[dict[str, Any]] | None = None, timeout: float | None = None,
             cancel: threading.Event | None = None,
             transport: Callable[..., ModelReply] | None = None) -> ModelReply:
        """Ask the role's model, then the fallbacks, and count every attempt of the way.

        The caller's `timeout` is the whole budget for this call, because that is what the
        setting it comes from — `agent.step_timeout` — promises the owner: everything below
        it lives inside that number, the probes a fallback needs and the repeats included.
        An attempt never gets longer than what is left, a repeat is not started with less
        time than it can use, and a fallback is entered only where a real probe showed it
        can do what this call needs. A stop is honoured before the next request is dialled,
        never in the middle of one, so nothing here is recorded as a call that never went
        out. Each model that was tried is summarised once, with what it said and how many
        tries it took, rather than the same sentence per attempt.
        """
        limit = MODEL_TIMEOUT if timeout is None else float(timeout)
        deadline = time.monotonic() + limit
        needs = needs_of(messages, tools)
        problems: list[str] = []
        for position, (provider, model, why) in enumerate(self.fallback_chain(role)):
            if provider is None or not model:
                problems.append(why)
                continue
            remaining = deadline - time.monotonic()
            if position and remaining < MIN_ATTEMPT:
                problems.append(f"{provider.name}/{model}: not tried, no time left in this call")
                continue
            if position and needs:
                refused = self._not_eligible(provider, model, needs,
                                             min(PROBE_TIMEOUT, remaining), cancel)
                if refused:
                    problems.append(f"{provider.name}/{model}: {refused}")
                    continue
            key = self.key_for(provider)
            said = ""
            tries = 0
            while True:
                remaining = deadline - time.monotonic()
                if tries and remaining < MIN_ATTEMPT:
                    said += "; no time left in this call for another try"
                    break
                if cancel is not None and cancel.is_set():
                    raise Canceled(self._stopped(provider, model))
                tries += 1
                entry = self._open(role, provider.name, model, tries, detail=why)
                started = time.monotonic()
                try:
                    reply = self._ask(provider, model, key, messages, tools,
                                      max(0.1, min(limit, remaining)), transport)
                except ChatError as exc:
                    self._close(entry, ok=False, outcome=_outcome(exc), error=str(exc),
                                ms=int((time.monotonic() - started) * 1000))
                    said = str(exc)
                    if exc.retryable and tries < MAX_ATTEMPTS:
                        self._wait(tries, exc.retry_after, cancel, deadline)
                        continue
                    break
                self._close(entry, ok=True, outcome="completed",
                            ms=int((time.monotonic() - started) * 1000), served=reply.served,
                            upstream=reply.upstream, cost=reply.cost,
                            tokens_in=_tokens(reply, "prompt_tokens"),
                            tokens_out=_tokens(reply, "completion_tokens"),
                            detail=why)
                return reply
            tried = f" (after {tries} tries)" if tries > 1 else ""
            problems.append(f"{provider.name}/{model}: {said}{tried}")
        raise ModelError(self._pressed(problems))

    def _not_eligible(self, provider: Provider, model: str, needs: tuple[str, ...],
                      budget: float, cancel: threading.Event | None) -> str:
        """Why a fallback may not be used, or "" when a real call says it may.

        The model a role uses is the owner's own choice and is called as it is; this rule is
        for the models after it, which are entered only on evidence.
        """
        with self._lock:
            known = self._capabilities.get(self._place(provider) + (model,))
        if known is not None and known.covers(needs):
            return ""
        if budget < MIN_ATTEMPT:
            return (f"not used: there was no time left to check whether it can do "
                    f"{', '.join(needs)}")
        found = self.probe(provider, model, needs=needs, timeout=budget, cancel=cancel)
        if found.covers(needs):
            return ""
        said = "; ".join(found.notes) or f"it was not shown to do {', '.join(needs)}"
        return f"not used: {said}"

    def _ask(self, provider: Provider, model: str, key: str, messages: list[dict[str, Any]],
             tools: list[dict[str, Any]] | None, timeout: float,
             transport: Callable[..., ModelReply] | None) -> ModelReply:
        """One request, through the seam this module owns."""
        ask = transport or self.transport or TRANSPORT
        if not key:
            named = f"`{provider.key_env}`" if provider.key_env else "key_env"
            raise ChatError(f"no key was found for {named} and no provider key is saved")
        return ask(messages, base_url=provider.base_url, api_key=key, model=model,
                   tools=tools, timeout=timeout)

    @staticmethod
    def _wait(attempt: int, retry_after: float, cancel: threading.Event | None,
              deadline: float) -> None:
        """Wait before repeating a request, never past the deadline, and let a stop end the
        wait at once. A provider asking for more patience than the call has left does not
        get it: the budget belongs to the caller."""
        delay = min(BACKOFF_CAP, BACKOFF_BASE * 2 ** (attempt - 1))
        if retry_after:
            delay = max(delay, min(120.0, float(retry_after)))
        delay = min(delay, deadline - time.monotonic())
        if delay <= 0:
            return
        if cancel is None:
            time.sleep(delay)
        else:
            cancel.wait(delay)

    @staticmethod
    def _stopped(provider: Provider, model: str) -> str:
        return (f"the call to {provider.name}/{model} was stopped before it was made; a "
                f"request already on the wire may have been served")

    @staticmethod
    def _pressed(problems: list[str]) -> str:
        text = "; ".join(problems) or "no model could be called"
        return text if len(text) <= MAX_PROBLEM else text[:MAX_PROBLEM] + " …"

    # -------------------------------------------------------------------- the ledger

    @property
    def accounting(self) -> bool:
        """Whether calls are recorded. A value that cannot be read means they are kept."""
        return self._accounting_setting()[0]

    @staticmethod
    def _accounting_setting() -> tuple[bool, str]:
        """The setting and, when it cannot be read, the sentence that says so."""
        try:
            return bool(config.value("models.accounting")), ""
        except ValueError as exc:
            return True, (f"models.accounting cannot be read ({exc}), so every call is being "
                          f"recorded rather than dropped")

    def _open(self, role: str, provider: str, model: str, attempt: int = 1,
              detail: str = "") -> Call | None:
        """Start a ledger line. It exists before the request does, on purpose."""
        entry = Call(at=time.time(), role=role, provider=provider, model=model, attempt=attempt,
                     detail=detail)
        if not self.accounting:
            return None
        with self._lock:
            self.records.append(entry)
            if len(self.records) > MAX_LEDGER:
                self.dropped += len(self.records) - MAX_LEDGER
                del self.records[:len(self.records) - MAX_LEDGER]
        return entry

    @staticmethod
    def _close(entry: Call | None, *, ok: bool, outcome: str, ms: int = 0, served: str = "",
               upstream: str = "", cost: str = "", tokens_in: int = 0, tokens_out: int = 0,
               error: str = "", detail: str = "") -> None:
        if entry is None:
            return
        entry.ok = ok
        entry.outcome = outcome
        entry.ms = ms or entry.ms
        entry.served = served or entry.served
        entry.upstream = upstream or entry.upstream
        entry.cost = cost or entry.cost
        entry.tokens_in = tokens_in or entry.tokens_in
        entry.tokens_out = tokens_out or entry.tokens_out
        entry.error = error[:300] if error else entry.error
        entry.detail = detail or entry.detail

    def report(self) -> dict[str, Any]:
        """The ledger as a report: what was recorded, and what it adds up to."""
        enabled, unreadable = self._accounting_setting()
        with self._lock:
            entries = [call.to_dict() for call in self.records]
            dropped = self.dropped
        # Every line is a request the provider saw, so the outcomes are exactly these:
        # completed, refused, failed, and in flight for one that has not come back yet.
        totals: dict[str, Any] = {"calls": 0, "completed": 0, "refused": 0, "failed": 0,
                                 "in_flight": 0, "tokens_in": 0, "tokens_out": 0, "served": {}}
        for entry in entries:
            totals["calls"] += 1
            totals[entry["outcome"].replace(" ", "_")] = \
                totals.get(entry["outcome"].replace(" ", "_"), 0) + 1
            totals["tokens_in"] += entry["tokens_in"]
            totals["tokens_out"] += entry["tokens_out"]
            if entry["served"]:
                totals["served"][entry["served"]] = totals["served"].get(entry["served"], 0) + 1
        report = {"accounting": enabled, "totals": totals, "entries": entries,
                  "dropped": dropped}
        if not enabled:
            report["note"] = ("models.accounting is off, so no call of this process was "
                              "recorded; the calls themselves happened and are not counted "
                              "here")
        elif unreadable:
            report["note"] = unreadable
        return report

    def facts(self) -> dict[str, Any]:
        """What the registry can say without asking anyone anything.

        This is what `/api/status` reports, so it holds only what is known: the configured
        providers and models, the probes that really ran, and the ledger.
        """
        accounting, unreadable = self._accounting_setting()
        facts: dict[str, Any] = {"providers": [], "roles": {}, "fallback": [],
                                 "probes": [item.to_dict() for item in self.capabilities()],
                                 "discovered": [], "accounting": accounting}
        try:
            providers = self.providers()
        except ModelError as exc:
            facts["problem"] = str(exc)
            return facts
        facts["providers"] = [self.describe(provider) for provider in providers]
        if unreadable:
            facts["accounting_problem"] = unreadable
        for role in ROLES:
            try:
                facts["roles"][role] = self.model_for(role)
            except ValueError as exc:                     # a setting that cannot be read
                facts["roles"][role] = f"unreadable: {exc}"
        try:
            facts["fallback"] = [str(item) for item in (config.value("models.fallback") or [])]
        except ValueError as exc:                          # a setting that cannot be read
            facts["fallback"] = []
            facts["fallback_problem"] = str(exc)
        with self._lock:
            facts["discovered"] = [found.to_dict() for found in self._discovered.values()]
        return facts


def _tokens(reply: ModelReply, name: str) -> int:
    value = reply.usage.get(name)
    return int(value) if isinstance(value, (int, float)) else 0


#: The seam every request goes through. A test or a turn may replace it, and the registry
#: reads it at call time, so a replacement is seen by what is already running.
TRANSPORT: Callable[..., ModelReply] = chat_call

_REGISTRY: Registry | None = None
_REGISTRY_LOCK = threading.Lock()


def registry() -> Registry:
    """The one registry of this process: one ledger, one probe cache, one provider list."""
    global _REGISTRY
    with _REGISTRY_LOCK:
        if _REGISTRY is None:
            _REGISTRY = Registry()
        return _REGISTRY
