#!/usr/bin/env python
"""Build the 14 October talk's deck: one PPTX, its PDF, its page images, its index.

    python scripts/forumit-slides.py            # writes docs/forumit-2026/slides/

Why `python-pptx` and not a JavaScript deck library: this project already builds its
office artefacts with the `python-*` packages (`scripts/forumit-build.py` writes the
talk's docx with `python-docx`), and a Node toolchain would be a second one for a
single file. `python-pptx` writes the chart natively and its output opens in
PowerPoint, LibreOffice and the renderer this script checks with.

The deck is the one `docs/TALK-RU-2026-10-13.md` Appendix A lists, slide by slide:
title → roles → memory (kinds, provenance, the value an edit replaced, the metric,
the panel) → autonomy (text, then the journal) → proactivity → self-improvement
(the refusal, then the rejected candidate) → what is next → the code. The school and
the adviser appear on the title slide only (answer 5); every other slide carries the
claim the room is asked to check, and the **speaker notes** of each slide name the
answers and the evidence file it rests on.

The conversion is LibreOffice inside the `oneiro-office` image, which is the office
suite this project already ships and uses. The host's own fonts are mounted read-only
into that container so the preview renders Calibri and Cambria with their real
metrics; without them LibreOffice substitutes DejaVu and every fit measured here
would be a measurement of the wrong font. PDF pages are then rendered with PyMuPDF,
so each page can be looked at as a page.

Nothing the owner owns is written: the deck, the PDF, the page images and the index
all land under `docs/forumit-2026/slides/`, and the temporary conversion directory is
removed at the end.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.oxml.ns import qn
from pptx.enum.chart import XL_CHART_TYPE, XL_DATA_LABEL_POSITION
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
SLIDES = PROJECT / "docs" / "forumit-2026" / "slides"
IMG = SLIDES / "img"
PAGES = SLIDES / "pages"
PPTX = SLIDES / "oneiro-doklad-2026-10-14.pptx"
PDF = SLIDES / "oneiro-doklad-2026-10-14.pdf"

#: The office image this project already runs, and the host font directory mounted into
#: it for the preview: LibreOffice's own substitute for Calibri is DejaVu Sans, which is
#: wider, so a fit measured on the substitute would be a measurement of another font.
OFFICE_IMAGE = "oneiro-office:local"
HOST_FONTS = "C:/Windows/Fonts"
#: 16:9 in inches, and the page size the PDF must come back as (13.333 x 7.5 in, 72 dpi).
SLIDE_W, SLIDE_H = 13.333, 7.5
PAGE_POINTS = (SLIDE_W * 72, SLIDE_H * 72)
MARGIN = 0.6
BODY_W = SLIDE_W - 2 * MARGIN
#: A frame (image) smaller than this is a broken render, not a picture.
MIN_FRAME_PIXELS = 200 * 100

INK = RGBColor.from_string("0E2438")          # the dark slides: title and closing
BLOCK = RGBColor.from_string("16324B")        # a card on a dark slide
PAPER = RGBColor.from_string("FFFFFF")
TINT = RGBColor.from_string("EDF3F8")         # a card on a light slide
TINT_2 = RGBColor.from_string("DFE9F1")
TEAL = RGBColor.from_string("0F7C86")         # the graph, the sources, the calm claims
TEAL_LIGHT = RGBColor.from_string("5FD0CB")
CORAL = RGBColor.from_string("C2405A")        # the refused change
BODY = RGBColor.from_string("1D2A38")
MUTED = RGBColor.from_string("5A6B7B")
MUTED_LIGHT = RGBColor.from_string("AFC3D4")
WHITE = RGBColor.from_string("FFFFFF")
HEAD_FONT = "Cambria"
BODY_FONT = "Calibri"

#: Every slide, in the order Appendix A of the talk lists them. `carries` is what the
#: content check reads back out of the built file, `evidence` is what the claim rests on
#: and goes into the speaker notes, `answers` are the answers of `opros-100.md`.
SLIDE_PLAN: list[dict] = [
    {"key": "01-title", "title": "Титул",
     "caption": "Тема, автор, руководитель и школа — только на этом слайде.",
     "answers": "5, 6", "evidence": "docs/forumit-2026/Письмо-в-оргкомитет.md",
     "carries": ("Oneiro-OSTIS", "Ступчик Юлиан Владиславович", "Ковалевская",
                 "Дубненская средняя школа")},
    {"key": "02-roles", "title": "Схема ролей",
     "caption": "Три части системы и роли с их правами: право на отправку есть у исполнителя, у менеджера его нет.",
     "answers": "37, 38, 49, 51, 54, 99",
     "evidence": "python/oneiro/tools.py (ROLE_EFFECTS), python/oneiro/tasks.py (ROLES), "
                 "python/oneiro/records.py (Approval.covers)",
     "carries": ("Менеджер", "Исследователь", "Исполнитель", "одобрение")},
    {"key": "03-memory-kinds", "title": "Память: виды записей и происхождение",
     "caption": "Записи разных видов, и у каждой — источник, дата создания и дата изменения.",
     "answers": "19, 21, 31, 35",
     "evidence": "python/oneiro/records.py (Provenance), python/oneiro/agent.py (remember → MODEL_CLAIM)",
     "carries": ("курируемый факт", "Происхождение", "утверждение модели", "дата создания")},
    {"key": "04-memory-previous", "title": "Правка не стирает прежнее значение",
     "caption": "Прежняя редакция того же факта остаётся со своей датой и своим источником; вся ли история прочитана, панель говорит.",
     "answers": "27, 28",
     "evidence": "python/oneiro/recall.py (history_complete), tests/live_memory_check.py — 22 шага, код 0",
     "carries": ("Прежнее значение", "источник", "датой")},
    {"key": "05-memory-metric", "title": "Что даёт память: два числа замера",
     "caption": "С памятью 0,73, без памяти 0,06 на пятидесяти вопросах; слабое место названо.",
     "answers": "22, 24, 25, 30",
     "evidence": "~/.openclaw/bench-memory/runs/s-50-2-report.md (сохранённый прогон: 50 вопросов, "
                 "судья вынес вердикт 49 клеткам графа и 50 — без памяти); bench/memory/run.py",
     "carries": ("0,73", "0,06", "ограничение")},
    {"key": "06-memory-panel", "title": "Раздел памяти в панели",
     "caption": "Кадр панели: три факта владельца, источник, даты, прежнее значение.",
     "answers": "32",
     "evidence": "docs/forumit-2026/slides/img/ru-memory-facts.png (снят tests/live_slide_shots.py "
                 "на отдельном корне данных и отдельном графе)",
     "carries": ("Курируемая память", "источник", "Прежнее значение")},  # noqa: E501
    {"key": "07-autonomy", "title": "Автономность: границы записаны в коде",
     "caption": "Текстом, без схемы: пакеты не вливаются сами, одобрение привязано к точному вызову, изоляция контейнерная.",
     "answers": "38, 45, 47, 48, 51, 54",
     "evidence": "python/oneiro/tools.py (arguments_digest), python/oneiro/records.py (Approval), "
                 "python/oneiro/web.py (/api/settings), python/oneiro/office_env.py, docker-compose.yml",
     "carries": ("не вливаются сами", "точным аргументам", "свои данные", "контейнерная")},  # noqa: E501
    {"key": "08-journal", "title": "Журнал организации",
     "caption": "Кадр панели: две задачи с ролями и состояниями и постоянное расписание с cron.",
     "answers": "43",
     "evidence": "docs/forumit-2026/slides/img/ru-tasks-journal.png (снят tests/live_slide_shots.py); "
                 "python/oneiro/tasks.py, python/oneiro/schedule.py",
     "carries": ("Экран задач панели", "cron", "переживает перезапуск")},
    {"key": "09-proactivity", "title": "Проактивность: расписание и тишина",
     "caption": "Расписание, тихие часы 22:00-09:00, один утренний разбор и одно повторное напоминание — на одном тике.",
     "answers": "57, 58, 63, 65, 66, 67, 71, 73, 75",
     "evidence": "python/oneiro/proactive.py, python/oneiro/schedule.py (tick), "
                 "tests/live_proactive_check.py — 23 шага, код 0 (лог _tmp/recheck-20261013/live-proactive.log); "
                 "docs/forumit-2026/slides/img/ru-initiative.png",
     "carries": ("Тихие часы", "22:00-09:00", "второго таймера нет")},
    {"key": "10-refusal", "title": "Самоулучшение: механизм отказа",
     "caption": "Три правила: повтор только по наблюдаемому решению, три повтора на задачу, шлюз с отдельным применением и откатом.",
     "answers": "80, 83, 86, 88, 93",
     "evidence": "docs/harness.md (Judge calibration), harness/policy.py (VARIANTS), "
                 "python/oneiro/dream/gate.py, python/oneiro/dream/measure.py",
     "carries": ("наблюдалось", "Три повтора", "откат", "утверждает изменение человек")},  # noqa: E501
    {"key": "11-rejected", "title": "Отклонённый кандидат: одно число",
     "caption": "4589,8 против 4583,0 — на 0,15 % дороже, разница не вышла за шум, изменение отклонено.",
     "answers": "78",
     "evidence": "docs/O8-2026-10-12.md, строки 119-130 и 241; payload _tmp/o8-live6-payload.json",
     "carries": ("4589,8", "4583,0", "отклонён")},
    {"key": "12-next", "title": "Что дальше",
     "caption": "Поиск по смыслу, изоляция уровня отдельной машины, больше повторов в замерах.",
     "answers": "13, 91, 94",
     "evidence": "docs/TALK-RU-2026-10-13.md, раздел 9; docs/ACCEPTANCE-REPORT.md (границы)",
     "carries": ("по смыслу", "отдельной машины", "повторов")},
    {"key": "13-code", "title": "Ссылка на исходный код",
     "caption": "Ссылка на репозиторий в последнем слайде и то, что в нём лежит.",
     "answers": "14, 96, 100",
     "evidence": "репозиторий открыт (проверено 2026-10-13: api.github.com/repos/youlianvr/oneiro-ostis → HTTP 200)",
     "carries": ("github.com/youlianvr/oneiro-ostis", "Спасибо")},
]


def say(text: str = "") -> None:
    print(text, flush=True)


# --------------------------------------------------------------------------------------
# Primitives: the whole deck is written with these few shapes.
# --------------------------------------------------------------------------------------
def blank(prs: Presentation, *, dark: bool = False):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    if dark:
        # Full bleed and square: a rounded full-page plate leaves the page's own white
        # showing in the corners, which reads as a slide that failed to fill.
        plate(slide, 0, 0, SLIDE_W, SLIDE_H, fill=INK, radius=None)
    return slide


def flatten(shape):
    """Drop the template's shape style: the deck draws its own fill, line and no shadow.

    `shadow.inherit = False` writes an empty effect list, which PowerPoint reads as "no
    shadow" but LibreOffice falls back from to the theme's own effect reference — and a
    theme shadow around a full-bleed plate paints a light rim on every dark slide. The
    style element is what carries that reference, and nothing in it is used here.
    """
    style = shape._element.find(qn("p:style"))
    if style is not None:
        shape._element.remove(style)
    shape.shadow.inherit = False
    return shape


def plate(slide, x, y, w, h, *, fill=TINT, radius: float | None = 0.06,
          line=None, line_pt: float = 0.75):
    """A card: a rounded rectangle with no default shadow and no accent stripe."""
    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE
    shape = slide.shapes.add_shape(shape_type, Inches(x), Inches(y), Inches(w), Inches(h))
    if radius:
        shape.adjustments[0] = radius
    if fill is None:
        shape.fill.background()
    else:
        shape.fill.solid()
        shape.fill.fore_color.rgb = fill
    if line is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = line
        shape.line.width = Pt(line_pt)
    flatten(shape)
    shape.text_frame.word_wrap = True
    return shape


def line(slide, x1, y1, x2, y2, *, color=TEAL, width_pt: float = 1.25):
    connector = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1),
                                           Inches(x2), Inches(y2))
    connector.line.color.rgb = color
    connector.line.width = Pt(width_pt)
    return connector


def dot(slide, cx, cy, d, *, fill=TEAL, line_color=None):
    shape = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(cx - d / 2), Inches(cy - d / 2),
                                   Inches(d), Inches(d))
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    if line_color is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = line_color
        shape.line.width = Pt(1.0)
    return flatten(shape)


def motif(slide, x, y, *, color=TEAL, node=0.13, gap=0.42):
    """The one recurring mark: three linked nodes, the smallest picture of a graph."""
    centers = [(x, y + 0.34), (x + gap, y), (x + 2 * gap, y + 0.34)]
    for index, (cx, cy) in enumerate(centers):
        for other in centers[index + 1:]:
            line(slide, cx, cy, other[0], other[1], color=color, width_pt=1.0)
    for cx, cy in centers:
        dot(slide, cx, cy, node, fill=color)


def write(tf, blocks, *, anchor=MSO_ANCHOR.TOP, align=PP_ALIGN.LEFT, pad: bool = False):
    """Fill a text frame from a list of paragraph descriptions.

    A card's text is inset from its border; text that has to line up with a shape or
    with another text frame gets no inset at all, which is why this is a choice and not
    a default.
    """
    tf.vertical_anchor = anchor
    if pad:
        tf.margin_left = tf.margin_right = Inches(0.2)
        tf.margin_top = Inches(0.14)
        tf.margin_bottom = Inches(0.14)
    else:
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.word_wrap = True
    for index, block in enumerate(blocks):
        paragraph = tf.paragraphs[0] if index == 0 else tf.add_paragraph()
        paragraph.alignment = block.get("align", align)
        if block.get("space_after") is not None:
            paragraph.space_after = Pt(block["space_after"])
        if block.get("space_before") is not None:
            paragraph.space_before = Pt(block["space_before"])
        if block.get("line_spacing"):
            paragraph.line_spacing = block["line_spacing"]
        if block.get("bullet"):
            paragraph.text = f"•  {block['text']}"
            runs = paragraph.runs
            run = runs[0] if runs else paragraph.add_run()
            run.text = paragraph.text
        else:
            run = paragraph.add_run()
            run.text = block["text"]
        run.font.size = Pt(block.get("size", 14))
        run.font.bold = bool(block.get("bold"))
        run.font.italic = bool(block.get("italic"))
        run.font.name = block.get("font", BODY_FONT)
        run.font.color.rgb = block.get("color", BODY)
    return tf


def text_block(slide, x, y, w, h, blocks, *, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    return write(box.text_frame, blocks, anchor=anchor, align=align)


def title_block(slide, text: str, *, dark: bool = False, y: float = 0.45, size: float = 29):
    text_block(slide, MARGIN, y, BODY_W - 1.6, 0.8,
               [{"text": text, "size": size, "bold": True, "font": HEAD_FONT,
                 "color": WHITE if dark else INK, "line_spacing": 1.0}])
    motif(slide, SLIDE_W - MARGIN - 0.9, y + 0.06,
          color=TEAL_LIGHT if dark else TEAL)


def footer(slide, source: str, number: int, *, dark: bool = False):
    color = MUTED_LIGHT if dark else MUTED
    text_block(slide, MARGIN, SLIDE_H - 0.52, BODY_W - 1.0, 0.3,
               [{"text": source, "size": 9.5, "color": color}])
    text_block(slide, SLIDE_W - MARGIN - 0.8, SLIDE_H - 0.52, 0.8, 0.3,
               [{"text": str(number), "size": 9.5, "color": color, "align": PP_ALIGN.RIGHT}])


def image(slide, path: Path, x, y, w, h, *, caption: str = ""):
    """Place a frame inside the box, keeping its own aspect ratio, and caption it."""
    with Image.open(path) as frame:
        width_px, height_px = frame.size
    scale = min(w / width_px, h / height_px)
    drawn_w, drawn_h = width_px * scale, height_px * scale
    left = x + (w - drawn_w) / 2
    top = y + (h - drawn_h) / 2
    picture = slide.shapes.add_picture(str(path), Inches(left), Inches(top),
                                      Inches(drawn_w), Inches(drawn_h))
    picture.line.color.rgb = TINT_2
    picture.line.width = Pt(1.0)
    if caption:
        text_block(slide, x, top + drawn_h + 0.12, w, 0.5,
                   [{"text": caption, "size": 10.5, "color": MUTED, "line_spacing": 1.15}])
    return drawn_w, drawn_h


def notes(slide, plan: dict) -> None:
    """The slide's own claim record: what it rests on, and which answers asked for it."""
    slide.notes_slide.notes_text_frame.text = (
        f"{plan['title']}.\n"
        f"Кадр: {plan['caption']}\n"
        f"Ответы опроса: {plan['answers']}\n"
        f"Доказательство: {plan['evidence']}\n"
        "Ничего, чего нет в этом файле, на слайде не утверждается. "
        "Формулировки из приложения C речи на слайдах не используются."
    )


