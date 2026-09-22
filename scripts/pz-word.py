"""Finish the Word version of the research work: fields, page numbers, PDF.

    python scripts/pz-word.py`scripts/pz-build.py` writes the docx but cannot lay text out, so two things
are only knowable in Word:

* the table of contents has real page numbers only after the field is updated;
* the number printed on the first body page depends on how many pages the front
  matter (title page, contents, annotation) occupies, and none of those carry a
  number.

This script opens the generated file, updates every field, finds the page where
the body starts, writes that number as the section's first page number, saves,
and exports a PDF next to the docx so the layout can be checked without Word.

Word must be installed. Nothing outside `docs/pz/` is touched.
"""

from __future__ import annotations

import sys
from pathlib import Path

import win32com.client as win32
from docx import Document
from docx.oxml.ns import qn

HERE = Path(__file__).resolve().parent.parent
DOCX = HERE / "docs" / "pz" / "Пояснительная записка.docx"
PDF = DOCX.with_suffix(".pdf")

WD_GO_TO_PAGE = 1
WD_GO_TO_ABSOLUTE = 1
WD_EXPORT_PDF = 17
WD_STAT_PAGES = 2
WD_STAT_WORDS = 0

FIRST_BODY_HEADING = "Введение"


def set_first_page_number(path: Path, start_at: int) -> None:
    """Set `w:pgNumType/@w:start` on the last section, which is the body.

    Word's own object model is used to lay the document out and to fill the
    table of contents; this one number is written into the XML directly,
    between two Word sessions, because Word's PageNumbers object is not
    reachable through late binding on this machine.
    """
    document = Document(str(path))
    sect_pr = document.sections[-1]._sectPr
    for existing in sect_pr.findall(qn("w:pgNumType")):
        sect_pr.remove(existing)
    pg_num = sect_pr.makeelement(qn("w:pgNumType"), {})
    pg_num.set(qn("w:start"), str(start_at))
    sect_pr.append(pg_num)
    document.save(str(path))


def quit_word(word) -> None:
    """Close whatever is open and quit.

    A Word instance left behind holds a lock on the docx and the next build
    fails with a permission error, so cleanup is not optional.
    """
    try:
        for open_document in word.Documents:
            open_document.Close(0)
    except Exception:
        pass
    word.Quit()


def page_start(doc, page: int) -> int:
    return doc.GoTo(What=WD_GO_TO_PAGE, Which=WD_GO_TO_ABSOLUTE, Count=page).Start


def body_page(doc, pages: int) -> int | None:
    """First page whose text begins with the body's first heading."""
    for page in range(2, pages + 1):
        start = page_start(doc, page)
        end = page_start(doc, page + 1) if page < pages else doc.Content.End
        chunk = doc.Range(start, end).Text.strip()
        if chunk.startswith(FIRST_BODY_HEADING):
            return page
    return None


def main() -> int:
    if not DOCX.exists():
        print(f"FAIL: {DOCX} is missing; run scripts/pz-build.py first", file=sys.stderr)
        return 1

    word = win32.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        doc = word.Documents.Open(str(DOCX))
        for field in doc.Fields:
            field.Update()
        doc.Repaginate()

        pages = doc.ComputeStatistics(WD_STAT_PAGES)
        words = doc.ComputeStatistics(WD_STAT_WORDS)
        start = body_page(doc, pages)
        if start is None:
            doc.Close(0)
            print("FAIL: could not find where the body starts", file=sys.stderr)
            return 1

        doc.Save()
        doc.Close(0)
    finally:
        quit_word(word)

    # the body carries continuous numbering and the pages before it carry none,
    # so its first printed number is its physical position in the document
    set_first_page_number(DOCX, start)

    word = win32.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        doc = word.Documents.Open(str(DOCX))
        doc.Repaginate()
        doc.Save()
        doc.ExportAsFixedFormat(str(PDF), WD_EXPORT_PDF)
        doc.Close(0)
    finally:
        quit_word(word)

    print(f"body starts on page {start}, so the first printed number is {start}")
    print(f"pages: {pages}  words: {words}")
    print(f"pdf:   {PDF}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
