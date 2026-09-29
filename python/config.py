"""One owner for every setting Oneiro reads.

The project used to read about fifteen differently-named environment variables
straight from the modules that needed them, and two names for one field: the
provider address was `ONEIRO_LLM_BASE_URL` in one place and `ONEIRO_BASE_URL`
in another, the key was `ONEIRO_LLM_API_KEY` here and `OMNIROUTE_API_KEY`
there. Nothing could offer real settings to a UI, because there was no single
place that knew what a setting *is*.

Declared here once: the key a human sees, the environment variable, the older
names still honoured, the type, the default, and the sentence that explains it.
A value is looked up in this order:

  1. the settings file  (``~/.openclaw/oneiro/settings.json``; what the UI writes)
  2. the environment    (what scripts and the workspace ``.env`` set)
  3. the declared default

The file wins over the environment on purpose: a value the owner saved in the
settings page must survive a shell that still exports the old one. Every read
also reports which layer answered, so the page can show *why* a value is what it
is instead of pretending a default is a stored preference.

Writes go through :func:`save`, which validates, coerces, touches only the keys
it is given, and replaces the file atomically. A corrupt file is reported rather
than silently ignored — :func:`describe` carries the error.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

SETTINGS_DIR = Path.home() / ".openclaw" / "oneiro"
SETTINGS_PATH = SETTINGS_DIR / "settings.json"


@dataclass(frozen=True)
class Setting:
    """One declared setting. The registry below is the whole truth about it.

    `label` and `help` are written in the product's user-facing language
    (English, per PLAN-V2 decision 1: one language for the product). The
    settings page shows them as they come; only the chrome around them is
    translated.
    """

    key: str
    env: str
    default: Any
    label: str
    help: str
    group: str
    kind: str = "str"           # str | int | bool | path | secret
    aliases: tuple[str, ...] = ()

    @property
    def secret(self) -> bool:
        return self.kind == "secret"

    @property
    def empty_means_unset(self) -> bool:
        """Paths fall back to their default when blank; a secret falls to env."""
        return self.kind in ("path", "secret")


SETTINGS: tuple[Setting, ...] = (
    Setting(
        "llm.base_url", "ONEIRO_LLM_BASE_URL", "http://127.0.0.1:20128/v1",
        "Provider address",
        "Address of an OpenAI-compatible provider. Any one that understands /chat/completions.",
        "Model", aliases=("ONEIRO_BASE_URL",),
    ),
    Setting(
        "llm.api_key", "ONEIRO_LLM_API_KEY", "",
        "Provider key",
        "Empty — looked up in environment variables and in a .env next to the project.",
        "Model", kind="secret", aliases=("ONEIRO_API_KEY", "OMNIROUTE_API_KEY"),
    ),
    Setting(
        "llm.model", "ONEIRO_LLM_MODEL", "auto/coding",
        "Default model",
        "The model for the researcher and worker roles.",
        "Model",
    ),
    Setting(
        "graph.host", "ONEIRO_HOST", "localhost",
        "Graph address",
        "The address of the OSTIS sc-machine.",
        "Graph",
    ),
    Setting(
        "graph.port", "ONEIRO_PORT", 8090,
        "Graph port",
        "The SCTP port of the OSTIS sc-machine.",
        "Graph", kind="int",
    ),
    Setting(
        "dashboard.port", "ONEIRO_DASH_PORT", 8130,
        "Panel port",
        "The port of the Oneiro panel and its settings API. Change only before restarting the panel.",
        "Interface", kind="int",
    ),
    Setting(
        "world.seed", "ONEIRO_SEED", "oneiro-0",
        "Island-world seed",
        "The same seed is a repeatable experiment. The workshop has its own seed, workshop-0.",
        "World",
    ),
    Setting(
        "loop.rounds", "ONEIRO_ROUNDS", 4,
        "Rounds per run",
        "How many self-improvement rounds one cycle run makes.",
        "Cycle", kind="int",
    ),
    Setting(
        "series.seeds", "ONEIRO_SEEDS", 5,
        "Seeds in a series",
        "How many seeds one series run walks through. The workshop uses the same.",
        "Cycle", kind="int",
    ),
    Setting(
        "workspace", "ONEIRO_WORKSPACE", "~/.openclaw/workspace",
        "Working folder",
        "The folder the agent disposes of, and where it looks for the skill catalog.",
        "Work", kind="path",
    ),
    Setting(
        "bench.dir", "ONEIRO_BENCH_DIR", "~/.openclaw/bench-memory",
        "Measurements folder",
        "Where memory benchmark runs are written.",
        "Measurements", kind="path",
    ),
    Setting(
        "bench.lme_dir", "ONEIRO_LME_DIR", "~/.openclaw/datasets/longmemeval",
        "LongMemEval dataset",
        "Where the dataset lives. It is not in the repository — it is too large.",
        "Measurements", kind="path",
    ),
    Setting(
        "mcp.source", "ONEIRO_MCP_SOURCE", "~/.openclaw/workspace/.mcp.json",
        "MCP server list",
        "The file the list of MCP servers for this machine is read from.",
        "Harness", kind="path",
    ),
)

_BY_KEY: dict[str, Setting] = {s.key: s for s in SETTINGS}
# Attribute spelling for the `settings` object: graph_port -> graph.port.
_ATTR: dict[str, str] = {s.key.replace(".", "_"): s.key for s in SETTINGS}

_lock = threading.Lock()
_cache: tuple[float, int, dict] | None = None   # (mtime, size, values)
_load_error: str = ""


def settings_path() -> Path:
    """Where the file lives. `ONEIRO_SETTINGS_FILE` moves it, for tests."""
    override = os.environ.get("ONEIRO_SETTINGS_FILE")
    return Path(override).expanduser() if override else SETTINGS_PATH


def _read_file() -> dict:
    """The file's contents, or an empty mapping with the reason recorded."""
    global _load_error, _cache
    file_path = settings_path()
    try:
        stat = file_path.stat()
    except OSError:
        _load_error = ""
        return {}
    with _lock:
        if _cache and _cache[0] == stat.st_mtime and _cache[1] == stat.st_size:
            return _cache[2]
    try:
        raw = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _load_error = f"{file_path}: {exc}"
        return {}
    if not isinstance(raw, dict):
        _load_error = f"{file_path}: the top level must be an object"
        return {}
    _load_error = ""
    with _lock:
        _cache = (stat.st_mtime, stat.st_size, raw)
    return raw