# --------------------------------------------------------------------------------------
# The slides.
# --------------------------------------------------------------------------------------
def slide_title(prs, plan) -> None:
    slide = blank(prs, dark=True)
    motif(slide, MARGIN + 0.2, 0.55, color=TEAL_LIGHT, node=0.16, gap=0.5)
    text_block(slide, MARGIN + 0.2, 1.28, 7.2, 0.4,
               [{"text": "Форум, секция информатики · 14 октября 2026", "size": 12.5,
                 "color": TEAL_LIGHT}])
    text_block(slide, MARGIN + 0.2, 1.78, 7.5, 2.3,
               [{"text": "Oneiro-OSTIS: автономный агент с памятью в графе знаний",
                 "size": 37, "bold": True, "font": HEAD_FONT, "color": WHITE,
                 "line_spacing": 1.02}])
    text_block(slide, MARGIN + 0.2, 3.86, 7.0, 0.9,
               [{"text": "Работа строится вокруг вопроса: какое наблюдение подтверждает "
                         "каждое действие?", "size": 15, "color": MUTED_LIGHT,
                 "line_spacing": 1.2}])
    card = plate(slide, MARGIN + 0.2, 4.86, 7.5, 1.45, fill=BLOCK, radius=0.06)
    write(card.text_frame, [
        {"text": "Ступчик Юлиан Владиславович, учащийся 10 класса", "size": 13, "bold": True,
         "color": WHITE, "space_after": 5},
        {"text": "Государственное учреждение образования «Дубненская средняя школа "
                 "имени Андрея Степановича Данилова», Гродненская область",
         "size": 11, "color": MUTED_LIGHT, "space_after": 5, "line_spacing": 1.15},
        {"text": "Научный руководитель: Ковалевская Ольга Вячеславовна, учитель информатики",
         "size": 11, "color": MUTED_LIGHT},
    ], pad=True)
    # The graph itself, drawn rather than described: five records on one page.
    nodes = [("задача", 9.35, 2.05), ("черновик", 11.75, 1.72), ("одобрение", 9.6, 3.35),
             ("запись", 11.95, 3.05), ("опыт", 10.75, 4.6)]
    edges = [(0, 2), (0, 1), (1, 3), (2, 3), (2, 4), (3, 4)]
    for source, target in edges:
        line(slide, nodes[source][1] + 0.0, nodes[source][2], nodes[target][1], nodes[target][2],
             color=TEAL, width_pt=1.1)
    for label, cx, cy in nodes:
        dot(slide, cx, cy, 0.22, fill=TEAL_LIGHT)
        text_block(slide, cx - 0.7, cy + 0.16, 1.4, 0.3,
                   [{"text": label, "size": 10.5, "color": MUTED_LIGHT,
                     "align": PP_ALIGN.CENTER}])
    text_block(slide, MARGIN + 0.2, 6.5, 6.0, 0.3,
               [{"text": "Гродненская область, 2026", "size": 11, "color": MUTED_LIGHT}])
    notes(slide, plan)


