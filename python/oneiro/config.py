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

  1. the settings file  (``~/.oneiro/settings.json``; what the UI writes)
  2. the owner's keys file (``~/.config/keys.env``; one place for every key)
  3. the environment    (what scripts set)
  4. the project ``.env`` next to the repository (optional)
  5. the declared default

Everything Oneiro keeps for itself — settings, ownership files, the runtime
lock — lives under one root, :func:`data_root`. Settings written by the
pre-package location (``~/.openclaw/oneiro``, inside the agent workspace's
parent) are moved there on first read; see :func:`_migrate_legacy`.

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
import shutil
import tempfile
import threading
import uuid
from contextlib import contextmanager
from urllib.parse import urlsplit

from pathlib import Path
from typing import Any, Iterable

from oneiro.ownership import FileLease, OwnershipError
from oneiro.settings_registry import (DEFAULT_DATA_DIR, JSON_LISTS, SETTINGS, Setting,
                                      _ATTR, _BY_KEY)

SETTINGS_FILENAME = "settings.json"
# The repository's own .env, optional: two levels above python/oneiro/.
PROJECT_ENV = Path(__file__).resolve().parents[2] / ".env"
_lock = threading.RLock()   # guards the cache and a migration; see _read_file
_cache: tuple[str, int, int, dict] | None = None   # (path, mtime_ns, size, values)
_load_error: str = ""
_migrated_from: str = ""    # where settings were moved from, this process only


def data_root() -> Path:
    """The one directory Oneiro keeps its own state in.

    Answered by the environment (``ONEIRO_DATA_DIR``) or the default; never by
    the settings file, because the settings file is inside this directory and a
    file cannot relocate itself. ``runtime.data_dir`` declares the same value
    for the settings page; ``data_root`` is what the code reads.
    """
    override = os.environ.get("ONEIRO_DATA_DIR")
    return (Path(override) if override else Path(DEFAULT_DATA_DIR)).expanduser()


def settings_path() -> Path:
    """Where the file lives. `ONEIRO_SETTINGS_FILE` moves it, for tests."""
    override = os.environ.get("ONEIRO_SETTINGS_FILE")
    return Path(override).expanduser() if override else data_root() / SETTINGS_FILENAME


def _legacy_settings_path() -> Path:
    """Where the pre-package build kept settings, if it ever wrote any."""
    return Path.home() / ".openclaw" / "oneiro" / SETTINGS_FILENAME


def _migrate_legacy() -> None:
    """Move pre-package settings into the data root, once, without destroying.

    Skipped when `ONEIRO_SETTINGS_FILE` names a path: a test or a scripted run
    must never pick up the owner's real configuration. Nothing is deleted —
    files are moved, and the old directory goes only if it is left empty, so a
    lock marker or an unknown file keeps it alive for the owner to inspect.
    """
    global _migrated_from
    if os.environ.get("ONEIRO_SETTINGS_FILE"):
        return
    target = settings_path()
    legacy = _legacy_settings_path()
    with _lock:
        if target.exists() or not legacy.is_file():
            return
        # History first: it may hold credentials, and a half-moved history is
        # recoverable while a half-moved settings file would not be.
        source_history = legacy.parent / "settings-history"
        if source_history.is_dir():
            destination = target.parent / "settings-history"
            if not destination.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source_history), str(destination))
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                shutil.move(str(legacy), str(target))
        except OSError:
            return          # the old copy stays exactly where it was
        _migrated_from = str(legacy)
        try:
            legacy.parent.rmdir()      # only succeeds when nothing is left
        except OSError:
            pass


def _read_file() -> dict:
    """The file's contents, or an empty mapping with the reason recorded."""
    global _load_error, _cache
    file_path = settings_path()
    _migrate_legacy()
    try:
        stat = file_path.stat()
    except FileNotFoundError:
        _load_error = ""
        return {}
    except OSError:
        _load_error = "Settings file cannot be read"
        return {}
    identity = (str(file_path.resolve()), stat.st_mtime_ns, stat.st_size)
    with _lock:
        if _cache and _cache[:3] == identity:
            _load_error = ""
            return dict(_cache[3])
    try:
        raw = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _load_error = "Settings file is unreadable or invalid JSON"
        return {}
    if not isinstance(raw, dict):
        _load_error = f"{file_path}: the top level must be an object"
        return {}
    _load_error = ""
    with _lock:
        _cache = (*identity, raw)
    return raw


