"""Live shots for the 14 October talk: the panel frames the slides embed.

Run it with `python tests/live_slide_shots.py`. It is not a unit test; it produces
the pictures `docs/forumit-2026/slides/` embeds, and it produces them the way the
plan asks for them — from the running console, not from a mock-up:

* a real console process on a free loopback port with its own data root, its own
  settings file and its own MCP list, so the owner's console on 9899 is untouched;
* the facts go in through the panel's **own HTTP routes** (`/api/memory/facts` and
  the edit route), so the section that is photographed is the section a person
  writes in; one fact is edited, so the picture carries the earlier value with its
  own date and source (plan P4, answers 27, 28, 32);
* a task with a finished run, a task whose run failed and one standing schedule are
  published through the product's own record lane, then read back from `/api/tasks`
  before the shutter — a picture of an empty journal fails the run (answer 43);
* the Initiative section is shot from the real settings page, with the quiet hours
  and the digest the product declares (plan P2 slide 9, answers 63, 65).

Before every shutter the frame's language is asserted from the product's own
catalog (`oneiro.i18n`), and every file is checked against a size floor: a blank
frame is not evidence. What was shot is written to `img/shots.json`, which is the
record the slides and this check's own summary are read from.

    python tests/live_slide_shots.py            # writes docs/forumit-2026/slides/img/
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image

TESTS = Path(__file__).resolve().parent
PROJECT = TESTS.parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(PROJECT / "python"))

#: Everything of this run's own lives here; the owner's files are never opened.
(PROJECT / "_tmp").mkdir(exist_ok=True)
WORK = Path(tempfile.mkdtemp(prefix="oneiro-slide-shots-", dir=PROJECT / "_tmp"))
#: Where the slides read their pictures from.
IMG = PROJECT / "docs" / "forumit-2026" / "slides" / "img"
#: A frame smaller than this is a blank page or a broken stylesheet, not a screen.
MIN_BYTES = 5000
LANG = "ru"
#: The panel's own theme for the frames: a light one, because the slides are light.
THEME = "paper"

#: The three facts this run writes. The first is edited afterwards, which is what
#: puts an earlier value with its own date and source into the picture.
FACTS = (
    ("slide-fact-0001", "Владелец пишет по-русски.", "Владелец пишет по-русски и по-английски."),
    ("slide-fact-0002", "Отчёты готовятся к пятнице.", ""),
    ("slide-fact-0003", "Тихие часы — с 22:00 до 09:00; ночью уведомления удерживаются.", ""),
)

FRAMES: list[dict] = []


def say(text: str = "") -> None:
    print(text, flush=True)


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def isolate(port: int) -> None:
    """A temporary settings file, data root and MCP list: the owner's are untouched."""
    os.environ["ONEIRO_SETTINGS_FILE"] = str(WORK / "settings.json")
    os.environ["ONEIRO_DATA_DIR"] = str(WORK / "runtime")
    os.environ["ONEIRO_KEYS_FILE"] = str(WORK / "no-keys.env")
    os.environ["ONEIRO_MCP_FILE"] = str(WORK / "mcp.json")
    os.environ["ONEIRO_WEB_HOST"] = "127.0.0.1"
    os.environ["ONEIRO_WEB_PORT"] = str(port)
    os.environ["ONEIRO_HEADLESS"] = "1"


