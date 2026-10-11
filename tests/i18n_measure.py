"""The language measurement the acceptance report quotes, as one command.

    python tests/i18n_measure.py

It uses the same rule and the same extractor as `tests/test_i18n_themes.py`, so the
numbers in `docs/ACCEPTANCE-REPORT.md` § 2 are the output of this script rather than of
a rule that lived in a shell history. The rule, stated so a reviewer can disagree with
it precisely:

* a **visible line** is a line of the document after `<script>`, `<style>` and
  `<textarea>` content is removed, tags become newlines and entities are unescaped —
  the set of *distinct* such lines, because a repeated row is one sentence;
* **English prose** is a visible line of four or more whitespace-separated words, every
  character printable ASCII and no Cyrillic anywhere in it. That rule counts a line
  like `How tightly lists and cards are packed: comfortable, or compact to fit more on
  screen.` as prose, which a rule that excused anything containing a colon would miss —
  measured 2026-10-11, 24 of the 80 English lines on `/settings` contain a colon or a
  slash;
* a line is **Latin-only** when it holds no Cyrillic character. A settings form has to
  show paths, enum values and JSON it is editing, so Latin-only is not prose.

Exits non-zero if a Russian screen shows English prose or if the two languages share a
sentence, so it is a check and not only a printer.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(TESTS.parent / "python"))

import re  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from chat_fakes import MemoryLinks, make_app  # noqa: E402
from test_i18n_themes import (  # noqa: E402
    _CYRILLIC, _english_sentences, _shared_english_sentences, _visible_lines)

SCREENS = ("/", "/tasks", "/tools", "/settings", "/memory", "/setup")
LANGUAGES = ("ru", "en")


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="oneiro-i18n-measure-"))
    os.environ["ONEIRO_SETTINGS_FILE"] = str(work / "settings.json")
    os.environ["ONEIRO_DATA_DIR"] = str(work / "data")
    os.environ["ONEIRO_MCP_FILE"] = str(work / "mcp.json")
    failures: list[str] = []

    with TestClient(make_app(work, MemoryLinks())) as client:
        pages = {lang: {} for lang in LANGUAGES}
        for lang in LANGUAGES:
            for route in SCREENS:
                pages[lang][route] = client.get(f"{route}?lang={lang}").text

    print(f"{'screen':<12}{'lang':<5}{'lines':>7}{'cyrillic':>10}{'latin':>7}{'prose':>7}")
    for route in SCREENS:
        for lang in LANGUAGES:
            lines = _visible_lines(pages[lang][route])
            latin = {line for line in lines if not _CYRILLIC.search(line)}
            prose = _english_sentences(lines)
            print(f"{route:<12}{lang:<5}{len(lines):>7}"
                  f"{len(lines) - len(latin):>10}{len(latin):>7}{len(prose):>7}")
            if lang == "ru" and prose:
                failures.append(f"{route} shows English prose on the Russian page: "
                                f"{sorted(prose)[:3]}")
        shared = _shared_english_sentences(pages["ru"][route], pages["en"][route])
        print(f"{route:<12}shared English sentences between ru and en: {len(shared)}")
        if shared:
            failures.append(f"{route} shares English sentences across languages: "
                            f"{sorted(shared)[:3]}")

    print("\nThe Latin-only lines on the Russian /settings page, so a reader can judge them:")
    for line in sorted({l for l in _visible_lines(pages["ru"]["/settings"])
                        if not _CYRILLIC.search(l)}):
        print(f"  {line}")

    if failures:
        print("\nFAILED: " + "; ".join(failures))
        return 1
    print("\nOK: no Russian screen shows English prose and no sentence is shared.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
