"""Finish the Word version of the forum доклад: fields, page count, PDF.

    python scripts/forumit-word.py

`scripts/forumit-build.py` writes the docx but cannot lay text out, so the page
count of the article is only knowable in Word. This script opens the generated
file, updates every field (the footer number among them), repaginates, checks
that the result still fits the forum's 5-10 page limit, and exports a PDF next
to the docx so the layout can be read without Word.

Word must be installed. Nothing outside `docs/forumit-2026/` is touched.
"""

from __future__ import annotations

import sys
from pathlib import Path

import win32com.client as win32

HERE = Path(__file__).resolve().parent.parent
DOCX = HERE / "docs" / "forumit-2026" / "Доклад.docx"
PDF = DOCX.with_suffix(".pdf")

WD_EXPORT_PDF = 17
WD_STAT_PAGES = 2
WD_STAT_WORDS = 0
WD_STAT_CHARS = 3

MIN_PAGES = 5
MAX_PAGES = 10


def start_word():
    """A hidden Word instance that never writes an autosave record."""
    word = win32.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        word.Options.SaveInterval = 0
    except Exception:
        pass
    return word


def quit_word(word) -> None:
    """Close whatever is open and quit, so no lock is left on the docx."""
    try:
        for open_document in word.Documents:
            open_document.Close(0)
    except Exception:
        pass
    word.Quit()


def main() -> int:
    if not DOCX.exists():
        print(f"FAIL: {DOCX} is missing; run scripts/forumit-build.py first", file=sys.stderr)
        return 1

    word = start_word()
    try:
        doc = word.Documents.Open(str(DOCX))
        for field in doc.Fields:
            field.Update()
        doc.Repaginate()
        pages = doc.ComputeStatistics(WD_STAT_PAGES)
        words = doc.ComputeStatistics(WD_STAT_WORDS)
        characters = doc.ComputeStatistics(WD_STAT_CHARS)
        doc.Save()
        doc.ExportAsFixedFormat(str(PDF), WD_EXPORT_PDF)
        doc.Close(0)
    finally:
        quit_word(word)

    print(f"pages: {pages}  words: {words}  characters: {characters}")
    print(f"pdf:   {PDF}")
    if not MIN_PAGES <= pages <= MAX_PAGES:
        print(f"FAIL: the forum accepts {MIN_PAGES}-{MAX_PAGES} pages, this file has {pages}",
              file=sys.stderr)
        return 1
    print(f"limits: fit {MIN_PAGES}-{MAX_PAGES} pages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