def slide_roles(prs, plan) -> None:
    slide = blank(prs)
    title_block(slide, "Как устроена работа и роли")
    card = plate(slide, MARGIN, 1.42, 4.5, 3.33, fill=TINT)
    write(card.text_frame, [
        {"text": "Три части системы", "size": 16, "bold": True, "font": HEAD_FONT,
         "color": INK, "space_after": 20},
        {"text": "Модель предлагает текст и вызовы инструментов", "size": 13.5,
         "space_after": 20, "line_spacing": 1.15},
        {"text": "Исполнитель проверяет право на вызов", "size": 13.5, "space_after": 20,
         "line_spacing": 1.15},
        {"text": "Память удерживает записи и связи", "size": 13.5, "space_after": 20,
         "line_spacing": 1.15},
        {"text": "Внешние инструменты подключаются по MCP: сервер объявляет инструмент "
                 "и схему аргументов", "size": 12, "color": MUTED, "line_spacing": 1.15},
    ], anchor=MSO_ANCHOR.TOP, pad=True)
    cards = [
        ("Менеджер", "ведёт разговор и ставит задачу", "права на отправку нет"),
        ("Исследователь", "ищет и читает", "права на отправку нет"),
        ("Исполнитель", "выполняет и получает право на отправку", "роль записана в задаче"),
        ("Права различаются", "каждая роль видит только свои инструменты",
         "граница объявлена в коде"),
    ]
    for index, (name, what, extra) in enumerate(cards):
        column, row = index % 2, index // 2
        x = 5.42 + column * 3.72
        y = 1.42 + row * 1.78
        box = plate(slide, x, y, 3.5, 1.55, fill=PAPER, line=TINT_2)
        write(box.text_frame, [
            {"text": name, "size": 14.5, "bold": True, "font": HEAD_FONT, "color": INK,
             "space_after": 4},
            {"text": what, "size": 12, "line_spacing": 1.12, "space_after": 3},
            {"text": extra, "size": 10.5, "color": TEAL, "line_spacing": 1.12},
        ], pad=True)
    band = plate(slide, MARGIN, 5.08, BODY_W, 1.28, fill=TINT_2)
    write(band.text_frame, [
        {"text": "Пакет изменений не вливается сам: одобрение привязано к точному вызову "
                 "с точными аргументами.", "size": 14, "bold": True, "color": INK,
         "space_after": 5},
        {"text": "Изменился адресат или текст — человек решает заново. Роль записана в самой "
                 "задаче, поэтому видно, кто её выполнял.", "size": 12.5, "color": MUTED,
         "line_spacing": 1.15},
    ], pad=True)
    footer(slide, "python/oneiro/tools.py (ROLE_EFFECTS) · python/oneiro/records.py "
                  "(Approval.covers) · python/oneiro/tasks.py (ROLES)", 2)
    notes(slide, plan)