def _env_value(setting: Setting) -> str | None:
    for name in (setting.env, *setting.aliases):
        raw = os.environ.get(name)
        if raw is not None and raw != "":
            return raw
    return None


def _coerce(setting: Setting, value: Any) -> Any:
    """Turn a stored string into the declared type, or refuse with a reason."""
    if setting.kind == "int":
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            raise ValueError(
                f"{setting.key}: an integer was expected, got {value!r}"
            ) from None
    if setting.kind == "bool":
        return str(value).strip().lower() in ("1", "true", "yes", "on")
    return str(value).strip()


def _raw_layers(setting: Setting) -> tuple[Any, str]:
    """The value and the layer that answered, before emptiness is considered."""
    data = _read_file()
    if setting.key in data and data[setting.key] is not None:
        if not (setting.empty_means_unset and str(data[setting.key]).strip() == ""):
            return data[setting.key], "file"
    env = _env_value(setting)
    if env is not None:
        return env, "env"
    return setting.default, "default"


def resolve(key: str) -> tuple[Any, str]:
    """The value of one setting and which layer it came from."""
    setting = _BY_KEY.get(key)
    if setting is None:
        raise KeyError(f"unknown setting: {key!r}; known: {', '.join(_BY_KEY)}")
    raw, source = _raw_layers(setting)
    return _coerce(setting, raw), source


def value(key: str, default: Any = None) -> Any:
    """The resolved value of a setting; `default` only for unknown keys."""
    if key not in _BY_KEY:
        return default
    return resolve(key)[0]


def path(key: str) -> Path:
    """A path setting, with ``~`` expanded."""
    return Path(str(value(key))).expanduser()


def snapshot() -> dict[str, Any]:
    """Every setting, resolved, as one plain mapping."""
    return {s.key: resolve(s.key)[0] for s in SETTINGS}


class _Settings:
    """The resolved values as attributes: ``settings.graph_port``.

    Reading an attribute resolves it, so a long-lived process sees a saved
    change on its next read instead of holding the value it started with.
    Values come back as text or numbers — never a ``Path`` — so anything read
    here survives a trip through JSON. Ask `path()` when a path is wanted.
    """

    def __getattr__(self, name: str) -> Any:
        key = _ATTR.get(name)
        if key is None:
            raise AttributeError(f"no setting named {name!r}")
        return value(key)

    def path(self, key: str) -> Path:
        """One path setting, ``~`` expanded."""
        return path(key)

    def __dir__(self) -> list[str]:
        return sorted(_ATTR)