def _env_value(setting: Setting) -> str | None:
    for name in (setting.env, *setting.aliases):
        raw = os.environ.get(name)
        if raw is not None and raw != "":
            return raw
    return None


def keys_file() -> Path:
    """The owner's shared keys file. `ONEIRO_KEYS_FILE` moves it, for tests."""
    override = os.environ.get("ONEIRO_KEYS_FILE")
    return Path(override).expanduser() if override else Path.home() / ".config" / "keys.env"


def _read_key_file(file_path: Path) -> dict[str, str]:
    """NAME=value lines. Comments, blanks and an optional `export` are skipped.

    A missing or unreadable file is simply no values. Nothing is logged: the
    contents are credentials.
    """
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError:
        return {}
    values: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, raw = line.partition("=")
        name = name.strip().removeprefix("export ").strip()
        raw = raw.strip()
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
            raw = raw[1:-1]
        if name:
            values[name] = raw
    return values


def _file_value(file_path: Path, setting: Setting) -> str | None:
    values = _read_key_file(file_path)
    for name in (setting.env, *setting.aliases):
        raw = values.get(name)
        if raw:
            return raw
    return None


def _coerce(setting: Setting, value: Any) -> Any:
    """Turn a stored string into the declared type, or refuse with a reason."""
    if setting.kind == "int":
        try:
            parsed = int(str(value).strip())
        except (TypeError, ValueError):
            raise ValueError(f"{setting.key}: an integer was expected") from None
        # A port is 16 bits; a byte budget is deliberately larger than the
        # generic ceiling, because a 20 MB attachment limit is a sane default
        # and the writer must not refuse the value the page shows.
        if setting.key.endswith(".port"):
            maximum = 65535
        elif setting.key.endswith("_bytes"):
            maximum = 2_000_000_000
        else:
            maximum = 1000000
        if not 1 <= parsed <= maximum:
            raise ValueError(f"{setting.key}: expected 1..{maximum}")
        return parsed
    if setting.kind == "bool":
        token = str(value).strip().lower()
        if token not in ("1", "true", "yes", "on", "0", "false", "no", "off"):
            raise ValueError(f"{setting.key}: a boolean was expected")
        return token in ("1", "true", "yes", "on")
    if setting.kind == "choice":
        chosen = str(value).strip().lower()
        if chosen not in setting.choices:
            raise ValueError(
                f"{setting.key}: one of {', '.join(setting.choices)} was expected")
        return chosen
    if setting.kind == "json":
        return _json_value(setting, value)
    if not isinstance(value, str):
        raise ValueError(f"{setting.key}: text was expected")
    result = value.strip()
    if setting.key == "llm.base_url":
        parsed_url = urlsplit(result)
        if parsed_url.scheme not in ("http", "https") or not parsed_url.hostname or parsed_url.username or parsed_url.password or parsed_url.query or parsed_url.fragment:
            raise ValueError("llm.base_url: HTTP(S) URL without credentials/query required")
        try:
            parsed_url.port
        except ValueError:
            raise ValueError("llm.base_url: invalid port") from None
    if setting.key == "web.host" and result != "127.0.0.1":
        raise ValueError("web.host: foundation supports 127.0.0.1 only")
    if setting.key in ("graph.host", "llm.model", "llm.manager_model", "llm.researcher_model", "llm.executor_model") and not result:
        raise ValueError(f"{setting.key}: nonempty text required")
    return result


def _json_value(setting: Setting, value: Any) -> Any:
    """Parse and check a structured setting: provider records, lists of names.

    A blank value clears the key, the same way a blank path or secret does, so an
    emptied field can never be stored as a broken structure.
    """
    if isinstance(value, (list, dict)):
        data: Any = value
    else:
        text = str(value).strip()
        if not text:
            return ""
        try:
            data = json.loads(text)
        except ValueError:
            raise ValueError(f"{setting.key}: valid JSON was expected") from None
    if len(json.dumps(data, ensure_ascii=False)) > 64000:
        raise ValueError(f"{setting.key}: the value is too large")
    return _validate_json(setting.key, data)