def slide_memory_kinds(prs, plan) -> None:
    slide = blank(prs)
    title_block(slide, "Память: типизированные записи и происхождение")
    text_block(slide, MARGIN, 1.4, 6.3, 0.35,
               [{"text": "Виды записей", "size": 16, "bold": True, "font": HEAD_FONT,
                 "color": INK}])
    kinds = ("сообщение", "задача", "действие", "одобрение", "наблюдение", "опыт",
             "заметка", "курируемый факт")
    for index, kind in enumerate(kinds):
        column, row = index % 4, index // 4
        box = plate(slide, MARGIN + column * 1.58, 1.85 + row * 0.66, 1.46, 0.5,
                    fill=TINT, radius=0.18)
        write(box.text_frame, [{"text": kind, "size": 10.5, "color": BODY,
                                "align": PP_ALIGN.CENTER}],
              anchor=MSO_ANCHOR.MIDDLE, align=PP_ALIGN.CENTER)
    text_block(slide, MARGIN, 3.35, 6.3, 1.4,
               [{"text": "Больше всего мне важны решения и ошибки: по ним видно, как система "
                         "работала и где ошибалась.", "size": 13.5, "space_after": 10,
                 "line_spacing": 1.18},
                {"text": "Запись — не строка журнала переписки: у неё есть вид, источник и "
                         "связи с другими записями.", "size": 12.5, "color": MUTED,
                 "line_spacing": 1.18}])
    text_block(slide, 7.2, 1.4, 5.53, 0.35,
               [{"text": "Происхождение записи", "size": 16, "bold": True, "font": HEAD_FONT,
                 "color": INK}])
    sources = (("сказал владелец", "указание владельца: это утверждение человека"),
               ("заявила модель", "утверждение модели, а не проверенное доказательство"),
               ("наблюдал инструмент", "наблюдение: то, что видел вызов"),
               ("проверил результат вызова", "проверенный результат, а не обещание"))
    for index, (name, what) in enumerate(sources):
        box = plate(slide, 7.2, 1.85 + index * 0.78, 5.53, 0.68, fill=PAPER, line=TINT_2)
        write(box.text_frame, [
            {"text": name, "size": 12.5, "bold": True, "color": INK, "space_after": 2},
            {"text": what, "size": 10.5, "color": MUTED},
        ], pad=True)
    links = plate(slide, MARGIN, 4.95, 6.3, 1.28, fill=TINT_2)
    write(links.text_frame, [
        {"text": "Связи", "size": 13.5, "bold": True, "font": HEAD_FONT, "color": INK,
         "space_after": 5},
        {"text": "Задача связана с запуском, запуск — с действием, одобрение — с точным "
                 "вызовом. По этим связям видно, откуда взялась запись и что за ней "
                 "последовало.", "size": 11.5, "color": BODY, "line_spacing": 1.18},
    ], pad=True)
    band = plate(slide, 7.2, 4.95, 5.53, 1.28, fill=TINT_2)
    write(band.text_frame, [
        {"text": "У каждой записи есть дата создания и дата изменения.", "size": 12.5,
         "color": BODY, "space_after": 8, "line_spacing": 1.15},
        {"text": "По источнику видно, можно ли опираться на запись.", "size": 12.5,
         "color": BODY, "line_spacing": 1.15},
    ], pad=True)
    footer(slide, "python/oneiro/records.py (Provenance) · python/oneiro/agent.py "
                  "(remember → MODEL_CLAIM)", 3)
    notes(slide, plan)


def slide_memory_previous(prs, plan) -> None:
    slide = blank(prs)
    title_block(slide, "Правка не стирает прежнее значение")
    current = plate(slide, MARGIN, 1.45, 6.4, 1.15, fill=PAPER, line=TINT_2)
    write(current.text_frame, [
        {"text": "Владелец пишет по-русски и по-английски", "size": 14.5, "bold": True,
         "color": INK, "space_after": 5},
        {"text": "источник: указание владельца · записан: 2026-10-13 01:29 · "
                 "изменён: 2026-10-13 01:29", "size": 10.5, "color": MUTED},
    ], pad=True)
    text_block(slide, MARGIN + 2.9, 2.72, 0.8, 0.3,
               [{"text": "правка", "size": 11, "color": TEAL, "align": PP_ALIGN.CENTER}])
    line(slide, MARGIN + 3.2, 2.78, MARGIN + 3.2, 3.34, color=TEAL, width_pt=1.25)
    earlier = plate(slide, MARGIN, 3.42, 6.4, 1.4, fill=TINT)
    write(earlier.text_frame, [
        {"text": "Прежнее значение — остаётся в записи с датой и источником",
         "size": 11.5, "color": MUTED, "space_after": 8},
        {"text": "Владелец пишет по-русски", "size": 14, "bold": True, "color": INK,
         "space_after": 5},
        {"text": "источник: указание владельца · изменён: 2026-10-13 01:29",
         "size": 10.5, "color": MUTED},
    ], pad=True)
    text_block(slide, 7.4, 1.45, 5.33, 3.6,
               [{"text": "Что делает система", "size": 16, "bold": True, "font": HEAD_FONT,
                 "color": INK, "space_after": 12},
                {"text": "Старая редакция того же факта остаётся рядом — со своей датой и "
                         "своим источником.", "size": 13.5, "space_after": 12,
                 "line_spacing": 1.18},
                {"text": "Панель называет, прочитана ли история записей целиком: оборванное "
                         "чтение не выглядит полным.", "size": 13.5, "space_after": 12,
                 "line_spacing": 1.18},
                {"text": "Помечается прежняя редакция того же факта. Суждения о "
                         "совместимости двух разных записей нет: обосновать его система "
                         "не может, и видимость пометки была бы хуже её отсутствия.",
                 "size": 12, "color": MUTED, "line_spacing": 1.18}])
    band = plate(slide, MARGIN, 5.05, BODY_W, 1.3, fill=TINT_2)
    write(band.text_frame, [
        {"text": "Как это проверено: живая проверка записывает факт, правит его и читает "
                 "раздел обратно — 22 шага, код 0.", "size": 12.5, "bold": True,
         "color": INK, "space_after": 6, "line_spacing": 1.15},
        {"text": "Предел курируемой памяти — 2000 символов, и он проверяется до записи: "
                 "если сохранённое не удаётся прочитать целиком, запись отказывается.",
         "size": 11.5, "color": MUTED, "line_spacing": 1.15},
    ], pad=True)
    footer(slide, "python/oneiro/recall.py (history_complete) · tests/live_memory_check.py — "
                  "22 шага, код 0", 4)
    notes(slide, plan)


