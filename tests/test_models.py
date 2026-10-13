"""The registry: what is read from the settings, what is really probed, what is counted.

The provider here is a real HTTP server on loopback, not a patched function, because the
things under test are exactly the ones a patched function would hide: which address and
which key travelled, how many requests a retry actually made, what the model list said,
whether the call that failed is on the record, and whether a fallback was entered only
after a real call showed it could do the job.

Settings, data root, keys file and project `.env` all live in a temporary folder, so
neither the owner's address nor his key is part of any of this.
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from oneiro import config, i18n, models
from oneiro.runtime import Runtime

PROBE_REPLY = {"role": "assistant", "content": "",
               "tool_calls": [{"id": "probe-1", "type": "function",
                               "function": {"name": "oneiro_probe",
                                            "arguments": json.dumps({"text": "ready"})}}]}


class Answers:
    """One stub provider: what it lists, what it answers, every request it saw."""

    def __init__(self) -> None:
        self.models: list[tuple[str, dict]] = [("auto/coding", {"tool_calling": True,
                                                                "vision": False}),
                                              ("plain/text", {})]
        self.models_status = 200
        #: The chat script: each item is `(status, message)`; the last one repeats forever.
        self.script: list[tuple[int, dict | None]] = []
        self.default: tuple[int, dict | None] = (200, {"role": "assistant", "content": "ok"})
        self.retry_after = ""
        self.calls: list[dict] = []
        self.auth: list[str] = []
        #: Called at the start of every chat request, before it is answered.
        self.on_chat = None

    def reset(self) -> None:
        Answers.__init__(self)

    def answer(self, status: int, message: dict | None = None) -> None:
        self.script.append((status, message))

    def next_answer(self) -> tuple[int, dict | None]:
        if len(self.script) > 1:
            return self.script.pop(0)
        return self.script[0] if self.script else self.default


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *_: object) -> None:
        return None

    def _send(self, status: int, payload: dict, headers: dict | None = None) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802 - http.server's naming
        answers: Answers = self.server.answers                       # type: ignore[attr-defined]
        answers.calls.append({"kind": "models", "path": self.path,
                              "auth": self.headers.get("Authorization", ""),
                              "user_agent": self.headers.get("User-Agent", "")})
        answers.auth.append(self.headers.get("Authorization", ""))
        if answers.models_status != 200:
            self._send(answers.models_status, {"error": {"message": "no"}})
            return
        self._send(200, {"data": [{"id": name, "object": "model", "capabilities": caps}
                                  for name, caps in answers.models]})

    def do_POST(self) -> None:  # noqa: N802
        answers: Answers = self.server.answers                       # type: ignore[attr-defined]
        body = json.loads(self.rfile.read(int(self.headers.get("content-length") or 0)) or b"{}")
        model = str(body.get("model") or "")
        answers.calls.append({"kind": "chat", "model": model, "tools": body.get("tools"),
                              "messages": body.get("messages") or [],
                              "auth": self.headers.get("Authorization", ""),
                              "user_agent": self.headers.get("User-Agent", "")})
        answers.auth.append(self.headers.get("Authorization", ""))
        if answers.on_chat is not None:
            answers.on_chat()
        status, message = answers.next_answer()
        if status != 200:
            extra = {"Retry-After": answers.retry_after} if answers.retry_after else {}
            self._send(status, {"error": {"message": "refused"}}, extra)
            return
        self._send(200, {"choices": [{"message": message or {"content": "ok"}}],
                         "usage": {"prompt_tokens": 3, "completion_tokens": 2},
                         "model": "served-model"},
                   {"x-omniroute-provider": "stub-upstream",
                    "x-omniroute-response-cost": "0.0001"})


class Stub:
    """A stub provider on its own loopback port, usable as a context manager."""

    def __init__(self) -> None:
        self.answers = Answers()
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._server.answers = self.answers                          # type: ignore[attr-defined]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}/v1"

    @property
    def calls(self) -> list[dict]:
        return self.answers.calls

    @property
    def auth(self) -> list[str]:
        return self.answers.auth

    @property
    def chats(self) -> list[dict]:
        return [call for call in self.calls if call["kind"] == "chat"]

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def __enter__(self) -> "Stub":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


@pytest.fixture
def provider():
    stub = Stub()
    try:
        yield stub
    finally:
        stub.close()


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """The owner's settings, keys, data root and address are not part of these tests."""
    monkeypatch.setenv("ONEIRO_SETTINGS_FILE", str(tmp_path / "settings.json"))
    monkeypatch.setenv("ONEIRO_DATA_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("ONEIRO_KEYS_FILE", str(tmp_path / "no-keys.env"))
    monkeypatch.setattr(config, "PROJECT_ENV", tmp_path / "no-project.env")
    for name in ("ONEIRO_LLM_API_KEY", "ONEIRO_API_KEY", "OMNIROUTE_API_KEY",
                 "ONEIRO_LLM_BASE_URL", "ONEIRO_LLM_MODEL", "ONEIRO_MODELS_PROVIDERS",
                 "ONEIRO_MODELS_FALLBACK", "ONEIRO_MODEL_MANAGER", "STUB_KEY"):
        monkeypatch.delenv(name, raising=False)
    # The waits between retries are zeroed: what these tests assert is how many attempts a
    # failure produces, never how long the process sat still, so the suite must not depend
    # on wall-clock time to pass.
    monkeypatch.setattr(models, "BACKOFF_BASE", 0.0)
    monkeypatch.setattr(models, "BACKOFF_CAP", 0.0)
    # The process-wide registry is the one a real turn uses; a test gets its own, so its
    # ledger holds this test's calls and nothing else.
    monkeypatch.setattr(models, "_REGISTRY", models.Registry())
    config.save({"llm.api_key": "sk-test-key"})


def pointing(stub: Stub, *, name: str = "stub", key_env: str = "STUB_KEY",
             fallback: list[str] | None = None, models_in: list[str] | None = None) -> None:
    """Point the provider list at the stub, and the fallback list when one is given."""
    record: dict = {"name": name, "base_url": stub.base, "key_env": key_env,
                    "discover_models": True}
    if models_in is not None:
        record["models"] = models_in
    patch: dict = {"models.providers": [record]}
    if fallback is not None:
        patch["models.fallback"] = list(fallback)
    config.save(patch)


def a_registry() -> models.Registry:
    return models.Registry()


# ------------------------------------------------------------- what the settings say

def test_the_provider_list_is_read_as_the_settings_declare_it(provider):
    pointing(provider)
    found = a_registry().providers()
    assert [item.name for item in found] == ["stub"]
    assert found[0].base_url == provider.base and found[0].key_env == "STUB_KEY"
    assert found[0].discover_models is True


def test_the_shipped_provider_takes_the_pre_registry_address_until_the_owner_writes_his_own(
        provider):
    config.save({"llm.base_url": provider.base})
    shipped = a_registry().providers()
    assert shipped[0].name == models.SHIPPED_PROVIDER and shipped[0].base_url == provider.base

    # An owned list decides everything about itself: the pre-registry address stops applying.
    config.save({"models.providers": [{"name": "local", "base_url": "http://127.0.0.1:9/v1"}]})
    assert a_registry().providers()[0].base_url == "http://127.0.0.1:9/v1"


def test_an_empty_provider_list_is_a_refusal_that_names_the_setting(monkeypatch):
    real = config.resolve
    monkeypatch.setattr(config, "resolve", lambda key: (([], "file") if key == "models.providers"
                                                        else real(key)))
    with pytest.raises(models.NoProvider) as caught:
        a_registry().providers()
    assert "models.providers names no provider" in str(caught.value)


def test_a_disabled_provider_is_skipped_and_all_disabled_is_a_refusal():
    config.save({"models.providers": [{"name": "off", "base_url": "http://127.0.0.1:9/v1",
                                       "enabled": False},
                                      {"name": "on", "base_url": "http://127.0.0.1:9/v1"}]})
    assert [item.name for item in a_registry().providers()] == ["on"]
    config.save({"models.providers": [{"name": "off", "base_url": "http://127.0.0.1:9/v1",
                                       "enabled": False}]})
    with pytest.raises(models.NoProvider, match="disabled"):
        a_registry().providers()


def test_a_provider_address_carrying_a_key_is_refused():
    config.save({"models.providers": [{"name": "bad", "base_url": "http://user:key@localhost/v1",
                                       "key_env": "K"}]})
    with pytest.raises(models.NoProvider) as caught:
        a_registry().providers()
    assert "never travels in the address" in str(caught.value)


def test_a_role_uses_its_own_model_then_the_default_then_the_pre_registry_name():
    registry = a_registry()
    assert registry.model_for("researcher") == "auto/coding"          # the declared default
    config.save({"llm.model": "old/alias"})
    assert registry.model_for("researcher") == "old/alias"            # the pre-registry name
    config.save({"models.default": "new/default"})
    assert registry.model_for("researcher") == "new/default"          # the new name outranks it
    config.save({"models.roles.researcher": "research/model"})
    assert registry.model_for("researcher") == "research/model"
    assert registry.model_for("manager") == "new/default"


def test_a_provider_model_reference_and_a_bare_name_both_resolve():
    config.save({"models.providers": [
        {"name": "one", "base_url": "http://127.0.0.1:9/v1", "models": ["one/model"]},
        {"name": "two", "base_url": "http://127.0.0.1:8/v1", "models": ["two/model"]}]})
    registry = a_registry()
    # `provider/model` names the provider and the model after the slash …
    assert registry.resolve("two/model") == (registry.providers()[1], "model")
    # … while a name nobody declares as a provider is one model id, slash and all.
    assert registry.resolve("vendor/model-7") == (registry.providers()[0], "vendor/model-7")


def test_the_needs_of_a_call_are_read_from_the_request_itself():
    image = [{"role": "user", "content": [{"type": "text", "text": "look"},
                                          {"type": "image_url",
                                           "image_url": {"url": models.VISION_PIXEL}}]}]
    assert models.needs_of([{"role": "user", "content": "hi"}]) == ()
    assert models.needs_of([{"role": "user", "content": "hi"}], [models.PROBE_TOOL]) == ("tools",)
    assert models.needs_of(image) == ("vision",)
    assert models.needs_of(image, [models.PROBE_TOOL]) == ("tools", "vision")


# -------------------------------------------------------------------------- discovery

def test_discovery_reads_the_models_the_provider_lists(provider):
    provider.answers.models = [("auto/coding", {"tool_calling": True, "vision": False}),
                               ("plain/text", {})]
    pointing(provider)
    registry = a_registry()
    found = registry.discover(registry.providers()[0])

    assert found.models == ("auto/coding", "plain/text")
    # What the provider advertises is kept as what it says, never as what was seen, and
    # "it did not mention it" stays distinct from "it says it cannot".
    assert found.says("auto/coding", "tools") is True
    assert found.says("auto/coding", "vision") is False
    assert found.says("plain/text", "tools") is None
    assert [call["kind"] for call in provider.calls] == ["models"]
    entry = registry.report()["entries"][0]
    assert entry["role"] == "discover" and entry["ok"] is True
    assert entry["detail"] == "2 models listed"


def test_discovery_says_which_variable_the_key_was_looked_for_in(provider):
    provider.answers.models_status = 401
    config.save({"models.providers": [{"name": "stub", "base_url": provider.base,
                                       "key_env": "STUB_KEY"}]})
    config.save({"llm.api_key": ""})
    registry = a_registry()
    with pytest.raises(models.ModelError) as caught:
        registry.discover(registry.providers()[0])
    assert "STUB_KEY" in str(caught.value) and "refused the key" in str(caught.value)
    assert provider.auth == [""]                      # no key travelled, and none was invented
    assert registry.report()["entries"][0]["outcome"] == "refused"


def test_a_changed_address_is_not_answered_from_the_old_one_s_cache(provider):
    """The owner can edit a provider's address while the process runs, and then the answer
    about the old address is not the answer about the new one."""
    with Stub() as other:
        other.answers.models = [("elsewhere/model", {})]
        pointing(provider)                      # the declared list carries no models
        registry = a_registry()
        first = registry.providers()[0]
        assert registry.discover(first).models == ("auto/coding", "plain/text")

        pointing(other)
        second = registry.providers()[0]
        assert second.base_url == other.base
        found = registry.discover(second, refresh=False)
        assert found.models == ("elsewhere/model",)
        assert [call["kind"] for call in other.calls] == ["models"]


def test_discovery_that_fails_is_still_counted(provider):
    provider.answers.models_status = 503
    pointing(provider)
    registry = a_registry()
    with pytest.raises(models.ModelError, match="HTTP 503"):
        registry.discover(registry.providers()[0])
    assert len(provider.calls) == len(registry.report()["entries"]) == 1


def test_the_key_the_provider_names_is_the_key_that_travels(provider, tmp_path, monkeypatch):
    keys = tmp_path / "keys.env"
    keys.write_text("STUB_KEY=sk-from-keys-file\n", encoding="utf-8")
    monkeypatch.setenv("ONEIRO_KEYS_FILE", str(keys))
    config.save({"llm.api_key": ""})
    pointing(provider, key_env="STUB_KEY")
    a_registry().call("manager", [{"role": "user", "content": "hello"}])
    assert provider.chats[0]["auth"] == "Bearer sk-from-keys-file"


def test_only_the_first_provider_may_borrow_the_pre_registry_key(provider):
    config.save({"models.providers": [
        {"name": "first", "base_url": "http://127.0.0.1:9/v1", "key_env": "NOTHING_SET"},
        {"name": "second", "base_url": provider.base, "key_env": "NOTHING_SET"}]})
    registry = a_registry()
    first, second = registry.providers()
    assert registry.key_for(first) == "sk-test-key"
    assert registry.key_for(second) == ""


# ----------------------------------------------------------------------------- probes

def test_a_probe_establishes_tools_and_vision_by_a_real_call(provider):
    provider.answers.script = [(200, PROBE_REPLY), (200, {"role": "assistant", "content": "red"})]
    pointing(provider)
    registry = a_registry()
    capability = registry.probe(registry.providers()[0], "auto/coding")

    assert capability.answers == {"tools": True, "vision": True}
    assert capability.answered and capability.probed
    assert len(provider.calls) == 2
    assert provider.chats[0]["tools"][0]["function"]["name"] == "oneiro_probe"
    sent = provider.chats[1]["messages"][0]["content"]
    assert sent[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert [entry["role"] for entry in registry.report()["entries"]] == ["probe", "probe"]


def test_a_model_that_answers_without_the_tool_is_recorded_as_unproven(provider):
    provider.answers.default = (200, {"role": "assistant", "content": "I would rather talk."})
    pointing(provider)
    registry = a_registry()
    capability = registry.probe(registry.providers()[0], "auto/coding", needs=("tools",))
    assert capability.says("tools") is False and capability.answered
    assert "unproven" in " ".join(capability.notes)


def test_an_image_the_provider_refuses_is_that_provider_s_own_answer(provider):
    provider.answers.script = [(200, PROBE_REPLY), (400, None)]
    pointing(provider)
    registry = a_registry()
    capability = registry.probe(registry.providers()[0], "auto/coding")
    assert capability.says("tools") is True and capability.says("vision") is False
    assert any("HTTP 400" in note for note in capability.notes)
    outcomes = [entry["outcome"] for entry in registry.report()["entries"]]
    assert outcomes == ["completed", "refused"]


def test_a_probe_that_could_not_be_made_establishes_nothing():
    config.save({"models.providers": [{"name": "gone", "base_url": "http://127.0.0.1:9/v1",
                                       "key_env": "K"}]})
    registry = a_registry()
    capability = registry.probe(registry.providers()[0], "auto/coding", needs=("tools",))
    assert capability.answers == {} and capability.probed is False and capability.answered is False
    assert capability.covers(("tools",)) is False
    assert "did not establish anything" in " ".join(capability.notes)
    assert registry.report()["entries"][0]["outcome"] == "failed"


# ------------------------------------------------------------------- calls and fallback

def test_a_call_goes_to_the_model_the_role_uses(provider):
    pointing(provider)
    registry = a_registry()
    reply = registry.call("manager", [{"role": "user", "content": "hello"}])
    assert reply.content == "ok"
    assert provider.chats[0]["model"] == "auto/coding"
    assert provider.chats[0]["tools"] is None


def test_changing_a_setting_changes_which_model_is_asked(provider):
    pointing(provider)
    registry = a_registry()
    registry.call("manager", [{"role": "user", "content": "one"}])
    config.save({"models.roles.manager": "another/model"})
    registry.call("manager", [{"role": "user", "content": "two"}])
    assert [call["model"] for call in provider.chats] == ["auto/coding", "another/model"]


def test_a_transient_failure_is_repeated_and_the_second_answer_is_used(provider):
    provider.answers.script = [(500, None), (200, {"role": "assistant", "content": "the second"})]
    pointing(provider)
    reply = a_registry().call("manager", [{"role": "user", "content": "hello"}])
    assert reply.content == "the second"
    assert len(provider.calls) == 2


def test_the_retries_are_bounded_and_the_failure_names_the_model(provider):
    provider.answers.default = (503, None)
    pointing(provider)
    registry = a_registry()
    with pytest.raises(models.ModelError) as caught:
        registry.call("manager", [{"role": "user", "content": "hello"}])
    assert len(provider.calls) == models.MAX_ATTEMPTS
    assert "stub/auto/coding" in str(caught.value) and "HTTP 503" in str(caught.value)
    # One line per model, not the same sentence three times over.
    assert str(caught.value).count("HTTP 503") == 1
    assert "after 3 tries" in str(caught.value)
    assert [entry["attempt"] for entry in registry.report()["entries"]] == [1, 2, 3]


def test_the_declared_limit_is_the_budget_for_the_whole_call(provider):
    """`agent.step_timeout` promises the owner a bound on one model call; repeating a
    failure must fit inside that bound instead of multiplying it."""
    provider.answers.default = (503, None)          # retryable, so only time stops it
    pointing(provider)
    registry = a_registry()
    started = time.monotonic()
    with pytest.raises(models.ModelError) as caught:
        registry.call("manager", [{"role": "user", "content": "hello"}], timeout=0.5)
    spent = time.monotonic() - started
    assert spent < 3, f"a half-second budget took {spent:.1f}s"
    assert len(provider.calls) == 1, "a try was started with no time left for it"
    assert "no time left in this call" in str(caught.value)
    # The failure it did have is the one reported: the budget did not overwrite it.
    assert "HTTP 503" in str(caught.value)


def test_a_refusal_is_taken_at_its_word_and_not_repeated(provider):
    provider.answers.default = (401, None)
    pointing(provider)
    registry = a_registry()
    with pytest.raises(models.ModelError):
        registry.call("manager", [{"role": "user", "content": "hello"}])
    assert len(provider.calls) == 1
    assert registry.report()["entries"][0]["outcome"] == "refused"


def test_a_fallback_is_entered_only_after_a_real_call_showed_it_can_do_the_job(provider,
                                                                               monkeypatch):
    monkeypatch.setenv("STUB_KEY", "sk-test-key")
    with Stub() as spare:
        provider.answers.default = (503, None)
        spare.answers.script = [(200, PROBE_REPLY), (200, {"role": "assistant",
                                                           "content": "the real answer"})]
        config.save({"models.providers": [
            {"name": "primary", "base_url": provider.base, "key_env": "STUB_KEY"},
            {"name": "spare", "base_url": spare.base, "key_env": "STUB_KEY"}],
            "models.fallback": ["spare/auto/coding"]})
        registry = a_registry()
        reply = registry.call("manager", [{"role": "user", "content": "hello"}],
                              tools=[models.PROBE_TOOL])

        assert reply.content == "the real answer" and reply.served == "served-model"
        # The probe came first, and only then the work.
        assert [call["tools"] is not None for call in spare.chats] == [True, True]
        entries = registry.report()["entries"]
        assert [entry["role"] for entry in entries] == ["manager", "manager", "manager",
                                                        "probe", "manager"]
        assert [entry["outcome"] for entry in entries] == ["failed", "failed", "failed",
                                                           "completed", "completed"]
        assert entries[-1]["detail"] == "a fallback for manager"


def test_a_fallback_that_was_not_shown_to_use_tools_is_skipped_with_the_reason(provider,
                                                                               monkeypatch):
    monkeypatch.setenv("STUB_KEY", "sk-test-key")
    with Stub() as spare:
        provider.answers.default = (401, None)
        spare.answers.default = (200, {"role": "assistant", "content": "I would rather talk."})
        config.save({"models.providers": [
            {"name": "primary", "base_url": provider.base, "key_env": "STUB_KEY"},
            {"name": "spare", "base_url": spare.base, "key_env": "STUB_KEY"}],
            "models.fallback": ["spare/auto/coding"]})
        registry = a_registry()
        with pytest.raises(models.ModelError) as caught:
            registry.call("manager", [{"role": "user", "content": "hello"}],
                          tools=[models.PROBE_TOOL])

        assert "spare/auto/coding: not used" in str(caught.value)
        assert "unproven" in str(caught.value)
        # It was asked to prove itself and never asked to do the work.
        assert len(spare.chats) == 1
        assert spare.chats[0]["tools"] is not None


def test_a_provider_without_a_key_cannot_be_fallen_back_to_and_says_which_name_is_missing(
        provider):
    """The pre-registry key belongs to the first provider only, and a missing key is said."""
    with Stub() as spare:
        provider.answers.default = (401, None)
        config.save({"models.providers": [
            {"name": "primary", "base_url": provider.base, "key_env": "NOTHING_SET"},
            {"name": "spare", "base_url": spare.base, "key_env": "STUB_KEY"}],
            "models.fallback": ["spare/auto/coding"]})
        registry = a_registry()
        with pytest.raises(models.ModelError) as caught:
            registry.call("manager", [{"role": "user", "content": "hello"}],
                          tools=[models.PROBE_TOOL])
        assert "no key was found for `STUB_KEY`" in str(caught.value)
        assert spare.calls == []                   # nothing was asked of it without a key


def test_a_plain_turn_may_fall_back_without_a_probe(provider, monkeypatch):
    monkeypatch.setenv("STUB_KEY", "sk-test-key")
    with Stub() as spare:
        provider.answers.default = (503, None)
        spare.answers.default = (200, {"role": "assistant", "content": "from the spare"})
        config.save({"models.providers": [
            {"name": "primary", "base_url": provider.base, "key_env": "STUB_KEY"},
            {"name": "spare", "base_url": spare.base, "key_env": "STUB_KEY"}],
            "models.fallback": ["spare/auto/coding"]})
        reply = a_registry().call("manager", [{"role": "user", "content": "hello"}])
        assert reply.content == "from the spare"
        assert len(spare.chats) == 1                      # nothing to probe: text needs no pair


def test_a_fallback_reference_that_cannot_be_resolved_is_named_in_the_failure(provider,
                                                                              monkeypatch):
    real = config.value
    monkeypatch.setattr(config, "value", lambda key, default=None: (
        [" "] if key == "models.fallback" else real(key, default)))
    provider.answers.default = (401, None)
    pointing(provider)
    with pytest.raises(models.ModelError) as caught:
        a_registry().call("manager", [{"role": "user", "content": "hello"}])
    assert "models.fallback cannot use" in str(caught.value)


def test_provider_user_agent_reaches_discovery_and_chat(provider):
    config.save({"models.providers": [{"name": "primary", "base_url": provider.base,
                                       "user_agent": "Mozilla/5.0 (compatible; Oneiro/0.2)"}]})
    registry = a_registry()
    registry.discover(registry.providers()[0])
    registry.call("manager", [{"role": "user", "content": "hello"}])
    assert [call["user_agent"] for call in provider.calls] == [
        "Mozilla/5.0 (compatible; Oneiro/0.2)"] * 2


@pytest.mark.parametrize("field,value", [("requests_per_minute", -1),
                                         ("requests_per_minute", True),
                                         ("requests_per_minute", "36"),
                                         ("timeout_seconds", 0.5),
                                         ("timeout_seconds", 3601),
                                         ("user_agent", "bad\nheader")])
def test_provider_limits_are_validated_without_echoing_values(field, value):
    with pytest.raises(ValueError, match=field):
        config.save({"models.providers": [{"name": "primary", "base_url": "https://example.invalid/v1",
                                           field: value}]})


def test_pacing_bounds_every_rolling_minute_and_discovery_shares_it(provider, monkeypatch):
    config.save({"models.providers": [{"name": "primary", "base_url": provider.base,
                                       "requests_per_minute": 36}]})
    registry = a_registry()
    primary = registry.providers()[0]
    registry.discover(primary)   # discovery consumes the same provider allowance
    with pytest.raises(models.ChatError, match="rate limit"):
        registry._ask(primary, "text", registry.key_for(primary), [], None, 0.01, None)
    assert len(provider.calls) == 1

    now = [100.0]
    with monkeypatch.context() as patch:
        patch.setattr(models.time, "monotonic", lambda: now[0])
        patch.setattr(models.time, "sleep", lambda seconds: now.__setitem__(0, now[0] + seconds))
        registry = a_registry()
        timestamps = []
        for _ in range(80):
            registry._paced_timeout(primary, 5, None)
            timestamps.append(now[0])
        assert all(sum(start <= t < start + 60 - 1e-8 for t in timestamps) <= 36
                   for start in timestamps)
        assert timestamps[-1] - timestamps[0] == pytest.approx(79 * 60 / 36)


def test_cancel_during_pacing_starts_no_second_request(provider):
    config.save({"models.providers": [{"name": "primary", "base_url": provider.base,
                                       "requests_per_minute": 36}]})
    registry = a_registry()
    primary = registry.providers()[0]
    registry._paced_timeout(primary, 1, None)
    stop = threading.Event()
    timer = threading.Timer(0.02, stop.set)
    timer.start()
    try:
        with pytest.raises(models.Canceled):
            registry._ask(primary, "text", registry.key_for(primary), [], None, 5, None, stop)
    finally:
        timer.join()
    assert not provider.calls


@pytest.mark.parametrize("status", [401, 403, 429, 503])
def test_failed_primary_uses_its_own_key_then_fallback_key(provider, monkeypatch, status):
    monkeypatch.setenv("PRIMARY_KEY", "primary-only")
    monkeypatch.setenv("SPARE_KEY", "gateway-only")
    provider.answers.default = (status, None)
    with Stub() as spare:
        config.save({"models.providers": [
            {"name": "primary", "base_url": provider.base, "key_env": "PRIMARY_KEY"},
            {"name": "gateway", "base_url": spare.base, "key_env": "SPARE_KEY"}],
            "models.default": "primary/model", "models.fallback": ["gateway/text"]})
        registry = a_registry()
        assert registry.call("manager", [{"role": "user", "content": "hello"}]).content == "ok"
        assert set(provider.auth) == {"Bearer primary-only"}
        assert set(spare.auth) == {"Bearer gateway-only"}
        assert registry.report()["entries"][-1]["provider"] == "gateway"


def test_primary_timeout_leaves_budget_for_real_fallback(provider, monkeypatch):
    monkeypatch.setenv("SPARE_KEY", "gateway-only")
    config.save({"models.providers": [
        {"name": "primary", "base_url": "https://example.invalid/v1", "timeout_seconds": 1},
        {"name": "gateway", "base_url": provider.base, "key_env": "SPARE_KEY"}],
        "models.default": "primary/model", "models.fallback": ["gateway/text"]})
    timeouts = []

    def transport(messages, **kwargs):
        if kwargs["base_url"].startswith("https://example.invalid"):
            timeouts.append(kwargs["timeout"])
            time.sleep(kwargs["timeout"] + 0.01)
            raise models.ChatError("simulated socket timeout", retryable=True)
        return models.chat_call(messages, **kwargs)

    registry = models.Registry(transport=transport)
    started = time.monotonic()
    reply = registry.call("manager", [{"role": "user", "content": "hello"}], timeout=4)
    assert reply.content == "ok" and len(provider.chats) == 1
    assert len(timeouts) == 1 and timeouts[0] <= 1
    assert time.monotonic() - started < 3


# ----------------------------------------------------------------------- cancellation

def test_a_stop_before_the_call_makes_no_request(provider):
    pointing(provider)
    stop = threading.Event()
    stop.set()
    registry = a_registry()
    with pytest.raises(models.Canceled) as caught:
        registry.call("manager", [{"role": "user", "content": "hello"}], cancel=stop)
    assert provider.calls == []
    assert "may have been served" in str(caught.value)
    assert registry.report()["entries"] == []


def test_a_stop_during_the_wait_ends_the_chain_at_the_next_attempt(provider):
    pointing(provider)
    stop = threading.Event()
    provider.answers.default = (503, None)
    provider.answers.on_chat = stop.set            # the owner stops while the first is out
    registry = a_registry()
    with pytest.raises(models.Canceled):
        registry.call("manager", [{"role": "user", "content": "hello"}], cancel=stop)
    assert len(provider.calls) == 1
    assert registry.report()["entries"][0]["outcome"] == "failed"


# -------------------------------------------------------------------------- the ledger

def test_every_call_the_provider_saw_is_in_the_ledger(provider):
    provider.answers.script = [(200, PROBE_REPLY), (200, {"role": "assistant", "content": "red"}),
                               (500, None), (200, {"role": "assistant", "content": "finally"})]
    pointing(provider)
    registry = a_registry()
    provider_object = registry.providers()[0]
    registry.discover(provider_object)
    registry.probe(provider_object, "auto/coding")
    registry.call("manager", [{"role": "user", "content": "hello"}])

    report = registry.report()
    assert len(provider.calls) == len(report["entries"]) == 5
    assert [entry["role"] for entry in report["entries"]] == ["discover", "probe", "probe",
                                                              "manager", "manager"]
    assert report["totals"]["calls"] == 5 and report["totals"]["completed"] == 4
    # The model that answered is named four times; the model list is not a model.
    assert report["totals"]["failed"] == 1 and report["totals"]["served"] == {"served-model": 3}


def test_the_report_is_one_line_per_call_with_what_the_provider_reported(provider):
    pointing(provider)
    registry = a_registry()
    registry.call("manager", [{"role": "user", "content": "hello"}])
    entry = registry.report()["entries"][0]
    assert entry["role"] == "manager" and entry["provider"] == "stub"
    assert entry["model"] == "auto/coding" and entry["ok"] is True
    assert entry["served"] == "served-model" and entry["upstream"] == "stub-upstream"
    assert entry["tokens_in"] == 3 and entry["tokens_out"] == 2 and entry["cost"] == "0.0001"
    assert entry["ms"] >= 0 and entry["outcome"] == "completed"


def test_a_call_that_never_came_back_is_still_on_the_record(provider):
    """The entry is written before the request is dialled, which is the whole point."""
    answering = threading.Event()

    def hang() -> None:
        # Long enough that the request is certainly still out while the ledger is read; the
        # test sets this event itself before it finishes, so it never waits that long.
        answering.wait(30)

    provider.answers.on_chat = hang
    pointing(provider)
    registry = a_registry()
    stop = threading.Event()
    thread = threading.Thread(target=registry.call,
                              args=("manager", [{"role": "user", "content": "hello"}]),
                              kwargs={"cancel": stop}, daemon=True)
    thread.start()
    try:
        for _ in range(500):                       # wait for the request to be on the wire
            if provider.calls:
                break
            time.sleep(0.02)
        entries = registry.report()["entries"]
        assert len(entries) == 1 and entries[0]["outcome"] == "in flight"
    finally:
        answering.set()
        stop.set()
        thread.join(10)


def test_accounting_off_records_nothing_and_says_so(provider):
    config.save({"models.accounting": False})
    pointing(provider)
    registry = a_registry()
    registry.call("manager", [{"role": "user", "content": "hello"}])

    assert len(provider.calls) == 1                # the call happened
    report = registry.report()
    assert report["accounting"] is False and report["entries"] == []
    assert report["totals"]["calls"] == 0 and "off" in report["note"]


def test_an_accounting_setting_that_cannot_be_read_keeps_recording_and_says_so(provider,
                                                                              monkeypatch):
    """The cautious value is the one that keeps the evidence, and the page is told."""
    real = config.value

    def broken(key, default=None):
        if key == "models.accounting":
            raise ValueError("models.accounting: a boolean was expected")
        return real(key, default)

    monkeypatch.setattr(config, "value", broken)
    pointing(provider)
    registry = a_registry()
    registry.call("manager", [{"role": "user", "content": "hello"}])

    report = registry.report()
    assert report["accounting"] is True and report["totals"]["calls"] == 1
    assert "cannot be read" in report["note"]
    assert "cannot be read" in registry.facts()["accounting_problem"]


def test_the_ledger_stays_bounded(provider):
    pointing(provider)
    registry = a_registry()
    for number in range(models.MAX_LEDGER + 5):
        registry.call("manager", [{"role": "user", "content": f"turn {number}"}])
    report = registry.report()
    assert len(report["entries"]) == models.MAX_LEDGER and report["dropped"] == 5


# -------------------------------------------------------------------- what status sees

def test_a_fallback_list_that_cannot_be_read_is_named_in_the_failure(provider, monkeypatch):
    real = config.value

    def broken(key, default=None):
        if key == "models.fallback":
            raise ValueError("models.fallback: a list of non-empty strings was expected")
        return real(key, default)

    monkeypatch.setattr(config, "value", broken)
    provider.answers.default = (401, None)
    pointing(provider)
    with pytest.raises(models.ModelError) as caught:
        a_registry().call("manager", [{"role": "user", "content": "hello"}])
    assert "models.fallback cannot be read" in str(caught.value)


def test_facts_ask_nothing_and_claim_nothing(provider):
    pointing(provider)
    registry = a_registry()
    facts = registry.facts()
    assert facts["providers"][0] == {"name": "stub", "base_url": provider.base,
                                     "key_env": "STUB_KEY", "key_found": True,
                                     "discover_models": True, "models": [], "enabled": True}
    assert facts["roles"]["manager"] == "auto/coding"
    assert facts["probes"] == [] and facts["discovered"] == []
    assert provider.calls == []                    # a status page is not a provider call


def test_status_reports_providers_probes_and_the_ledger(provider):
    provider.answers.script = [(200, PROBE_REPLY), (200, {"role": "assistant", "content": "red"})]
    pointing(provider)
    report = asyncio.run(Runtime().verify_model(timeout=5))

    assert report["verified"] is True and report["used_tools"] is True and report["vision"] is True
    described = report["providers"][0]
    assert described["name"] == "stub" and described["key_found"] is True
    assert described["model_list"] == "2 models" and described["lists_the_role_model"] is True
    assert described["advertises"] == {"tools": True, "vision": False}
    probes = {entry["provider"]: entry for entry in report["probes"]}
    assert probes["stub"]["tools"] is True and probes["stub"]["answered"] is True
    assert report["accounting"]["totals"]["calls"] == 3

    status = asyncio.run(Runtime().status())
    assert status["model"]["verified"] is False            # a new process probed nothing
    assert status["model"]["providers"][0]["name"] == "stub"
    # The payload carries a code, not the sentence: the panel prints it in the language
    # of the page, and this is the command that sentence names.
    code = status["model"]["reason_code"]
    assert code == "reason.verify_model"
    assert "verify-model" in i18n.t(code, "en")
    assert code not in i18n.t(code, "en"), "the code itself must not be what the panel shows"


def test_verify_model_says_when_the_model_answers_without_a_tool(provider):
    provider.answers.script = [(200, {"role": "assistant", "content": "hello"}),
                               (200, {"role": "assistant", "content": "red"})]
    pointing(provider)
    report = asyncio.run(Runtime().verify_model(timeout=5))
    assert report["verified"] is True and report["used_tools"] is False
    assert any("unproven" in note for note in report.get("notes", []))


def test_verify_model_names_a_provider_list_it_cannot_use(monkeypatch):
    real = config.resolve
    monkeypatch.setattr(config, "resolve", lambda key: (([], "file") if key == "models.providers"
                                                        else real(key)))
    report = asyncio.run(Runtime().verify_model(timeout=5))
    assert report["verified"] is False
    assert "models.providers names no provider" in report["reason"]


def test_verify_model_reports_each_fallback_and_what_it_can_do(provider, monkeypatch):
    monkeypatch.setenv("STUB_KEY", "sk-test-key")
    with Stub() as spare:
        provider.answers.script = [(200, PROBE_REPLY), (200, {"role": "assistant",
                                                              "content": "red"})]
        spare.answers.default = (200, {"role": "assistant", "content": "I would rather talk."})
        config.save({"models.providers": [
            {"name": "primary", "base_url": provider.base, "key_env": "STUB_KEY"},
            {"name": "spare", "base_url": spare.base, "key_env": "STUB_KEY"}],
            "models.fallback": ["spare/auto/coding"]})
        report = asyncio.run(Runtime().verify_model(timeout=5))

        entry = report["fallback"][0]
        assert entry["reference"] == "spare/auto/coding" and entry["provider"] == "spare"
        assert entry["usable_for_tools"] is False and "unproven" in entry["why"]
        assert {probe["provider"] for probe in report["probes"]} == {"primary", "spare"}