def settings_file() -> None:
    """The settings the frames show: a light theme and the declared initiative rules."""
    (WORK / "settings.json").write_text(json.dumps({
        "ui.theme": THEME,
        "initiative.level": "proactive",
        "initiative.quiet_hours": "22:00-09:00",
        "initiative.digest": True,
        "initiative.reminders": True,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    (WORK / "mcp.json").write_text(json.dumps({"mcp": {}}), encoding="utf-8")


def request(port: int, path: str, body=None, *, token: str = "", tries: int = 6):
    """One real HTTP call over the loopback console."""
    headers: dict[str, str] = {}
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
        if token:
            headers["X-Oneiro-CSRF"] = token
    call = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data,
                                  headers=headers, method="POST" if data else "GET")
    for attempt in range(1, tries + 1):
        try:
            with urllib.request.urlopen(call, timeout=60) as response:
                raw = response.read().decode("utf-8", "replace")
                return response.status, (json.loads(raw) if raw.strip().startswith(("{", "[")) else raw)
        except urllib.error.HTTPError as error:
            raw = error.read().decode("utf-8", "replace")
            try:
                return error.code, json.loads(raw)
            except ValueError:
                return error.code, {"error": raw[:200]}
        except Exception as error:                       # console not up yet
            if attempt == tries:
                raise
            say(f"  [note] {path}: {type(error).__name__}; asking again ({attempt + 1})")
            time.sleep(0.5 + attempt * 0.5)
    raise AssertionError("unreachable")


def write_facts(port: int) -> dict:
    """The owner's own routes: add three facts, edit the first, read the section back."""
    _, session = request(port, "/api/session")
    token = session["csrf"]
    added = []
    for client_id, text, _edited in FACTS:
        status, payload = request(port, "/api/memory/facts",
                                  {"text": text, "client_id": client_id}, token=token)
        assert status == 200, f"adding a fact failed: HTTP {status} {payload}"
        added.append(payload["fact"]["id"])
    status, payload = request(port, f"/api/memory/facts/{added[0]}/edit",
                              {"text": FACTS[0][2], "client_id": "slide-edit-0001", "revision": 1},
                              token=token)
    assert status == 200, f"editing a fact failed: HTTP {status} {payload}"
    status, listing = request(port, "/api/memory/facts")
    assert status == 200, f"reading the facts failed: HTTP {status}"
    facts = listing["facts"]
    assert len(facts) == len(FACTS), f"expected {len(FACTS)} facts, the section holds {len(facts)}"
    edited = next(fact for fact in facts if fact["id"] == added[0])
    assert edited["text"] == FACTS[0][2], f"the edit did not land: {edited['text']!r}"
    earlier = edited.get("superseded") or []
    assert earlier, "the earlier value is not in the answer, so the picture would not carry it"
    assert earlier[0]["text"] == FACTS[0][1], f"the earlier value is {earlier[0]['text']!r}"
    assert earlier[0].get("provenance"), "the earlier value has no source"
    assert earlier[0].get("updated_at"), "the earlier value has no date"
    assert listing.get("history_complete") is True, "the section did not read the whole history"
    say(f"  three facts through /api/memory/facts; the first edited: "
        f"earlier={earlier[0]['text']!r} source={earlier[0]['provenance']} "
        f"date={earlier[0]['updated_at']}")
    return {"facts": facts, "earlier": earlier, "edited_id": added[0]}


def publish_journal(port: int, runtime) -> dict:
    """A finished task, a failed run and one standing schedule: a journal that is not empty."""
    from oneiro.records import Provenance, Run, Schedule, State, Task

    stamp = "2026-10-13T22:40:00+03:00"
    later = "2026-10-13T23:05:00+03:00"
    records = (
        Task(id="slide-task-0001", title="Подготовить отчёт для куратора",
             detail="Собрать черновик из тестовой почты.", assigned_role="executor",
             state=State.QUEUED, created_at=stamp, updated_at=stamp,
             provenance=Provenance.OWNER_INSTRUCTION),
        Run(id="slide-run-0001", task_id="slide-task-0001", role="executor", attempt=1,
            state=State.COMPLETED, notes="Черновик готов; отправка ждёт решения человека.",
            created_at=stamp, updated_at=later, provenance=Provenance.SYSTEM),
        Task(id="slide-task-0002", title="Разобрать письмо от куратора",
             detail="Тестовый ящик.", assigned_role="researcher",
             state=State.QUEUED, created_at=later, updated_at=later,
             provenance=Provenance.OWNER_INSTRUCTION),
        Run(id="slide-run-0002", task_id="slide-task-0002", role="researcher", attempt=1,
            state=State.FAILED, notes="модель не ответила",
            created_at=later, updated_at=later, provenance=Provenance.SYSTEM),
        Schedule(id="slide-schedule-0001", cron="0 8 * * *", task_title="Утренний разбор памяти",
                 task_detail="Разбор того, что сделано за тихие часы.", role="executor",
                 enabled=True, created_at=stamp, updated_at=stamp,
                 provenance=Provenance.OWNER_INSTRUCTION),
    )
    for record in records:
        asyncio.run(runtime.publish(record.to_dict(), record.id))
    for route in ("/api/tasks", "/api/schedules"):
        status, payload = request(port, route)
        assert status == 200, f"reading {route} failed: HTTP {status}"
        text = json.dumps(payload, ensure_ascii=False)
        wanted = (("Подготовить отчёт для куратора", "Разобрать письмо от куратора",
                   "модель не ответила") if route == "/api/tasks"
                  else ("Утренний разбор памяти",))
        for needle in wanted:
            assert needle in text, f"{route} does not carry {needle!r}, so the picture is empty"
    say(f"  journal: {len(records)} records published, all of them read back from "
        f"the panel's own routes /api/tasks and /api/schedules")
    return {"records": [record.id for record in records]}


def fieldset_for(page, group_ru: str):
    """The settings fieldset whose legend is that group: the Initiative section itself."""
    return page.locator("fieldset").filter(has=page.locator("legend", has_text=group_ru))


def shoot(page, base: str, route: str, target: Path, *, element: str = "",
          wait_for: str = "", must_show: tuple[str, ...] = (), note: str = "",
          width: int = 1440) -> dict:
    """One frame, taken only after the page says what the file's name claims.

    `width` is the window the panel is asked for. A slide can only carry so much: an
    element 1200 px wide placed in a 5-inch column renders its 11 pt text at 3 pt, so
    the frame that has to be *read* is shot in a narrower window, where the same words
    take more of the frame's width and survive the scaling onto a slide.
    """
    url = f"{base}{route}"
    page.set_viewport_size({"width": width, "height": 1000})
    page.goto(url, wait_until="networkidle")
    page.wait_for_timeout(250)
    page.wait_for_function("document.fonts.status === 'loaded'", timeout=8000)
    assert page.get_attribute("html", "lang") == LANG, f"{url}: rendered lang is not {LANG}"
    assert page.get_attribute("html", "data-theme") == THEME, f"{url}: theme is not {THEME}"
    if wait_for:
        page.wait_for_selector(wait_for, timeout=8000)
    where = page.locator(element) if element else page
    if element:
        where.first.wait_for(state="visible", timeout=8000)
    # What a person reads in a frame includes the value written in a control: a
    # settings row whose value is only in an `<input>` is shown, not empty.
    read_text = ("el => el.innerText + '\\n' "
                 "+ [...el.querySelectorAll('input,select,textarea')].map(n => n.value).join('\\n')")
    text = where.first.evaluate(read_text) if element else page.locator("body").evaluate(read_text)
    missing = [needle for needle in must_show if needle not in text]
    assert not missing, f"{url}: the frame does not show {missing}"
    target.parent.mkdir(parents=True, exist_ok=True)
    if element:
        where.first.screenshot(path=str(target))
    else:
        page.screenshot(path=str(target), full_page=True)
    size = target.stat().st_size
    assert size >= MIN_BYTES, f"{target.name} is {size} bytes: a blank frame is not evidence"
    with Image.open(target) as shot:
        pixels = shot.size
    frame = {"file": str(target.relative_to(PROJECT)).replace("\\", "/"), "route": route,
             "element": element or "whole page", "url": url, "theme": THEME, "lang": LANG,
             "window_px": width, "pixels": list(pixels), "bytes": size, "note": note,
             "text_head": " ".join(text.split())[:220]}
    FRAMES.append(frame)
    say(f"  {target.name:<26} <- {url} @{width}px  ({size} bytes, {pixels[0]}x{pixels[1]} px)")
    return frame


def shoot_stack(page, base: str, route: str, target: Path, selectors: tuple[str, ...], *,
                width: int, must_show: tuple[str, ...] = (), note: str = "", gap: int = 14) -> dict:
    """Several panel rows as one frame, in the order they stand on the page.

    Rows are shot one by one and stacked, so the frame carries exactly the rows a slide
    is about and none of the page around them. There is no clip arithmetic here: what
    is measured is the element's own picture, which is what the page itself drew.
    """
    url = f"{base}{route}"
    page.set_viewport_size({"width": width, "height": 1000})
    page.goto(url, wait_until="networkidle")
    page.wait_for_timeout(250)
    page.wait_for_function("document.fonts.status === 'loaded'", timeout=8000)
    assert page.get_attribute("html", "lang") == LANG, f"{url}: rendered lang is not {LANG}"
    assert page.get_attribute("html", "data-theme") == THEME, f"{url}: theme is not {THEME}"
    parts: list[Path] = []
    texts: list[str] = []
    for index, selector in enumerate(selectors):
        row = page.locator(selector).first
        row.wait_for(state="visible", timeout=8000)
        # A row's value lives in its control, so the row's text is read with it: a
        # quiet window that is only in an `<input>` is shown, not missing.
        texts.append(row.evaluate("el => el.innerText + '\\n' "
                                 "+ [...el.querySelectorAll('input,select,textarea')]"
                                 ".map(n => n.value).join('\\n')"))
        part = target.with_name(f"{target.stem}-part{index}{target.suffix}")
        row.screenshot(path=str(part))
        parts.append(part)
    text = "\n".join(texts)
    missing = [needle for needle in must_show if needle not in text]
    assert not missing, f"{url}: the frame does not show {missing}"
    with Image.open(parts[0]) as first:
        width_px = first.width
    heights = []
    for part in parts:
        with Image.open(part) as image:
            heights.append(image.height)
    stacked = Image.new("RGB", (width_px, sum(heights) + gap * (len(parts) - 1)), "white")
    top = 0
    for part, height in zip(parts, heights):
        with Image.open(part) as image:
            stacked.paste(image, (0, top))
        top += height + gap
    target.parent.mkdir(parents=True, exist_ok=True)
    stacked.save(target, "PNG")
    for part in parts:
        part.unlink()
    size = target.stat().st_size
    assert size >= MIN_BYTES, f"{target.name} is {size} bytes: a blank frame is not evidence"
    frame = {"file": str(target.relative_to(PROJECT)).replace("\\", "/"), "route": route,
             "element": " + ".join(selectors), "url": url, "theme": THEME, "lang": LANG,
             "window_px": width, "pixels": list(stacked.size), "bytes": size, "note": note,
             "text_head": " ".join(text.split())[:220]}
    FRAMES.append(frame)
    say(f"  {target.name:<26} <- {url} @{width}px  ({size} bytes, "
        f"{stacked.width}x{stacked.height} px, {len(selectors)} rows)")
    return frame


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        say("ERROR: Playwright is not installed, so no real picture can be taken.")
        say("       pip install playwright && playwright install chromium")
        return 1

    port = free_port()
    isolate(port)
    settings_file()

    from chat_fakes import GraphStub, MemoryLinks
    from oneiro import i18n
    from oneiro.runtime import Runtime
    from oneiro.web import create_app
    import uvicorn

    say("== Slide shots: the panel frames the 14 October talk embeds ==")
    say(f"  working directory: {WORK}")
    say(f"  frames go to {IMG}")

    runtime = Runtime(graph=GraphStub(MemoryLinks(), WORK / "graph-writer.lock"))
    app = create_app(runtime=runtime, scheduler=False)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port,
                                           log_level="error", access_log=False))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base = f"http://127.0.0.1:{port}"
    for _ in range(80):
        try:
            with urllib.request.urlopen(f"{base}/api/health", timeout=1) as response:
                if response.status == 200:
                    break
        except Exception:
            time.sleep(0.25)
    else:
        say("ERROR: the console never answered /api/health")
        return 1
    say(f"  console on {base} (the owner's own on 9899 is untouched)\n")

    facts = write_facts(port)
    journal = publish_journal(port, runtime)

    # The product's own catalog decides what each frame must carry, so a frame in the
    # wrong language or from a half-rendered page fails here rather than on a slide.
    heading = i18n.t("heading.curated_memory", LANG)
    earlier_label = i18n.t("facts.earlier", LANG)
    source_label = i18n.t("facts.source", LANG)
    group_ru = i18n.group_text("Initiative", LANG)
    quiet_label = i18n.t("setting.initiative.quiet_hours.label", LANG)
    digest_label = i18n.t("setting.initiative.digest.label", LANG)

    written: list[dict] = []
    try:
        with sync_playwright() as play:
            browser = play.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 900})

            say("== 1. Curated memory: source, dates and the value an edit replaced ==")
            frame = shoot(page, base, f"/memory?lang={LANG}", IMG / "ru-memory-facts.png",
                          element="#facts", wait_for="#facts-list .fact-card",
                          must_show=(heading, earlier_label, source_label, facts["earlier"][0]["text"]),
                          note="Раздел панели «Курируемая память»: три факта владельца, источник, "
                               "дата создания и изменения; у первого показано прежнее значение "
                               "со своим источником и своей датой.")
            frame["facts"] = [fact["text"] for fact in facts["facts"]]
            frame["earlier"] = facts["earlier"][0]
            written.append(frame)

            # The fact card itself, in a narrow window: this is the one record the
            # slide about a replaced value has to be read in.
            written.append(shoot(page, base, f"/memory?lang={LANG}", IMG / "ru-memory-card.png",
                                 element=f'li.fact-card[data-fact="{facts["edited_id"]}"]',
                                 must_show=(facts["earlier"][0]["text"],
                                            i18n.t("facts.earlier", LANG),
                                            i18n.t("facts.updated", LANG)),
                                 note="Одна запись раздела «Курируемая память» крупно: факт "
                                      "владельца после правки, источник, даты и прежнее "
                                      "значение с его источником и датой.",
                                 width=700))

            say("\n== 2. The journal: tasks, runs and a standing schedule ==")
            # The screen body rather than the whole page: the host's own readiness
            # block above it belongs to the host, not to what the slide claims, and
            # this run's console reads a graph that lives in this process.
            written.append(shoot(page, base, f"/tasks?lang={LANG}", IMG / "ru-tasks-journal.png",
                                 element=".screen-container",
                                 wait_for="#task-list .card-item, #schedule-list .card-item",
                                 must_show=("Подготовить отчёт для куратора",
                                            "Разобрать письмо от куратора",
                                            "Утренний разбор памяти"),
                                 note="Экран задач, разделы «Активные и ожидающие задачи» и "
                                      "«Постоянные расписания»: две задачи и постоянное "
                                      "расписание."))

            say("\n== 3. Initiative: the quiet window and the digest, row by row ==")
            written.append(shoot(page, base, f"/settings?lang={LANG}", IMG / "ru-initiative.png",
                                 element=f"fieldset:has(legend:text-is('{group_ru}'))",
                                 must_show=(quiet_label, digest_label, "22:00-09:00"),
                                 note="Настройки, раздел «Инициатива» целиком: уровень, тихие "
                                      "часы 22:00-09:00, утренняя сводка и одно повторное "
                                      "напоминание.", width=1000))
            written.append(shoot_stack(
                page, base, f"/settings?lang={LANG}", IMG / "ru-initiative-rows.png",
                (f"div.field:has([id='f-initiative.quiet_hours'])",
                 f"div.field:has([id='f-initiative.digest'])"),
                width=560,
                must_show=(quiet_label, "22:00-09:00", digest_label),
                note="Две строки раздела «Инициатива» крупно: тихие часы со значением и "
                     "объяснением и утренняя сводка."))

            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=5)

    record = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
              "console_url": base, "theme": THEME, "lang": LANG, "work": str(WORK),
              "facts": facts["facts"], "journal_records": journal["records"], "frames": written}
    (IMG / "shots.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    say(f"\n{len(written)} frames written to {IMG}")
    say(f"  record: {IMG / 'shots.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
