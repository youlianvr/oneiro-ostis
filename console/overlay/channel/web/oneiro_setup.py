"""Is the product ready, and if not, what is missing - asked of live state.

A fresh machine lands on the chat with no model credentials, and when the graph
stack is down the panel's page only reports errors. Nothing said that the
product is not yet usable, or what to do about it - and a one-time "configured"
flag would be worse than nothing, because the environment breaks later and the
answer has to come back on its own. Every answer here is recomputed from state
that is read at the moment of asking:

  * the console's own configuration (passed in by the caller as a plain dict)
    says whether the chat has a usable model: a custom provider with address,
    key and model, or a builtin provider with a key somewhere in the config;
  * the Oneiro panel's settings API (served by the project's `python/config.py`)
    says what the project side knows - including where the graph lives, so the
    graph address is never configured a second time;
  * the graph stack answers a plain TCP connect on the machine's address for
    sc-machine, and on the port sc-web is published to.

Nothing here holds state of its own, nothing writes configuration, and nothing
imports the console: the module is stdlib-only and testable on its own.
"""

import json
import os
import socket
import subprocess
import urllib.error
import urllib.request

PANEL_FALLBACK = "http://127.0.0.1:8130"
CUSTOM_PREFIX = "custom:"
GRAPH_WEB_PORT = 8000          # sc-web, the port docker-compose.yml publishes


# ------------------------------------------------------------------ the console side

def custom_provider(config: dict, provider_id: str):
    """The custom provider entry with this id, or None."""
    for entry in config.get("custom_providers") or []:
        if isinstance(entry, dict) and str(entry.get("id")) == provider_id:
            return entry
    return None


def model_state(config: dict) -> dict:
    """What the chat will answer with, read from the console's own config."""
    bot_type = str(config.get("bot_type") or "").strip()
    state = {
        "bot_type": bot_type,
        "configured": False,
        "provider": "",
        # The console owns provider ids and generates one when a provider is
        # created. The setup page needs the id to edit that very provider
        # later - a made-up id makes the console create another one.
        "provider_id": bot_type[len(CUSTOM_PREFIX):] if bot_type.startswith(CUSTOM_PREFIX) else "",
        "base_url": "",
        "model": str(config.get("model") or "").strip(),
        "key_set": False,
        "detail": "",
    }

    if bot_type.startswith(CUSTOM_PREFIX):
        entry = custom_provider(config, bot_type[len(CUSTOM_PREFIX):])
        if entry is None:
            state["detail"] = f"провайдер {bot_type} не найден в config.json"
            return state
        state["provider"] = str(entry.get("name") or bot_type)
        state["base_url"] = str(entry.get("api_base") or "").strip()
        state["key_set"] = bool(str(entry.get("api_key") or "").strip())
        state["model"] = str(entry.get("model") or state["model"]).strip()
        absent = [name for name, ok in (("адрес", bool(state["base_url"])),
                                        ("ключ", state["key_set"]),
                                        ("модель", bool(state["model"]))) if not ok]
        state["configured"] = not absent
        state["detail"] = (f"провайдер «{state['provider']}»" if not absent else
                           "у провайдера «{}» нет: {}".format(state["provider"], ", ".join(absent)))
        return state

    # A builtin provider (or none chosen yet): the console stores its credentials
    # as `<provider>_api_key` fields. Any filled one is a usable chat model; the
    # legacy single-provider `custom_api_key` is deliberately not counted, since
    # the product's own path is the custom provider above.
    keys = sorted(key for key in config
                  if key.endswith("_api_key") and key != "custom_api_key"
                  and str(config.get(key) or "").strip())
    state["configured"] = bool(keys)
    state["key_set"] = bool(keys)
    state["provider"] = bot_type or "встроенный провайдер"
    state["detail"] = (f"ключ встроенного провайдера: {', '.join(keys)}" if keys else
                       "нет ни своего провайдера, ни ключа встроенного")
    return state


def stored_key(config: dict) -> str:
    """The key the chat would use. Stays inside the process that checks with it."""
    bot_type = str(config.get("bot_type") or "")
    if bot_type.startswith(CUSTOM_PREFIX):
        entry = custom_provider(config, bot_type[len(CUSTOM_PREFIX):])
        return str((entry or {}).get("api_key") or "")
    for key in sorted(config):
        if key.endswith("_api_key") and key != "custom_api_key" \
                and str(config.get(key) or "").strip():
            return str(config[key])
    return ""


# ------------------------------------------------------------------ the panel side

def panel_base(proxy_spec: str = "") -> str:
    """Where the panel answers, taken from the launcher's proxy specification."""
    for part in (proxy_spec or "").split(","):
        prefix, _, target = part.partition("=")
        if prefix.strip() == "/oneiro" and target.strip():
            return target.strip().rstrip("/")
    return PANEL_FALLBACK


def panel_state(base: str, timeout: float = 5.0) -> dict:
    """What the project's settings owner knows, read through its own API.

    The document is the panel's settings page payload: one row per setting with
    a `set` flag (a secret's value is never handed out) and the resolved value
    for everything else - which is where the graph address comes from.
    """
    try:
        with urllib.request.urlopen(f"{base}/api/settings", timeout=timeout) as response:
            document = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError) as error:
        return {"reachable": False, "base": base, "settings_path": "", "llm": {},
                "graph": {}, "detail": f"панель не ответила ({base}): {type(error).__name__}"}

    rows = {row.get("key"): row for row in document.get("settings") or [] if isinstance(row, dict)}

    def value(key, fallback):
        row = rows.get(key) or {}
        return row.get("value") if row.get("value") not in (None, "") else fallback

    return {
        "reachable": True,
        "base": base,
        "settings_path": document.get("path") or "",
        "llm": {name: bool((rows.get("llm." + name) or {}).get("set"))
                for name in ("base_url", "api_key", "model")},
        "graph": {"host": str(value("graph.host", "localhost")),
                  "port": value("graph.port", 8090)},
        "detail": "панель отвечает",
    }


