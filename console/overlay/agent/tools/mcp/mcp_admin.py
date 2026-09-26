"""Local administration helpers for MCP connections managed by the web console.

The browser edits the normal MCP configuration shape; it never receives values
from server environment blocks, sensitive headers, or credential-like fields.
Secrets are moved to the instance .env file and referenced as ``${env:NAME}``.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import tempfile
import threading
from pathlib import Path
from urllib.parse import parse_qsl, quote, quote_plus, urlsplit, urlunsplit

from common.log import logger


_METADATA_KEY = "_cowagent"
_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ENV_REF_RE = re.compile(r"\$\{(?:env:)?([A-Za-z_][A-Za-z0-9_]*)\}")
_SECRET_KEY_RE = re.compile(
    r"(?:api[_-]?key|access[_-]?key|token|secret|password|passwd|credential|authorization|auth)",
    re.IGNORECASE,
)
_ENV_LOCK = threading.RLock()
_CONFIG_LOCK = threading.RLock()


class McpAdminError(ValueError):
    """Invalid or unsafe operation requested through the local MCP console."""


def _effective_agent(agent_id: str | None = None):
    from agent.registry import get_agent_registry

    registry = get_agent_registry()
    try:
        profile = registry.get(agent_id or None, require_enabled=False)
    except (KeyError, ValueError) as exc:
        raise McpAdminError(f"Unknown Agent: {agent_id or ''}") from exc
    return registry, profile


def _manager_for(profile):
    from agent.tools.tool_manager import ToolManager
    from common.runtime_identity import identity_scope

    with identity_scope(agent_id=profile.id):
        manager = ToolManager()
    return manager


def _paths(profile, manager):
    from common.state_dir import env_file

    # ToolManager uses the same shared-vs-private resolver for mcp.json. This
    # keeps the panel aligned with what that Agent actually loads.
    return Path(manager._mcp_json_path()), Path(env_file(base=profile.workspace))


def _canonical_json(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def _config_hash(config: dict) -> str:
    clean = {k: v for k, v in config.items() if not str(k).startswith("_cow_")}
    return hashlib.sha256(_canonical_json(clean).encode("utf-8")).hexdigest()


def _running_view(config: dict) -> dict:
    """Comparable view of a config the ToolManager already runs.

    The manager normalises every entry by adding the server name as a `name`
    key, while the on-disk document keeps it as the mapping key. Hashing the
    two as-is reported every server as "pending apply" even when nothing had
    changed, so the name is dropped here before comparing.
    """
    return {k: v for k, v in config.items() if k != "name"}


def _pick_server_block(document):
    if not isinstance(document, dict):
        raise McpAdminError("MCP configuration must be a JSON object")
    for key in ("mcpServers", "servers", "mcp_servers"):
        if key in document:
            return document[key]
    return {k: v for k, v in document.items() if not str(k).startswith("_")}


def normalize_servers(raw) -> dict:
    """Return a name -> config mapping for common MCP config formats."""
    if isinstance(raw, list):
        rows = {}
        for index, item in enumerate(raw):
            if not isinstance(item, dict):
                raise McpAdminError(f"mcp_servers[{index}] must be an object")
            name = str(item.get("name") or "").strip()
            if not name:
                raise McpAdminError(f"mcp_servers[{index}] is missing a name")
            config = {k: v for k, v in item.items() if k != "name"}
            if name in rows:
                raise McpAdminError(f"Duplicate MCP server name: {name}")
            rows[name] = config
        raw = rows
    if not isinstance(raw, dict):
        raise McpAdminError("MCP server list must be an object or a list")

    result = {}
    for raw_name, raw_config in raw.items():
        name = str(raw_name).strip()
        if not name or len(name) > 200 or any(ord(ch) < 32 for ch in name):
            raise McpAdminError("MCP server names must be non-empty and contain no control characters")
        if not isinstance(raw_config, dict):
            raise McpAdminError(f"Configuration for MCP server {name!r} must be an object")
        config = copy.deepcopy(raw_config)
        transport = str(config.get("type") or ("sse" if config.get("url") else "stdio")).strip().lower()
        if transport in ("http", "streamable_http", "streamablehttp"):
            transport = "streamable-http"
        if transport not in ("stdio", "sse", "streamable-http"):
            raise McpAdminError(f"Unsupported MCP transport {transport!r} for {name!r}")
        if "timeout" in config:
            try:
                timeout = int(config["timeout"])
            except (TypeError, ValueError) as exc:
                raise McpAdminError(f"timeout for {name!r} must be a positive integer") from exc
            if timeout <= 0:
                raise McpAdminError(f"timeout for {name!r} must be a positive integer")
            config["timeout"] = timeout
        config["type"] = transport
        if transport == "stdio":
            command = config.get("command")
            if not isinstance(command, str) or not command.strip():
                raise McpAdminError(f"stdio server {name!r} needs a command")
            args = config.get("args", [])
            if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
                raise McpAdminError(f"args for {name!r} must be a list of strings")
            env = config.get("env", {})
            if not isinstance(env, dict) or not all(isinstance(k, str) for k in env):
                raise McpAdminError(f"env for {name!r} must be an object with string keys")
            if any(not isinstance(value, (str, int, float, bool)) for value in env.values()):
                raise McpAdminError(f"env values for {name!r} must be strings or scalar values")
            working_dir = config.get("cwd", config.get("workingDirectory"))
            if working_dir is not None and not isinstance(working_dir, str):
                raise McpAdminError(f"cwd for {name!r} must be a string")
        else:
            url = config.get("url")
            if not isinstance(url, str) or not url.strip():
                raise McpAdminError(f"{transport} server {name!r} needs a URL")
            headers = config.get("headers", {})
            if not isinstance(headers, dict) or not all(isinstance(k, str) for k in headers):
                raise McpAdminError(f"headers for {name!r} must be an object with string keys")
            if any(not isinstance(value, (str, int, float, bool)) for value in headers.values()):
                raise McpAdminError(f"header values for {name!r} must be strings or scalar values")
        result[name] = config
    return result


def _document_servers(document) -> dict:
    return normalize_servers(_pick_server_block(document))


def _read_document(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            document = json.load(handle)
    except Exception as exc:
        raise McpAdminError(f"Could not read MCP configuration: {exc}") from exc
    if not isinstance(document, dict):
        raise McpAdminError("MCP configuration must be a JSON object")
    return document


def _safe_env_name(name: str, *parts: str) -> str:
    bits = [name, *parts]
    slug = "_".join(re.sub(r"[^A-Za-z0-9]+", "_", bit).strip("_").upper() for bit in bits)
    slug = re.sub(r"_+", "_", slug).strip("_") or "SERVER"
    candidate = "COW_MCP_" + slug
    if len(candidate) > 120:
        digest = hashlib.sha256(candidate.encode("utf-8")).hexdigest()[:10].upper()
        candidate = candidate[:109].rstrip("_") + "_" + digest
    return candidate


def _env_ref(name: str) -> str:
    return "${env:" + name + "}"


def _reference_name(value) -> str | None:
    if not isinstance(value, str):
        return None
    match = _ENV_REF_RE.fullmatch(value.strip())
    return match.group(1) if match else None


def _contains_reference(value) -> bool:
    return isinstance(value, str) and bool(_ENV_REF_RE.search(value))


def _secret_value_for_display(value, env_name: str):
    if value in (None, "") or _contains_reference(value):
        return value
    return _env_ref(env_name)


def _safe_url_for_display(name: str, url: str) -> str:
    try:
        parts = urlsplit(url)
        query = []
        for key, value in parse_qsl(parts.query, keep_blank_values=True):
            if value and _SECRET_KEY_RE.search(key) and not _contains_reference(value):
                value = _env_ref(_safe_env_name(name, "query", key))
            query.append((key, value))
        query_text = "&".join(
            quote_plus(key, safe="") + "=" + quote_plus(value, safe="${}:")
            for key, value in query
        )
        # User-info is uncommon and discouraged, but can contain credentials.
        # Hide it rather than putting it in the browser's JSON editor.
        netloc = parts.netloc
        if parts.password is not None:
            host = parts.hostname or ""
            if ":" in host and not host.startswith("["):
                host = "[" + host + "]"
            if parts.port:
                host += ":" + str(parts.port)
            user_ref = _env_ref(_safe_env_name(name, "url", "username"))
            pass_ref = _env_ref(_safe_env_name(name, "url", "password"))
            netloc = quote(user_ref, safe="${}:") + ":" + quote(pass_ref, safe="${}:") + "@" + host
        return urlunsplit((parts.scheme, netloc, parts.path, query_text, parts.fragment))
    except Exception:
        # If URL parsing fails, keep the value only when it has no obvious
        # credential marker. Malformed URLs are rejected on save/test.
        return "[redacted URL]" if _SECRET_KEY_RE.search(url) else url


def _safe_server_config(name: str, config: dict) -> dict:
    safe = copy.deepcopy(config)
    env = safe.get("env")
    if isinstance(env, dict):
        safe_env = {}
        for key, value in env.items():
            key_text = str(key)
            variable = key_text if _ENV_NAME_RE.fullmatch(key_text) else _safe_env_name(name, "env", key_text)
            safe_env[key_text] = _secret_value_for_display(value, variable)
        safe["env"] = safe_env

    headers = safe.get("headers")
    if isinstance(headers, dict):
        safe_headers = {}
        for key, value in headers.items():
            # Any header can carry credentials; store header values in .env so
            # custom authentication schemes remain possible without exposing
            # them to browser developer tools or cached JSON.
            variable = _safe_env_name(name, "header", str(key))
            safe_headers[key] = _secret_value_for_display(value, variable)
        safe["headers"] = safe_headers

    if isinstance(safe.get("url"), str):
        safe["url"] = _safe_url_for_display(name, safe["url"])

    def visit(node, path=()):
        if isinstance(node, dict):
            for key, value in list(node.items()):
                if key in ("env", "headers") and len(path) == 0:
                    continue
                if key == "url" and len(path) == 0:
                    continue
                if _SECRET_KEY_RE.search(str(key)) and isinstance(value, str):
                    if value and not _contains_reference(value):
                        node[key] = _env_ref(_safe_env_name(name, *(path + (str(key),))))
                else:
                    visit(value, path + (str(key),))
        elif isinstance(node, list):
            for index, value in enumerate(node):
                visit(value, path + (str(index),))

    visit(safe)
    return safe


def _write_json_atomic(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=str(path.parent),
            prefix=path.name + ".", suffix=".tmp", delete=False,
        ) as handle:
            temp_name = handle.name
            json.dump(document, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(temp_name, 0o600)
        except OSError:
            pass
        os.replace(temp_name, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    except Exception:
        # Retain a failed temporary write for recovery/inspection rather than
        # deleting data from a privileged administration path.
        raise


def _set_env_values(path: Path, updates: dict[str, str]) -> None:
    try:
        from dotenv import load_dotenv, set_key
    except ImportError as exc:
        raise McpAdminError("python-dotenv is required to manage MCP secrets") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    with _ENV_LOCK:
        for key, value in updates.items():
            if not _ENV_NAME_RE.fullmatch(key):
                raise McpAdminError(f"Invalid environment variable name: {key!r}")
            if "\x00" in value:
                raise McpAdminError("Environment variable values cannot contain NUL bytes")
            written, _ = set_key(str(path), key, value, quote_mode="always")
            if not written:
                raise McpAdminError(f"Could not save environment variable {key}")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        load_dotenv(str(path), override=True)


def _read_env(path: Path) -> dict:
    try:
        from dotenv import dotenv_values
    except ImportError as exc:
        raise McpAdminError("python-dotenv is required to read MCP secret status") from exc
    try:
        return {str(k): v for k, v in dotenv_values(str(path)).items() if k}
    except Exception as exc:
        raise McpAdminError(f"Could not read the local environment file: {exc}") from exc


def _old_secret_migrations(name: str, old: dict, new: dict, env_path: Path) -> dict:
    """Move unchanged, previously-inline credentials into .env on first save."""
    updates = {}
    old_safe = _safe_server_config(name, old)

    old_env = old.get("env") if isinstance(old.get("env"), dict) else {}
    new_env = new.get("env") if isinstance(new.get("env"), dict) else {}
    for key, new_value in new_env.items():
        old_value = old_env.get(key)
        reference = _reference_name(new_value)
        if reference and isinstance(old_value, (str, int, float, bool)):
            old_safe_value = (old_safe.get("env") or {}).get(key)
            if old_safe_value == new_value and old_value not in (None, "") and not _contains_reference(old_value):
                updates[reference] = str(old_value)

    old_headers = old.get("headers") if isinstance(old.get("headers"), dict) else {}
    new_headers = new.get("headers") if isinstance(new.get("headers"), dict) else {}
    safe_headers = old_safe.get("headers") if isinstance(old_safe.get("headers"), dict) else {}
    for key, new_value in new_headers.items():
        old_value = old_headers.get(key)
        reference = _reference_name(new_value)
        if reference and isinstance(old_value, (str, int, float, bool)):
            if safe_headers.get(key) == new_value and old_value not in (None, "") and not _contains_reference(old_value):
                updates[reference] = str(old_value)

    # Credential-like custom fields retain their JSON path in the safe view.
    def migrate_tree(old_node, new_node, safe_node, path=()):
        if not isinstance(old_node, dict) or not isinstance(new_node, dict) or not isinstance(safe_node, dict):
            return
        for key, new_value in new_node.items():
            old_value = old_node.get(key)
            safe_value = safe_node.get(key)
            if key in ("env", "headers", "url") and not path:
                continue
            if _SECRET_KEY_RE.search(str(key)) and isinstance(new_value, str):
                reference = _reference_name(new_value)
                if reference and safe_value == new_value and isinstance(old_value, str) and old_value and not _contains_reference(old_value):
                    updates[reference] = old_value
            else:
                migrate_tree(old_value, new_value, safe_value, path + (str(key),))

    migrate_tree(old, new, old_safe)

    # Query credentials are compared by parameter name so reordering a URL in
    # the editor doesn't accidentally discard the existing value.
    try:
        old_url = old.get("url")
        new_url = new.get("url")
        safe_url = old_safe.get("url")
        if all(isinstance(item, str) for item in (old_url, new_url, safe_url)):
            old_parts = urlsplit(old_url)
            new_parts = urlsplit(new_url)
            safe_parts = urlsplit(safe_url)
            old_q = dict(parse_qsl(old_parts.query, keep_blank_values=True))
            new_q = dict(parse_qsl(new_parts.query, keep_blank_values=True))
            safe_q = dict(parse_qsl(safe_parts.query, keep_blank_values=True))
            for key, new_value in new_q.items():
                reference = _reference_name(new_value)
                old_value = old_q.get(key)
                if reference and safe_q.get(key) == new_value and old_value and not _contains_reference(old_value):
                    updates[reference] = old_value
            if old_parts.password is not None and new_parts.password is not None and safe_parts.password is not None:
                old_user = old_parts.username or ""
                old_password = old_parts.password
                if _reference_name(new_parts.username) and safe_parts.username == new_parts.username:
                    updates[_reference_name(new_parts.username)] = old_user
                if _reference_name(new_parts.password) and safe_parts.password == new_parts.password:
                    updates[_reference_name(new_parts.password)] = old_password
    except Exception:
        pass

    return updates


def _promote_new_secrets(name: str, config: dict, env_updates: dict[str, str]) -> dict:
    """Replace inline env/header/credential values with local .env references."""
    result = copy.deepcopy(config)
    env = result.get("env")
    if isinstance(env, dict):
        for key, value in list(env.items()):
            if value in (None, "") or _contains_reference(str(value)):
                continue
            variable = str(key) if _ENV_NAME_RE.fullmatch(str(key)) else _safe_env_name(name, "env", str(key))
            env_updates[variable] = str(value)
            env[key] = _env_ref(variable)

    headers = result.get("headers")
    if isinstance(headers, dict):
        for key, value in list(headers.items()):
            if value in (None, "") or _contains_reference(str(value)):
                continue
            variable = _safe_env_name(name, "header", str(key))
            env_updates[variable] = str(value)
            headers[key] = _env_ref(variable)

    if isinstance(result.get("url"), str):
        url = result["url"]
        try:
            parts = urlsplit(url)
            if parts.password is not None:
                host = parts.hostname or ""
                if ":" in host and not host.startswith("["):
                    host = "[" + host + "]"
                if parts.port:
                    host += ":" + str(parts.port)
                old_user = parts.username or ""
                old_password = parts.password
                user_key = _safe_env_name(name, "url", "username")
                password_key = _safe_env_name(name, "url", "password")
                if old_user and not _contains_reference(old_user):
                    env_updates[user_key] = old_user
                if old_password and not _contains_reference(old_password):
                    env_updates[password_key] = old_password
                netloc = quote(_env_ref(user_key), safe="${}:") + ":" + quote(_env_ref(password_key), safe="${}:") + "@" + host
                parts = parts._replace(netloc=netloc)
            pairs = []
            for key, value in parse_qsl(parts.query, keep_blank_values=True):
                if value and _SECRET_KEY_RE.search(key) and not _contains_reference(value):
                    variable = _safe_env_name(name, "query", key)
                    env_updates[variable] = value
                    value = _env_ref(variable)
                pairs.append((key, value))
            query = "&".join(
                quote_plus(key, safe="") + "=" + quote_plus(value, safe="${}:")
                for key, value in pairs
            )
            result["url"] = urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))
        except Exception:
            pass

    def visit(node, path=()):
        if isinstance(node, dict):
            for key, value in list(node.items()):
                if key in ("env", "headers", "url") and not path:
                    continue
                if _SECRET_KEY_RE.search(str(key)) and isinstance(value, str) and value and not _contains_reference(value):
                    variable = _safe_env_name(name, *(path + (str(key),)))
                    env_updates[variable] = value
                    node[key] = _env_ref(variable)
                else:
                    visit(value, path + (str(key),))
        elif isinstance(node, list):
            for index, value in enumerate(node):
                visit(value, path + (str(index),))

    visit(result)
    return result


def _config_from_legacy(manager) -> dict:
    try:
        return {str(cfg.get("name") or ""): {k: v for k, v in cfg.items() if k != "name"} for cfg in manager._load_mcp_configs() if cfg.get("name")}
    except Exception as exc:
        raise McpAdminError(f"Could not read the active MCP configuration: {exc}") from exc


def _get_context(agent_id: str | None = None):
    registry, profile = _effective_agent(agent_id)
    manager = _manager_for(profile)
    config_path, env_path = _paths(profile, manager)
    document = _read_document(config_path)
    if config_path.exists():
        servers = _document_servers(document)
    else:
        servers = normalize_servers(_config_from_legacy(manager))
    metadata = document.get(_METADATA_KEY, {}) if isinstance(document, dict) else {}
    if not isinstance(metadata, dict):
        metadata = {}
    return registry, profile, manager, config_path, env_path, document, servers, metadata


def _render_json(servers: dict) -> str:
    safe_servers = {name: _safe_server_config(name, cfg) for name, cfg in servers.items()}
    return json.dumps({"mcpServers": safe_servers}, ensure_ascii=False, indent=2)


def mcp_snapshot(agent_id: str | None = None) -> dict:
    registry, profile, manager, config_path, env_path, _document, servers, _metadata = _get_context(agent_id)
    env_values = _read_env(env_path)
    rows = []
    referenced = set()
    active_configs = getattr(manager, "_mcp_active_configs", {}) or {}
    for name, config in sorted(servers.items(), key=lambda item: item[0].lower()):
        safe = _safe_server_config(name, config)
        for match in _ENV_REF_RE.finditer(_canonical_json(safe)):
            referenced.add(match.group(1))
        status = manager._mcp_status.get(name)
        if config.get("disabled") is True or config.get("enabled") is False:
            status = "disabled"
        elif config.get("_cow_stdio_managed") and not config.get("_cow_stdio_approved"):
            status = "approval_required"
        elif name in active_configs and _config_hash(_running_view(active_configs[name])) != _config_hash(config):
            status = "pending_apply"
        elif not status:
            status = "configured"
        tools = [tool for tool in manager._mcp_tool_instances.values() if getattr(tool, "server_name", None) == name]
        rows.append({
            "name": name,
            "transport": config.get("type", "stdio"),
            "status": status,
            "tool_count": len(tools),
            "tools": [getattr(tool, "name", "") for tool in tools],
        })
        if isinstance(config.get("env"), dict):
            for key, value in config["env"].items():
                if value not in (None, "") and not _contains_reference(str(value)):
                    if _ENV_NAME_RE.fullmatch(str(key)):
                        referenced.add(str(key))
    variables = [
        {"name": name, "configured": bool(env_values.get(name) or os.environ.get(name))}
        for name in sorted(referenced)
    ]
    archived = _metadata.get("archivedServers", {}) if isinstance(_metadata.get("archivedServers"), dict) else {}
    archived_rows = []
    for name, record in sorted(archived.items(), key=lambda item: item[0].lower()):
        archived_config = record.get("config", {}) if isinstance(record, dict) else {}
        archived_rows.append({
            "name": name,
            "transport": archived_config.get("type", "stdio") if isinstance(archived_config, dict) else "stdio",
            "archived_at": record.get("archived_at", "") if isinstance(record, dict) else "",
            "config": _safe_server_config(name, archived_config) if isinstance(archived_config, dict) else {},
        })
    return {
        "status": "success",
        "agent": {"id": profile.id, "name": profile.name, "enabled": profile.enabled},
        "agents": [
            {"id": item.id, "name": item.name, "enabled": item.enabled}
            for item in registry.list(include_disabled=True)
        ],
        "default_agent_id": registry.default_agent_id,
        "config": _render_json(servers),
        "servers": rows,
        "archived": archived_rows,
        "environment": variables,
        "config_exists": config_path.exists(),
    }


def save_mcp_config(agent_id: str | None, submitted) -> dict:
    if isinstance(submitted, str):
        try:
            submitted = json.loads(submitted)
        except json.JSONDecodeError as exc:
            raise McpAdminError(f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    new_servers = _document_servers(submitted)
    _registry, _profile, manager, config_path, env_path, old_document, old_servers, metadata = _get_context(agent_id)

    env_updates = {}
    secured_servers = {}
    managed = set(metadata.get("managedStdioServers", [])) if isinstance(metadata.get("managedStdioServers"), list) else set()
    approvals = metadata.get("stdioApprovals", {}) if isinstance(metadata.get("stdioApprovals"), dict) else {}
    next_managed = set()
    next_approvals = {}

    for name, config in new_servers.items():
        config = {k: v for k, v in config.items() if not str(k).startswith("_cow_")}
        previous = old_servers.get(name)
        if previous:
            env_updates.update(_old_secret_migrations(name, previous, config, env_path))
        secured = _promote_new_secrets(name, config, env_updates)
        secured_servers[name] = secured

        if secured.get("type") == "stdio":
            # Existing hand-authored configs keep their historical behavior.
            # A new or edited stdio entry created through this UI is marked as
            # managed and will not launch until the owner approves that exact
            # configuration from the separate Apply action.
            changed = previous is None or _canonical_json(previous) != _canonical_json(secured)
            if name in managed or changed:
                next_managed.add(name)
                current_hash = _config_hash(secured)
                if approvals.get(name) == current_hash:
                    next_approvals[name] = current_hash

    archived = metadata.get("archivedServers", {}) if isinstance(metadata.get("archivedServers"), dict) else {}
    removed_names = set(old_servers) - set(new_servers)
    for name in removed_names:
        if name in archived:
            continue
        previous = old_servers[name]
        env_updates.update(_old_secret_migrations(name, previous, previous, env_path))
        archived[name] = {
            "config": _promote_new_secrets(name, previous, env_updates),
            "archived_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        }

    if env_updates:
        _set_env_values(env_path, env_updates)

    root = copy.deepcopy(old_document) if isinstance(old_document, dict) else {}
    root["mcpServers"] = secured_servers
    next_metadata = copy.deepcopy(metadata)
    next_metadata["managedStdioServers"] = sorted(next_managed)
    next_metadata["stdioApprovals"] = next_approvals
    next_metadata["archivedServers"] = archived
    root[_METADATA_KEY] = next_metadata
    with _CONFIG_LOCK:
        _write_json_atomic(config_path, root)
    logger.info("[MCP admin] Saved MCP configuration for Agent %s (%d server(s))", profile.id, len(secured_servers))
    return {"status": "success", "message": "MCP configuration saved", "requires_apply": True}


def save_secret(agent_id: str | None, name: str, value: str) -> dict:
    name = str(name or "").strip()
    if not _ENV_NAME_RE.fullmatch(name):
        raise McpAdminError("Environment variable names must start with a letter or underscore and contain only letters, numbers, and underscores")
    if not isinstance(value, str):
        raise McpAdminError("Secret value must be text")
    _registry, profile = _effective_agent(agent_id)
    manager = _manager_for(profile)
    _config_path, env_path = _paths(profile, manager)
    _set_env_values(env_path, {name: value})
    return {"status": "success", "name": name, "configured": bool(value)}


def restore_archived_server(agent_id: str | None, name: str) -> dict:
    name = str(name or "").strip()
    if not name:
        raise McpAdminError("Choose an archived MCP server to restore")
    _registry, profile, manager, config_path, _env_path, document, servers, metadata = _get_context(agent_id)
    archived = metadata.get("archivedServers", {}) if isinstance(metadata.get("archivedServers"), dict) else {}
    record = archived.get(name)
    if not isinstance(record, dict) or not isinstance(record.get("config"), dict):
        raise McpAdminError("Archived MCP server was not found")
    if name in servers:
        raise McpAdminError("A server with this name is already configured")
    restored = copy.deepcopy(record["config"])
    servers[name] = restored
    # Reuse the normal write path to keep validation, secret handling and
    # stdio approval rules consistent. The archived copy remains as recovery.
    payload = {"mcpServers": servers}
    result = save_mcp_config(profile.id, payload)
    return {**result, "restored": name}


def _load_env_for_agent(profile, manager):
    try:
        from dotenv import load_dotenv
    except ImportError as exc:
        raise McpAdminError("python-dotenv is required to load MCP secrets") from exc
    _config_path, env_path = _paths(profile, manager)
    if env_path.exists():
        load_dotenv(str(env_path), override=True)


def _approve_managed_stdio(config_path: Path, servers: dict, metadata: dict) -> None:
    managed = set(metadata.get("managedStdioServers", [])) if isinstance(metadata.get("managedStdioServers"), list) else set()
    approvals = metadata.get("stdioApprovals", {}) if isinstance(metadata.get("stdioApprovals"), dict) else {}
    for name, config in servers.items():
        if config.get("type") == "stdio" and name in managed:
            approvals[name] = _config_hash(config)
    metadata["stdioApprovals"] = approvals
    document = _read_document(config_path)
    document[_METADATA_KEY] = metadata
    _write_json_atomic(config_path, document)


def apply_mcp_config(agent_id: str | None, confirmed: bool = False) -> dict:
    _registry, profile, manager, config_path, env_path, document, servers, metadata = _get_context(agent_id)
    stdio = [
        (name, cfg) for name, cfg in servers.items()
        if cfg.get("type") == "stdio" and not _is_mcp_disabled(cfg)
    ]
    if stdio and not confirmed:
        raise McpAdminError("Starting or restarting local MCP commands requires explicit confirmation")
    if not config_path.exists():
        # Preserve an empty configuration as a valid, explicit file.
        document = {"mcpServers": {}}
        _write_json_atomic(config_path, document)
    if stdio:
        _approve_managed_stdio(config_path, servers, metadata)
    _load_env_for_agent(profile, manager)
    manager.refresh_mcp_if_changed(force=True)
    return {
        "status": "success",
        "message": "MCP reload started",
        "servers": len(servers),
        "local_commands": [
            {"name": name, "command": cfg.get("command", ""), "args": cfg.get("args", [])}
            for name, cfg in stdio
        ],
    }


def test_mcp_server(agent_id: str | None, name: str, config, confirmed: bool = False) -> dict:
    name = str(name or "").strip()
    if not name:
        raise McpAdminError("Choose an MCP server to test")
    servers = normalize_servers({name: config})
    server_config = servers[name]
    if server_config.get("type") == "stdio" and not confirmed:
        raise McpAdminError("Testing this stdio server starts a local command and requires explicit confirmation")
    _registry, profile = _effective_agent(agent_id)
    manager = _manager_for(profile)
    _load_env_for_agent(profile, manager)
    from agent.tools.mcp.mcp_client import McpClient

    client = None
    try:
        client = McpClient(server_config)
        if not client.initialize():
            if getattr(client, "needs_auth", False):
                raise McpAdminError("The server requires OAuth authorization; save it and complete the browser authorization flow")
            raise McpAdminError("Connection failed. Check the server settings and local CowAgent logs for details.")
        tools = client.list_tools()
        return {
            "status": "success",
            "name": name,
            "transport": server_config["type"],
            "tool_count": len(tools),
            "tools": [
                {"name": str(tool.get("name") or ""), "description": str(tool.get("description") or "")}
                for tool in tools
            ],
        }
    except McpAdminError:
        raise
    except Exception as exc:
        # Avoid returning exception text: URLs and third-party clients sometimes
        # include request details. The useful failure remains in the local log.
        logger.warning("[MCP admin] Connection check failed for %s (%s)", name, type(exc).__name__)
        raise McpAdminError("Connection check failed. Check the server settings and local CowAgent logs.") from exc
    finally:
        if client is not None:
            try:
                client.shutdown()
            except Exception:
                pass


def host_status() -> dict:
    import platform
    import sys
    from agent.registry import get_agent_registry
    from cli import __version__
    from config import conf

    registry = get_agent_registry()
    agents = []
    mcp_count = 0
    for profile in registry.list(include_disabled=True):
        manager = _manager_for(profile)
        configured = manager._load_mcp_configs()
        mcp_count += len(configured)
        agents.append({
            "id": profile.id,
            "name": profile.name,
            "enabled": profile.enabled,
            "mcp_servers": len(configured),
        })
    settings = conf()
    return {
        "status": "success",
        "version": __version__,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "default_agent_id": registry.default_agent_id,
        "agents": agents,
        "mcp_servers": mcp_count,
        "web_host": str(settings.get("web_host", "127.0.0.1") or "127.0.0.1"),
        "web_port": int(os.environ.get("COW_WEB_PORT") or settings.get("web_port", 9899)),
        "password_protected": bool(settings.get("web_password")),
    }
