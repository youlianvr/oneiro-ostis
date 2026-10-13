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
  `config.data_root()` reads `ONEIRO_DATA_DIR` itself. Only a **read** counts: a
  module that *sets* `os.environ["ONEIRO_DATA_DIR"]` for a child process is not a
  module that acts on the setting, and counting the write would have made a
  measurement harness a reader of a key it only passes on;
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
import sys
from pathlib import Path

from oneiro import config, tools

PRODUCT = Path(__file__).resolve().parents[1] / "python" / "oneiro"
#: Not behaviour: the catalog itself, and the page that renders every declared
#: setting (a `pending` key is rendered on purpose — showing it with its value and
#: saying it is not in force is the whole point of the label). `config` stays in the
#: scan: a literal key or environment name in it is a real reader, not a generic one.
NOT_BEHAVIOUR = {"settings_registry.py", "pages.py"}


def _sources() -> dict[str, str]:
    """Every behaviour module, named by its **path** under the package.

    Named by path, not by file name: `python/oneiro/` is a package with sub-packages
    (`oneiro/dream/`), and keying this by `path.name` once let `dream/cli.py` stand in
    for `cli.py`, which silently dropped every setting the product's own command line
    reads and reported them as unread. A name a person reading the failure can act on
    is part of the check working.
    """
    return {path.relative_to(PRODUCT).as_posix(): path.read_text(encoding="utf-8")
            for path in PRODUCT.rglob("*.py") if path.name not in NOT_BEHAVIOUR}


def _read_through_the_api(key: str, text: str, env: str = "") -> bool:
    attr = key.replace(".", "_")
    patterns = [
        rf'config\.value\(\s*["\']{re.escape(key)}["\']',
        rf'config\.path\(\s*["\']{re.escape(key)}["\']',
        rf'config\.resolve\(\s*["\']{re.escape(key)}["\']',
        rf"config\.attr\.{re.escape(attr)}\b"]
    if env:
        # A read, never a write: `os.environ["X"] = ...` hands a value to a child, and a
        # module that only passes a name on does not act on the setting that owns it.
        patterns.append(rf'os\.environ(?:\[["\']{re.escape(env)}["\']\](?!\s*[=])'
                        rf'|\.get\(\s*["\']{re.escape(env)}["\'])')
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


def test_two_modules_with_one_file_name_do_not_hide_each_other(monkeypatch, tmp_path: Path):
    """The scan names files by path, so a sub-package cannot stand in for its parent.

    Falsified, not assumed: a real tree where `pkg/a.py` reads a key and `pkg/sub/a.py`
    does not. Keyed by file name — which is how this check was written first — the second
    file silently replaced the first, and a setting in force was reported as unread. The
    failure was found on `python/oneiro/cli.py` against `python/oneiro/dream/cli.py`.
    """
    package = tmp_path / "pkg"
    (package / "sub").mkdir(parents=True)
    (package / "a.py").write_text('x = config.value("demo.one")\n', encoding="utf-8")
    (package / "sub" / "a.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "PRODUCT", package)

    sources = _sources()
    assert sorted(sources) == ["a.py", "sub/a.py"], "both modules are read, under two names"
    assert "a.py" in readers("demo.one")


def test_only_reading_an_environment_name_counts(monkeypatch, tmp_path: Path):
    """A module that sets the variable for a child has not acted on the setting.

    `os.environ["ONEIRO_DATA_DIR"] = ...` is how a harness hands a root to a process it
    starts; counting it as a reader would report the setting as wired to a module that
    only passes the name on. Falsified on real file text, both ways round.
    """
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "sets.py").write_text('os.environ["ONEIRO_DEMO"] = "x"\n', encoding="utf-8")
    (package / "reads.py").write_text('os.environ.get("ONEIRO_DEMO")\n', encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "PRODUCT", package)

    assert readers("demo.two", "ONEIRO_DEMO") == ["reads.py"]