settings = _Settings()


def describe() -> dict:
    """Everything the settings page needs, with secrets never handed out."""
    rows = []
    for s in SETTINGS:
        stored = _read_file()
        raw, source = _raw_layers(s)
        in_file = s.key in stored and stored[s.key] is not None
        if s.secret:
            # The value is never described, only whether one is in force. An
            # empty field in the page must mean "leave it alone", never "write
            # these dots as the key".
            shown = ""
            changed = str(raw or "").strip() != ""
        else:
            shown = raw
            changed = str(raw) != str(s.default)
        rows.append({
            "key": s.key,
            "env": s.env,
            "label": s.label,
            "group": s.group,
            "kind": s.kind,
            "help": s.help,
            "value": shown,
            "default": "" if s.secret else s.default,
            "source": source,
            "changed": changed,
            "stored": in_file,
            "secret": s.secret,
            "set": bool(str(raw or "").strip()),
        })
    return {
        "settings": rows,
        "path": str(settings_path()),
        "writable": True,
        "error": _load_error,
    }


def save(patch: dict) -> dict:
    """Store the given keys, and only them. Returns the fresh description.

    Unknown keys and values of the wrong type are refused together, so a form
    with two mistakes comes back with two messages instead of one at a time.
    """
    if not isinstance(patch, dict):
        raise ValueError("a settings object was expected")
    unknown = [k for k in patch if k not in _BY_KEY]
    if unknown:
        raise ValueError(f"unknown settings: {', '.join(sorted(unknown))}")
    problems: list[str] = []
    coerced: dict[str, Any] = {}
    for key, raw in patch.items():
        try:
            coerced[key] = _coerce(_BY_KEY[key], raw)
        except ValueError as exc:
            problems.append(str(exc))
    if problems:
        raise ValueError("; ".join(problems))

    data = dict(_read_file())
    for key, val in coerced.items():
        # Blank clears the key rather than storing an empty override, so the
        # environment or the default can answer again.
        if str(val).strip() == "" and _BY_KEY[key].empty_means_unset:
            data.pop(key, None)
        else:
            data[key] = val

    path_ = settings_path()
    path_.parent.mkdir(parents=True, exist_ok=True)
    tmp = path_.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path_)
    global _cache
    with _lock:
        _cache = None
    return describe()


def reset(keys: Iterable[str] | None = None) -> dict:
    """Forget stored values: the named keys, or all of them if none are given."""
    data = dict(_read_file())
    if keys is None:
        data = {}
    else:
        for key in keys:
            if key not in _BY_KEY:
                raise ValueError(f"unknown setting: {key!r}")
            data.pop(key, None)
    path_ = settings_path()
    path_.parent.mkdir(parents=True, exist_ok=True)
    tmp = path_.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path_)
    global _cache
    with _lock:
        _cache = None
    return describe()


def main(argv: list[str] | None = None) -> int:
    """`python python/config.py` — what every setting is and who answered."""
    import argparse

    parser = argparse.ArgumentParser(description="Oneiro settings: read, set, list")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--set", nargs="*", metavar="KEY=VALUE", help="store values")
    parser.add_argument("--reset", nargs="*", metavar="KEY", help="forget stored values")
    args = parser.parse_args(argv)

    try:
        if args.set:
            patch = {}
            for item in args.set:
                if "=" not in item:
                    raise ValueError(f"KEY=VALUE was expected, got {item!r}")
                k, v = item.split("=", 1)
                patch[k.strip()] = v
            save(patch)
        if args.reset is not None:
            reset(args.reset or None)
    except ValueError as exc:
        print(f"error: {exc}")
        return 2

    description = describe()
    if args.json:
        print(json.dumps(description, ensure_ascii=False, indent=2))
        return 0
    print(f"file: {description['path']}")
    if description["error"]:
        print(f"error: {description['error']}")
    group = None
    for row in description["settings"]:
        if row["group"] != group:
            group = row["group"]
            print(f"\n{group}")
        print(f"  {row['key']:<20} {str(row['value']):<40} [{row['source']}] {row['help']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