# ------------------------------------------------------------------ the graph

def tcp_open(host: str, port, timeout: float = 1.5) -> bool:
    """Whether something is listening. The cheapest honest answer there is."""
    try:
        with socket.create_connection((str(host), int(port)), timeout=timeout):
            return True
    except (OSError, ValueError):
        return False


def graph_state(host: str, port, web_port=GRAPH_WEB_PORT) -> dict:
    """The graph stack as the panel needs it: sc-machine, plus sc-web for the eye."""
    host = str(host or "localhost")
    try:
        machine_port = int(port)
    except (TypeError, ValueError):
        machine_port = 8090
    machine = tcp_open(host, machine_port)
    web = tcp_open(host, web_port)
    return {
        "host": host,
        "port": machine_port,
        "reachable": machine,
        "web_reachable": web,
        "detail": (f"sc-machine на {host}:{machine_port} отвечает" if machine
                   else f"sc-machine на {host}:{machine_port} не отвечает"),
    }


def start_graph(project_dir: str, timeout: float = 240.0) -> dict:
    """Bring the stack up the way the installer does, and report the last words."""
    if not project_dir or not os.path.isdir(project_dir):
        return {"ok": False, "detail": "не найден каталог проекта (ONEIRO_PROJECT не задан)"}
    try:
        result = subprocess.run(["docker", "compose", "up", "-d"], cwd=project_dir,
                                capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return {"ok": False, "detail": "docker не найден в PATH"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "detail": "docker compose не ответил за отведённое время"}
    tail = ((result.stdout or "") + (result.stderr or "")).strip().splitlines()[-3:]
    return {"ok": result.returncode == 0,
            "detail": " | ".join(tail) or f"код возврата {result.returncode}"}


# ------------------------------------------------------------------ the answer

def readiness(state: dict) -> dict:
    """Ready, or the list of what is missing - each with what to do about it."""
    missing = []
    if not state["model"]["configured"]:
        missing.append({
            "id": "model",
            "title": "Модель для чата не настроена",
            "detail": state["model"]["detail"],
            "fix": "Укажите адрес OpenAI-совместимого провайдера, ключ и имя модели.",
        })
    if not state["graph"]["reachable"]:
        missing.append({
            "id": "graph",
            "title": "Стек графа не отвечает",
            "detail": state["graph"]["detail"],
            "fix": "Поднимите его кнопкой ниже (docker compose up -d в папке проекта).",
        })
    if not state["panel"]["reachable"]:
        missing.append({
            "id": "panel",
            "title": "Панель Oneiro не отвечает",
            "detail": state["panel"]["detail"],
            "fix": "Перезапустите Oneiro ярлыком: лаунчер поднимает панель вместе с консолью.",
        })
    return {"ready": not missing, "missing": missing}


def status(config: dict, proxy_spec: str = "") -> dict:
    """The whole first-run answer, computed now: model, graph, panel, missing."""
    base = panel_base(proxy_spec)
    panel = panel_state(base)
    graph = graph_state(panel["graph"].get("host", "localhost"),
                        panel["graph"].get("port", 8090))
    model = model_state(config)
    state = {"model": model, "graph": graph, "panel": panel}
    state.update(readiness(state))
    return state


# ------------------------------------------------------------------ verification

def _http_json(url: str, api_key: str, payload=None, timeout: float = 25.0):
    """(status, body) from an OpenAI-compatible endpoint; (None, reason) if it didn't answer."""
    headers = {"Authorization": f"Bearer {api_key}"}
    data = None
    method = "GET"
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
        method = "POST"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")
    except (OSError, ValueError) as error:
        return None, f"{type(error).__name__}: {error}"


def _shorten(body: str, limit: int = 240) -> str:
    text = str(body or "").strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            error = parsed.get("error")
            if isinstance(error, dict) and error.get("message"):
                text = str(error["message"])
            elif isinstance(error, str):
                text = error
    except ValueError:
        pass
    return text[:limit]


def verify_model(base_url: str, api_key: str, model: str, timeout: float = 25.0) -> dict:
    """Ask the provider itself, with the same call the chat makes.

    One completion of a single token: that is the real path - address, key and
    model name together - and it costs a fraction of a cent. A provider that
    refuses the completion but lists its models is reported as the weaker pass
    it is, not as a failure.
    """
    base = str(base_url or "").strip().rstrip("/")
    model = str(model or "").strip()
    api_key = str(api_key or "").strip()
    if not base or not model or not api_key:
        return {"ok": False, "via": "", "status": None,
                "detail": "нужны адрес, ключ и модель"}

    code, body = _http_json(base + "/chat/completions", api_key,
                            {"model": model, "messages": [{"role": "user", "content": "ping"}],
                             "max_tokens": 1}, timeout)
    if code == 200:
        return {"ok": True, "via": "chat/completions", "status": 200,
                "detail": f"модель «{model}» ответила"}

    list_code, list_body = _http_json(base + "/models", api_key, None, timeout)
    if list_code == 200:
        return {"ok": True, "via": "models", "status": 200,
                "detail": "провайдер принял ключ и перечислил модели (без запроса к модели)"}

    return {"ok": False, "via": "chat/completions", "status": code,
            "detail": _shorten(body) or _shorten(list_body) or "провайдер не ответил"}
