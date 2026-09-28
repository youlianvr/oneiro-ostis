"""The one settings owner: layers, types, secrets, and what a write touches.

Nothing here touches the network or the real settings file: every test points
`ONEIRO_SETTINGS_FILE` at a file under `tmp_path`, which is exactly the door the
module is built with.
"""

import json

import pytest

from config import describe, path, reset, resolve, save, settings, value


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """Every test gets its own settings file and no inherited overrides."""
    target = tmp_path / "settings.json"
    monkeypatch.setenv("ONEIRO_SETTINGS_FILE", str(target))
    for name in ("ONEIRO_LLM_BASE_URL", "ONEIRO_BASE_URL", "ONEIRO_LLM_API_KEY",
                 "ONEIRO_API_KEY", "OMNIROUTE_API_KEY", "ONEIRO_LLM_MODEL",
                 "ONEIRO_HOST", "ONEIRO_PORT", "ONEIRO_DASH_PORT", "ONEIRO_SEED",
                 "ONEIRO_ROUNDS", "ONEIRO_SEEDS", "ONEIRO_WORKSPACE",
                 "ONEIRO_BENCH_DIR", "ONEIRO_LME_DIR", "ONEIRO_MCP_SOURCE"):
        monkeypatch.delenv(name, raising=False)
    return target


def test_every_declared_key_is_unique():
    keys = [row["key"] for row in describe()["settings"]]
    assert len(keys) == len(set(keys))


def test_the_default_answers_when_nothing_else_does():
    assert resolve("graph.port") == (8090, "default")


def test_the_environment_answers_over_the_default(monkeypatch):
    monkeypatch.setenv("ONEIRO_PORT", "9999")
    assert resolve("graph.port") == (9999, "env")


def test_an_older_name_still_answers(monkeypatch):
    """`ONEIRO_BASE_URL` was the same field under a second name."""
    monkeypatch.setenv("ONEIRO_BASE_URL", "http://elsewhere.invalid/v1")
    assert value("llm.base_url") == "http://elsewhere.invalid/v1"


def test_the_saved_value_answers_over_the_environment(monkeypatch, isolated_settings):
    monkeypatch.setenv("ONEIRO_PORT", "9999")
    save({"graph.port": 7000})
    assert resolve("graph.port") == (7000, "file")


def test_a_saved_value_survives_a_reread(isolated_settings):
    save({"graph.host": "graph.local"})
    assert json.loads(isolated_settings.read_text(encoding="utf-8"))["graph.host"] == "graph.local"
    assert settings.graph_host == "graph.local"


def test_an_attribute_spelling_reaches_the_dotted_key():
    assert settings.graph_port == 8090
    assert settings.llm_base_url == "http://127.0.0.1:20128/v1"


def test_a_path_setting_expands_the_home_marker():
    assert str(path("workspace")).startswith(str(__import__("pathlib").Path.home()))


def test_an_integer_setting_refuses_text():
    with pytest.raises(ValueError, match="graph.port"):
        save({"graph.port": "not a number"})


def test_an_unknown_key_is_refused_by_name():
    with pytest.raises(ValueError, match="graph.por"):
        save({"graph.por": 1})


def test_a_write_touches_only_the_keys_it_was_given(isolated_settings):
    save({"graph.host": "a.local", "world.seed": "seed-a"})
    save({"graph.host": "b.local"})
    stored = json.loads(isolated_settings.read_text(encoding="utf-8"))
    assert stored == {"graph.host": "b.local", "world.seed": "seed-a"}


def test_two_mistakes_come_back_together():
    with pytest.raises(ValueError) as excinfo:
        save({"graph.port": "x", "dashboard.port": "y"})
    assert "graph.port" in str(excinfo.value) and "dashboard.port" in str(excinfo.value)


def test_a_blank_path_forgets_the_stored_value(isolated_settings):
    save({"workspace": "/somewhere/else"})
    save({"workspace": ""})
    assert "workspace" not in json.loads(isolated_settings.read_text(encoding="utf-8"))


def test_the_key_is_never_handed_out(isolated_settings):
    save({"llm.api_key": "sk-secret-value"})
    row = next(r for r in describe()["settings"] if r["key"] == "llm.api_key")
    assert row["value"] == ""          # nothing to put in a field, by design
    assert row["set"] is True           # only the fact that one is in force
    assert row["source"] == "file"
    assert "sk-secret-value" not in json.dumps(describe(), ensure_ascii=False)


def test_a_blank_key_falls_back_to_the_environment(monkeypatch, isolated_settings):
    save({"llm.api_key": "sk-secret-value"})
    save({"llm.api_key": ""})
    monkeypatch.setenv("OMNIROUTE_API_KEY", "from-env")
    assert value("llm.api_key") == "from-env"


def test_reset_forgets_one_key_and_then_all(isolated_settings):
    save({"graph.host": "a.local", "world.seed": "seed-a"})
    reset(["graph.host"])
    assert value("graph.host") == "localhost"
    assert value("world.seed") == "seed-a"
    reset()
    assert value("world.seed") == "oneiro-0"


def test_a_corrupt_file_is_reported_and_not_fatal(isolated_settings):
    isolated_settings.write_text("{not json", encoding="utf-8")
    assert value("graph.port") == 8090            # the default still answers
    assert describe()["error"]                    # and the reason is on record


def test_the_description_carries_the_layer_that_answered(monkeypatch):
    monkeypatch.setenv("ONEIRO_HOST", "graph.local")
    row = next(r for r in describe()["settings"] if r["key"] == "graph.host")
    assert row["source"] == "env"
    assert row["changed"] is True
    assert row["default"] == "localhost"