def slide_memory_metric(prs, plan) -> None:
    slide = blank(prs)
    title_block(slide, "Что даёт память: два числа сохранённого замера")
    for index, (value, label, detail) in enumerate((
            ("0,73", "верных ответов с памятью", "память в типизированном графе"),
            ("0,06", "верных ответов без памяти", "тот же вопрос, память отключена"))):
        x = MARGIN + index * 6.13
        box = plate(slide, x, 1.45, 5.9, 2.15, fill=TINT)
        write(box.text_frame, [
            {"text": value, "size": 52, "bold": True, "font": HEAD_FONT, "color": TEAL,
             "space_after": 4},
            {"text": label, "size": 14.5, "bold": True, "color": INK, "space_after": 4},
            {"text": detail, "size": 12, "color": MUTED},
        ], pad=True)
    text_block(slide, MARGIN, 3.75, BODY_W, 0.4,
               [{"text": "LongMemEval, 50 вопросов, сохранённый прогон; верных ответов — "
                         "доля клеток, которым судья вынес вердикт.", "size": 11.5,
                 "color": MUTED, "line_spacing": 1.15}])
    left = plate(slide, MARGIN, 4.35, 5.9, 1.8, fill=PAPER, line=TINT_2)
    write(left.text_frame, [
        {"text": "Слабое место — вопросы про время", "size": 13.5, "bold": True,
         "color": INK, "space_after": 5},
        {"text": "Они даются хуже остальных. Это ограничение, а не победа.",
         "size": 12, "color": MUTED, "line_spacing": 1.15},
    ], pad=True)
    right = plate(slide, MARGIN + 6.13, 4.35, 5.9, 1.8, fill=PAPER, line=TINT_2)
    write(right.text_frame, [
        {"text": "Поиск по памяти — по словам и связям", "size": 13.5, "bold": True,
         "color": INK, "space_after": 5},
        {"text": "Поиск «по смыслу» — цель, а не сделанное.",
         "size": 12, "color": MUTED, "line_spacing": 1.15},
    ], pad=True)
    footer(slide, "~/.openclaw/bench-memory/runs/s-50-2-report.md (сохранённый прогон) · "
                  "bench/memory/run.py", 5)
    notes(slide, plan)


def slide_memory_panel(prs, plan) -> None:
    slide = blank(prs)
    title_block(slide, "Раздел памяти в панели")
    # Two figures of the same section: the whole section for its shape, and one record
    # large enough to be read from the room — a 1200 px section shrunk into a column
    # renders its 11 pt text at 5 pt, which is a picture of text, not text.
    image(slide, IMG / "ru-memory-facts.png", MARGIN, 1.3, 4.6, 2.55,
          caption="Раздел «Курируемая память» целиком: три факта владельца.")
    image(slide, IMG / "ru-memory-card.png", 5.5, 1.3, 6.85, 1.85,
          caption="Одна запись крупно: источник, даты и прежнее значение правки.")
    bullets = ("Строка «источник»: это утверждение владельца, а не наблюдение инструмента.",
               "Даты «записан» и «изменён»: когда запись появилась и менялась ли после.",
               "Блок «Прежнее значение»: то, что правка заменила, со своим источником.",
               "Счётчик символов: у курируемой памяти объявлен предел 2000.")
    for index, text in enumerate(bullets):
        column, row = index % 2, index // 2
        x = MARGIN + column * 6.13
        y = 4.62 + row * 0.86
        dot(slide, x + 0.09, y + 0.14, 0.18, fill=TEAL)
        text_block(slide, x + 0.34, y, 5.6, 0.8,
                   [{"text": text, "size": 12.5, "line_spacing": 1.18}])
    footer(slide, "docs/forumit-2026/slides/img/ · tests/live_slide_shots.py (отдельный "
                  "корень данных и отдельный граф)", 6)
    notes(slide, plan)


def slide_autonomy(prs, plan) -> None:
    slide = blank(prs)
    title_block(slide, "Автономность: границы записаны в коде")
    items = (
        ("Пакеты не вливаются сами", "Изменение проходит шлюз; применение и откат — "
                                     "отдельные записанные действия."),
        ("Одобрение привязано к точным аргументам", "Человек разрешает не намерение, а "
                                                    "конкретный вызов."),
        ("Правила и записи меняет человек", "Агент не трогает свои данные — правила и "
                                           "записи меняет человек."),
        ("Инструменты MCP объявляют схему", "Нет обязательного поля — отказ с причиной, "
                                           "а не догадка."),
        ("Остановить может человек и его правила", "Право на эффект объявлено ролью и "
                                                  "настройкой разрешений."),
        ("Изоляция контейнерная, не машинная", "Docker и WSL2; изоляция уровня отдельной "
                                              "машины — цель, и она названа целью."),
    )
    for index, (headline, detail) in enumerate(items):
        column, row = index % 2, index // 2
        x = MARGIN + column * 6.13
        y = 1.45 + row * 1.24
        dot(slide, x + 0.16, y + 0.24, 0.32, fill=TINT_2)
        text_block(slide, x - 0.04, y + 0.16, 0.4, 0.26,
                   [{"text": str(index + 1), "size": 11.5, "bold": True, "color": TEAL,
                     "align": PP_ALIGN.CENTER}], anchor=MSO_ANCHOR.MIDDLE)
        text_block(slide, x + 0.62, y, 5.4, 1.1,
                   [{"text": headline, "size": 13.5, "bold": True, "color": INK,
                     "space_after": 3},
                    {"text": detail, "size": 11.5, "color": MUTED, "line_spacing": 1.15}])
    band = plate(slide, MARGIN, 5.35, BODY_W, 1.05, fill=TINT_2)
    write(band.text_frame, [{"text": "Система работает сама в пределах настроенных правил "
                                      "и останавливается там, где нужно решение человека.",
                             "size": 14.5, "bold": True, "color": INK}],
          anchor=MSO_ANCHOR.MIDDLE, pad=True)
    footer(slide, "python/oneiro/tools.py (arguments_digest) · python/oneiro/records.py "
                  "(Approval) · python/oneiro/web.py (/api/settings)", 7)
    notes(slide, plan)


