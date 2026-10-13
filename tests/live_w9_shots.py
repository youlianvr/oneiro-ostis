"""Live check for W9: capture the acceptance screenshots § 6 asks for.

Run it with `python tests/live_w9_shots.py`. The script starts the product's own
web console on a free loopback port (never 9899), drives a real Chromium with
Playwright and writes the pictures into `docs/shots/oneiro-v1/`.

Pictures taken (22):
* 5 screens x 2 languages  — Conversation, Tasks, Tools, Settings, Memory

  The drafts screen (`/drafts`) is not in this set: its acceptance picture is the press
  itself, taken by `tests/live_drafts_check.py` in a browser with a waiting draft on the
  page (before and after the click), and the count of frames this script writes is quoted
  in `docs/ACCEPTANCE-REPORT.md` § 2 — a sixth screen here would change that number.
* 5 themes x 2 languages   — the Conversation screen under each `ui.theme`
* the console served from an **installed copy outside this checkout**, both languages,
  so § 6 row 1 has a picture of the product and not only a log line

Every frame is checked against the catalog before the shutter: a `ru` frame must carry
`oneiro.i18n`'s Russian text for that screen as element text and must not carry the
English value of those same keys. A file whose name claims a language its picture does
not show fails the run.

After the five screens are shot, their **rendered** text is measured in both languages:
the two must share no English sentence. This is the check that would have caught the
settings screen being a Russian page rendering an English form, and it runs on what the
browser actually shows, not only on the markup the server sent.

Every frame is a real render: the attributes in the document (`lang`, `data-theme`)
are asserted before the shutter, and a picture below the size floor fails the run.
Settings and data go to a temporary root, and the owner's own files are
fingerprinted before and after so the check proves it left nothing behind.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

TESTS = Path(__file__).resolve().parent
PROJECT = TESTS.parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(PROJECT / "python"))

WORK = Path(tempfile.mkdtemp(prefix="oneiro-w9-shots-"))
SHOTS = PROJECT / "docs" / "shots" / "oneiro-v1"

OWNER_SETTINGS = Path.home() / ".oneiro" / "settings.json"
OWNER_KEYS = Path.home() / ".config" / "keys.env"
WATCHED = (OWNER_SETTINGS, OWNER_KEYS, PROJECT / ".env",
           PROJECT / "knowledge-base" / "repo.path")

#: name -> route. The names are the five screens of § 3.
SCREENS = (
    ("conversation", "/"),
    ("tasks", "/tasks"),
    ("tools", "/tools"),
    ("settings", "/settings"),
    ("memory", "/memory"),
)
LANGUAGES = ("ru", "en")
THEMES = ("night", "paper", "editorial", "cosmic", "agentic")
#: A frame smaller than this is a blank page or a broken stylesheet, not a screen.
MIN_BYTES = 5000

#: Catalog keys each screen must show in the language of its frame. A frame whose
#: name says `ru` and whose markup carries the English value fails before the shutter.
SCREEN_KEYS = {
    "conversation": ("app.tagline", "heading.prerequisites", "heading.chat",
                     "btn.send", "btn.attach", "btn.new_conversation", "btn.find",
                     "placeholder.message"),
    "tasks": ("app.tagline", "heading.prerequisites", "heading.tasks",
              "heading.active_tasks", "btn.queue_task", "heading.schedules"),
    "tools": ("app.tagline", "heading.prerequisites", "heading.tools", "tab.mcp",
              "tab.local", "heading.available_skills"),
    "settings": ("app.tagline", "heading.prerequisites", "heading.settings",
                 "btn.save_settings", "setting.web.port.label", "group.Interface"),
    "memory": ("app.tagline", "heading.prerequisites", "heading.memory",
               "heading.curated_memory", "btn.add_fact"),
}


def say(text: str = "") -> None:
    print(text, flush=True)


def fingerprint(paths) -> dict[str, str]:
    seen = {}
    for path in paths:
        try:
            raw = Path(path).read_bytes()
        except OSError:
            seen[str(path)] = "absent"
            continue
        seen[str(path)] = f"{len(raw)} bytes, sha256 {hashlib.sha256(raw).hexdigest()[:12]}"
    return seen


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


#: Words per line, and characters per line, that make a line look like a sentence.
_SENTENCE = re.compile(r"[ -~]{20,}")
_CYRILLIC = re.compile("[\u0400-\u04ff]")


def english_sentences(text: str) -> set[str]:
    """Lines that read as English prose: several words, all printable ASCII."""
    lines = (line.strip() for line in text.splitlines())
    return {line for line in lines
            if len(line.split()) >= 4 and _SENTENCE.fullmatch(line) and not _CYRILLIC.search(line)}


def assert_no_shared_sentence(ru_text: str, en_text: str, screen: str) -> int:
    """RU and EN must not say the same English sentence. Returns what was measured.

    Both directions matter: `english_sentences(ru)` being empty is asserted by the
    caller, so a screen that is English on both sides is caught there, and this one
    catches a Russian screen that still prints an English sentence the other language
    also prints.
    """
    ru = english_sentences(ru_text)
    en = english_sentences(en_text)
    shared = ru & en
    assert not shared, (
        f"the {screen} screen shows the same English sentence in both languages: "
        f"{sorted(shared)[:4]}")
    return len(en)


def assert_the_frame_speaks(markup: str, lang: str, keys) -> None:
    """Before the shutter: the frame's own language is in the markup, the other is not.

    The name of a file is a claim about the picture inside it, so `ru-settings.png`
    must not be a screenshot of an English form. Both directions are checked: the
    catalog's value for this language is present as element text, and the value for
    the other language is not.
    """
    from html import escape
    from oneiro import i18n

    def present(value: str) -> bool:
        """Element text or an attribute value: a placeholder is text a person reads too."""
        wrapped = escape(value, quote=True)
        return f">{escape(value)}<" in markup or f'"{wrapped}"' in markup

    other = "en" if lang == "ru" else "ru"
    for key in keys:
        expected = i18n.t(key, lang)
        wrong = i18n.t(key, other)
        assert present(expected), f"{key} is not rendered in {lang}"
        if expected != wrong:
            assert not present(wrong), f"{key} is still {other} on a {lang} page"


def isolate(port: int) -> None:
    """A temporary settings file and data root: the owner's own are untouched."""
    os.environ["ONEIRO_SETTINGS_FILE"] = str(WORK / "settings.json")
    os.environ["ONEIRO_DATA_DIR"] = str(WORK / "runtime")
    os.environ["ONEIRO_KEYS_FILE"] = str(WORK / "keys.env")
    os.environ["ONEIRO_MCP_FILE"] = str(WORK / "mcp.json")
    os.environ["ONEIRO_WEB_PORT"] = str(port)
    os.environ["ONEIRO_HEADLESS"] = "1"


