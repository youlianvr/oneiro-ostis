#!/usr/bin/env python3
"""One click, one program: the console, with the Oneiro panel underneath it.

    python scripts/oneiro-app.py            # start (Ctrl+C stops both)
    python scripts/oneiro-app.py --check    # what is running, without starting
    python scripts/oneiro-app.py --stop     # stop both

The console is the program the owner sees: it serves the only address the
browser is given and proxies /oneiro/ to the panel (see `oneiro_proxy.py` for
why the panel keeps its own process). This launcher exists so that the two
start and stop as one thing, and so the environment they need is set in one
place instead of being retyped at a prompt.

Output is Russian because the person who runs this is the owner, not a
programmer; comments and the code stay English like the rest of the project.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import runpy
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent          # the project
WORKSPACE = HERE.parent.parent.parent                  # .openclaw/workspace


def find_console() -> Path:
    """Where the console tree lives.

    The installer unpacks it inside the project, which is what makes a fresh
    clone self-contained. A machine that already ran the product out of the
    workspace vendor tree keeps working from there, so both are searched.

    A runnable console is one with its environment: unpacking without the
    virtualenv is a half-finished install, and the vendor tree is a better
    answer than a tree that cannot start. The check mirrors scripts/oneiro-app.cmd,
    so the shim and this script never disagree about which tree the product is.
    """
    candidates = [HERE / ".runtime" / "cowagent",
                  WORKSPACE / "tools" / "upstream" / "cowagent"]
    for candidate in candidates:
        if (candidate / "app.py").exists() and (candidate / ".venv" / "Scripts" / "python.exe").exists():
            return candidate
    for candidate in candidates:
        if (candidate / "app.py").exists():
            return candidate
    return candidates[0]


CONSOLE = find_console()
CONSOLE_PYTHON = CONSOLE / ".venv" / "Scripts" / "python.exe"
STATE = HERE / "state"

DEFAULT_PANEL_PORT = 8130
DEFAULT_CONSOLE_PORT = 9899
PANEL_START_TIMEOUT = 60.0


WMI_SEED = HERE / "scripts" / "wmi-seed" / "sitecustomize.py"


def seed_platform_cache() -> None:
    """Answer `platform` from memory instead of asking WMI, which can hang.

    cheroot - the WSGI server both the console and the panel sit on - calls
    `platform.system()` while it imports, and on this machine that call reaches
    WMI and never comes back: the console then stops at "Starting channels"
    with no port ever bound. Measured: `import cheroot.server` does not return
    within 45 seconds without the seed and takes 0.19 seconds with it.

    The answer itself lives in `scripts/wmi-seed/sitecustomize.py`, which is
    also the copy every installed environment gets (see `scripts/install.py`),
    so the console process and everything it starts agree. Loaded by path
    rather than imported by name, because outside a virtualenv it has no
    importable name of its own.
    """
    if not WMI_SEED.exists():
        print(f"Нет обхода зависшего WMI ({WMI_SEED}) — консоль может не подняться.")
        return
    spec = importlib.util.spec_from_file_location("oneiro_wmi_seed", WMI_SEED)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.seed()


def mount_panel(spec: str) -> None:
    """Make the console serve /oneiro/* from the panel process.

    Done by wrapping the console's WSGI application from the outside rather
    than by editing the console's source. The vendor tree is upstream's, and an
    edit inside it is lost the moment that release is unpacked again; this
    lives in the one repository that is the product, so reinstalling upstream
    cannot take the mount away.

    `wsgifunc` is what builds the WSGI callable the console hands to its
    server, and it is called exactly once per application, which makes it a
    stable seam to wrap. In web.py `web.application` is the class itself, not
    the module of the same name.

    This raises rather than degrading: a product whose settings page and graph
    panel are silently missing is not the product, and a window that says why
    is worth more than one that half works.
    """
    import web
    sys.path.insert(0, str(HERE))
    from oneiro_proxy import wrap

    application_class = web.application
    original = application_class.wsgifunc

    def wsgifunc(self, *middleware):
        return wrap(original(self, *middleware), spec)

    application_class.wsgifunc = wsgifunc
    print("Панель графа будет отдаваться этой же консолью на /oneiro/.")


def port_of(env_name: str, default: int) -> int:
    try:
        return int(os.environ.get(env_name) or default)
    except ValueError:
        return default


def panel_answers(port: int, timeout: float = 2.0) -> bool:
    """The panel is up if its settings route answers; nothing else is trusted."""
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/settings", timeout=timeout
        ) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def port_busy(port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def start_panel(port: int) -> subprocess.Popen | None:
    """Start the panel unless one already answers; return it only if we own it."""
    if panel_answers(port):
        print(f"Панель Oneiro уже работает на порту {port} — беру её как есть.")
        return None
    if port_busy(port):
        print(f"Порт {port} занят, но панель не отвечает: освободите его и повторите.")
        return None

    STATE.mkdir(exist_ok=True)
    log = open(STATE / "panel.log", "ab", buffering=0)
    env = dict(os.environ, ONEIRO_DASH_PORT=str(port))
    child = subprocess.Popen(
        [str(CONSOLE_PYTHON), str(HERE / "dashboard" / "server.py")],
        cwd=str(HERE), env=env, stdout=log, stderr=log, stdin=subprocess.DEVNULL,
    )
    deadline = time.time() + PANEL_START_TIMEOUT
    while time.time() < deadline:
        if child.poll() is not None:
            print("Панель Oneiro не поднялась — подробности в state/panel.log.")
            return None
        if panel_answers(port):
            print(f"Панель Oneiro поднята на порту {port}.")
            return child
        time.sleep(1)
    print("Панель Oneiro не ответила за минуту — запускаю консоль без неё.")
    return child


def stop_process(pid: int, label: str) -> None:
    """Stop-Process, not taskkill: taskkill hangs on this machine by itself."""
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"Stop-Process -Id {pid} -Force -ErrorAction SilentlyContinue"],
        capture_output=True, timeout=30,
    )
    print(f"Остановлено: {label} (процесс {pid}).")


def listening_ports() -> dict[int, int]:
    """Every local listener as port -> pid.

    Netstat's output is decoded leniently on purpose: it is written in the
    console's own codepage, which is not UTF-8 here, and a strict decode
    raises on exactly the bytes that would have answered the question.
    """
    try:
        raw = subprocess.run(["netstat", "-ano"], capture_output=True,
                             timeout=60).stdout or b""
    except (subprocess.SubprocessError, OSError):
        return {}
    found: dict[int, int] = {}
    for line in raw.decode("utf-8", "replace").splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[3] == "LISTENING":
            try:
                found[int(parts[1].rsplit(":", 1)[1])] = int(parts[4])
            except (ValueError, IndexError):
                continue
    return found


def pid_on(port: int) -> int | None:
    return listening_ports().get(port)


def check(panel_port: int, console_port: int) -> int:
    """Report what is up. Says what it measured, never what it assumes."""
    listening = listening_ports()
    if 8000 in listening and 8090 in listening:
        print("Стек графа (8000 sc-web, 8090 sc-machine): поднят.")
    else:
        print("Стек графа (8000 sc-web, 8090 sc-machine): не поднят — "
              "панель не сможет читать граф (docker compose up).")
    if panel_answers(panel_port):
        print(f"Панель Oneiro: работает на порту {panel_port}.")
    else:
        print(f"Панель Oneiro: не отвечает на порту {panel_port}.")
    pid = listening.get(console_port)
    print(f"Консоль: {'работает' if pid else 'не работает'} на порту {console_port}"
          + (f" (процесс {pid})." if pid else "."))
    return 0


def stop(panel_port: int, console_port: int) -> int:
    stopped = False
    listening = listening_ports()
    for port, label in ((console_port, "консоль"), (panel_port, "панель Oneiro")):
        pid = listening.get(port)
        if pid:
            stop_process(pid, label)
            stopped = True
    if not stopped:
        print("Останавливать нечего: ни консоль, ни панель не слушают свои порты.")
    return 0


def run(panel_port: int, console_port: int) -> int:
    seed_platform_cache()

    os.environ.setdefault("COW_DATA_DIR", str(Path.home() / "cow" / "instance"))
    os.environ.setdefault("ONEIRO_PROJECT", str(HERE))
    os.environ.setdefault(
        "ONEIRO_PROXY", f"/oneiro=http://127.0.0.1:{panel_port}"
    )
    os.environ.setdefault("COW_WEB_PORT", str(console_port))

    mount_panel(os.environ["ONEIRO_PROXY"])
    panel = start_panel(panel_port)
    print(f"Адрес продукта: http://127.0.0.1:{console_port}  (панель графа на нём же: /oneiro/)")
    print("Остановить: Ctrl+C в этом окне.")
    try:
        # The console runs in this process, so "one program" is literal for
        # everything the owner starts and stops; the panel is the only child.
        #
        # Its directory goes on sys.path explicitly: `python app.py` would add
        # the script's own directory for us, but runpy does not, and the
        # console imports its packages (channel, bridge, common) by bare name.
        os.chdir(CONSOLE)
        sys.path.insert(0, str(CONSOLE))
        sys.argv = ["app.py"]
        runpy.run_path(str(CONSOLE / "app.py"), run_name="__main__")
    except KeyboardInterrupt:
        print("Остановка по запросу владельца.")
    finally:
        if panel is not None:
            stop_process(panel.pid, "панель Oneiro")
        else:
            print("Панель Oneiro не была поднята этим запуском — оставляю как есть.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Oneiro как одна программа: консоль и панель вместе.")
    parser.add_argument("--check", action="store_true",
                        help="показать, что работает, и выйти")
    parser.add_argument("--stop", action="store_true",
                        help="остановить консоль и панель")
    args = parser.parse_args()

    panel_port = port_of("ONEIRO_DASH_PORT", DEFAULT_PANEL_PORT)
    console_port = port_of("COW_WEB_PORT", DEFAULT_CONSOLE_PORT)

    if not CONSOLE_PYTHON.exists():
        print(f"Не найдено окружение консоли: {CONSOLE_PYTHON}")
        print("Похоже, Oneiro ещё не установлен в этой копии проекта.")
        print("Запустите один раз:  python scripts/install.py")
        return 2
    if args.check:
        return check(panel_port, console_port)
    if args.stop:
        return stop(panel_port, console_port)
    return run(panel_port, console_port)


if __name__ == "__main__":
    raise SystemExit(main())
