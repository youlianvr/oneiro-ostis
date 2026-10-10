"""The settings catalog is a contract with the owner, so it is tested as one.

Every declared setting must be complete enough to render and to write: a group, a
sentence, a type, and a default the type actually accepts. The owner's catalog of
2026-10-09 (`docs/MASTER-PLAN.md` § 4) is asserted by key, so a rename cannot
quietly drop a setting the owner was promised.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from oneiro import config

#: The keys the owner's plan § 4 promises, verified to exist here.
PROMISED_KEYS = (
    "ui.language", "ui.theme", "ui.density", "ui.window", "ui.tray",
    "initiative.level", "initiative.suggestions", "initiative.quiet_hours",
    "permissions.mode", "permissions.web_read", "permissions.write_workspace",
    "permissions.write_outside", "permissions.delete", "permissions.install",
    "permissions.exec", "permissions.send_publish",
    "agent.max_turns", "agent.step_timeout", "agent.tool_timeout", "agent.show_steps",
    "models.providers", "models.default", "models.roles.manager",
    "models.roles.researcher", "models.roles.executor", "models.fallback",
    "models.accounting",
    "tools.workspace", "tools.internet", "tools.max_file_bytes",
    "mcp.file", "mcp.autostart",
    "skills.catalog", "skills.paths", "skills.auto_use",
    "memory.facts_budget", "research.sources",
    "attachments.max_bytes", "attachments.max_pages",
    "graph.host", "graph.port", "web.port", "logging.level", "backup.mode",
)

KINDS = ("str", "int", "bool", "path", "secret", "choice", "json")


def test_every_promised_setting_is_declared():
    missing = [key for key in PROMISED_KEYS if key not in config._BY_KEY]
    assert not missing, f"the plan promises settings that do not exist: {missing}"


def test_every_setting_has_a_group_a_description_and_a_type():
    for setting in config.SETTINGS:
        assert setting.group.strip(), f"{setting.key} has no group"
        assert setting.label.strip(), f"{setting.key} has no label"
        assert setting.help.strip().endswith("."), f"{setting.key} has no full sentence"
        assert setting.kind in KINDS, f"{setting.key} has kind {setting.kind!r}"
        assert setting.key == setting.key.strip().lower(), setting.key
        assert setting.env == setting.env.strip().upper(), setting.env
        # Dotted by convention; the pre-package flat names (`workspace`) stay
        # until the modules that read them are retired in W9.
        assert re.fullmatch(r"[a-z0-9_]+(\.[a-z0-9_]+)*", setting.key), setting.key


def test_every_default_is_accepted_by_its_own_type():
    """A declared default the writer refuses would break the settings page."""
    for setting in config.SETTINGS:
        try:
            config._coerce(setting, setting.default)
        except ValueError as exc:      # pragma: no cover - the failure message is the point
            raise AssertionError(f"{setting.key} default {setting.default!r}: {exc}") from None


def test_a_choice_declares_its_options_and_defaults_inside_them():
    for setting in config.SETTINGS:
        if setting.kind != "choice":
            assert not setting.choices, f"{setting.key} lists choices but is {setting.kind}"
            continue
        assert len(setting.choices) >= 2, f"{setting.key} offers {setting.choices}"
        assert len(set(setting.choices)) == len(setting.choices), setting.key
        assert all(option == option.strip().lower() for option in setting.choices)
        assert str(setting.default) in setting.choices, \
            f"{setting.key} defaults to {setting.default!r}, not one of {setting.choices}"


def test_a_structured_setting_declares_something_the_writer_accepts():
    for setting in config.SETTINGS:
        if setting.kind != "json":
            continue
        written = config._validate_json(setting.key, setting.default)
        assert written == setting.default


def test_an_unknown_structured_key_is_not_silently_accepted_as_a_provider():
    with pytest.raises(ValueError):
        config._coerce(config._BY_KEY["models.providers"], '[{"name": "x"}]')
    with pytest.raises(ValueError):
        config._coerce(config._BY_KEY["models.providers"], '[{"name": "x", "long_lived_key": "y"}]')


def test_every_env_name_is_unique_across_the_catalog():
    names: dict[str, str] = {}
    for setting in config.SETTINGS:
        for name in (setting.env, *setting.aliases):
            assert name not in names, f"{name} is claimed by {names.get(name)} and {setting.key}"
            names[name] = setting.key


def test_the_page_description_carries_what_a_form_needs():
    described = {row["key"]: row for row in config.describe()["settings"]}
    assert set(described) == {setting.key for setting in config.SETTINGS}
    for key, row in described.items():
        assert row["group"].strip(), key
        assert row["help"].strip(), key
        assert row["kind"] in KINDS, key
        assert isinstance(row["pending"], bool), key
        assert isinstance(row["choices"], list), key
        if row["kind"] == "choice":
            assert row["choices"], key
            assert str(row["value"]) in row["choices"], key


def test_every_setting_name_read_by_the_code_is_declared():
    """The defect this catches: code reading a key the catalog renamed.

    `agent.max_steps` was renamed to `agent.max_turns` in the catalog while the
    agent still read the old name, and `config.value` answered `None` instead of
    failing — a missing setting has to be a test failure, not a `TypeError` at
    the first turn.
    """
    root = pathlib.Path(__file__).resolve().parents[1]
    pattern = re.compile(r"config\.(?:value|path)\(\s*[\"']([a-z0-9_.]+)[\"']")
    reads: list[str] = []
    undeclared: list[str] = []
    for folder in ("python", "scripts"):
        for path in sorted((root / folder).rglob("*.py")):
            text = path.read_text(encoding="utf-8", errors="replace")
            for name in pattern.findall(text):
                reads.append(name)
                if name not in config._BY_KEY:
                    undeclared.append(f"{path.relative_to(root).as_posix()}: {name}")
    assert len(reads) > 10, f"the scan found only {len(reads)} settings reads"
    assert not undeclared, f"code reads settings that do not exist: {undeclared}"


def test_a_theme_setting_names_themes_the_stylesheet_can_apply():
    """The two halves of a theme choice — the setting and the CSS — must agree."""
    stylesheet = (pathlib.Path(config.__file__).parent / "static" / "console.css").read_text(
        encoding="utf-8")
    declared = re.findall(r'\[data-theme="([a-z0-9-]+)"\]', stylesheet)
    assert set(declared) == set(config._BY_KEY["ui.theme"].choices), declared
    assert config._BY_KEY["ui.theme"].default in declared