def set_theme(base_url: str, theme: str) -> None:
    """Change `ui.theme` through the same route the settings page posts to."""
    with urllib.request.urlopen(f"{base_url}/api/session", timeout=5) as resp:
        token = json.loads(resp.read().decode("utf-8"))["csrf"]
    body = json.dumps({"ui.theme": theme}).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/api/settings", data=body,
        headers={"Content-Type": "application/json", "X-Oneiro-CSRF": token})
    with urllib.request.urlopen(request, timeout=5) as resp:
        assert resp.status == 200, f"theme {theme} was refused: HTTP {resp.status}"
    with urllib.request.urlopen(f"{base_url}/api/health", timeout=5) as resp:
        assert resp.status == 200


def install_out_of_tree(work: Path) -> Path:
    """Build the installer payload and copy it where this checkout is not on the path."""
    sys.path.insert(0, str(PROJECT))
    from scripts.build_installer_payload import build_payload

    built = build_payload(work / "staging_payload")
    installed = work / "installed_app"
    shutil.copytree(built, installed)

    # The picture only proves § 6 row 1 if the process that serves it reads the
    # installed copy: assert where `oneiro` resolves, with the checkout cwd-free.
    probe_env = dict(os.environ)
    probe_env["PYTHONPATH"] = str(installed / "app" / "python")
    probe = subprocess.run(
        [sys.executable, "-c", "import oneiro, sys; print(oneiro.__file__)"],
        cwd=str(installed), env=probe_env, capture_output=True, text=True)
    where = (probe.stdout or "").strip().splitlines()[-1] if probe.stdout.strip() else ""
    say(f"  payload built at {built}, installed at {installed}")
    say(f"  the installed copy imports oneiro from {where}")
    assert probe.returncode == 0, f"the installed copy cannot import oneiro: {probe.stderr[-300:]}"
    assert Path(where).resolve().is_relative_to(installed.resolve()), \
        f"the installed copy resolved oneiro outside itself: {where}"
    return installed


