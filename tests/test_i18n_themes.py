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


def _strings(payload, path: str = "") -> list[tuple[str, str]]:
    """Every string in a JSON payload, with where it came from."""
    found: list[tuple[str, str]] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            found.extend(_strings(value, f"{path}.{key}" if path else str(key)))
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            found.extend(_strings(value, f"{path}[{index}]"))
    elif isinstance(payload, str):
        found.append((path, payload))
    return found


def _reads_as_english_prose(text: str) -> bool:
    """The screens' shape rule, applied to a single value."""
    return bool(len(text.split()) >= 4 and re.fullmatch(r"[ -~]+", text)
                and not _CYRILLIC.search(text))


def _panel(status: dict, lang: str) -> str:
    """The readiness panel as `app.js` builds it, for this payload and language.

    The panel is written in the browser, so no rule over the served markup can see it;
    that asymmetry is how an English instruction lived on Russian screens under two
    green checks. This mirrors `statusLines`/`sayReason`, and
    `test_the_client_script_reads_only_keys_the_page_ships` asserts that the script
    still renders reasons through `sayReason`, so the mirror cannot drift unnoticed.
    """
    lines = [i18n.t("status.ready" if status.get("ready") else "status.not_ready", lang)]
    if status.get("phase"):
        lines.append(i18n.t("status.phase", lang, phase=str(status["phase"])))
    memory = status.get("memory") or {}
    lines.append(i18n.t("status.memory_ok" if memory.get("verified") else
                        "status.memory_readback" if memory.get("tcp_reachable") else
                        "status.memory_unreachable", lang))
    model = status.get("model") or {}
    if model.get("verified"):
        lines.append(i18n.t("status.model_ok_tools" if model.get("used_tools")
                            else "status.model_ok", lang))
    elif model.get("reason_code"):
        lines.append(i18n.reason(model["reason_code"], lang))
    else:
        lines.append(i18n.t("status.model_unverified", lang))
    blocked = status.get("blocked") or []
    if blocked:
        lines.append(i18n.t("status.blocked_title", lang))
        lines.extend(f"  - {i18n.reason(item, lang)}" for item in blocked)
    return "\n".join(lines)


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
    # The panel renders reason *codes* it is handed at runtime, which a literal scan of
    # the script cannot see. Every code a backend can report must therefore be shipped
    # to the client by name, or the panel would print a bare code on a finished screen.
    missing = set(i18n.REASON_KEYS) - set(i18n.CLIENT_KEYS)
    assert missing == set(), f"the client cannot render these reason codes: {sorted(missing)}"
    for lang in i18n.SUPPORTED_LANGUAGES:
        shipped = i18n.client_catalog(lang)
        assert set(i18n.REASON_KEYS) <= set(shipped), \
            f"the {lang} client catalog ships no text for {sorted(set(i18n.REASON_KEYS) - set(shipped))}"
        assert all(shipped[code] != code for code in i18n.REASON_KEYS), \
            f"a reason code has no {lang} sentence and would print as itself"
    assert "sayReason(model.reason_code)" in script and "sayReason(item)" in script, \
        "app.js no longer renders reasons through the catalog; the panel test above is stale"


def test_the_graph_screen_names_its_reasons_as_codes_the_catalog_translates():
    """The legacy graph route: its chrome and its reasons are both catalog text.

    `/oneiro/` renders what `memory.probe` reported. It used to render the probe's own
    English sentences and the test excused them by subtracting exactly the strings the
    probe returned — a subtraction that cannot fail on a *translation* regression, only
    on the probe's wording changing. The probe now reports codes with their data, so
    nothing is subtracted: an English line on the Russian graph page is a failure.
    """
    from oneiro import memory
    with TestClient(make_app(Path("/tmp"), MemoryLinks())) as client:
        ru = client.get("/oneiro/?lang=ru").text
        en = client.get("/oneiro/?lang=en").text
        for key in ("heading.graph", "nav.graph", "graph.heading", "footer.note"):
            assert i18n.t(key, "ru") in ru, f"{key} is not rendered on the Russian graph page"
    assert _shared_english_sentences(ru, en) == set(), (
        f"the graph page shows the same English sentences in both languages: "
        f"{sorted(_shared_english_sentences(ru, en))[:6]}")
    assert _english_sentences(_visible_lines(ru)) == set(), (
        f"the Russian graph page shows English prose: "
        f"{sorted(_english_sentences(_visible_lines(ru)))[:4]}")
    facts = memory.probe(str(config.value("graph.host")), int(config.value("graph.port")))
    assert facts.blocked, "an unreachable graph must still say why"
    for item in facts.blocked:
        code, data = i18n.reason_data(item)
        assert code and code != item, (
            f"the probe reported a sentence instead of a code, so no page can translate "
            f"it: {item!r}")
        for lang in i18n.SUPPORTED_LANGUAGES:
            said = i18n.reason(item, lang)
            assert said != code, f"{code} has no {lang} text"
        if code == "blocked.probe_failed":
            # The exception's own prose is data: it is carried through verbatim inside
            # the catalog's sentence, which is the only part a translator can write.
            assert data.get("exception"), "a failed probe must carry the exception it saw"
            assert str(data["exception"]) in i18n.reason(item, "ru")


def test_the_readiness_panel_says_nothing_a_backend_composed():
    """§ 6 row 14, the part two green checks could not see.

    The panel is filled by the browser from `/api/status`, so the served-markup rule
    reads a placeholder there, and the live DOM rule removed `#status` before
    comparing. Measured 2026-10-11, that left four English lines on every Russian
    screen: `run `oneiro verify-model` to check the configured model with a real call`
    and three blocked reasons. The payload now carries codes with their data, and this
    test fails the moment a sentence comes back.
    """
    with TestClient(make_app(Path("/tmp"), MemoryLinks())) as client:
        status = client.get("/api/status").json()

    for where, value in _strings(status):
        assert not _reads_as_english_prose(value), (
            f"/api/status.{where} is an English sentence, so the panel can only print it "
            f"in one language: {value!r}")

    blocked = status.get("blocked") or []
    assert blocked, "nothing is blocked in this environment, so the panel test measures nothing"
    for item in blocked:
        assert isinstance(item, dict) and item.get("code"), (
            f"a reason reached the panel as a bare sentence: {item!r}")
        for lang in i18n.SUPPORTED_LANGUAGES:
            assert i18n.reason(item, lang) != item["code"], \
                f"{item['code']} has no {lang} text, so the panel would print the code"

    ru = _panel(status, "ru")
    assert _english_sentences(ru.splitlines()) == set(), (
        f"the Russian panel shows English prose: "
        f"{sorted(_english_sentences(ru.splitlines()))[:3]}")
    en = _panel(status, "en")
    shared = _english_sentences(ru.splitlines()) & _english_sentences(en.splitlines())
    assert shared == set(), (
        f"the panel says the same English sentence in both languages: {sorted(shared)[:3]}")
    assert _CYRILLIC.search(ru) and not _CYRILLIC.search(en), \
        "the two panels are not in the two languages"


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