def _validate_json(key: str, data: Any) -> Any:
    """What each structured setting means, beyond being valid JSON."""
    if key in JSON_LISTS:
        if not isinstance(data, list) or any(
                not isinstance(item, str) or not item.strip() for item in data):
            raise ValueError(f"{key}: a list of non-empty strings was expected")
        return [item.strip() for item in data]
    if key == "models.providers":
        if not isinstance(data, list) or not data:
            raise ValueError(f"{key}: a list of providers was expected")
        for item in data:
            if not isinstance(item, dict) or not str(item.get("name", "")).strip() \
                    or not str(item.get("base_url", "")).strip():
                raise ValueError(f"{key}: every provider needs a name and a base_url")
            if any(field not in ("name", "base_url", "key_env", "discover_models", "models",
                                 "enabled")
                   for field in item):
                raise ValueError(f"{key}: a provider has fields name, base_url, key_env, "
                                 f"discover_models, models, enabled")
        return data
    return data


def env_value(name: str) -> str:
    """One named variable out of the layers a secret setting falls through.

    A provider record names the variable that holds its key (`key_env`) instead of
    storing the key, so the registry has to ask for a name the catalog never declared.
    The order is the one `llm.api_key` already falls through — the owner's keys file,
    then the environment, then the project `.env` — and a name nobody set is empty text
    rather than an error, because a provider without a key is a provider without a key.
    """
    if not name:
        return ""
    raw = _read_key_file(keys_file()).get(name)
    if not raw:
        raw = os.environ.get(name)
    if not raw:
        raw = _read_key_file(PROJECT_ENV).get(name)
    return str(raw or "").strip()


def _raw_layers(setting: Setting) -> tuple[Any, str]:
    """The value and the layer that answered, before emptiness is considered."""
    data = _read_file()
    if setting.key in data and data[setting.key] is not None:
        if not (setting.empty_means_unset and str(data[setting.key]).strip() == ""):
            return data[setting.key], "file"
    keys = _file_value(keys_file(), setting)
    if keys is not None:
        return keys, "keys.env"
    env = _env_value(setting)
    if env is not None:
        return env, "env"
    project = _file_value(PROJECT_ENV, setting)
    if project is not None:
        return project, "project .env"
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


def _writable() -> tuple[bool, str]:
    """Whether the settings file can actually be written, and why not.

    Asked of the filesystem rather than assumed: an existing file is opened for
    writing without truncating it, and a directory that does not exist yet is
    probed with a temporary file in the nearest existing ancestor, because the
    directory is created by the first save. Nothing is left behind.
    """
    target = settings_path()
    if target.exists():
        try:
            os.close(os.open(target, os.O_WRONLY))
            return True, ""
        except OSError:
            return False, f"{target} cannot be opened for writing"
    ancestor = target.parent
    while not ancestor.exists() and ancestor != ancestor.parent:
        ancestor = ancestor.parent
    if not ancestor.is_dir():
        return False, f"{ancestor} is not a directory"
    try:
        handle, probe = tempfile.mkstemp(dir=ancestor, prefix=".oneiro-write-probe-")
        os.close(handle)
        os.remove(probe)
        return True, ""
    except OSError:
        return False, f"{ancestor} is not writable"


def describe() -> dict:
    """Everything the settings page needs, with secrets never handed out."""
    stored = _read_file()
    writable, writable_error = _writable()
    rows = []
    for s in SETTINGS:
        raw, source = _raw_layers(s)
        in_file = s.key in stored and stored[s.key] is not None
        if s.secret:
            # The value is never described, only whether one is in force. An
            # empty field in the page must mean "leave it alone", never "write
            # these dots as the key".
            shown = ""
            changed = str(raw or "").strip() != ""
        elif s.kind == "json":
            # Structured values travel to the page as JSON text, so the field
            # can be edited and saved back without a Python repr in between.
            shown = json.dumps(raw, ensure_ascii=False, indent=2)
            changed = json.dumps(raw, sort_keys=True) != json.dumps(s.default, sort_keys=True)
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
            "choices": list(s.choices),
            "pending": s.pending,
            "value": shown,
            "default": "" if s.secret else (
                json.dumps(s.default, ensure_ascii=False, indent=2)
                if s.kind == "json" else s.default),
            "source": source,
            "changed": changed,
            "stored": in_file,
            "secret": s.secret,
            "readonly": s.readonly,
            "set": bool(str(raw or "").strip()),
        })
    return {
        "settings": rows,
        "path": str(settings_path()),
        "data_root": str(data_root()),
        "writable": writable,
        "writable_error": writable_error,
        "migrated_from": _migrated_from,
        "error": _load_error,
    }


