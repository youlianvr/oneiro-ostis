"""The five themes are tokens, and the tokens are checked, not asserted.

A theme that forgets a token renders a broken surface, and a palette that reads
badly is a real defect. Both are measured here from the stylesheet itself, so the
claim "contrast is verified in every theme" has a command behind it.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from oneiro import config

STYLESHEET = pathlib.Path(config.__file__).parent / "static" / "console.css"

#: Every theme must declare all of these, or a surface renders without a colour.
REQUIRED = (
    "bg", "bg-alt", "surface", "surface-2", "fg", "muted", "border",
    "accent", "accent-fg", "accent-soft", "success", "warning", "danger", "focus",
)

#: Text pairs that must reach WCAG 2.2 AA for normal text (4.5:1).
TEXT_PAIRS = (("fg", "bg"), ("fg", "surface"), ("muted", "bg"), ("accent-fg", "accent"))

#: Colours used for meaning (a state, an icon, a border) must reach 3:1.
NON_TEXT_ON_BACKGROUND = ("success", "warning", "danger", "accent")


def _themes() -> dict[str, dict[str, str]]:
    text = STYLESHEET.read_text(encoding="utf-8")
    themes: dict[str, dict[str, str]] = {}
    for name, body in re.findall(r'\[data-theme="([a-z0-9-]+)"\]\s*\{([^}]*)\}', text):
        themes[name] = dict(re.findall(r"--oi-([a-z0-9-]+):\s*([^;]+);", body))
    return themes


def _luminance(colour: str) -> float:
    """WCAG relative luminance of #rrggbb."""
    digits = colour.strip().lstrip("#")
    assert len(digits) == 6, colour
    channels = []
    for index in (0, 2, 4):
        value = int(digits[index:index + 2], 16) / 255
        channels.append(value / 12.92 if value <= 0.04045
                        else ((value + 0.055) / 1.055) ** 2.4)
    red, green, blue = channels
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast(first: str, second: str) -> float:
    light, dark = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def test_the_stylesheet_declares_exactly_the_themes_the_setting_offers():
    assert set(_themes()) == set(config._BY_KEY["ui.theme"].choices)


def test_every_theme_declares_every_token():
    for name, tokens in _themes().items():
        missing = [token for token in REQUIRED if token not in tokens]
        assert not missing, f"{name} is missing {missing}"


def test_every_colour_token_is_a_hex_colour():
    for name, tokens in _themes().items():
        for token, value in tokens.items():
            if token in ("color-scheme",):
                continue
            if token.startswith("font") or token.startswith("text") or token == "leading":
                continue
            assert re.fullmatch(r"#[0-9a-fA-F]{6}", value.strip()), f"{name}: {token}={value}"


@pytest.mark.parametrize("theme", sorted(_themes()))
def test_text_meets_aa_contrast_in_every_theme(theme):
    tokens = _themes()[theme]
    for foreground, background in TEXT_PAIRS:
        ratio = _contrast(tokens[foreground], tokens[background])
        assert ratio >= 4.5, f"{theme}: {foreground} on {background} is {ratio:.2f}:1"


@pytest.mark.parametrize("theme", sorted(_themes()))
def test_semantic_colours_are_visible_against_the_background(theme):
    tokens = _themes()[theme]
    for token in NON_TEXT_ON_BACKGROUND:
        ratio = _contrast(tokens[token], tokens["bg"])
        assert ratio >= 3.0, f"{theme}: {token} on bg is {ratio:.2f}:1"


def test_the_stylesheet_honours_reduced_motion():
    text = STYLESHEET.read_text(encoding="utf-8")
    assert "prefers-reduced-motion: reduce" in text
    assert ":focus-visible" in text, "keyboard focus must be visible"


def test_no_rule_paints_a_literal_colour_outside_the_token_blocks():
    """A colour named below the tokens is a theme that will not switch."""
    text = STYLESHEET.read_text(encoding="utf-8")
    below_tokens = text.split("/* ---- base", 1)[1]
    literals = re.findall(r"#[0-9a-fA-F]{3,6}\b", below_tokens)
    assert not literals, f"colours outside the token blocks: {literals}"