def slide_journal(prs, plan) -> None:
    slide = blank(prs)
    title_block(slide, "Журнал организации")
    image(slide, IMG / "ru-tasks-journal.png", MARGIN, 1.25, BODY_W, 3.6,
          caption="Экран задач панели: две задачи с ролями и состояниями и постоянное "
                  "расписание с cron. Кадр снят tests/live_slide_shots.py.")
    bullets = ("Роль записана в задаче, поэтому видно, кто её выполнял.",
               "Расписание — запись в памяти, а не строка настроек: оно переживает "
               "перезапуск.",
               "Задача по расписанию идёт в ту же очередь и проходит те же ограничения.",
               "Интервалы и расписание задаёт человек — система не выбирает их сама.")
    for index, text in enumerate(bullets):
        column, row = index % 2, index // 2
        x = MARGIN + column * 6.13
        y = 5.42 + row * 0.72
        dot(slide, x + 0.09, y + 0.13, 0.18, fill=TEAL)
        text_block(slide, x + 0.32, y, 5.7, 0.7,
                   [{"text": text, "size": 12.5, "line_spacing": 1.15}])
    footer(slide, "docs/forumit-2026/slides/img/ru-tasks-journal.png · python/oneiro/tasks.py · "
                  "python/oneiro/schedule.py", 8)
    notes(slide, plan)


def slide_proactivity(prs, plan) -> None:
    slide = blank(prs)
    title_block(slide, "Проактивность: расписание и тишина")
    items = (
        "Работа в фоне по расписанию: интервалы и время задаёт человек.",
        "Тихие часы 22:00-09:00: работа идёт, уведомления удерживаются, а не приходят "
        "ночью по одному.",
        "Утром — один разбор: что завершено, что ждёт решения, где был отказ.",
        "Если человек не ответил, напоминание приходит один раз — не бесконечно.",
        "Разбор и напоминание решает тот же тик, что и расписание: второго таймера нет.",
        "Система не молчит до конца: она либо делает, либо говорит, что не смогла.",
    )
    for index, text in enumerate(items):
        y = 1.38 + index * 0.78
        dot(slide, MARGIN + 0.09, y + 0.14, 0.18, fill=TEAL)
        text_block(slide, MARGIN + 0.34, y, 4.7, 0.76,
                   [{"text": text, "size": 12.5, "line_spacing": 1.18}])
    image(slide, IMG / "ru-initiative-rows.png", 5.8, 1.35, 6.93, 4.2,
          caption="Фрагмент раздела «Инициатива» крупно: тихие часы со значением и "
                  "объяснением и утренняя сводка. Раздел целиком — "
                  "img/ru-initiative.png.")
    footer(slide, "python/oneiro/proactive.py · python/oneiro/schedule.py (tick) · "
                  "tests/live_proactive_check.py — 23 шага, код 0", 9)
    notes(slide, plan)


def slide_refusal(prs, plan) -> None:
    slide = blank(prs)
    title_block(slide, "Самоулучшение: механизм отказа")
    steps = (
        ("Повтор только по записи", "Эпизод повторяется там, где решение уже наблюдалось. "
                                    "Где решения нет, эпизод обрывается, а покрытие "
                                    "показывается числом."),
        ("Три повтора на задачу", "Кандидатов сравнивают на настоящих запусках: одиночный "
                                  "запуск легко попадает на хорошую сторону случайности."),
        ("Шлюз, применение, откат", "Новое поведение не применяется само. Применение и "
                                    "откат — отдельные записанные действия, утверждает "
                                    "изменение человек."),
    )
    for index, (headline, detail) in enumerate(steps):
        x = MARGIN + index * 4.18
        plate(slide, x, 1.5, 3.95, 3.5, fill=PAPER, line=TINT_2)
        dot(slide, x + 0.55, 2.02, 0.5, fill=TINT_2)
        text_block(slide, x + 0.4, 1.86, 0.3, 0.32,
                   [{"text": str(index + 1), "size": 16, "bold": True, "font": HEAD_FONT,
                     "color": TEAL, "align": PP_ALIGN.CENTER}], anchor=MSO_ANCHOR.MIDDLE)
        text_block(slide, x + 0.32, 2.45, 3.31, 0.6,
                   [{"text": headline, "size": 15, "bold": True, "font": HEAD_FONT,
                     "color": INK, "line_spacing": 1.08}])
        text_block(slide, x + 0.32, 3.15, 3.31, 1.7,
                   [{"text": detail, "size": 12, "color": BODY, "line_spacing": 1.2}])
    band = plate(slide, MARGIN, 5.25, BODY_W, 1.15, fill=TINT_2)
    write(band.text_frame, [
        {"text": "Масштаб механизма измерен: семь контрольных политик, написанных вручную, "
                 "оценили по записям и измерили на запусках.", "size": 13, "bold": True,
         "color": INK, "space_after": 5},
        {"text": "Оценка судьи разошлась с замером от −43 % до +26 % — поэтому кандидатов "
                 "сравнивают запусками, а не оценкой.", "size": 12, "color": MUTED,
         "line_spacing": 1.15},
    ], pad=True)
    footer(slide, "docs/harness.md (Judge calibration) · harness/policy.py (VARIANTS) · "
                  "python/oneiro/dream/gate.py", 10)
    notes(slide, plan)


def slide_rejected(prs, plan) -> None:
    slide = blank(prs)
    title_block(slide, "Отклонённый кандидат: одно число")
    chart_data = CategoryChartData()
    chart_data.categories = ("контроль (recorded)", "кандидат (windowed)")
    chart_data.add_series("средние токены подсказки", (4583.0, 4589.8))
    frame = slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(MARGIN), Inches(1.5),
                                   Inches(6.5), Inches(4.35), chart_data)
    chart = frame.chart
    chart.has_legend = False
    chart.chart_title.text_frame.text = "Средние токены подсказки на задачу"
    chart.chart_title.text_frame.paragraphs[0].runs[0].font.size = Pt(12)
    chart.chart_title.text_frame.paragraphs[0].runs[0].font.name = BODY_FONT
    chart.chart_title.text_frame.paragraphs[0].runs[0].font.color.rgb = MUTED
    plot = chart.plots[0]
    plot.gap_width = 130
    plot.has_data_labels = True
    labels = plot.data_labels
    labels.number_format = "0.0"
    labels.number_format_is_linked = False
    labels.font.size = Pt(13)
    labels.font.name = BODY_FONT
    labels.font.bold = True
    labels.position = XL_DATA_LABEL_POSITION.OUTSIDE_END
    for index, color in enumerate((TEAL, CORAL)):
        point = plot.series[0].points[index]
        point.format.fill.solid()
        point.format.fill.fore_color.rgb = color
    value_axis = chart.value_axis
    value_axis.minimum_scale = 0
    value_axis.has_major_gridlines = False
    value_axis.visible = False
    chart.category_axis.tick_labels.font.size = Pt(11.5)
    chart.category_axis.tick_labels.font.name = BODY_FONT
    text_block(slide, 7.5, 1.5, 5.23, 4.35,
               [{"text": "4589,8 против 4583,0", "size": 26, "bold": True, "font": HEAD_FONT,
                 "color": INK, "space_after": 4},
                {"text": "на 0,15 % дороже контроля", "size": 13.5, "color": CORAL,
                 "space_after": 12},
                {"text": "Разница не вышла за шум: beyond_noise — false.",
                 "size": 12.5, "space_after": 12, "line_spacing": 1.18},
                {"text": "Кандидат отклонён. Это и есть полезный результат: система "
                         "отказалась от изменения, которое выглядело разумным, но не "
                         "подтвердилось.", "size": 12.5, "space_after": 12,
                 "line_spacing": 1.18},
                {"text": "Ускорения и экономии не обещаю: в замере их нет.", "size": 12.5,
                 "color": MUTED, "line_spacing": 1.18}])
    footer(slide, "docs/O8-2026-10-12.md, строки 119-130 и 241 · payload "
                  "_tmp/o8-live6-payload.json", 11)
    notes(slide, plan)