class SettingsRejected(ValueError):
    """A write the settings layer refused, carrying the reasons it refused.

    One reason per problem, each naming a key and what was expected of it —
    never a submitted value, so a caller may show the reasons to the owner
    without spilling a key or a password into a page, a log or a chat. The
    caller that knows the owner's language is `web.py`; this module only knows
    what went wrong.
    """

    def __init__(self, *reasons: str) -> None:
        self.reasons = tuple(reason for reason in reasons if reason)
        super().__init__("; ".join(self.reasons) or "the settings write was refused")


def save(patch: dict) -> dict:
    """Store the given keys, and only them. Returns the fresh description.

    Unknown keys and values of the wrong type are refused together, so a form
    with two mistakes comes back with two messages instead of one at a time.
    """
    if not isinstance(patch, dict):
        raise SettingsRejected("a settings object was expected")
    unknown = [k for k in patch if k not in _BY_KEY]
    if unknown:
        raise SettingsRejected(f"unknown settings: {', '.join(sorted(unknown))}")
    locked = [k for k in patch if _BY_KEY[k].readonly]
    if locked:
        raise SettingsRejected(
            f"read-only settings, set in the environment instead: {', '.join(sorted(locked))}")
    problems: list[str] = []
    coerced: dict[str, Any] = {}
    for key, raw in patch.items():
        try:
            coerced[key] = _coerce(_BY_KEY[key], raw)
        except ValueError as exc:
            problems.append(str(exc))
    if problems:
        raise SettingsRejected(*problems)

    with _write_transaction():
        _save_coerced(coerced)
    return describe()


def _save_coerced(coerced: dict[str, Any]) -> None:
    data = dict(_read_file())
    if _load_error:
        raise SettingsRejected(
            "Repair the existing settings file before writing; it is preserved")
    for key, val in coerced.items():
        # Blank clears the key rather than storing an empty override, so the
        # environment or the default can answer again.
        if str(val).strip() == "" and _BY_KEY[key].empty_means_unset:
            data.pop(key, None)
        else:
            data[key] = val

    _store(data)


def reset(keys: Iterable[str] | None = None) -> dict:
    """Forget stored values: the named keys, or all of them if none are given."""
    with _write_transaction():
        data = dict(_read_file())
        if _load_error:
            raise SettingsRejected(
                "Repair the existing settings file before resetting; it is preserved")
        if keys is None:
            data = {}
        else:
            for key in keys:
                if key not in _BY_KEY:
                    raise SettingsRejected(f"unknown setting: {key!r}")
                data.pop(key, None)
        _store(data)
    return describe()


@contextmanager
def _write_transaction():
    """Serialize local writers and reject competing processes without data loss."""
    with _lock:
        target = settings_path()
        marker = target.with_name(target.name + ".write.lock")
        lease = FileLease(marker)
        try:
            lease.acquire()
        except OwnershipError:
            raise SettingsRejected("Another settings writer owns the file") from None
        try:
            yield
        finally:
            lease.release()


def _store(data: dict[str, Any]) -> None:
    global _cache
    target = settings_path()
    # Preserve each previous owner configuration rather than overwrite its only
    # copy. Recovery files may contain credentials: never serve or log them.
    if target.exists():
        history = target.parent / "settings-history"
        history.mkdir(exist_ok=True)
        backup = history / (uuid.uuid4().hex + ".json")
        with backup.open("xb") as stream:
            os.chmod(backup, 0o600)
            stream.write(target.read_bytes())
    temp = target.with_name(target.name + "." + uuid.uuid4().hex + ".pending")
    with temp.open("x", encoding="utf-8") as stream:
        os.chmod(temp, 0o600)
        stream.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, target)
    _cache = None


# The command line lives with the other commands (`oneiro settings`, see
# `oneiro/cli.py`); this module is the settings layer and nothing else.
