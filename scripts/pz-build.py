"""Build the Word version of the research work from its markdown source.

    python scripts/pz-build.py

The markdown file in `docs/pz/` is the source; this script is the only writer of
`docs/pz/Пояснительная записка.docx`. Formatting follows the competition's
form: A4 portrait, Times New Roman 14, single line spacing, margins left 20 mm,
right 12,5 mm, top and bottom 20 mm, 10 mm first-line indent, justified body,
headings left, a table of contents right after the title page, page numbers
bottom centre and absent from the front matter, appendices after the sources
list. The title page follows the form accepted in the region (the related work
beside this project): the words ПОЯСНИТЕЛЬНАЯ ЗАПИСКА above the theme, then the
author, the institution, the supervisor, and the region with the year.

Two rules the script enforces instead of trusting the writer:

* no em dash anywhere in the document text (the workspace bans it);
* every ТИТУЛЬНЫЙ ЛИСТ placeholder is present, so a filled title page cannot
  silently lose the author's name.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Mm, Pt, RGBColor

HERE = Path(__file__).resolve().parent.parent
SOURCE = HERE / "docs" / "pz" / "Пояснительная записка.md"
TARGET = HERE / "docs" / "pz" / "Пояснительная записка.docx"

FONT = "Times New Roman"
BODY_SIZE = Pt(14)
TABLE_SIZE = Pt(12)
# Margins of the form the region accepts: 20 mm left, right 12,5 mm,
# 20 mm top and bottom. The text block is therefore 177,5 mm wide.
LEFT_MARGIN = Mm(20)
RIGHT_MARGIN = Mm(12.5)
VERTICAL_MARGIN = Mm(20)
FIGURE_WIDTH = Cm(16)
# Height a figure may take: an A4 page holds 257 mm of text, and the caption
# needs a line of its own, so nothing may be taller than this.
FIGURE_MAX_HEIGHT = Cm(19)
# Text width of an A4 page with these margins (210 - 20 - 12,5 = 177,5 mm, the
# same width the body text uses), minus the table indent above, so the frame of
# a table ends on the right margin.
TABLE_WIDTH_TWIPS = 9955

PLACEHOLDER_KEYS = ("АВТОР:", "РУКОВОДИТЕЛЬ:", "УЧРЕЖДЕНИЕ:", "МЕСТО:")

TOC_INSTRUCTION = 'TOC \\o "1-3" \\h \\z \\u'
# How many front-matter pages stand before the body: the title page and the
# table of contents. Word measures the real value in `scripts/pz-word.py`;
# this is the build-time guess.
FRONT_MATTER_PAGES = 2
TOC_NOTE = "Содержание собирается при обновлении полей: выделить и нажать F9."


# --------------------------------------------------------------------------- #
# document skeleton
# --------------------------------------------------------------------------- #

def base_document() -> Document:
    doc = Document()
    section = doc.sections[0]
    section.page_width = Mm(210)
    section.page_height = Mm(297)
    section.top_margin = VERTICAL_MARGIN
    section.bottom_margin = VERTICAL_MARGIN
    section.left_margin = LEFT_MARGIN
    section.right_margin = RIGHT_MARGIN

    normal = doc.styles["Normal"]
    normal.font.name = FONT
    normal.font.size = BODY_SIZE
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    fmt = normal.paragraph_format
    fmt.line_spacing = 1.0
    fmt.space_before = Pt(0)
    fmt.space_after = Pt(0)
    fmt.first_line_indent = Mm(10)
    fmt.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    for name in ("Heading 1", "Heading 2"):
        style = doc.styles[name]
        style.font.name = FONT
        style.font.size = BODY_SIZE
        style.font.bold = True
        style.font.color.rgb = RGBColor(0, 0, 0)
        pf = style.paragraph_format
        pf.first_line_indent = Mm(0)
        pf.alignment = WD_ALIGN_PARAGRAPH.LEFT
        pf.space_before = Pt(12)
        pf.space_after = Pt(6)
        pf.keep_with_next = True
        pf.line_spacing = 1.0
    return doc


def page_number_footer(section, start_at: int) -> None:
    """PAGE field at the bottom centre of the page, counting from `start_at`."""
    footer = section.footer
    footer.is_linked_to_previous = False
    paragraph = footer.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.first_line_indent = Mm(0)
    # The formulary centres the number on the sheet, and the text column is not
    # centred: it spans 30 mm to 200 mm, so its middle sits 10 mm right of the
    # sheet's. The indent below moves the footer's own column back by exactly
    # that offset, which puts the number on the middle of the page.
    paragraph.paragraph_format.left_indent = -int(LEFT_MARGIN - RIGHT_MARGIN)
    run = paragraph.add_run()
    for element, attrs, text in (
        ("w:fldChar", {"w:fldCharType": "begin"}, None),
        ("w:instrText", {"xml:space": "preserve"}, " PAGE "),
        ("w:fldChar", {"w:fldCharType": "end"}, None),
    ):
        node = OxmlElement(element)
        for key, value in attrs.items():
            node.set(qn(key), value)
        if text is not None:
            node.text = text
        run._r.append(node)
    run.font.name = FONT
    run.font.size = BODY_SIZE

    sect_pr = section._sectPr
    pg_num = OxmlElement("w:pgNumType")
    pg_num.set(qn("w:start"), str(start_at))
    sect_pr.append(pg_num)


def toc_field(paragraph) -> None:
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = TOC_INSTRUCTION
    sep = OxmlElement("w:fldChar")
    sep.set(qn("w:fldCharType"), "separate")
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(begin)
    run._r.append(instr)
    run._r.append(sep)
    note = OxmlElement("w:t")
    note.text = TOC_NOTE
    run._r.append(note)
    run._r.append(end)
    run.font.name = FONT
    run.font.size = BODY_SIZE
    run.font.italic = True
    run.font.color.rgb = RGBColor(0x60, 0x60, 0x60)


# --------------------------------------------------------------------------- #
# inline and block rendering
# --------------------------------------------------------------------------- #

INLINE = re.compile(r"(\*\*.+?\*\*|`[^`]+`)")


def plain(paragraph, text: str) -> None:
    """Add `text` to `paragraph`, honouring **bold** and `code` spans."""
    for chunk in INLINE.split(text):
        if not chunk:
            continue
        if chunk.startswith("**") and chunk.endswith("**"):
            run = paragraph.add_run(chunk[2:-2])
            run.bold = True
        elif chunk.startswith("`") and chunk.endswith("`"):
            run = paragraph.add_run(chunk[1:-1])
            run.font.name = "Consolas"
            run.font.size = Pt(12)
        else:
            paragraph.add_run(chunk)
        paragraph.runs[-1].font.name = paragraph.runs[-1].font.name or FONT


def body_paragraph(doc, text: str):
    paragraph = doc.add_paragraph()
    plain(paragraph, text)
    return paragraph


def heading(doc, text: str, level: int):
    paragraph = doc.add_heading(level=level)
    plain(paragraph, text)
    return paragraph


def align_table(table) -> None:
    """Keep a table inside the same 20 mm margins as the text.

    Word lays a plain table out 0.19 cm to the left of the text margin (its
    default cell margin), so the frame of the table sticks into the margin.
    The indent below cancels exactly that offset, and a small inner cell margin
    keeps the text off the frame. Both numbers were measured on the rendered
    pages, not guessed.
    """
    tbl_pr = table._tbl.tblPr
    for existing in tbl_pr.findall(qn("w:tblInd")):
        tbl_pr.remove(existing)
    indent = OxmlElement("w:tblInd")
    indent.set(qn("w:w"), "108")
    indent.set(qn("w:type"), "dxa")
    marker = tbl_pr.find(qn("w:tblLook"))
    if marker is not None:
        marker.addprevious(indent)
    else:
        tbl_pr.append(indent)

    for existing in tbl_pr.findall(qn("w:tblCellMar")):
        tbl_pr.remove(existing)
    cell_margin = OxmlElement("w:tblCellMar")
    for side in ("left", "right"):
        node = OxmlElement(f"w:{side}")
        node.set(qn("w:w"), "56")
        node.set(qn("w:type"), "dxa")
        cell_margin.append(node)
    tbl_pr.append(cell_margin)

    for existing in tbl_pr.findall(qn("w:tblW")):
        tbl_pr.remove(existing)
    width = OxmlElement("w:tblW")
    width.set(qn("w:w"), str(TABLE_WIDTH_TWIPS))
    width.set(qn("w:type"), "dxa")
    tbl_pr.append(width)


def add_table(doc, rows: list[list[str]]) -> None:
    table = doc.add_table(rows=len(rows), cols=len(rows[0]))
    table.style = "Table Grid"
    table.autofit = True
    align_table(table)
    for r, cells in enumerate(rows):
        for c, value in enumerate(cells):
            cell = table.cell(r, c)
            paragraph = cell.paragraphs[0]
            paragraph.paragraph_format.first_line_indent = Mm(0)
            paragraph.paragraph_format.line_spacing = 1.0
            paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
            plain(paragraph, value)
            for run in paragraph.runs:
                run.font.size = TABLE_SIZE
                run.font.name = FONT
                if r == 0:
                    run.bold = True
    doc.add_paragraph()


def figure_width(path: Path) -> Cm:
    """Width for a figure, capped so its height still fits on one page.

    A tall screenshot scaled to the page width would overflow by itself, and a
    figure that cannot be placed is a figure nobody reads.
    """
    try:
        from PIL import Image
    except ImportError:  # Pillow is only needed for the height cap
        return FIGURE_WIDTH
    with Image.open(path) as image:
        ratio = image.height / image.width
    if ratio <= 0:
        return FIGURE_WIDTH
    limit = Cm(19)
    allowed = Cm(limit.cm / ratio)
    return allowed if allowed < FIGURE_WIDTH else FIGURE_WIDTH


def add_figure(doc, path: Path, caption: str) -> None:
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.first_line_indent = Mm(0)
    # the caption must never land on the page after its picture
    paragraph.paragraph_format.keep_with_next = True
    paragraph.add_run().add_picture(str(path), width=figure_width(path))


def is_table_row(line: str) -> bool:
    return line.startswith("|") and line.endswith("|")


def split_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip("|").split("|")]


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

def read_source() -> tuple[dict[str, str], list[str]]:
    """Title page fields and the body lines, comments removed."""
    text = SOURCE.read_text(encoding="utf-8")
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    lines = [line.rstrip() for line in text.splitlines()]
    lines = [line for line in lines]

    title = ""
    fields: dict[str, str] = {}
    body_start = 0
    for index, line in enumerate(lines):
        if line.startswith("# ") and not title:
            title = line[2:].strip()
            continue
        if any(line.startswith(key) for key in PLACEHOLDER_KEYS):
            key, _, value = line.partition(":")
            fields[key.strip() + ":"] = value.strip()
            continue
        if line.startswith("## ") and title:
            body_start = index
            break
    return {"title": title, **fields}, lines[body_start:]


def build() -> int:
    title_page, body = read_source()
    missing = [key for key in PLACEHOLDER_KEYS if key not in title_page]
    if missing:
        print(f"FAIL: title page is missing {missing}", file=sys.stderr)
        return 1

    doc = base_document()

    # ---- title page (section 1, no page number) -------------------------- #
    # The form is the one accepted in the region (the related work that sits
    # next to this project): both headings above the theme, then the author,
    # the institution, the supervisor, and the region with the year.
    def centered(text: str, *, bold: bool = False) -> None:
        paragraph = doc.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.first_line_indent = Mm(0)
        plain(paragraph, text)
        if bold:
            for piece in paragraph.runs:
                piece.bold = True

    def blank() -> None:
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.first_line_indent = Mm(0)

    centered("ПОЯСНИТЕЛЬНАЯ ЗАПИСКА", bold=True)
    centered("к исследовательской работе")
    blank()
    centered(f"«{title_page['title']}»")

    for _ in range(3):
        blank()

    centered(f"Автор: {title_page['АВТОР:']}")
    centered(title_page["УЧРЕЖДЕНИЕ:"])
    centered(f"Научный руководитель: {title_page['РУКОВОДИТЕЛЬ:']}")

    for _ in range(3):
        blank()

    centered(title_page["МЕСТО:"])

    # ---- table of contents (still section 1) ----------------------------- #
    doc.add_page_break()
    label = doc.add_paragraph()
    label.alignment = WD_ALIGN_PARAGRAPH.CENTER
    label.paragraph_format.first_line_indent = Mm(0)
    run = label.add_run("Оглавление")
    run.bold = True
    run.font.name = FONT
    run.font.size = BODY_SIZE
    toc_paragraph = doc.add_paragraph()
    toc_paragraph.paragraph_format.first_line_indent = Mm(0)
    toc_field(toc_paragraph)

    # ---- body (section 2) ------------------------------------------------ #
    # The regional form has no annotation page: the related work of the same
    # region goes straight from the contents to the introduction.
    # The front matter carries no page number. The first body page is therefore
    # numbered after it; `scripts/pz-word.py` measures the real number once
    # Word has laid the table of contents out.
    section = doc.add_section(WD_SECTION.NEW_PAGE)
    page_number_footer(section, start_at=FRONT_MATTER_PAGES + 1)

    figures = 0
    tables = 0
    index = 0
    while index < len(body):
        line = body[index]

        if not line.strip():
            index += 1
            continue

        image = re.match(r"!\[(.*?)\]\((.*?)\)", line)
        if image:
            path = SOURCE.parent / image.group(2)
            if not path.exists():
                print(f"FAIL: missing figure {path}", file=sys.stderr)
                return 1
            add_figure(doc, path, image.group(1))
            figures += 1
            index += 1
            continue

        if is_table_row(line) and index + 1 < len(body) and set(body[index + 1]) <= set("|-: "):
            rows: list[list[str]] = []
            cursor = index
            while cursor < len(body) and is_table_row(body[cursor]):
                if not set(body[cursor]) <= set("|-: "):
                    rows.append(split_row(body[cursor]))
                cursor += 1
            width = max(len(row) for row in rows)
            rows = [row + [""] * (width - len(row)) for row in rows]
            add_table(doc, rows)
            tables += 1
            index = cursor
            continue

        if line.startswith("### "):
            heading(doc, line[4:].strip(), 2)
            index += 1
            continue

        if line.startswith("## "):
            title = line[3:].strip()
            # Appendices are required to start on their own sheet with the
            # heading in the top right corner.
            if title.startswith("Приложение"):
                doc.add_page_break()
                paragraph = heading(doc, title, 1)
                paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            else:
                heading(doc, title, 1)
            index += 1
            continue

        if re.match(r"^\d+\.\s", line):
            body_paragraph(doc, line.strip())
            index += 1
            continue

        if line.startswith("- "):
            paragraph = body_paragraph(doc, "• " + line[2:].strip())
            paragraph.paragraph_format.first_line_indent = Mm(0)
            paragraph.paragraph_format.left_indent = Mm(10)
            index += 1
            continue

        body_paragraph(doc, line.strip())
        index += 1

    # ---- the two gates --------------------------------------------------- #
    problems: list[str] = []
    for paragraph in doc.paragraphs:
        if "\u2014" in paragraph.text:
            problems.append(f"em dash in: {paragraph.text[:60]}")
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                if "\u2014" in cell.text:
                    problems.append(f"em dash in table: {cell.text[:40]}")
    if problems:
        for problem in problems:
            print("FAIL:", problem, file=sys.stderr)
        return 1

    doc.save(TARGET)
    print(f"saved: {TARGET}")
    print(f"paragraphs: {len(doc.paragraphs)}  tables: {tables}  figures: {figures}")
    print(f"title page: {title_page['АВТОР:']} / {title_page['УЧРЕЖДЕНИЕ:']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(build())
