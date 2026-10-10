"""Every declared setting tells the truth about whether this build acts on it.

The catalog has exactly one honest way to say "declared, but nothing here acts on
it": `pending`, which the settings page renders as *declared here; the part of
Oneiro that acts on it is not in this build yet*. This test keeps both directions
of that sentence true, because a page that says "in force" about a key no module
reads is the kind of lie the plan's stopping criterion forbids:

* an **in-force** setting must reach behaviour — either a product module reads it
  through the config API, or it governs an effect through `tools.EFFECT_SETTINGS`;
* a **pending** setting must not: if it acted, the page would be denying a
  capability that runs.

How a setting counts as read, in `python/oneiro/` and outside the two modules that
are not behaviour (the registry, which declares, and `pages`, which renders every
declared setting, in force or not, because that is what the catalog page is):

* `config.value("key")`, `config.path("key")`, `config.resolve("key")` or
  `config.attr.<key>` — the config API the product reads settings through;
* the setting's declared **environment name**, read directly with
  `os.environ.get(...)` — the one documented exception is `runtime.data_dir`, which
  has to answer before the settings file (inside that directory) can be read, so
  `config.data_root()` reads `ONEIRO_DATA_DIR` itself;
* membership in `tools.EFFECT_SETTINGS`, which hands an effect's decision to a
  permission setting (that is how `permissions.*` reaches behaviour).

A reader that computes the key name at runtime would escape a textual check like this
one, so this is a floor rather than a proof; it covers all 62 declared keys today, and
it is the check that would have caught `permissions.write_outside` and
`memory.facts_budget` while they were in force and unread.

Adding a setting is therefore a two-line decision: either wire it, or mark it
`pending=True` with a reason a person can read.
"""
from __future__ import annotations

import dataclasses
import re
from pathlib import Path

from oneiro import config, tools

PRODUCT = Path(__file__).resolve().parents[1] / "python" / "oneiro"
#: Not behaviour: the catalog itself, and the page that renders every declared
#: setting (a `pending` key is rendered on purpose — showing it with its value and
#: saying it is not in force is the whole point of the label). `config` stays in the
#: scan: a literal key or environment name in it is a real reader, not a generic one.
NOT_BEHAVIOUR = {"settings_registry.py", "pages.py"}


def _sources() -> dict[str, str]:
    return {path.name: path.read_text(encoding="utf-8")
            for path in PRODUCT.rglob("*.py") if path.name not in NOT_BEHAVIOUR}


def _read_through_the_api(key: str, text: str, env: str = "") -> bool:
    attr = key.replace(".", "_")
    patterns = [
        rf'config\.value\(\s*["\']{re.escape(key)}["\']',
        rf'config\.path\(\s*["\']{re.escape(key)}["\']',
        rf'config\.resolve\(\s*["\']{re.escape(key)}["\']',
        rf"config\.attr\.{re.escape(attr)}\b"]
    if env:
        patterns.append(rf'os\.environ(?:\[["\']{re.escape(env)}["\']\]|\.get\(\s*["\']'
                        rf'{re.escape(env)}["\'])')
    return any(re.search(pattern, text) for pattern in patterns)


def _governs_an_effect(key: str) -> bool:
    """Whether the effect table hands this setting the decision over an effect."""
    return key in set(tools.EFFECT_SETTINGS.values())


def readers(key: str, env: str = "") -> list[str]:
    """The product modules that act on this setting, by the accepted routes."""
    found = [name for name, text in _sources().items()
             if _read_through_the_api(key, text, env)]
    if _governs_an_effect(key):
        found.append("tools.py (EFFECT_SETTINGS)")
    return sorted(found)


def _silent() -> list[str]:
    return [setting.key for setting in config.SETTINGS
            if not setting.pending and not readers(setting.key, setting.env)]


def _acting_pending() -> list[str]:
    return [setting.key for setting in config.SETTINGS
            if setting.pending and readers(setting.key, setting.env)]


def test_every_setting_in_force_is_read_by_the_product():
    silent = _silent()
    assert silent == [], (
        "these settings are shown as in force while no module of the product reads "
        f"them: {silent}. Wire each one to the behaviour it promises, or mark it "
        "pending=True (with a reason in its help) so the page stops claiming it acts.")


def test_no_pending_setting_acts_behind_the_page():
    acting = _acting_pending()
    assert acting == [], (
        "these settings say on the page that the part of Oneiro that acts on them is "
        f"not in this build, while the product reads them: {acting}. Either they are "
        "in force and must not be pending, or the reader is wrong.")


def test_the_check_can_see_a_reader_and_a_pending_setting():
    """A test of the test: the routes above recognise real code and real labels.

    Without this, the two rules above would pass just as well if the pattern simply
    stopped matching anything.
    """
    text = _sources()["agent.py"]
    assert _read_through_the_api("agent.max_turns", text)
    assert not _read_through_the_api("models.accounting", text)
    assert readers("permissions.write_workspace") == ["tools.py (EFFECT_SETTINGS)"]
    assert readers("memory.facts_budget") == ["web.py"]
    assert readers("runtime.data_dir", "ONEIRO_DATA_DIR") == ["config.py"]
    # W4 wired the model settings to `models.py`, and left this one declared-only: the two
    # directions have to be visible on the same kinds of key, not only on today's pair.
    assert readers("models.accounting", "ONEIRO_MODEL_ACCOUNTING") == ["models.py"]
    assert readers("skills.auto_use", "ONEIRO_SKILLS_AUTO_USE") == []
    assert _governs_an_effect("permissions.exec") and not _governs_an_effect("mcp.file")


def test_a_setting_added_tomorrow_without_a_reader_fails_the_rule(monkeypatch):
    """The rule is exercised on keys that are not on disk, not only on today's two.

    The audit that produced this file found `permissions.write_outside` and
    `memory.facts_budget` in force with no reader. The point of the rule is the
    *next* such key, so it is shown catching a synthetic one: as declared, it is
    named; the two honest ways out (wire it, or say it is not in force yet with a
    reason) each clear it, and a `pending` key nobody reads stays clear.
    """
    declared = list(config.SETTINGS)
    ghost = config.Setting(key="demo.unwired", env="ONEIRO_DEMO_UNWIRED", default="x",
                           label="Ghost", help="A setting with nothing behind it.",
                           group="Demo")
    monkeypatch.setattr(config, "SETTINGS", [*declared, ghost])
    assert _silent() == ["demo.unwired"]
    assert _acting_pending() == []

    # Marked `pending` with a reason, the same key stops claiming to act — which is
    # the second honest answer, and the one `mcp.source` uses.
    monkeypatch.setattr(config, "SETTINGS",
                        [*declared, dataclasses.replace(ghost, pending=True)])
    assert _silent() == [] and _acting_pending() == []