def slide_next(prs, plan) -> None:
    slide = blank(prs)
    title_block(slide, "Что дальше")
    cards = (
        ("Поиск по смыслу по памяти", "Сегодня поиск токенный: по словам и связям. "
                                      "Семантический поиск — следующая работа."),
        ("Изоляция уровня отдельной машины", "Сейчас изоляция контейнерная. Границу "
                                            "обеспечивает Docker и WSL2."),
        ("Больше повторов в замерах", "Чтобы экономия подтверждалась на нескольких "
                                      "наборах задач, а не на одном."),
    )
    for index, (headline, detail) in enumerate(cards):
        x = MARGIN + index * 4.18
        box = plate(slide, x, 1.5, 3.95, 2.35, fill=TINT)
        write(box.text_frame, [
            {"text": headline, "size": 15, "bold": True, "font": HEAD_FONT, "color": INK,
             "space_after": 10, "line_spacing": 1.1},
            {"text": detail, "size": 12.5, "color": BODY, "line_spacing": 1.2},
        ], pad=True)
    band = plate(slide, MARGIN, 4.15, BODY_W, 1.75, fill=PAPER, line=TINT_2)
    write(band.text_frame, [
        {"text": "Отказ уже работает: следующий шаг — масштаб измерения.", "size": 15,
         "bold": True, "color": INK, "space_after": 8},
        {"text": "Для меня главный вывод — не набор возможностей, а понятные границы "
                 "уверенности: система различает намерение, разрешение, исполнение и "
                 "подтверждение. По этому различию человек доверяет результату ровно "
                 "настолько, насколько он проверен.", "size": 12.5, "color": BODY,
         "line_spacing": 1.2},
    ], pad=True)
    footer(slide, "docs/TALK-RU-2026-10-13.md, раздел 9 · docs/ACCEPTANCE-REPORT.md (границы)", 12)
    notes(slide, plan)


def slide_code(prs, plan) -> None:
    slide = blank(prs, dark=True)
    title_block(slide, "Ссылка на исходный код", dark=True)
    card = plate(slide, MARGIN + 0.2, 2.0, 8.4, 1.25, fill=BLOCK)
    write(card.text_frame, [{"text": "github.com/youlianvr/oneiro-ostis", "size": 30,
                             "bold": True, "font": HEAD_FONT, "color": TEAL_LIGHT}],
          anchor=MSO_ANCHOR.MIDDLE, pad=True)
    text_block(slide, MARGIN + 0.2, 3.6, 8.4, 1.6,
               [{"text": "Прогон показа — scripts/forum-demo.py", "size": 13,
                 "color": MUTED_LIGHT, "space_after": 8},
                {"text": "Живые проверки — tests/live_*.py: вебхук, черновики, память, "
                         "проактивность, офисная среда", "size": 13, "color": MUTED_LIGHT,
                 "space_after": 8, "line_spacing": 1.15},
                {"text": "Речь, план и доказательства — docs/forumit-2026/", "size": 13,
                 "color": MUTED_LIGHT}])
    text_block(slide, MARGIN + 0.2, 5.5, 9.5, 1.1,
               [{"text": "Спасибо.", "size": 24, "bold": True, "font": HEAD_FONT,
                 "color": WHITE, "space_after": 6},
                {"text": "Готов ответить на вопросы: что показано, чего ещё нет и почему.",
                 "size": 13, "color": MUTED_LIGHT}])
    nodes = [("память", 10.4, 2.35), ("роли", 12.5, 2.05), ("проверки", 10.7, 3.7),
             ("замеры", 12.6, 3.35)]
    for source, target in ((0, 1), (0, 2), (1, 3), (2, 3)):
        line(slide, nodes[source][1], nodes[source][2], nodes[target][1], nodes[target][2],
             color=TEAL, width_pt=1.1)
    for label, cx, cy in nodes:
        dot(slide, cx, cy, 0.2, fill=TEAL_LIGHT)
        text_block(slide, cx - 0.7, cy + 0.15, 1.4, 0.3,
                   [{"text": label, "size": 10.5, "color": MUTED_LIGHT,
                     "align": PP_ALIGN.CENTER}])
    footer(slide, "Репозиторий открыт: проверено 2026-10-13 "
                  "(api.github.com/repos/youlianvr/oneiro-ostis → HTTP 200)", 13, dark=True)
    notes(slide, plan)


BUILDERS = (slide_title, slide_roles, slide_memory_kinds, slide_memory_previous,
            slide_memory_metric, slide_memory_panel, slide_autonomy, slide_journal,
            slide_proactivity, slide_refusal, slide_rejected, slide_next, slide_code)


def build_pptx() -> Presentation:
    if len(BUILDERS) != len(SLIDE_PLAN):
        raise SystemExit("the plan and the builders disagree: "
                         f"{len(BUILDERS)} builders, {len(SLIDE_PLAN)} planned slides")
    prs = Presentation()
    prs.slide_width = Inches(SLIDE_W)
    prs.slide_height = Inches(SLIDE_H)
    for plan, builder in zip(SLIDE_PLAN, BUILDERS):
        builder(prs, plan)
    SLIDES.mkdir(parents=True, exist_ok=True)
    prs.save(PPTX)
    return prs


def convert_to_pdf() -> None:
    """The deck's own PDF, through the office image this project already ships."""
    command = (
        "mkdir -p /usr/share/fonts/truetype/host && "
        "cp -n /hostfonts/calibri*.ttf /hostfonts/cambria*.tt* "
        "/usr/share/fonts/truetype/host/ 2>/dev/null; "
        "fc-cache -f >/dev/null 2>&1; "
        "export HOME=/tmp; "
        f"cd /deck && soffice --headless --norestore --convert-to pdf --outdir /deck "
        f"'{PPTX.name}' && fc-match Calibri && fc-match Cambria"
    )
    result = subprocess.run(
        ["docker", "run", "--rm", "-v", f"{SLIDES}:/deck", "-v",
         f"{HOST_FONTS}:/hostfonts:ro", "--entrypoint", "sh", OFFICE_IMAGE, "-c", command],
        capture_output=True, text=True, timeout=600, encoding="utf-8", errors="replace")
    say(f"  soffice in {OFFICE_IMAGE}: exit {result.returncode}")
    for line in (result.stdout or "").strip().splitlines()[-3:]:
        say(f"  {line.strip()}")
    if result.returncode != 0 or not PDF.exists():
        raise SystemExit(f"the conversion failed: {(result.stderr or result.stdout)[-400:]}")


