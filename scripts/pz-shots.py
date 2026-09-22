"""Screenshots of the live dashboard for the explanatory note (ПЗ).

The figures in `docs/pz/` must be re-shootable: the dashboard changes, and a
picture in a document that nobody can reproduce is a claim, not evidence.

    python scripts/pz-shots.py            # dashboard must be running on 8130

Every selector below names a real section of `dashboard/index.html` by its
heading, so renaming a section fails loudly instead of silently shooting the
wrong card.
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

DASHBOARD = "http://127.0.0.1:8130/"
OUT = Path(__file__).resolve().parent.parent / "docs" / "pz"

# (file name, heading, the card whose body carries the data, what it shows)
SECTIONS = [
    ("fig-02-organization.png", "Организация: рой агентов", "swarmBody",
     "research, decision and work packets of the swarm"),
    ("fig-03-memory.png", "Память: LongMemEval", "memoryBench",
     "the memory comparison and its honest status"),
    ("fig-04-proofs.png", "Что здесь доказывается", "claimsBody",
     "what the run actually proved"),
    ("fig-05-world.png", "Рост счёта в мире", "ascent",
     "the online score across rounds"),
]

# Loading is slow where the page asks the graph (the swarm feed takes about
# thirty seconds), so wait on the content itself rather than on a timer.
LOADING = "загрузка"
EMPTY = "записей пока нет"


def wait_ready(page, body_id: str, timeout_ms: int = 150_000) -> None:
    page.wait_for_function(
        """([id, loading, empty]) => {
            const el = document.getElementById(id);
            if (!el) return false;
            const t = el.innerText || '';
            return t.length > 0 && !t.includes(loading) && !t.includes(empty);
        }""",
        arg=[body_id, LOADING, EMPTY],
        timeout=timeout_ms,
    )


def grab(page, heading: str, body_id: str, target: Path) -> str:
    """Screenshot the card that carries `heading`; return a short status line."""
    wait_ready(page, body_id)
    card = page.query_selector(
        f"xpath=//h2[contains(normalize-space(.), '{heading}')]"
        "/ancestor::div[contains(@class,'card')][1]"
    )
    if card is None:
        raise RuntimeError(f"no card for heading: {heading}")
    card.screenshot(path=str(target))
    box = card.bounding_box() or {}
    height = int(box.get("height", 0))
    if height < 200:
        raise RuntimeError(f"{target.name} looks empty: {height}px tall")
    return f"{target.name}: {int(box.get('width', 0))}x{height}"


OVERVIEW = ("header", "#pipeline", ".deck", "#stats")


def overview(page, target: Path) -> str:
    """The control and summary band, not the whole page.

    A full-page shot of this dashboard is 3000x7528, which on A4 at 16 cm wide
    is 40 cm tall: it does not fit a page and cannot be read once scaled down.
    The band that carries the state, the stages, the buttons and the numbers
    keeps a readable shape.
    """
    # the numbers arrive last, after the page has asked the graph for them
    page.wait_for_function(
        """() => {
            const el = document.getElementById('stats');
            const box = el ? el.getBoundingClientRect() : null;
            return !!box && box.height > 20 && (el.innerText || '').trim().length > 0;
        }""",
        timeout=150_000,
    )
    boxes = []
    for selector in OVERVIEW:
        element = page.query_selector(selector)
        if element is None:
            raise RuntimeError(f"dashboard lost {selector}")
        box = element.bounding_box()
        if not box or box["height"] < 20:
            raise RuntimeError(f"{selector} has no size")
        boxes.append(box)
    left = min(box["x"] for box in boxes)
    top = min(box["y"] for box in boxes)
    right = max(box["x"] + box["width"] for box in boxes)
    bottom = max(box["y"] + box["height"] for box in boxes)
    page.screenshot(path=str(target), clip={
        "x": left, "y": top, "width": right - left, "height": bottom - top})
    return f"{target.name}: {int(right - left)}x{int(bottom - top)}"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 1100},
                                device_scale_factor=2)
        page.on("console", lambda m: errors.append(m.text)
                if m.type == "error" else None)
        page.goto(DASHBOARD, wait_until="load", timeout=60_000)
        page.wait_for_timeout(6000)  # the page fills its cards from /api/*
        print(overview(page, OUT / "fig-01-dashboard.png"))
        for name, heading, body_id, _why in SECTIONS:
            print(grab(page, heading, body_id, OUT / name))
        browser.close()

    if errors:
        print("console errors:")
        for line in errors[:10]:
            print("  " + line.strip()[:200])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
