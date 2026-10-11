"""Unit and accessibility contrast tests for localization and the 5 themes."""
from __future__ import annotations

import html as html_module
import json
import re
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from chat_fakes import MemoryLinks, isolate, make_app
from oneiro import config, i18n

STATIC = Path(__file__).resolve().parents[1] / "python" / "oneiro" / "static"
#: The five canonical screens (§ 3) plus the legacy setup route.
SCREENS = ("/", "/tasks", "/tools", "/settings", "/memory", "/setup")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)


def test_catalog_key_parity():
    """100% key parity between Russian and English dictionaries."""
    ru_keys = set(i18n.CATALOG["ru"].keys())
    en_keys = set(i18n.CATALOG["en"].keys())
    missing_in_en = ru_keys - en_keys
    missing_in_ru = en_keys - ru_keys
    assert not missing_in_en, f"Keys missing in EN catalog: {missing_in_en}"
    assert not missing_in_ru, f"Keys missing in RU catalog: {missing_in_ru}"


def test_translation_function_resolution():
    assert i18n.t("nav.chat", "ru") == "Диалог"
    assert i18n.t("nav.chat", "en") == "Chat"
    assert i18n.t("non.existent.key", "ru") == "non.existent.key"


def test_page_renders_with_explicit_language():
    with TestClient(make_app(Path("/tmp"), MemoryLinks())) as client:
        res_ru = client.get("/?lang=ru")
        assert res_ru.status_code == 200
        assert 'lang="ru"' in res_ru.text
        assert "Диалог" in res_ru.text

        res_en = client.get("/?lang=en")
        assert res_en.status_code == 200
        assert 'lang="en"' in res_en.text
        assert "Chat" in res_en.text


# -------------------------------------------------------------
# WCAG 2.2 Level AA Contrast Ratio Validator
# -------------------------------------------------------------


def _srgb_to_lin(c_byte: int) -> float:
    c = c_byte / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _luminance(hex_str: str) -> float:
    hex_clean = hex_str.strip().lstrip("#")
    if len(hex_clean) == 3:
        hex_clean = "".join(c * 2 for c in hex_clean)
    r = int(hex_clean[0:2], 16)
    g = int(hex_clean[2:4], 16)
    b = int(hex_clean[4:6], 16)
    return 0.2126 * _srgb_to_lin(r) + 0.7152 * _srgb_to_lin(g) + 0.0722 * _srgb_to_lin(b)


