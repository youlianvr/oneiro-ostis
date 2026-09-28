#!/usr/bin/env python3
"""Bring a fresh clone of this repository to a working product.

    python scripts/install.py                 # the whole path, from a clean clone
    python scripts/install.py --from-zip F    # use a local CowAgent 2.1.9 archive
    python scripts/install.py --check         # report what is in place, change nothing

What "working product" means here, and why each step exists:

  1. the console tree        CowAgent 2.1.9, released by someone else, unpacked
                             into this project's `.runtime/cowagent` - inside the
                             repository rather than beside it, so a clone is
                             self-contained and nothing depends on where the
                             project happens to sit on disk
  2. its virtualenv          with `--system-site-packages`, because the graph
                             client (`sc_client`) comes from the machine's own
                             Python, not from a package index. Created without
                             pip, and given pip afterwards: the normal bootstrap
                             runs during creation, before the platform seed can
                             protect it, and hangs on this machine's WMI (a
                             virtualenv creation was measured stuck for the
                             full 150 seconds, pip never reached)
  3. the product's overlay   the console files this repository owns - the chat
                             page under the Oneiro name, the settings page, the
                             sidebar entry, the Russian strings, the server
                             routes they call - applied by `console/overlay.py`
                             with drift detection instead of blind copying
  4. the console's config    created from the vendor template when missing, set
                             to the web channel on the product's own port
  5. the memory link         `scripts/host-wire.py --apply` puts this project's
                             MCP server into the console's `mcp.json`, so the
                             chat actually remembers through the graph
  6. the graph stack         Docker containers sc-web and sc-machine; the panel
                             reads the graph through them
  7. the desktop shortcut    one icon that starts the product

Every step is skipped when it is already done, and says which case it took.
Nothing is downloaded twice and nothing is overwritten that someone else edited.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent          # the project
WORKSPACE = HERE.parent.parent.parent
RUNTIME = HERE / ".runtime" / "cowagent"
SHORTCUT = Path.home() / "Desktop" / "Oneiro.lnk"
LAUNCHER = HERE / "scripts" / "oneiro-app.cmd"
# Copied into the console environment: see seed_platform.
WMI_SEED = HERE / "scripts" / "wmi-seed" / "sitecustomize.py"

RELEASE = "2.1.9"
ARCHIVE_URL = f"https://api.github.com/repos/zhayujie/CowAgent/zipball/{RELEASE}"
# Sources tried in order. The first one ships with the repository on purpose:
# a clone must be enough on its own, and this is the exact archive the overlay
# was built against, which `verify_release` proves below. The workspace path and
# the temp directory are this machine's conveniences, not requirements.
LOCAL_ARCHIVES = [
    HERE / "console" / "vendor" / f"cowagent-{RELEASE}.zip",
    WORKSPACE / "tools" / "upstream" / f"cowagent-{RELEASE}.zip",
    Path(tempfile.gettempdir()) / f"cowagent-{RELEASE}.zip",
]

# The console imports these; installed the same way the working machine has
# them.
PACKAGES = [
    "numpy", "markdown-it-py", "aiohttp>=3.10", "requests", "chardet", "Pillow",
    "python-dotenv", "PyYAML", "croniter", "click", "qrcode", "json-repair",
    "regex", "websocket-client", "legacy-cgi",
]
# `web.py` is not on PyPI for this Python, so it comes from its own repository,
# last and with `--no-build-isolation`: with isolation pip builds it in a
# throwaway environment whose hook never returns on this machine (measured: the
# hook was still hanging when killed at 240 seconds), while the same build in
# this environment - the one `seed_platform` protects - takes 20 seconds.
WEBPY = "web.py @ git+https://github.com/webpy/webpy.git"
BUILD_TOOLS = ["setuptools", "wheel"]      # needed by the step above

DATA_DIR = Path(os.environ.get("COW_DATA_DIR") or Path.home() / "cow" / "instance")


def say(step: str, message: str) -> None:
    print(f"[{step}] {message}", flush=True)


# ---------------------------------------------------------------- 1. the console tree

def unpack(archive: Path, into: Path) -> None:
    """Unpack a CowAgent zipball, dropping its single top-level directory."""
    into.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as staging:
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(staging)
        roots = [p for p in Path(staging).iterdir() if p.is_dir()]
        if len(roots) != 1:
            raise SystemExit(f"в архиве {archive} ожидался один корневой каталог, найдено {len(roots)}")
        for item in roots[0].iterdir():
            destination = into / item.name
            if destination.exists():
                shutil.rmtree(destination) if destination.is_dir() else destination.unlink()
            shutil.move(str(item), str(destination))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_release(into: Path) -> None:
    """The archive has to be the release the overlay was built against.

    If it is not, `overlay.py apply` would call every recorded file someone
    else's edit and refuse to touch it: technically correct, and useless as a
    diagnosis. Checking the recorded upstream hashes here says what actually
    happened: the wrong archive was unpacked.
    """
    manifest = json.loads((HERE / "console" / "manifest.json").read_text(encoding="utf-8"))
    checked = 0
    mismatched = []
    for entry in manifest["files"]:
        expected = entry.get("pristine_sha256")
        if not expected:
            continue
        checked += 1
        target = into / entry["path"]
        if not target.exists() or sha256(target) != expected:
            mismatched.append(entry["path"])
    if mismatched:
        raise SystemExit(
            "Консоль из этого архива не совпадает с той, под которую записан продукт: "
            + ", ".join(mismatched[:4]) + (" и др." if len(mismatched) > 4 else "")
            + f". Нужен CowAgent {manifest['upstream']['release']} "
            "(положите архив рядом или укажите --from-zip)."
        )
    say("1/7", f"архив совпал с {manifest['upstream']['name']} "
               f"{manifest['upstream']['release']}: проверено исходных файлов — {checked}")


def obtain_console(from_zip: Path | None, into: Path) -> Path:
    if (into / "app.py").exists():
        say("1/7", f"консоль уже распакована: {into}")
        return into

    archive = from_zip
    if archive is None:
        archive = next((p for p in LOCAL_ARCHIVES if p.exists()), None)
    if archive is not None:
        say("1/7", f"распаковываю локальный архив {archive.name}")
        unpack(archive, into)
        verify_release(into)
        return into

    say("1/7", f"скачиваю CowAgent {RELEASE} с github")
    into.parent.mkdir(parents=True, exist_ok=True)
    download = into.parent / f"cowagent-{RELEASE}.zip"
    request = urllib.request.Request(ARCHIVE_URL, headers={"User-Agent": "oneiro-installer"})
    with urllib.request.urlopen(request, timeout=120) as response, open(download, "wb") as out:
        shutil.copyfileobj(response, out)
    unpack(download, into)
    verify_release(into)
    return into


# ---------------------------------------------------------------- 2. the virtualenv

def venv_python(into: Path) -> Path:
    if os.name == "nt":
        return into / ".venv" / "Scripts" / "python.exe"
    return into / ".venv" / "bin" / "python"


def site_packages(python: Path) -> Path | None:
    """Where this interpreter looks for third-party code, asked of itself."""
    try:
        result = subprocess.run(
            [str(python), "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
            capture_output=True, text=True, timeout=60)
    except (subprocess.SubprocessError, OSError):
        return None
    lines = (result.stdout or "").strip().splitlines()
    return Path(lines[-1]) if result.returncode == 0 and lines else None


def seed_platform(python: Path) -> None:
    """Give the environment the platform seed, before anything can hang.

    pip and ensurepip call `platform.uname()`, which on this machine reaches
    the WMI service and never returns - a virtualenv creation was measured
    hanging for the full 150 seconds until it was killed, with the pip step
    never reached. The file copied here is the same answer the launcher seeds
    into the console process itself, one layer earlier and for every process
    this environment starts. On a healthy machine it changes nothing: the
    seeded values are what the question would have returned.
    """
    if not WMI_SEED.exists():
        say("2/7", f"нет лекарства от WMI: {WMI_SEED} (продолжаю как есть)")
        return
    target = site_packages(python)
    if target is None:
        say("2/7", "не удалось определить site-packages окружения — шлюз платформы не поставлен")
        return
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(WMI_SEED, target / "sitecustomize.py")


def ensure_pip(python: Path) -> None:
    """pip for this environment, when system-site-packages did not bring one.

    The environment is created with `--without-pip` on purpose: the normal
    bootstrap runs during creation, before `seed_platform` could protect it,
    and hangs here. Adding pip afterwards, with the seed already in place, is
    the same pip, one step later.
    """
    try:
        probe = subprocess.run([str(python), "-m", "pip", "--version"],
                               capture_output=True, text=True, timeout=120)
    except (subprocess.SubprocessError, OSError):
        probe = None
    if probe is not None and probe.returncode == 0:
        return
    say("2/7", "ставлю pip в само окружение (ensurepip)")
    subprocess.run([str(python), "-m", "ensurepip", "--upgrade"], check=True)


def venv_ok(into: Path) -> bool:
    """The environment we would have built, or a half-written one?

    A venv without system-site-packages does not see `sc_client`, and a run
    killed mid-way leaves exactly that silently behind. Reuse only what was
    asked for; rebuild anything else with `--clear`.
    """
    python = venv_python(into)
    config = into / ".venv" / "pyvenv.cfg"
    if not python.exists() or not config.exists():
        return False
    try:
        return "include-system-site-packages = true" in config.read_text(
            encoding="utf-8", errors="replace")
    except OSError:
        return False


def build_env(into: Path, skip_deps: bool) -> Path:
    python = venv_python(into)
    flags = ["--system-site-packages", "--without-pip"]
    if venv_ok(into):
        say("2/7", f"окружение уже создано: {python}")
    else:
        if (into / ".venv").exists():
            say("2/7", "найденное окружение неполное — пересоздаю")
            flags.append("--clear")
        else:
            say("2/7", "создаю окружение (с системными пакетами: оттуда берётся sc_client)")
        subprocess.run([sys.executable, "-m", "venv", *flags, str(into / ".venv")], check=True)
    seed_platform(python)

    if skip_deps:
        say("2/7", "пакеты пропущены по --skip-deps")
        return python
    ensure_pip(python)
    say("2/7", f"ставлю {len(PACKAGES)} пакетов и web.py из его репозитория "
              "(первый раз это несколько минут)")
    subprocess.run([str(python), "-m", "pip", "install", "--disable-pip-version-check",
                    "--quiet", *PACKAGES], check=True)
    # The build tools first, in their own step: pip resolves a command's list
    # before building anything from it, so they would not be there yet when
    # web.py's build needs them.
    subprocess.run([str(python), "-m", "pip", "install", "--disable-pip-version-check",
                    "--quiet", *BUILD_TOOLS], check=True)
    subprocess.run([str(python), "-m", "pip", "install", "--disable-pip-version-check",
                    "--quiet", "--no-build-isolation", WEBPY], check=True)
    return python


# ---------------------------------------------------------------- 3. the overlay

def apply_overlay(into: Path) -> None:
    result = subprocess.run([sys.executable, str(HERE / "console" / "overlay.py"),
                             "apply", "--vendor", str(into)],
                            capture_output=True, text=True)
    for line in (result.stdout or "").splitlines():
        say("3/7", line)
    if result.returncode != 0:
        for line in (result.stderr or "").splitlines():
            print(line, file=sys.stderr)
        raise SystemExit("оверлей не применён: файлы консоли изменены не нами (см. выше)")


# ---------------------------------------------------------------- 4. the console config

def seed_config(into: Path) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    config = DATA_DIR / "config.json"
    if config.exists():
        say("4/7", f"конфиг консоли на месте: {config}")
        return
    template = into / "config-template.json"
    settings = json.loads(template.read_text(encoding="utf-8")) if template.exists() else {}
    settings.update({"channel_type": "web", "cow_lang": "ru",
                     "web_host": "127.0.0.1", "web_port": 9899})
    config.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    say("4/7", f"конфиг консоли создан из шаблона: {config}")


# ---------------------------------------------------------------- 5. the memory link

def wire_memory(python: Path) -> None:
    script = HERE / "scripts" / "host-wire.py"
    result = subprocess.run([str(python), str(script), "--apply"],
                            capture_output=True, text=True)
    lines = (result.stdout or result.stderr or "").strip().splitlines()
    # The script's last line is the closing brace of the entry it prints; the
    # useful lines are which servers the host now has and whether it changed.
    summary = [line for line in lines
               if line.startswith(("servers in the target", "changed", "already current"))]
    say("5/7", " | ".join(summary[-2:]) if summary
        else (lines[-1] if lines else "host-wire не ответил"))
    if result.returncode != 0:
        say("5/7", "не удалось прописать память — консоль поднимется, но без графа")


# ---------------------------------------------------------------- 6. the graph stack

def check_graph(compose: bool) -> bool:
    try:
        out = subprocess.run(["netstat", "-ano"], capture_output=True, timeout=60).stdout or b""
    except (subprocess.SubprocessError, OSError):
        out = b""
    text = out.decode("utf-8", "replace")
    up = all(f":{port} " in text and "LISTENING" in text for port in (8000, 8090))
    if up:
        say("6/7", "стек графа поднят (sc-web 8000, sc-machine 8090)")
        return True
    if not compose:
        say("6/7", "стек графа не поднят (это --no-docker)")
        return False
    say("6/7", "поднимаю стек графа: docker compose up -d")
    result = subprocess.run(["docker", "compose", "up", "-d"], cwd=str(HERE),
                            capture_output=True, text=True)
    if result.returncode != 0:
        say("6/7", "docker не поднял стек — панель не сможет читать граф")
        return False
    say("6/7", "стек графа поднят")
    return True


# ---------------------------------------------------------------- 7. the shortcut

def make_shortcut() -> None:
    if SHORTCUT.exists():
        say("7/7", f"ярлык уже есть: {SHORTCUT}")
        return
    script = (
        '$s = New-Object -ComObject WScript.Shell; '
        f'$l = $s.CreateShortcut("{SHORTCUT}"); '
        f'$l.TargetPath = "{LAUNCHER}"; '
        f'$l.WorkingDirectory = "{HERE}"; '
        '$l.Description = "Oneiro: one address for chat, settings and the graph panel"; '
        '$l.Save()'
    )
    result = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                            capture_output=True, text=True)
    # cmd.exe, not Git Bash: bash rewrites a value like /oneiro=http://... into a
    # Windows path, and the launcher must pass it through untouched.
    say("7/7", f"ярлык создан: {SHORTCUT}" if result.returncode == 0
        else f"ярлык не создан ({result.stderr.strip()[:120]}); запускайте {LAUNCHER}")


# ---------------------------------------------------------------- the run

def check() -> int:
    into = RUNTIME
    python = venv_python(into)
    print(f"каталог продукта: {HERE}")
    print(f"консоль:          {'есть' if (into / 'app.py').exists() else 'нет'} ({into})")
    print(f"окружение:        {'есть' if python.exists() else 'нет'}")
    manifest = json.loads((HERE / "console" / "manifest.json").read_text(encoding="utf-8"))
    if (into / "app.py").exists():
        result = subprocess.run([sys.executable, str(HERE / "console" / "overlay.py"),
                                 "apply", "--vendor", str(into), "--dry-run"],
                                capture_output=True, text=True)
        print("оверлей:          " + (result.stdout.strip().splitlines()[-1]
                                      if result.stdout.strip() else "не проверен"))
    else:
        print(f"оверлей:          ждёт распаковки ({len(manifest['files'])} файлов записано)")
    print(f"конфиг консоли:   {'есть' if (DATA_DIR / 'config.json').exists() else 'нет'}")
    print(f"ярлык:            {'есть' if SHORTCUT.exists() else 'нет'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Установка Oneiro из свежего клона.")
    parser.add_argument("--from-zip", type=Path, default=None,
                        help="архив CowAgent 2.1.9 вместо скачивания")
    parser.add_argument("--into", type=Path, default=RUNTIME,
                        help="куда распаковать консоль (по умолчанию .runtime/cowagent)")
    parser.add_argument("--skip-deps", action="store_true", help="не ставить пакеты")
    parser.add_argument("--no-docker", action="store_true", help="не поднимать стек графа")
    parser.add_argument("--no-shortcut", action="store_true", help="не создавать ярлык")
    parser.add_argument("--check", action="store_true", help="только показать состояние")
    args = parser.parse_args()

    if args.check:
        return check()

    print("Установка Oneiro: свежий клон -> работающий продукт.")
    into = obtain_console(args.from_zip, args.into)
    python = build_env(into, args.skip_deps)
    apply_overlay(into)
    seed_config(into)
    wire_memory(python)
    check_graph(not args.no_docker)
    if not args.no_shortcut:
        make_shortcut()

    print()
    print("Готово. Дальше — ярлык Oneiro на рабочем столе (или scripts\\oneiro-app.cmd).")
    print("Продукт слушает http://127.0.0.1:9899 : чат, настройки Oneiro и панель графа на /oneiro/.")
    print("Модель для чата задаётся в настройках самой консоли.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
