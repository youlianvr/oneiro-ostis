"""Playwright screenshots of the dream-tree page into docs/shots/.

    python scripts/take_shots.py [html-path]

Defaults to docs/dream-tree.html relative to the project root.
"""
from __future__ import annotations

import os
import sys

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    html_path = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "docs", "dream-tree.html"))
    shots_dir = os.path.join(ROOT, "docs", "shots")
    os.makedirs(shots_dir, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.goto(f"file:///{html_path}")
        page.wait_for_timeout(700)

        page.screenshot(path=os.path.join(shots_dir, "01-hero.png"))

        constellation = page.query_selector("#constellation")
        if constellation:
            constellation.screenshot(path=os.path.join(shots_dir, "02-constellation.png"))

        page.evaluate("document.querySelector('#dreamTable').scrollIntoView({block:'start'})")
        page.wait_for_timeout(300)
        page.screenshot(path=os.path.join(shots_dir, "03-dream-table.png"))

        page.evaluate("document.querySelector('#episodes').scrollIntoView({block:'start'})")
        page.wait_for_timeout(300)
        tabs = page.query_selector_all(".ep-tab")
        if len(tabs) > 1:
            tabs[1].click()
            page.wait_for_timeout(200)
        page.screenshot(path=os.path.join(shots_dir, "04-episodes.png"))

        page.screenshot(path=os.path.join(shots_dir, "05-fullpage.png"), full_page=True)
        browser.close()

    print(f"screenshots written to {shots_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