def shots_from_installed(page, installed: Path, port: int, shots_dir: Path,
                         work: Path) -> list[Path]:
    """Serve the console from the installed copy and photograph it."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(installed / "app" / "python")
    env["ONEIRO_SETTINGS_FILE"] = str(work / "installed-settings.json")
    env["ONEIRO_DATA_DIR"] = str(work / "installed-data")
    env["ONEIRO_KEYS_FILE"] = str(work / "installed-keys.env")
    env["ONEIRO_WEB_PORT"] = str(port)
    env["ONEIRO_HEADLESS"] = "1"

    log_path = work / "installed-console.log"
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "oneiro", "serve", "--no-window"],
            cwd=str(installed), env=env, stdout=log, stderr=subprocess.STDOUT)
        base = f"http://127.0.0.1:{port}"
        try:
            for _ in range(160):
                if process.poll() is not None:
                    say(f"ERROR: the installed console exited with {process.returncode}; "
                        f"its log is {log_path}")
                    return []
                try:
                    with urllib.request.urlopen(f"{base}/api/health", timeout=1) as resp:
                        if resp.status == 200:
                            break
                except Exception:
                    time.sleep(0.25)
            else:
                say(f"ERROR: the installed console never answered on {base}; its log is {log_path}")
                return []
            say(f"  installed console answering on {base} (log: {log_path})")

            frames: list[Path] = []
            for lang in LANGUAGES:
                url = f"{base}/?lang={lang}"
                page.goto(url, wait_until="networkidle")
                page.wait_for_timeout(300)
                page.wait_for_function("document.fonts.status === 'loaded'", timeout=5000)
                assert page.get_attribute("html", "lang") == lang, f"{url}: wrong language"
                assert_the_frame_speaks(page.content(), lang, SCREEN_KEYS["conversation"])
                target = shots_dir / f"installed-conversation-{lang}.png"
                page.screenshot(path=str(target), full_page=True)
                frames.append(target)
                say(f"  {target.name:<26} <- {url}  ({target.stat().st_size} bytes)")
            return frames
        finally:
            process.terminate()
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
            say(f"  installed console stopped (exit {process.returncode})")


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        say("ERROR: Playwright is not installed, so no real picture can be taken.")
        say("       Install it (pip install playwright && playwright install chromium),")
        say("       or mark the § 6 screenshot rows as 'manual shot required'.")
        return 1

    from oneiro.runtime import Runtime
    from oneiro.web import create_app
    import uvicorn
    from chat_fakes import GraphStub, MemoryLinks

    say("== W9 Live Check: acceptance screenshots for § 6 ==")
    say(f"  working directory: {WORK}")

    before = fingerprint(WATCHED)
    port = free_port()
    isolate(port)
    SHOTS.mkdir(parents=True, exist_ok=True)

    memory = Runtime(graph=GraphStub(MemoryLinks(), WORK / "graph-writer.lock"))
    app = create_app(runtime=memory, scheduler=False)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port,
                                          log_level="error", access_log=False))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"{base_url}/api/health", timeout=1) as resp:
                if resp.status == 200:
                    break
        except Exception:
            time.sleep(0.1)
    else:
        say("ERROR: the console did not become reachable")
        return 1
    say(f"  console on {base_url} (owner's preview on 9899 untouched)")

    written: list[Path] = []
    try:
        with sync_playwright() as play:
            browser = play.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 900})

            say("\n== 1. Five screens in both languages ==")
            rendered: dict[str, dict[str, str]] = {lang: {} for lang in LANGUAGES}
            for lang in LANGUAGES:
                for name, route in SCREENS:
                    url = f"{base_url}{route}?lang={lang}"
                    # networkidle, then a settled layout: a frame taken before the
                    # stylesheet and the page script land is a picture of a half page.
                    page.goto(url, wait_until="networkidle")
                    page.wait_for_timeout(300)
                    page.wait_for_function("document.fonts.status === 'loaded'", timeout=5000)
                    document_lang = page.get_attribute("html", "lang")
                    assert document_lang == lang, f"{url}: rendered lang={document_lang}"
                    assert_the_frame_speaks(page.content(), lang, SCREEN_KEYS[name])
                    target = SHOTS / f"{lang}-{name}.png"
                    page.screenshot(path=str(target), full_page=True)
                    written.append(target)
                    # What the browser shows, after the shutter - the readiness panel
                    # included. It used to be removed here, and that removal is exactly
                    # what hid an English instruction and three English reasons on Russian
                    # screens: the panel is client-filled, so the served-markup rule could
                    # not see it either.
                    rendered[lang][name] = page.evaluate("document.body.innerText")
                    say(f"  {target.name:<26} <- {url}  ({target.stat().st_size} bytes)")

            say("\n== 1b. The rendered text of each screen, measured in both languages ==")
            for name, _route in SCREENS:
                said = sorted(english_sentences(rendered["ru"][name]))
                assert not said, (
                    f"the {name} screen shows English prose on a Russian page, so a "
                    f"sentence reached the screen that the catalog does not own: {said[:3]}")
                sentences = assert_no_shared_sentence(rendered["ru"][name],
                                                      rendered["en"][name], name)
                say(f"  {name:<14} no English prose on the ru side, no shared sentence "
                    f"({sentences} English sentences on the en side, "
                    f"{len(rendered['ru'][name])} chars on the ru side)")

            say("\n== 2. Five themes, both languages (Conversation screen) ==")
            for theme in THEMES:
                set_theme(base_url, theme)
                for lang in LANGUAGES:
                    url = f"{base_url}/?lang={lang}"
                    page.goto(url, wait_until="networkidle")
                    page.wait_for_timeout(300)
                    page.wait_for_function("document.fonts.status === 'loaded'", timeout=5000)
                    document_theme = page.get_attribute("html", "data-theme")
                    assert document_theme == theme, f"{url}: theme={document_theme}, asked {theme}"
                    assert_the_frame_speaks(page.content(), lang, SCREEN_KEYS["conversation"])
                    target = SHOTS / f"theme-{theme}-{lang}.png"
                    page.screenshot(path=str(target), full_page=True)
                    written.append(target)
                    say(f"  {target.name:<26} <- {url}  ({target.stat().st_size} bytes)")

            say("\n== 3. The installed copy outside the checkout serves the console ==")
            installed = install_out_of_tree(WORK)
            installed_port = free_port()
            frames = shots_from_installed(page, installed, installed_port, SHOTS, WORK)
            written.extend(frames)

            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=5)

    say("\n== 4. Every frame is a real render ==")
    thin = [p.name for p in written if p.stat().st_size < MIN_BYTES]
    say(f"  {len(written)} pictures written to {SHOTS}")
    if thin:
        say(f"ERROR: these look blank or unstyled (< {MIN_BYTES} bytes): {thin}")
        return 1
    for expected in (
        *(SHOTS / f"{lang}-{name}.png" for lang in LANGUAGES for name, _ in SCREENS),
        *(SHOTS / f"theme-{theme}-{lang}.png" for theme in THEMES for lang in LANGUAGES),
        *(SHOTS / f"installed-conversation-{lang}.png" for lang in LANGUAGES),
    ):
        assert expected.is_file(), f"missing frame: {expected}"

    say("\n== 5. Integrity check: owner files ==")
    after = fingerprint(WATCHED)
    problems = []
    for path, seen in before.items():
        if after.get(path) != seen:
            say(f"  CHANGED: {path}")
            problems.append(path)
        else:
            say(f"  unchanged: {path}")
    if problems:
        say(f"ERROR: owner files were modified by the check: {problems}")
        return 1

    say(f"\nW9 screenshot check completed: {len(written)} frames in {SHOTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
