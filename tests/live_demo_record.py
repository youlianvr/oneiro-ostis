"""The fallback recording for the 14 October show (plan P6).

Run it with:

    python tests/live_demo_record.py [--marker WORD]

It answers one question: **if the live show fails in the room, is there something
real to play instead of an apology?** So it records, and it keeps what it records
honest about itself:

* the video is written by the browser driver's own recorder (Playwright), from a
  real Chromium session on the product's own pages — not a log renamed `.webm`;
* everything on screen belongs to this run: its own data root, its own settings
  file, its own MCP list, its own graph container made from the shipped image,
  and the **test** mailbox and bot servers (`live_drafts_check`'s fake stdio
  servers). No owner record, no real account and no real Telegram appears in any
  frame, and the owner's data root is hashed before and after to show that;
* the whole spoken chain is covered, not only the browser part: the **signed webhook**
  is delivered by this recording into the console of this run's own root, signed with
  the secret that console generated over the exact bytes sent, and the task it creates
  is read back out of the graph by its id and shot in the panel's journal (the refusals
  the talk names — no signature, a stranger's key, this key over other bytes — are sent
  as real calls and refused by name); the **office job** is run by the product's own
  command into this run's own folder, its produced files are checked on disk and a page
  of the produced PDF is rendered from that very file; and the **independent graph
  read** is the product's own reader, whose exit code is kept;
* the press on the draft is a click in that browser, on the screen the owner
  presses, through the test transport — the same moment the live show turns on;
* the office step is this run's own: the product's command converts the sources in
  the shipped container, the files that come out are checked against the size the
  job reported, and one produced PDF is shown as a picture rendered from that very
  file (the bundled headless browser downloads PDFs instead of displaying them, and
  renders no folder index). The durable artifacts viewer of the verified rehearsal
  is kept beside it, labelled as that page and not as this run's own;
* the file work happens before the console is started, and that is a measurement, not
  a preference: a console holds this root's writer lease (`graph-writer.lock`) while it
  runs, and the job's own publication needs that lease — with the console up, the job's
  graph write answers `graph_worker_failed`. So the job runs first, the console that is
  recorded starts afterwards and reads the records back from the graph;
* nothing is claimed about a model: the draft, the letter and the facts come from
  the product's own routes, not from a completion;
* four moments have no screen and are named instead of implied: the signed POST
  itself, the signatures that were refused, the conversion inside the office
  container, and the reader's printed page. The first is covered by its result (the
  task in the journal), the second by the status each call answered with and by the
  journal holding no such task, the third by the files on disk, the fourth by its exit
  code; a log is not presented as the UI.

Every frame is taken only after the product's own answer says what the frame
claims, and the recording is measured afterwards with `ffprobe`, decoded into
stills with `ffmpeg`, and opened in a browser to read its real duration — a file
whose length nobody measured is not evidence. The file is also asked about its own
contents: it is sampled once per second and every key screen is looked for in the
samples, so "the video shows this step" is a measurement of the artifact and not of
the code that took the frame. What was written is recorded in `record.json` next to
the files, each screen with the second of the recording it was found at.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

TESTS = Path(__file__).resolve().parent
PROJECT = TESTS.parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(PROJECT / "python"))

#: The demo's own test transport, private graph and console helpers. Importing it
#: runs no check: it only names this process's own run root.
import live_drafts_check as w3  # noqa: E402

from PIL import Image  # noqa: E402
import numpy  # noqa: E402

OUT = PROJECT / "docs" / "forumit-2026" / "demo-record"
#: Decoded stills, in a folder of this run's own: a flat folder would let one run's frame
#: pass for another's. `main` names the folder with this run's marker.
STILLS = OUT / "stills"
VIDEO_NAME = "oneiro-demo-run"
#: The talk's first entry point: a monitoring alert that arrives from outside the
#: conversation. The recording sends this delivery itself, into this run's own console.
HOOK = "monitor"
HOOK_TITLE = "Мониторинг: диск почти полон"
HOOK_DETAIL = "83% занято"
#: A key that is not this run's, and other bytes signed with the key that is.
STRANGER_KEY = b"a-key-that-is-not-the-one-in-force"
#: The verified rehearsal's artifacts, listed on their own durable page.
REHEARSAL = PROJECT / "docs" / "demo-artifacts" / "2026-10-13" / "index.html"
LANG = "ru"
VIEWPORT = {"width": 1280, "height": 720}
#: A frame smaller than this is a blank page or a broken stylesheet.
MIN_SHOT_BYTES = 5000
#: A decoded still flatter than this is a colour, not a screen.
MIN_STILL_STD = 4.0
#: How far a second of the recording may sit from a key screen and still be that screen.
#: Two different screens of this product differ by 40–98 in mean absolute pixel value
#: (measured), so a key found within this distance is the key, at that moment.
IN_VIDEO_TOLERANCE = 20.0
#: The same moments at the recorded window size, kept beside this run's own stills: an
#: element crop cannot be compared with a video frame, and a key screen that is *not* in
#: the file would otherwise be claimed by the code that took it. Set in `main`.
KEYVIEW: Path | None = None

FRAMES: list[dict] = []
CHECKS: list[dict] = []


def say(text: str = "") -> None:
    print(text, flush=True)


def check(label: str, ok: bool, detail: str = "") -> bool:
    CHECKS.append({"check": label, "ok": bool(ok), "detail": detail})
    say(f"  [{'ok ' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))
    return bool(ok)


def runner(name: str) -> str:
    return shutil.which(name) or ""


def probe(video: Path) -> dict:
    """What `ffprobe` says the file is: a real container with a real duration."""
    ffprobe = runner("ffprobe")
    if not ffprobe:
        return {"error": "ffprobe is not on this machine's PATH"}
    done = subprocess.run(
        [ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams",
         str(video)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    if done.returncode != 0:
        return {"error": (done.stderr or "").strip()[:200]}
    import json as _json
    payload = _json.loads(done.stdout or "{}")
    stream = next((row for row in payload.get("streams", [])
                   if row.get("codec_type") == "video"), {})
    fmt = payload.get("format", {})
    return {
        "duration_s": round(float(fmt.get("duration") or 0.0), 3),
        "size_bytes": int(fmt.get("size") or 0),
        "format": fmt.get("format_name", ""),
        "codec": stream.get("codec_name", ""),
        "width": int(stream.get("width") or 0),
        "height": int(stream.get("height") or 0),
        "frames": int(stream.get("nb_frames") or 0),
        "r_frame_rate": stream.get("r_frame_rate", ""),
    }


def to_mp4(video: Path, target: Path) -> dict:
    """An H.264 copy, so the file plays in whatever the room's machine has."""
    ffmpeg = runner("ffmpeg")
    if not ffmpeg:
        return {"error": "ffmpeg is not on this machine's PATH"}
    done = subprocess.run(
        [ffmpeg, "-y", "-loglevel", "error", "-i", str(video), "-c:v", "libx264",
         "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-movflags",
         "+faststart", str(target)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    if done.returncode != 0:
        return {"error": (done.stderr or "").strip()[:200]}
    return probe(target)


def stills_from(video: Path, stamps: list[float]) -> list[dict]:
    """Decoded frames at given moments: proof the file carries pictures, not a colour."""
    ffmpeg = runner("ffmpeg")
    if not ffmpeg:
        return []
    STILLS.mkdir(parents=True, exist_ok=True)
    rows = []
    for index, stamp in enumerate(stamps, 1):
        target = STILLS / f"at-{stamp:05.1f}s.png"
        done = subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", "-ss", f"{stamp:.2f}", "-i", str(video),
             "-frames:v", "1", str(target)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
        if done.returncode != 0 or not target.is_file():
            rows.append({"stamp_s": stamp, "file": "", "error":
                         (done.stderr or "no frame").strip()[:160]})
            continue
        with Image.open(target) as image:
            pixels = numpy.asarray(image.convert("RGB"), dtype="float32")
            pixels_size = list(image.size)
        rows.append({"stamp_s": stamp, "file": str(target.relative_to(PROJECT)).replace("\\", "/"),
                     "bytes": target.stat().st_size, "pixels": pixels_size,
                     "mean": round(float(pixels.mean()), 2), "std": round(float(pixels.std()), 2)})
    return rows


def run_step(label: str, command: list[str], env: dict[str, str], *, run_root: Path,
             timeout: int = 900) -> tuple[int, str]:
    """One real product path in its own process, with its log and its exit code kept."""
    log = run_root / f"{label}.log"
    # `-c` code gets no project on its path of its own, and the demo's own runner passes
    # the same two directories: the product's package and the live checks' helpers.
    env = {**env, "PYTHONPATH": os.pathsep.join((str(PROJECT / "python"), str(TESTS))),
           "PYTHONIOENCODING": "utf-8"}
    done = subprocess.run([sys.executable, "-u", *command], cwd=str(PROJECT), env=env,
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout)
    output = (done.stdout or "") + (done.stderr or "")
    log.write_text(output, encoding="utf-8")
    say(f"    {label}: exit {done.returncode} ({len(output)} characters, log {log.name})")
    return done.returncode, output


def json_tail(output: str) -> dict:
    """The last JSON object a command printed, or nothing.

    The office command prints its report after whatever else the job says, so the
    report is read from the last `{` that parses rather than from the whole output.
    """
    for start in range(len(output) - 1, -1, -1):
        if output[start] != "{":
            continue
        try:
            parsed = json.loads(output[start:])
        except ValueError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def video_frames(video: Path, folder: Path) -> list[tuple[int, Path]]:
    """One picture per second of the recording, so a claim about the file can be checked.

    A key screen says what was on screen when it was taken; it does not say the file
    carries it. Sampling the file and looking for each key in it is what turns "the video
    shows this step" from a property of the code into a measurement of the artifact.
    """
    ffmpeg = runner("ffmpeg")
    if not ffmpeg:
        return []
    folder.mkdir(parents=True, exist_ok=True)
    done = subprocess.run(
        [ffmpeg, "-y", "-loglevel", "error", "-i", str(video), "-vf", "fps=1",
         str(folder / "second-%04d.png")],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    if done.returncode != 0:
        say(f"    sampling the video failed: {(done.stderr or '').strip()[:160]}")
        return []
    return [(index, path) for index, path in enumerate(sorted(folder.glob("second-*.png")), 1)]


def best_frame(key: Path, frames: list[tuple[int, Path]]) -> dict:
    """The second of the recording that is this key screen, and how far it is from it."""
    with Image.open(key) as image:
        size = image.size
        target = numpy.asarray(image.convert("RGB"), dtype="float32")
    best: dict = {"second": None, "difference": None}
    for second, path in frames:
        with Image.open(path) as image:
            if image.size != size:
                continue
            frame = numpy.asarray(image.convert("RGB"), dtype="float32")
        difference = float(numpy.abs(frame - target).mean())
        if best["difference"] is None or difference < best["difference"]:
            best = {"second": second, "difference": round(difference, 2)}
    return best


def office_pages(pdf: Path, target: Path, limit: int = 2) -> dict:
    """How many pages the produced PDF has, and its first pages as pictures.

    The browser that records this cannot display a PDF at all (it downloads the file
    instead), so a page of the produced document is shown as a picture rendered from
    that file with PyMuPDF — and the page count is measured, not assumed.
    """
    try:
        import fitz                                        # PyMuPDF, as the deck uses
    except ImportError as exc:
        return {"error": f"PyMuPDF is not installed: {exc}"}
    rendered = []
    with fitz.open(pdf) as document:
        pages = document.page_count
        for index in range(min(limit, pages)):
            page = document.load_page(index)
            picture = target.with_name(f"{target.stem}-p{index + 1}.png")
            page.get_pixmap(dpi=110).save(str(picture))
            rendered.append({"page": index + 1, "file": str(picture.relative_to(PROJECT))
                             .replace("\\", "/"), "bytes": picture.stat().st_size})
    return {"pdf": str(pdf.relative_to(PROJECT)).replace("\\", "/"), "pages": pages,
            "rendered": rendered, "bytes": pdf.stat().st_size}


def show_file(page, path: Path, *, pause: float, target: Path, note: str) -> dict:
    """A file opened in the browser: a picture of a produced document, not a page.

    The product's screens are opened with `visit`, which asserts the language the
    panel declares. A file has no such declaration, so it is opened plainly — and
    what the frame is stays in its `note`.
    """
    page.set_viewport_size(VIEWPORT)
    page.goto(path.as_uri(), wait_until="load")
    page.wait_for_timeout(int(pause * 1000))
    row = shot(page, target)
    row.update({"route": path.as_uri(), "note": note,
                "opened": str(path.relative_to(PROJECT)).replace("\\", "/")})
    return row


def shot(page, target: Path, *, element: str = "") -> dict:
    """One key screen, taken after the page has already said what it is."""
    target.parent.mkdir(parents=True, exist_ok=True)
    where = page.locator(element).first if element else None
    if where is not None:
        where.wait_for(state="visible", timeout=15_000)
        where.screenshot(path=str(target))
    else:
        page.screenshot(path=str(target), full_page=True)
    size = target.stat().st_size
    if size < MIN_SHOT_BYTES:
        raise AssertionError(f"{target.name} is {size} bytes: a blank frame is not evidence")
    with Image.open(target) as image:
        pixels = image.size
    # The same moment at the recorded window size: the video is sampled afterwards and each
    # key screen is looked for in it, and an element crop is not comparable with a frame.
    if KEYVIEW is not None:
        KEYVIEW.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(KEYVIEW / f"{target.stem}.png"))
    text = " ".join((page.locator("body").inner_text() if where is None else where.inner_text()).split())
    row = {"file": str(target.relative_to(PROJECT)).replace("\\", "/"), "url": page.url,
           "element": element or "whole page", "bytes": size, "pixels": list(pixels),
           "text_head": text[:240]}
    FRAMES.append(row)
    say(f"    {target.name:<34} {size:>8} bytes  {pixels[0]}x{pixels[1]} px")
    return row


def visit(page, base: str, route: str, *, pause: float, wait_for: str = "",
          must_show: tuple[str, ...] = (), element: str = "", target: Path | None = None,
          note: str = "") -> dict:
    """One screen: opened, waited for, asserted, held for the recording, shot."""
    url = f"{base}{route}"
    page.set_viewport_size(VIEWPORT)
    page.goto(url, wait_until="networkidle")
    page.wait_for_function("document.fonts.status === 'loaded'", timeout=15_000)
    assert page.get_attribute("html", "lang") == LANG, f"{url}: rendered lang is not {LANG}"
    if wait_for:
        page.wait_for_selector(wait_for, timeout=30_000)
    if must_show:
        page.wait_for_function(
            "needles => needles.every(n => document.body.innerText.includes(n))",
            arg=list(must_show), timeout=30_000)
    page.wait_for_timeout(int(pause * 1000))
    if target is None:
        return {"route": route}
    row = shot(page, target, element=element)
    row.update({"route": route, "note": note, "must_show": list(must_show)})
    return row


def office_step(world: dict, run_root: Path) -> dict:
    """The office job, and the independent read of its records, before any console starts.

    The job publishes its own records, and a console holds this root's writer lease
    (`graph-writer.lock`) for as long as it runs; the job's publication needs that same
    lease, so with a console up the job's graph write answers `graph_worker_failed`
    (measured 2026-10-13: the recording's first run reported `not_recorded`). The file
    work therefore happens first, and the console that is recorded starts afterwards and
    reads these records back out of the graph.

    Everything is this run's own: the isolated data root, the shipped container, its own
    folder, and the test transport as the only declared server. The graph read is the
    product's own reader in its own process, so its exit code is kept.
    """
    step_env = w3.base_env(world, web_port=w3.free_port())

    # ---- the office job, by the product's own command — real conversions in the
    # shipped container, its own folder, its own records.
    office_out = run_root / "office"
    office_code = (
        "from oneiro import office_env,cli; real=office_env._subprocess_runner; "
        "office_env._subprocess_runner=lambda argv,**kw: real(([argv[0],'stop','--time','20',"
        "argv[-1]] if argv[1:2]==['rm'] else argv),**kw); "
        "raise SystemExit(cli.main(['office','run','--topic','Oneiro: локальный форум',"
        f"'--out',{str(office_out)!r},'--stream','demo','--json']))"
    )
    office_exit, office_text = run_step("office", ["-c", office_code], step_env,
                                        run_root=run_root)
    office_report = json_tail(office_text)
    office_job = office_report.get("job") or {}
    office_files = []
    for item in office_job.get("artifacts") or []:
        path = Path(str(item.get("path") or ""))
        exists = path.is_file()
        office_files.append({
            "name": item.get("name"), "bytes": item.get("bytes"),
            "on_disk_bytes": path.stat().st_size if exists else 0,
            "pages": item.get("pages"), "sha256": item.get("sha256"),
            "file": str(path.relative_to(PROJECT)).replace("\\", "/") if exists else str(path),
        })
    good_files = [row for row in office_files
                  if row["on_disk_bytes"] and row["on_disk_bytes"] == row["bytes"]]
    check("the office job converted the sources and its files came out of the container",
          office_exit == 0 and len(office_files) >= 6 and len(good_files) == len(office_files),
          f"office exit {office_exit}; {len(office_files)} artifacts, {len(good_files)} "
          f"on disk with the size the job reported; pages "
          f"{[(row['name'], row['pages']) for row in office_files]}")
    check("the container that did the work is stopped, not removed",
          bool(office_job.get("stopped")),
          f"container {office_job.get('container')} stopped={office_job.get('stopped')}")
    office_records = [str(rid) for rid in office_report.get("records") or []]
    readback_exit, readback_text = run_step(
        "office-readback",
        [str(PROJECT / "scripts" / "office-graph-read.py"), "--stream", "demo",
         "--limit", "40"],
        step_env, run_root=run_root)
    found, candidates, why = w3.read_records("demo", office_records)
    check("the graph holds the office records: asked for by id, and by the shell reader",
          readback_exit == 0 and bool(office_records)
          and len(found) == len(office_records),
          f"reader exit {readback_exit}; by id {len(found)}/{len(office_records)} found "
          f"{why}" + ("" if candidates is None else f"; stream holds {candidates}"))
    said_in_log = [rid for rid in office_records if rid in readback_text]
    say(f"    office records: {len(office_records)} claimed, {len(found)} read back by id, "
        f"{len(said_in_log)} inside the reader's printed page")

    pdfs = [row for row in office_files if str(row["name"]).lower().endswith(".pdf")]
    chosen = next((row for row in pdfs if "slides" in str(row["name"]).lower()),
                  pdfs[0] if pdfs else None)
    office_picture: dict = {"chosen": chosen, "pages": {}}
    if chosen is not None:
        office_picture["pages"] = office_pages(PROJECT / str(chosen["file"]),
                                               OUT / "office-document.png")
        check("the produced PDF was rendered from its own file",
              bool(office_picture["pages"].get("rendered")),
              f"{chosen['name']}: {office_picture['pages'].get('pages')} pages, "
              f"{len(office_picture['pages'].get('rendered') or [])} rendered")
    else:
        check("the office job produced a PDF that can be shown", False,
              f"artifacts: {[row['name'] for row in office_files]}")
    return {
        "chosen": chosen, "office_files": office_files, "office_picture": office_picture,
        "office": {"exit": office_exit,
                   "command": "oneiro office run --topic … --out "
                              + str(office_out.relative_to(PROJECT)).replace("\\", "/")
                              + " --stream demo --json",
                   "container": office_job.get("container"),
                   "container_stopped": office_job.get("stopped"),
                   "artifacts": office_files,
                   "listing_inside_the_container": office_job.get("listing"),
                   "records_claimed": office_records,
                   "records_read_back_by_id": sorted(found),
                   "records_inside_the_readers_page": said_in_log,
                   "reader_exit": readback_exit},
    }


def http_call(port: int, path: str, body: bytes | None = None,
              headers: dict[str, str] | None = None) -> tuple[int, dict]:
    """One real HTTP call to this run's console, refusal or acceptance as it came."""
    call = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=body,
                                  headers=headers or {},
                                  method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(call, timeout=120) as response:
            raw = response.read().decode("utf-8", "replace")
            return response.status, (json.loads(raw) if raw.strip().startswith(("{", "["))
                                     else {"body": raw[:200]})
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", "replace")
        try:
            return error.code, json.loads(raw)
        except ValueError:
            return error.code, {"error": raw[:200]}


def webhook_step(port: int, world: dict, marker: str) -> dict:
    """A signed POST from outside the conversation becomes a task in this run's graph.

    The talk's first entry point, delivered here by the recording: the console of this
    run's own root generates the secret, and this process signs the exact bytes it sends
    with it — the product's own HMAC-SHA256 over the body that arrived. Three refusals
    the talk names are real calls too: no signature at all, a stranger's key, and this
    key over other bytes. Every one of them has no screen (an HTTP refusal is engineering
    evidence, not the product's UI), so what is shot is what the accepted delivery made:
    the task in the panel's journal. The secret itself is never printed — only its
    length and a fingerprint — and no task is created by a refused call.
    """
    secret_path = Path(str(world["root"])) / "runtime" / "hooks.secret"
    secret = b""
    waited = 0.0
    while waited < 20 and not secret:
        if secret_path.is_file():
            secret = secret_path.read_bytes().strip()
        else:
            time.sleep(0.25)
            waited += 0.25
    check("the console of this run generated its own hook secret", bool(secret),
          f"{secret_path.name}: {len(secret)} bytes, fingerprint "
          f"{hashlib.sha256(secret).hexdigest()[:12] if secret else 'none'}")

    body = json.dumps({"title": HOOK_TITLE, "detail": f"{HOOK_DETAIL} ({marker})",
                       "host": "db-1"}, ensure_ascii=False).encode("utf-8")
    other = json.dumps({"title": "Другое дело"}, ensure_ascii=False).encode("utf-8")

    def post(payload: bytes, signature: str | None) -> tuple[int, dict]:
        headers = {"Content-Type": "application/json"}
        if signature is not None:
            headers["X-Oneiro-Signature"] = signature
        return http_call(port, f"/api/hooks/{HOOK}", payload, headers)

    signature = hmac.new(secret, body, hashlib.sha256).hexdigest() if secret else ""
    refusals = []
    for what, call, expected in (
            ("no signature", post(body, None), "signature_absent"),
            ("a stranger's key",
             post(body, hmac.new(STRANGER_KEY, body, hashlib.sha256).hexdigest()),
             "signature_mismatch"),
            ("this key over other bytes", post(other, signature), "signature_mismatch")):
        status, answer = call
        refusals.append({"what": what, "http": status, "code": answer.get("code"),
                         "reason": answer.get("error")})
        check(f"{what} is refused by name",
              status == 401 and answer.get("code") == expected,
              f"HTTP {status} {answer.get('code')} — {answer.get('error')}")

    # The delivery's own status is kept under its own name: the journal read below answers
    # 200 as well, and reusing one variable would record the delivery as a 200 (measured
    # 2026-10-13: the first artifact claimed exactly that).
    accepted_status, answer = post(body, signature)
    task_id = str(answer.get("task_id") or "")
    check("the signed delivery became a task, answered by the console",
          accepted_status == 202 and task_id.startswith(f"task-hook-{HOOK}-")
          and answer.get("duplicate") is False,
          f"HTTP {accepted_status} task_id={task_id!r} duplicate={answer.get('duplicate')} "
          f"title={answer.get('title')!r}")

    status, journal = http_call(port, "/api/tasks")
    journal_text = json.dumps(journal, ensure_ascii=False)
    in_journal = HOOK_TITLE in journal_text
    titles = [row.get("title") for row in (journal.get("tasks") or [])]
    # One task with the accepted title, not two: a refused delivery that still made a task
    # would show here as a second entry beside the one the signed call created.
    check("the journal holds exactly the task the signed call made, and none from a refusal",
          status == 200 and in_journal and titles.count(HOOK_TITLE) == 1
          and titles.count("Другое дело") == 0,
          f"HTTP {status} titles={titles}")

    found, candidates, why = w3.read_records(w3.STREAM, [task_id])
    record = found.get(task_id) or {}
    check("the task is in the graph as a task record, read back by its own id",
          record.get("kind") == "task" and record.get("title") == HOOK_TITLE,
          f"kind={record.get('kind')} state={record.get('state')} "
          f"provenance={record.get('provenance')} title={record.get('title')!r}"
          + ("" if candidates is None else f"; stream holds {candidates}") + (f" {why}" if why else ""))
    say(f"    webhook: {HOOK_TITLE!r} -> {task_id}, in the journal and in the graph")
    return {"hook": HOOK, "endpoint": f"POST /api/hooks/{HOOK}",
            "title": HOOK_TITLE, "task_id": task_id,
            "secret": {"file": secret_path.name, "bytes": len(secret),
                       "fingerprint": hashlib.sha256(secret).hexdigest()[:12]},
            "refused": refusals,
            "accepted": {"http": accepted_status, "duplicate": answer.get("duplicate")},
            "answer": {key: answer.get(key) for key in ("hook", "client_id", "title",
                                                        "task_id", "duplicate")},
            "task_seen_in_journal": in_journal, "journal_titles": titles,
            "record_read_back_by_id": {key: record.get(key) for key in
                                       ("id", "kind", "state", "provenance", "title")},
            "stream_holds": candidates,
            "graph": {"container": w3.GRAPH_NAME}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--marker", default="",
                        help="a word of this run's own: a draft's id is the digest of "
                             "the call it would make, so a named marker keeps this run's "
                             "draft new")
    args = parser.parse_args()
    marker = args.marker or time.strftime("p6-%Y%m%d-%H%M%S")
    run_started = time.time()
    w3._this_run(marker)
    global KEYVIEW, STILLS
    KEYVIEW = PROJECT / "_tmp" / f"p6-keyview-{marker}"
    STILLS = OUT / "stills" / marker

    from oneiro import i18n
    labels = {
        "drafts": i18n.t("heading.waiting_drafts", LANG),
        "send": i18n.t("btn.send_draft", LANG),
        "sent": i18n.t("draft.sent", LANG),
        "memory": i18n.t("heading.curated_memory", LANG),
        "earlier": i18n.t("facts.earlier", LANG),
        "source": i18n.t("facts.source", LANG),
        "graph": i18n.t("graph.heading", LANG),
        "tasks": i18n.t("heading.active_tasks", LANG),
    }
    #: The graph screen prints the arcs it walked, so the frame is asserted on the
    #: sentence that does not depend on the count.
    readable_prefix = i18n.t("graph.readable", LANG, arcs=0).split(".")[0].strip()

    OUT.mkdir(parents=True, exist_ok=True)
    run_root: Path = w3.WORK
    say("== P6: the fallback recording of the demo ==")
    say(f"  this run: {marker}")
    say(f"  run root: {run_root}")
    say(f"  artifacts: {OUT}")

    world = w3.prepare(run_root / "asks", allow_sending=True)
    owner_before = w3.fingerprint(w3.OWNER_ROOT)

    graph_port = w3.free_port()
    started, detail = w3.start_private_graph(graph_port)
    if not started:
        say(f"  a graph of the demo's own could not be started: {detail}")
        return 1
    w3.use_graph(graph_port)
    say(f"  private graph: container {w3.GRAPH_NAME} on 127.0.0.1:{graph_port} ({detail})")
    graph_env = w3.base_env(world, web_port=0)
    ready, why = w3.wait_for_graph(graph_env)
    if not check("the run's own graph answers a read", ready, why):
        w3.stop_private_graph()
        return 1

    port = w3.free_port()
    process = log_path = handle = None
    ffprobe = mp4 = {}
    rows: list[dict] = []
    performed = {}
    try:
        # The office job first, then the console: a console holds this root's writer lease
        # for as long as it runs and the job's own publication needs it (measured). The
        # signed delivery goes to that console, so it comes after it is up.
        office = office_step(world, run_root)
        process, log_path, handle = w3.start_console(world, port)
        ready, why = w3.wait_ready(process, port)
        say(f"  console: pid {process.pid} on http://127.0.0.1:{port}")
        if not check("the console answered on its own port", ready, why):
            say(log_path.read_text(encoding="utf-8", errors="replace")[-1200:])
            return 1
        status, session = w3.request(port, "/api/session")
        token = str(session.get("csrf") or "")
        status, facts = w3.request(port, "/api/graph")
        if not check("the console reads this run's own graph",
                     status == 200 and facts.get("verified") is True,
                     f"/api/graph HTTP {status}: reachable={facts.get('reachable')} "
                     f"verified={facts.get('verified')}"):
            return 1
        status, overview = w3.request(port, "/api/mcp")
        names = sorted(row["name"] for row in overview.get("servers") or [])
        check("only the demo's two test servers are declared",
              names == ["bot", "mailbox"], f"{overview.get('file')}: {names}")

        # ---- the talked chain's first step: a signed POST from outside the conversation.
        # The office job's own records are already in the graph (they were written before
        # this console took the writer lease); what is left is to deliver, to refuse, and
        # to read the delivery back out of the graph.
        hook = webhook_step(port, world, marker)

        status, read = w3.request(port, "/api/mail/read",
                                  {"tool": w3.READ, "arguments": {"query": "is:unread"},
                                   "limit": 5}, token=token)
        check("the letter is read from the test mailbox, which is not a send",
              status == 200 and read.get("read") == 1 and w3.sends(world) == [],
              f"HTTP {status} read={read.get('read')} sends={len(w3.sends(world))}")

        status, draft = w3.request(port, "/api/drafts",
                                   {"tool": w3.MAIL,
                                    "arguments": {"to": w3.TO, "subject": w3.SUBJECT,
                                                  "body": w3.BODY},
                                    "source_id": "mail-m-1"}, token=token)
        draft_id = str(draft.get("id") or "")
        if not check("the draft waits for a press", status == 201
                     and draft.get("state") == "waiting", f"HTTP {status} {draft_id}"):
            return 1

        facts_written = []
        for client_id, text in (("p6-fact-0001", "Владелец пишет по-русски."),
                                ("p6-fact-0002", "Отчёты готовятся к пятнице.")):
            status, payload = w3.request(port, "/api/memory/facts",
                                         {"text": text, "client_id": client_id}, token=token)
            if status != 200:
                raise AssertionError(f"adding a fact failed: HTTP {status} {payload}")
            facts_written.append(payload["fact"]["id"])
        status, edited = w3.request(
            port, f"/api/memory/facts/{facts_written[0]}/edit",
            {"text": "Владелец пишет по-русски и по-английски.",
             "client_id": "p6-edit-0001", "revision": 1}, token=token)
        if status != 200:
            raise AssertionError(f"editing a fact failed: HTTP {status} {edited}")
        status, listing = w3.request(port, "/api/memory/facts")
        earlier = next((fact for fact in listing["facts"]
                        if fact["id"] == facts_written[0]), {}).get("superseded") or []
        check("the memory section holds a value an edit replaced",
              status == 200 and earlier and earlier[0].get("provenance")
              and earlier[0].get("updated_at"),
              f"earlier={earlier[0]['text']!r} source={earlier[0]['provenance']}")

        # The chain's own steps (the signed webhook and the office job) ran before this
        # console was started: the office job publishes its records to the graph, and this
        # graph image serves one client at a time, so no second client may be connected
        # while the job writes. What is left here is to read the delivery back from the
        # panel — the screen the room would be shown — and to shoot it.
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            check("the browser driver is installed", False, str(exc))
            return 1
        base = f"http://127.0.0.1:{port}"
        say("\n  recording the browser session...")
        video_path = ""
        try:
            with sync_playwright() as play:
                browser = play.chromium.launch()
                context = browser.new_context(viewport=VIEWPORT,
                                              record_video_dir=str(OUT),
                                              record_video_size=VIEWPORT)
                page = context.new_page()
                try:
                    visit(page, base, f"/?lang={LANG}", pause=3.0,
                          target=OUT / "key-01-console.png",
                          note="Экран чата панели: консоль этого прогона на своём порту.")
                    visit(page, base, f"/tasks?lang={LANG}", pause=4.0,
                          wait_for="#task-list .card-item",
                          must_show=(labels["tasks"], hook["title"]),
                          element=".screen-container",
                          target=OUT / "key-07-tasks-webhook.png",
                          note="Журнал: задача, которую создал подписанный вебхук, прочитана "
                               "из графа этого прогона.")
                    visit(page, base, f"/drafts?lang={LANG}", pause=4.0,
                          wait_for=f'[data-draft="{draft_id}"]',
                          must_show=(labels["drafts"], labels["send"]),
                          target=OUT / "key-02-drafts-before.png",
                          note="Черновик до нажатия: точные аргументы будущего вызова, "
                               "транспорт тестовый.")
                    card = page.locator(f'[data-draft="{draft_id}"]')
                    card.locator(".draft-send").click()
                    page.wait_for_function(
                        "id => document.querySelector('#draft-settled [data-draft=\"' + id"
                        " + '\"]') !== null", arg=draft_id, timeout=30_000)
                    page.wait_for_function(
                        "said => (document.querySelector('#draft-meter').textContent || '')"
                        ".includes(said)", arg=labels["sent"], timeout=30_000)
                    page.wait_for_timeout(4000)
                    after = shot(page, OUT / "key-03-drafts-after.png")
                    after.update({"route": "/drafts",
                                  "note": "Тот же экран после нажатия: отправлено, ровно один "
                                          "вызов в журнале тестового транспорта.",
                                  "must_show": [labels["sent"]]})
                    performed["drafts_after"] = after
                    performed["meter"] = " ".join(
                        page.locator("#draft-meter").inner_text().split())
                    visit(page, base, f"/memory?lang={LANG}", pause=4.0,
                          wait_for="#facts-list .fact-card",
                          must_show=(labels["memory"], labels["earlier"], labels["source"],
                                     "по-английски"),
                          element="#facts", target=OUT / "key-04-memory.png",
                          note="Раздел «Курируемая память»: два факта, источник и даты; "
                               "у первого — прежнее значение со своим источником.")
                    performed["graph_read"] = visit(
                        page, base, f"/oneiro/?lang={LANG}", pause=3.5,
                        must_show=(labels["graph"], readable_prefix),
                        target=OUT / "key-05-graph-read.png",
                        note="Экран «Подложка памяти»: что панель прочитала из графа этого "
                             "прогона (проверка доступности и обхода).")
                    rendered = office["office_picture"].get("pages", {}).get("rendered") or []
                    if rendered:
                        first = PROJECT / rendered[0]["file"]
                        performed["office_document"] = show_file(
                            page, first, pause=4.0, target=OUT / "key-08-office-document.png",
                            note=f"Первая страница {office['chosen']['name']}: PDF, выпущенный офисным "
                                 f"заданием этого прогона, показан изображением, "
                                 f"отрендеренным из самого файла — браузер записи PDF "
                                 f"не отображает, а скачивает.")
                    else:
                        check("a page of the produced document could be shown", False,
                              "nothing was rendered from the produced PDFs")
                    if REHEARSAL.is_file():
                        visit(page, REHEARSAL.as_uri(), "", pause=5.0,
                              must_show=("Открыть ODT", "Открыть XLSX", "Открыть PPTX"),
                              target=OUT / "key-06-office-listing.png",
                              note="Листинг офисных файлов: страница доказательств проверенного "
                                   "показа (docs/demo-artifacts/2026-10-13/) — шесть файлов "
                                   "настоящего LibreOffice в контейнере; это не пересъёмка, а та "
                                   "же страница.")
                    else:
                        check("the rehearsal's artifacts page exists", False, str(REHEARSAL))
                finally:
                    # Read the path even when a scene failed: the recorder's file is
                    # written when the context closes, and a session that stopped early
                    # still produced a real video — losing it to an exception would leave
                    # the *previous* run's file in place and report it as this run's.
                    video_path = page.video.path() if page.video else ""
                    context.close()
                    browser.close()
        except Exception as exc:                      # noqa: BLE001 - the failure is the result
            performed["error"] = f"{type(exc).__name__}: {exc}"
        performed["video_raw"] = video_path

        raw = Path(video_path) if video_path else Path()
        video = OUT / f"{VIDEO_NAME}.webm"
        if video_path and raw.is_file():
            raw.replace(video)
        if "error" in performed:
            check("the recorded session ran without an error", False, performed["error"])
        if not check("the recorder wrote a video file", video.is_file(),
                     f"{video.name}: {video.stat().st_size if video.is_file() else 0} bytes"):
            return 1
        # A file left behind by an earlier run would pass every check below while showing
        # nothing of this session, so its own timestamp is checked too.
        check("the video is this run's, not a file left by an earlier one",
              video.stat().st_mtime >= run_started - 5,
              f"written {time.strftime('%H:%M:%S', time.localtime(video.stat().st_mtime))}, "
              f"this run started {time.strftime('%H:%M:%S', time.localtime(run_started))}")
        ffprobe = probe(video)
        say(f"  ffprobe: {json.dumps(ffprobe, ensure_ascii=False)}")
        if not check("the video is a real container with a measured duration",
                     not ffprobe.get("error") and ffprobe.get("duration_s", 0) > 3,
                     f"{ffprobe.get('format')} {ffprobe.get('codec')} "
                     f"{ffprobe.get('width')}x{ffprobe.get('height')} "
                     f"{ffprobe.get('duration_s')} s"):
            return 1
        check("the video carries pictures at the recorded frame size",
              ffprobe.get("width") == VIEWPORT["width"]
              and ffprobe.get("height") == VIEWPORT["height"],
              f"{ffprobe.get('width')}x{ffprobe.get('height')} vs viewport "
              f"{VIEWPORT['width']}x{VIEWPORT['height']}")

        duration = float(ffprobe.get("duration_s") or 0)
        rows = stills_from(video, [1.0, max(2.0, duration * 0.3), max(3.0, duration * 0.6),
                                   max(4.0, duration - 1.0)])
        performed["stills"] = rows
        flat = [row for row in rows if row.get("std", 0) < MIN_STILL_STD]
        check("every decoded still is a screen, not a colour",
              bool(rows) and not flat,
              f"{len(rows)} stills; flat: {[row['stamp_s'] for row in flat]}")
        if len(rows) >= 2 and all(row.get("pixels") for row in rows):
            with Image.open(PROJECT / rows[0]["file"]) as first:
                a = numpy.asarray(first.convert("RGB"), dtype="float32")
            with Image.open(PROJECT / rows[-1]["file"]) as last:
                b = numpy.asarray(last.convert("RGB"), dtype="float32")
            moved = float(numpy.abs(a - b).mean())
        else:
            moved = 0.0
        check("the recording moves between screens", moved > 1.0,
              f"mean abs difference between the first and the last still: {moved:.2f}")

        mp4_path = OUT / f"{VIDEO_NAME}.mp4"
        mp4 = to_mp4(video, mp4_path)
        check("an H.264 copy also plays",
              not mp4.get("error") and mp4.get("duration_s", 0) > 3,
              f"{mp4_path.name}: {mp4.get('codec')} {mp4.get('duration_s')} s "
              f"{mp4.get('size_bytes')} bytes" if not mp4.get("error") else str(mp4.get("error")))

        # Opened the way a person would open it: a browser decoding the local file.
        # The page has to be a file of its own: an `about:blank` document is not allowed
        # to pull a `file://` video, and a refusal there would say nothing about the file.
        wrapper = PROJECT / "_tmp" / "p6-playback-check.html"
        wrapper.write_text(
            '<!doctype html><html lang="ru"><meta charset="utf-8">'
            f'<video id="v" src="{video.as_uri()}" controls></video>', encoding="utf-8")
        played = {}
        with sync_playwright() as play:
            browser = play.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": 900, "height": 620})
                page.goto(wrapper.as_uri(), wait_until="load")
                played = page.evaluate("""async () => {
                    const v = document.getElementById('v');
                    try {
                        await new Promise((ok, no) => {
                            if (v.readyState >= 1) return ok();
                            v.addEventListener('loadedmetadata', ok, {once: true});
                            v.addEventListener('error', () => no('media error ' +
                                (v.error ? v.error.code + ' ' + v.error.message : 'unknown')),
                                {once: true});
                            setTimeout(() => no('no metadata within 20 s; readyState=' +
                                v.readyState), 20000);
                        });
                    } catch (why) { return {problem: String(why)}; }
                    v.currentTime = Math.min(2, (v.duration || 0) / 2);
                    await new Promise(ok => { v.addEventListener('seeked', ok, {once: true});
                                              setTimeout(ok, 5000); });
                    return {duration: v.duration, width: v.videoWidth,
                            height: v.videoHeight, readyState: v.readyState,
                            currentTime: v.currentTime, problem: ''};
                }""")
            finally:
                browser.close()
        performed["browser_playback"] = played
        check("a browser opens the file and reads its duration",
              bool(played) and not played.get("problem") and played.get("duration", 0) > 3
              and played.get("width") == VIEWPORT["width"],
              f"duration={played.get('duration')} {played.get('width')}x"
              f"{played.get('height')} readyState={played.get('readyState')} "
              f"{played.get('problem', '')}")

        sends = w3.sends(world)
        servers = sorted({row.get("server", "") for row in w3.calls(world)})
        check("exactly one press went out, through the test transport only",
              len(sends) == 1 and sends[0]["arguments"].get("subject") == w3.SUBJECT
              and set(servers) <= {"mailbox", "bot"},
              f"sends={len(sends)} servers={servers} arguments="
              f"{json.dumps(sends[0]['arguments'], ensure_ascii=False)[:120] if sends else 'none'}")
        owner_after = w3.fingerprint(w3.OWNER_ROOT)
        check("no owner data was touched by the recording",
              owner_before == owner_after, f"{len(owner_after)} files, digests compared")
        performed["live_sends"] = len(sends)
        performed["transport_servers"] = servers
    finally:
        if handle is not None:
            handle.flush()
        if process is not None:
            code, how = w3.stop(process)
            say(f"  console exit {code} ({how})")
        stopped = w3.stop_private_graph()
        state = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Running}}", w3.GRAPH_NAME],
            capture_output=True, text=True, timeout=60, encoding="utf-8",
            errors="replace").stdout.strip()
        say(f"  graph {w3.GRAPH_NAME}: {stopped} (running={state})")
        check("the private graph is stopped, its container kept",
              state == "false", f"container {w3.GRAPH_NAME}")

    screens = [row for row in FRAMES]
    # Which of those screens the file carries: the recording is sampled once per second and
    # every key is looked for in it. A key that is not in the file is named as missing here
    # instead of being implied by the still that was taken while it was on screen.
    frames = video_frames(video, KEYVIEW.parent / f"{KEYVIEW.name}-seconds") \
        if KEYVIEW is not None else []
    for row in screens:
        key = (KEYVIEW / f"{Path(row['file']).stem}.png") if KEYVIEW is not None else None
        match = best_frame(key, frames) if key is not None and key.is_file() \
            else {"error": "no window-sized frame of this key was kept"}
        row["in_video"] = {**match, "sampled": len(frames)}
    in_video = [row for row in screens
                if isinstance(row["in_video"].get("difference"), float)
                and row["in_video"]["difference"] <= IN_VIDEO_TOLERANCE]
    check("every key screen is in the recording, found by sampling the file",
          bool(frames) and len(in_video) == len(screens),
          f"{len(frames)} one-second frames of {video.name}; "
          + ", ".join(f"{Path(row['file']).stem}@{row['in_video'].get('second')}s "
                      f"d={row['in_video'].get('difference')}" for row in screens))
    record = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "marker": marker,
        "command": "python tests/live_demo_record.py --marker " + marker,
        "run_root": str(run_root),
        "private_graph": {"container": w3.GRAPH_NAME, "port": graph_port},
        "transport": {"mailbox": "test stdio server", "bot": "test stdio server",
                      "servers_seen": performed.get("transport_servers", []),
                      "live_sends": performed.get("live_sends")},
        "console_port": port,
        "video": {"webm": str((OUT / f"{VIDEO_NAME}.webm").relative_to(PROJECT)).replace("\\", "/"),
                  "mp4": str((OUT / f"{VIDEO_NAME}.mp4").relative_to(PROJECT)).replace("\\", "/"),
                  "ffprobe_webm": ffprobe, "ffprobe_mp4": mp4,
                  "browser_playback": performed.get("browser_playback", {}),
                  "stills": performed.get("stills", []),
                  "viewport": VIEWPORT},
        "screens": screens,
        "office_listing": {"page": str(REHEARSAL.relative_to(PROJECT)).replace("\\", "/"),
                           "what_it_is": "the durable artifacts viewer of the verified "
                                         "rehearsal: six files made by a real LibreOffice in "
                                         "a container, shown beside this run's own"},
        "webhook": hook,
        "office": office["office"],
        "office_document": office["office_picture"],
        "no_screen_exists_for": [
            "the signed POST itself: an HTTP request has no screen; its result (the task in "
            "the journal) is what is shot",
            f"the refused deliveries ({', '.join(row['code'] or 'no code' for row in hook['refused'])}): "
            "a refusal is a status code and a named reason, and the console has no screen "
            "for it; the check reads the journal to show no task came of them",
            "the conversion inside the office container: the work happens in the container, "
            "so the files that came out and their own page render are shown instead",
            "the reader's printed page: a JSON page is engineering evidence, and this "
            "recording does not pass a log off as the product's UI",
        ],
        "checks": CHECKS,
    }
    (OUT / "record.json").write_text(json.dumps(record, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
    failed = [row for row in CHECKS if not row["ok"]]
    say("\n== summary ==")
    say(f"  checks: {len(CHECKS) - len(failed)}/{len(CHECKS)} passed")
    say(f"  video: {VIDEO_NAME}.webm — {ffprobe.get('duration_s')} s, "
        f"{ffprobe.get('width')}x{ffprobe.get('height')}, {ffprobe.get('codec')}")
    say(f"  screens: {len(screens)} key screens + {len(rows)} stills in {STILLS.name}/")
    say(f"  record: {(OUT / 'record.json').relative_to(PROJECT)}")
    for row in failed:
        say(f"  FAILED: {row['check']} — {row['detail']}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
