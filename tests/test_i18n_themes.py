"""Unit and accessibility contrast tests for localization and the 5 themes."""
from __future__ import annotations

import re
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from chat_fakes import MemoryLinks, isolate, make_app
from oneiro import config, i18n


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