def render_pages() -> list[dict]:
    """Every page as a picture: the check `P2` asks for is done by looking at them."""
    import fitz

    PAGES.mkdir(parents=True, exist_ok=True)
    for stale in PAGES.glob("page-*.png"):
        stale.unlink()
    document = fitz.open(PDF)
    frames: list[dict] = []
    say(f"  PDF: {document.page_count} pages, "
        f"{document[0].rect.width:.1f}x{document[0].rect.height:.1f} pt on page 1")
    for number, page in enumerate(document, start=1):
        width, height = page.rect.width, page.rect.height
        if abs(width - PAGE_POINTS[0]) > 2 or abs(height - PAGE_POINTS[1]) > 2:
            raise SystemExit(f"page {number} is {width:.1f}x{height:.1f} pt, "
                             f"not the 16:9 canvas {PAGE_POINTS}")
        target = PAGES / f"page-{number:02d}.png"
        page.get_pixmap(dpi=110).save(target)
        with Image.open(target) as frame:
            pixels = frame.size
        if pixels[0] * pixels[1] < MIN_FRAME_PIXELS:
            raise SystemExit(f"{target.name} rendered at {pixels}: that is not a page")
        frames.append({"page": number, "file": str(target.relative_to(SLIDES)).replace("\\", "/"),
                       "pixels": list(pixels), "bytes": target.stat().st_size})
    document.close()
    return frames


def content_check() -> list[str]:
    """Read the built file back: the words are in it, and no placeholder survived."""
    prs = Presentation(str(PPTX))
    lines: list[str] = []
    if len(prs.slides) != len(SLIDE_PLAN):
        raise SystemExit(f"the file holds {len(prs.slides)} slides, "
                         f"the plan asks for {len(SLIDE_PLAN)}")
    forbidden = ("lorem", "ipsum", "todo", "xxxx", "[фио]", "[учреждение", "placeholder")
    for number, (slide, plan) in enumerate(zip(prs.slides, SLIDE_PLAN), start=1):
        text = "\n".join(shape.text_frame.text for shape in slide.shapes
                         if shape.has_text_frame)
        lowered = text.lower()
        missing = [needle for needle in plan["carries"] if needle.lower() not in lowered]
        if missing:
            raise SystemExit(f"slide {number} ({plan['key']}) does not say {missing}")
        found = [word for word in forbidden if word in lowered]
        if found:
            raise SystemExit(f"slide {number} carries placeholder text {found}")
        note = slide.notes_slide.notes_text_frame.text
        if plan["evidence"].split(" · ")[0] not in note:
            raise SystemExit(f"slide {number} does not name its evidence in the notes")
        lines.append(f"  {number:2d} {plan['key']:<20} {len(text):5d} chars, "
                     f"{len(note):4d} chars of notes")
    return lines


def write_index(page_frames: list[dict]) -> None:
    """The reader's page: the deck, its PDF, every page and the frames it embeds."""
    rows = []
    for plan, frame in zip(SLIDE_PLAN, page_frames):
        rows.append(
            f'<figure><img src="{frame["file"]}" alt="{plan["title"]}">'
            f'<figcaption><strong>{plan["title"]}</strong><span>{plan["caption"]}</span>'
            f'<small>Ответы опроса: {plan["answers"]}</small>'
            f'<small>Доказательство: {plan["evidence"]}</small></figcaption></figure>')
    shots = json.loads((IMG / "shots.json").read_text(encoding="utf-8"))
    frames = "".join(
        f'<figure><img src="img/{Path(item["file"]).name}" alt="{item["note"][:60]}">'
        f'<figcaption><strong>{item["note"]}</strong>'
        f'<small>{item["route"]} · {item["element"]} · тема «{item["theme"]}» · '
        f'{item["lang"]}, {item["bytes"]} байт</small></figcaption></figure>'
        for item in shots["frames"])
    body = f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Слайды доклада 14 октября 2026 — Oneiro</title>
<style>
  :root {{ color-scheme: light; }}
  body {{ margin: 0 auto; max-width: 1180px; padding: 28px 20px 60px;
         font: 15px/1.5 "Segoe UI", Arial, sans-serif; color: #1d2a38; background: #fff; }}
  h1 {{ font-size: 27px; margin: 0 0 6px; }}
  h2 {{ font-size: 19px; margin: 34px 0 12px; }}
  p.lead {{ color: #5a6b7b; margin: 0 0 18px; }}
  a {{ color: #0f7c86; }}
  .files a {{ display: inline-block; margin: 0 14px 8px 0; font-weight: 600; }}
  figure {{ margin: 0 0 26px; }}
  figure img {{ width: 100%; height: auto; border: 1px solid #dfe9f1; border-radius: 6px; }}
  figcaption {{ margin-top: 6px; }}
  figcaption span, figcaption small {{ display: block; color: #5a6b7b; }}
  figcaption small {{ font-size: 12.5px; }}
  .frames {{ display: grid; grid-template-columns: 1fr; gap: 18px; }}
</style></head>
<body>
<h1>Слайды доклада «Oneiro-OSTIS: автономный агент с памятью в графе знаний»</h1>
<p class="lead">14 октября 2026, форум, секция информатики. Порядок слайдов — приложение A
речи <a href="../TALK-RU-2026-10-13.md">TALK-RU-2026-10-13.md</a>; каждое утверждение слайда
названо в его примечаниях для докладчика.</p>
<p class="files">
  <a href="oneiro-doklad-2026-10-14.pptx">PPTX (PowerPoint)</a>
  <a href="oneiro-doklad-2026-10-14.pdf">PDF</a>
  <a href="img/shots.json">Записи кадров панели</a>
</p>
<h2>Слайды</h2>
{''.join(rows)}
<h2>Кадры панели, встроенные в слайды</h2>
<div class="frames">{frames}</div>
</body></html>
"""
    (SLIDES / "index.html").write_text(body, encoding="utf-8")


def main() -> int:
    say("== Слайды доклада: сборка ==")
    prs = build_pptx()
    say(f"  PPTX: {PPTX.relative_to(PROJECT)} — {len(prs.slides)} слайдов, "
        f"{PPTX.stat().st_size} байт")
    for line in content_check():
        say(line)
    say("\n== PDF и постраничные изображения ==")
    convert_to_pdf()
    say(f"  PDF: {PDF.relative_to(PROJECT)} — {PDF.stat().st_size} bytes")
    frames = render_pages()
    for frame in frames:
        say(f"  page {frame['page']:2d} -> {frame['file']}  "
            f"{frame['pixels'][0]}x{frame['pixels'][1]}, {frame['bytes']} bytes")
    write_index(frames)
    say(f"\n  указатель: {(SLIDES / 'index.html').relative_to(PROJECT)}")
    say(f"\nГотово: {len(frames)} страниц, "
        f"{len(json.loads((IMG / 'shots.json').read_text(encoding='utf-8'))['frames'])} кадров панели.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