def _contrast_ratio(hex1: str, hex2: str) -> float:
    l1 = _luminance(hex1)
    l2 = _luminance(hex2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


# -------------------------------------------------------------
# The language claim, measured instead of asserted
# -------------------------------------------------------------

_STRIPPED = re.compile(r"(?is)<(script|style|textarea)\b.*?</\1>")
_TAGS = re.compile(r"(?s)<[^>]+>")
_CYRILLIC = re.compile(r"[\u0400-\u04ff]")


def _visible_lines(markup: str) -> set[str]:
    """The text a person reads, one line per line, markup and data stripped.

    `script`, `style` and `textarea` come out: a JSON block, a stylesheet or a
    provider list in a form field is data both languages must show identically,
    and counting it as a sentence would hide the defect this test exists for.
    """
    text = _STRIPPED.sub(" ", markup)
    text = html_module.unescape(_TAGS.sub("\n", text))
    return {line.strip() for line in text.splitlines() if line.strip()}


def _english_sentences(lines) -> set[str]:
    """Lines that read as English prose: several words, all printable ASCII."""
    return {line for line in lines
            if len(line.split()) >= 4 and re.fullmatch(r"[ -~]+", line)}


def _shared_english_sentences(ru_markup: str, en_markup: str) -> set[str]:
    return _english_sentences(_visible_lines(ru_markup)) & _english_sentences(
        _visible_lines(en_markup))


def test_the_measurement_can_see_a_shared_sentence():
    """A test of the measurement: the rule must not pass by matching nothing.

    An English page compared with itself still shares every sentence it has, so a
    detector that found nothing there would make the screen checks below worthless.
    """
    with TestClient(make_app(Path("/tmp"), MemoryLinks())) as client:
        english = client.get("/settings?lang=en").text
    seen = _english_sentences(_visible_lines(english))
    assert len(seen) > 20, f"the extractor found {len(seen)} English sentences on a page full of them"
    assert _shared_english_sentences(english, english) == seen


@pytest.mark.parametrize("route", SCREENS)
@pytest.mark.parametrize("question", ["", "?lang=ru"])
def test_a_russian_screen_shares_no_english_sentence_with_the_english_one(route, question):
    """§ 6 row 14, measured: RU and EN share no sentence on any screen.

    `question` is empty for the language the settings declare, then `lang=ru` for the
    explicit one, because both routes have to reach the same bilingual screen.
    """
    joiner = "&" if question else "?"
    with TestClient(make_app(Path("/tmp"), MemoryLinks())) as client:
        ru = client.get(f"{route}{question}{joiner}lang=ru").text
        en = client.get(f"{route}{question}{joiner}lang=en").text
    shared = _shared_english_sentences(ru, en)
    assert shared == set(), (
        f"{route} shows the same English sentences in both languages, so the page is "
        f"not translated: {sorted(shared)[:6]}")


def test_every_declared_setting_speaks_the_active_language():
    """All 62 declarations have a label and a help in both catalogs, and they differ."""
    assert config.SETTINGS, "no settings are declared"
    for setting in config.SETTINGS:
        for part in ("label", "help"):
            key = f"setting.{setting.key}.{part}"
            assert key in i18n.CATALOG["ru"], f"{key} has no Russian"
            assert key in i18n.CATALOG["en"], f"{key} has no English"
            assert i18n.t(key, "ru") != i18n.t(key, "en"), \
                f"{key} reads the same in both languages, so the Russian page shows English"
    for group in {setting.group for setting in config.SETTINGS}:
        assert f"group.{group}" in i18n.CATALOG["ru"], f"group {group} has no Russian legend"


def test_the_page_shell_reads_its_sentences_from_the_catalog():
    """The shell's own words - tagline, section heading, footer - are catalog text."""
    with TestClient(make_app(Path("/tmp"), MemoryLinks())) as client:
        for lang in i18n.SUPPORTED_LANGUAGES:
            page = client.get(f"/?lang={lang}").text
            for key in ("app.name", "app.tagline", "heading.prerequisites", "footer.note"):
                assert i18n.t(key, lang) in page, f"{key} is not rendered on the {lang} page"
        assert "Standalone rewrite foundation" not in client.get("/?lang=ru").text


def test_the_client_script_reads_only_keys_the_page_ships():
    """`app.js` holds no sentence: it asks the page's catalog, by key."""
    script = (STATIC / "app.js").read_text(encoding="utf-8")
    used = set(re.findall(r'T\["([^"]+)"\]', script))
    assert used, "no catalog key found in app.js - the extraction is broken, not the script"
    unknown = used - set(i18n.CLIENT_KEYS)
    assert unknown == set(), f"app.js asks for keys the catalog does not declare: {sorted(unknown)}"
    for lang in i18n.SUPPORTED_LANGUAGES:
        with TestClient(make_app(Path("/tmp"), MemoryLinks())) as client:
            page = client.get(f"/?lang={lang}").text
        block = re.search(r'<script id="i18n" type="application/json">(.*?)</script>',
                          page, re.S)
        assert block, f"the {lang} page does not carry the client catalog"
        shipped = json.loads(block.group(1))
        assert used <= set(shipped), \
            f"the {lang} page ships no text for {sorted(used - set(shipped))}"
        assert shipped["status.not_ready"] == i18n.t("status.not_ready", lang), lang
    russian = i18n.client_catalog("ru")
    assert _CYRILLIC.search(russian["status.not_ready"]), \
        "the Russian client catalog is not Russian"
    assert not _CYRILLIC.search(i18n.client_catalog("en")["status.not_ready"])


def test_the_graph_screen_is_translated_apart_from_backend_diagnostics():
    """The legacy graph route: its chrome is catalog text, its reasons are not.

    `/oneiro/` shows the reasons `memory.probe` returned, and one probe branch embeds
    raw library exception prose (`ConnectionAbortedError: ...`) that no catalog can
    translate: a reason is data about a machine, not a sentence about the product.
    Turning them into codes is a separate change, so they are subtracted here — read
    from the probe itself, so this test still fails on a *template* regression — and
    named in `docs/ACCEPTANCE-REPORT.md` instead of being excused silently.
    """
    from oneiro import memory
    with TestClient(make_app(Path("/tmp"), MemoryLinks())) as client:
        ru = client.get("/oneiro/?lang=ru").text
        en = client.get("/oneiro/?lang=en").text
        for key in ("heading.graph", "nav.graph", "graph.heading", "footer.note"):
            assert i18n.t(key, "ru") in ru, f"{key} is not rendered on the Russian graph page"
    facts = memory.probe(str(config.value("graph.host")), int(config.value("graph.port")))
    remaining = _shared_english_sentences(ru, en) - set(facts.blocked)
    assert remaining == set(), (
        f"the graph page shows English beyond the probe's own diagnostics: "
        f"{sorted(remaining)[:6]}")
    assert all(_CYRILLIC.search(reason) is None for reason in facts.blocked), \
        "the probe started translating: fold those reasons back into the measurement"


def test_wcag_aa_contrast_for_all_five_themes():
    """§ 6 Row 16: Verify contrast ratio >= 4.5:1 for body text in every theme."""
    css_path = Path(__file__).resolve().parents[1] / "python" / "oneiro" / "static" / "console.css"
    css_text = css_path.read_text(encoding="utf-8")

    themes = ("night", "paper", "editorial", "cosmic", "agentic")
    for theme in themes:
        match = re.search(rf'\[data-theme="{theme}"\]\s*\{{([^}}]+)\}}', css_text)
        assert match, f"Theme block [data-theme='{theme}'] not found in console.css"
        block = match.group(1)

        bg_match = re.search(r'--oi-bg:\s*(#[0-9a-fA-F]{3,6});', block)
        fg_match = re.search(r'--oi-fg:\s*(#[0-9a-fA-F]{3,6});', block)
        assert bg_match, f"Missing --oi-bg in {theme}"
        assert fg_match, f"Missing --oi-fg in {theme}"

        bg_color = bg_match.group(1)
        fg_color = fg_match.group(1)
        ratio = _contrast_ratio(bg_color, fg_color)
        assert ratio >= 4.5, f"Theme {theme} contrast {ratio:.2f}:1 fails WCAG AA (>= 4.5:1)"
