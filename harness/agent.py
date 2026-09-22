"""Our own coding agent: the harness we own, measure and search over.

    python harness/run.py --task t01-start-total --agent ours --policy baseline

The loop is deliberately small and fully observed: a policy decides what the
model is shown, the model picks a tool, the tool acts on a scratch copy of the
task repository, and every step is measured. Nothing the policy does is hidden
from the record, because the record is what the judge replays.

The only network dependency is the OpenAI-compatible chat endpoint; the tools
themselves are local and deterministic.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import runner
from policy import HarnessPolicy, get_policy

# The MCP shelf lives beside the roles in python/; the harness is a flat
# directory, so the path is spelled out (same pattern as bench/memory).
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
import mcp_client  # noqa: E402
import skills_index  # noqa: E402

# The provider is any OpenAI-compatible endpoint; the key comes from the
# environment (see runner.api_key). Since 2026-09-22 that endpoint is the local
# OmniRoute proxy, and the model is a routing name rather than an upstream id:
# concrete provider ids through the proxy were either rejecting credentials or
# answering without honouring the tool schema, while the routing names answer
# with real tool calls in seconds. The proxy reports which upstream actually
# served each call, and that id is recorded per step, so an episode can always
# be attributed to the model that produced it.
DEFAULT_MODEL = "auto/coding"
BASE_URL = os.environ.get("ONEIRO_BASE_URL", "http://127.0.0.1:20128/v1")
REQUEST_TIMEOUT = 120.0
MAX_PLACEHOLDER_RETRIES = 8
MAX_REQUEST_ATTEMPTS = 4

# Provider hiccups (timeouts, connection resets, 5xx, truncated JSON) are normal
# on a shared inference endpoint and must not end an episode: one lost request
# would otherwise be recorded as a failed task and poison the results table.
RETRYABLE_ERRORS = (urllib.error.URLError, TimeoutError, ConnectionError,
                    json.JSONDecodeError, KeyError)

# The provider answers instantly with this text while it boots a cold model;
# it is not a model answer and must never enter the trajectory.
PLACEHOLDER_MARKER = "model is starting up"


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List the files in the repository.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a text file from the repository, with line numbers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "path relative to the repository root"},
                    "start": {"type": "integer", "description": "first line (1-based), optional"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a file with the given content.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace an exact string in a file. old_string must occur exactly once.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_string": {"type": "string"},
                    "new_string": {"type": "string"},
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_tests",
            "description": "Run the repository test suite with pytest and return its output.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run a shell command in the repository root and return its output.",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    },
]


# ---------- provider ----------


def _retry_after(exc: urllib.error.HTTPError) -> float:
    """The wait the provider asks for, in seconds, or 0 when it asks for none."""
    try:
        value = exc.headers.get("Retry-After") if exc.headers else None
        return min(120.0, float(value)) if value else 0.0
    except (TypeError, ValueError, AttributeError):
        return 0.0


class Provider:
    """Minimal OpenAI-compatible chat client with tool calling."""

    def __init__(self, model: str, api_key: str, temperature: float, base_url: str = BASE_URL):
        self.model = model
        self.api_key = api_key
        self.temperature = temperature
        self.base_url = base_url.rstrip("/")
        self.served: str = model
        # The proxy names the upstream that answered in its own headers. The
        # body model is the routing alias ("auto"), which says nothing; the
        # provider id is the evidence that one upstream served the episode.
        self.served_provider: str = ""

    def _post(self, payload: dict) -> tuple[dict, dict]:
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8")), dict(response.headers)

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> tuple[dict, dict]:
        """Return (message, usage), retrying transient provider failures.

        After the call, ``self.served`` holds the model id the provider says it
        used. Behind a routing alias that is not always the requested name, and
        the record must carry what really answered.
        """
        payload: dict = {"model": self.model, "messages": messages,
                         "temperature": self.temperature}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        placeholder_wait = 0
        last_error: Exception | None = None
        for attempt in range(MAX_REQUEST_ATTEMPTS):
            try:
                body, headers = self._post(payload)
                choice = body["choices"][0]
                message = choice["message"]
            except urllib.error.HTTPError as exc:
                if exc.code == 429:
                    # the provider's own wait, when it sends one: a rate limit
                    # outlives a one-second ladder, and a round that dies here
                    # would waste the runs it already paid for
                    last_error = exc
                    time.sleep(_retry_after(exc) or min(60.0, 5 * 2 ** attempt))
                    continue
                if exc.code >= 500:
                    last_error = exc
                    time.sleep(2 ** attempt)
                    continue
                detail = exc.read().decode("utf-8", errors="replace")[:300]
                raise RuntimeError(f"HTTP {exc.code} from provider: {detail}") from exc
            except RETRYABLE_ERRORS as exc:
                last_error = exc
                time.sleep(2 ** attempt)
                continue

            served = body.get("model")
            if served:
                self.served = served
            provider = (headers.get("x-omniroute-provider")
                        or headers.get("X-Omniroute-Provider") or "")
            if provider:
                self.served_provider = provider
            usage = body.get("usage") or {}
            content = message.get("content") or ""
            if PLACEHOLDER_MARKER in content and not message.get("tool_calls"):
                if placeholder_wait >= MAX_PLACEHOLDER_RETRIES:
                    raise RuntimeError(f"{self.model} is not warm: still booting after "
                                       f"{placeholder_wait} checks")
                placeholder_wait += 1
                time.sleep(15)
                continue
            return message, usage

        raise RuntimeError(f"provider failed after {MAX_REQUEST_ATTEMPTS} attempts: "
                           f"{last_error!r}")


# ---------- tools ----------


class ToolBox:
    """Executes the agent's tools inside one repository and reports what happened."""

    def __init__(self, repo: Path, policy: HarnessPolicy,
                 extra_tools: list[dict] | None = None, mcp=None, skills=None):
        self.repo = repo
        self.policy = policy
        self.actions: list[dict] = []
        # Tools the episode was given on top of the local ones (the MCP shelf
        # and the skill catalog), and what answers for them. All empty when the
        # run wants a bare harness, so a measured comparison is never changed
        # silently.
        self.extra_tools = list(extra_tools or [])
        self.mcp = mcp
        self.skills = skills
        self._allowed = {tool["function"]["name"] for tool in TOOLS} | {
            tool["function"]["name"] for tool in self.extra_tools}

    # -- helpers --

    def _resolve(self, path: str) -> Path:
        target = (self.repo / str(path)).resolve()
        if self.repo.resolve() not in target.parents and target != self.repo.resolve():
            raise ValueError(f"path escapes the repository: {path}")
        return target

    def _clip(self, text: str) -> str:
        limit = self.policy.observation_chars
        if limit and len(text) > limit:
            return text[:limit] + f"\n... [{len(text) - limit} characters truncated]"
        return text

    def _shell(self, command: str, timeout: float = 180.0) -> str:
        bash = shutil.which("bash")
        argv = [bash, "-lc", command] if bash else ["cmd", "/c", command]
        try:
            proc = subprocess.run(argv, cwd=str(self.repo), capture_output=True, text=True,
                                  timeout=timeout, encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            return f"[command timed out after {timeout:.0f}s]"
        out = (proc.stdout or "") + (proc.stderr or "")
        return out.strip() or f"[exit {proc.returncode}, no output]"

    # -- tools --

    def list_files(self) -> str:
        skip = {".git", "__pycache__", ".pytest_cache", "opencode.json"}
        rows = []
        for path in sorted(self.repo.rglob("*")):
            if any(part in skip for part in path.parts):
                continue
            if path.is_file():
                rows.append(f"{path.relative_to(self.repo).as_posix()} "
                            f"({path.stat().st_size} bytes)")
        return "\n".join(rows) or "[empty repository]"

    def read_file(self, path: str, start: int = 1) -> str:
        target = self._resolve(path)
        if not target.exists():
            return f"[no such file: {path}]"
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(1, int(start or 1))
        window = lines[start - 1:start - 1 + max(1, self.policy.read_lines)]
        numbered = [f"{start + i:>4} | {line}" for i, line in enumerate(window)]
        tail = "" if start - 1 + len(window) >= len(lines) else \
            f"\n... [{len(lines) - (start - 1 + len(window))} more lines]"
        return "\n".join(numbered) + tail

    def write_file(self, path: str, content: str) -> str:
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"[wrote {len(content)} characters to {path}]"

    def edit_file(self, path: str, old_string: str, new_string: str) -> str:
        target = self._resolve(path)
        if not target.exists():
            return f"[no such file: {path}]"
        text = target.read_text(encoding="utf-8", errors="replace")
        count = text.count(old_string)
        if count != 1:
            return f"[old_string occurs {count} times in {path}; need exactly one]"
        target.write_text(text.replace(old_string, new_string, 1), encoding="utf-8")
        return f"[edited {path}]"

    def find_skills(self, query: str, limit: int = 4) -> str:
        """Rank the catalog: what is already written for this kind of task."""
        if self.skills is None:
            return ("[no skill catalog in this run: it is a policy decision, "
                    "and this episode was run without it]")
        return skills_index.render_search(self.skills, str(query), int(limit or 4))

    def read_skill(self, name: str, chars: int = skills_index.CONTRACT_CHARS) -> str:
        """Open one contract, from the same file a person would open."""
        if self.skills is None:
            return "[no skill catalog in this run]"
        return skills_index.render_contract(self.skills, str(name), int(chars or
                                            skills_index.CONTRACT_CHARS))

    def run_tests(self) -> str:
        return self._shell("python -m pytest -q -p no:cacheprovider")

    def run_command(self, command: str) -> str:
        return self._shell(str(command))

    def execute(self, name: str, args: dict) -> str:
        if str(name).startswith("mcp__"):
            observation = (self.mcp.call(str(name), args if isinstance(args, dict) else {})
                           if self.mcp is not None
                           else "[refused: no mcp shelf is open in this run]")
            self.actions.append({"tool": name, "args": args, "observation": observation})
            return self._clip(observation)
        fn = getattr(self, name, None)
        if fn is None or name not in self._allowed:
            return f"[unknown tool: {name}]"
        try:
            observation = fn(**args) if isinstance(args, dict) else fn()
        except TypeError as exc:
            observation = f"[bad arguments for {name}: {exc}]"
        except ValueError as exc:
            observation = f"[refused: {exc}]"
        except Exception as exc:  # a broken tool must not kill the episode
            observation = f"[tool {name} failed: {exc.__class__.__name__}: {exc}]"

        self.actions.append({"tool": name, "args": args, "observation": observation})
        return self._clip(observation)


# ---------- prompt ----------


def system_prompt(policy: HarnessPolicy, file_list: str | None, tests: str | None) -> str:
    parts = [
        "You are a coding agent working in a small repository.",
        "Fix the task by editing files with the tools; then run the tests and make them pass.",
        "Work in the repository root; paths are relative to it. Keep edits minimal and correct.",
    ]
    if policy.include_file_list and file_list:
        parts.append(f"Files in the repository:\n{file_list}")
    if policy.include_initial_tests and tests:
        parts.append(f"The test suite currently reports:\n{tests}")
    if policy.include_skill_catalog:
        parts.append(
            "This workspace keeps a catalog of written procedures for recurring "
            "tasks. Search it with find_skills before you invent an approach of "
            "your own, then open a candidate with read_skill. A procedure that "
            "exists is cheaper to follow than one you improvise, and it states "
            "when it does not apply.")
    return "\n\n".join(parts)


# ---------- the episode ----------


def _usage_tokens(usage: dict) -> dict:
    """Token counts in the same shape the opencode runner records."""
    details = usage.get("prompt_tokens_details") or {}
    prompt = usage.get("prompt_tokens", 0)
    completion = usage.get("completion_tokens", 0)
    return {
        "input": prompt,
        "output": completion,
        "reasoning": usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0),
        "cache_read": details.get("cached_tokens", 0) or usage.get("cache_read_tokens", 0) or 0,
        "cache_write": 0,
        "total": usage.get("total_tokens", 0) or prompt + completion,
    }


def run_task(task_id: str, model: str = DEFAULT_MODEL, label: str = "ours",
             policy: HarnessPolicy | None = None, timeout: float = 900.0,
             mcp_servers: tuple[str, ...] = ()) -> dict:
    """Run one episode and return its record (same shape as the opencode runner).

    ``mcp_servers`` names services from the shared ``mcp.json`` (Telegram, the
    Google shelf, a database, ...) whose tools the agent may call. Empty by
    default: the bare harness stays the baseline everything is compared to.
    Whether the agent may search the skill catalog is the policy's decision
    (``include_skill_catalog``), for the same reason: it has to be ablatable.
    """
    policy = policy or get_policy("baseline")
    task_file = runner.TASKS_DIR / task_id / "task.json"
    if not task_file.exists():
        raise SystemExit(f"no such task: {task_id}")
    task = json.loads(task_file.read_text(encoding="utf-8"))

    scratch = runner.make_scratch(task, f"{label}-{policy.name}")
    repo = scratch / "repo"
    provider = Provider(model, runner.api_key(), policy.temperature)

    # The shelf is opened before the loop: a server that cannot start is an
    # episode fact (recorded), not a reason to lose the episode.
    hub = None
    mcp_schemas: list[dict] = []
    mcp_missing: list[str] = []
    mcp_evidence: dict | None = None
    if mcp_servers:
        try:
            hub = mcp_client.McpHub(mcp_client.load_servers(), tuple(mcp_servers))
            mcp_schemas = hub.tools()
        except (mcp_client.McpError, OSError) as exc:
            mcp_missing.append(str(exc)[:300])
            hub = None
    skill_schemas: list[dict] = []
    catalog = None
    catalog_missing = ""
    if policy.include_skill_catalog:
        try:
            catalog = skills_index.load()
        except (skills_index.CatalogError, OSError) as exc:
            catalog_missing = str(exc)[:300]
        else:
            skill_schemas = list(skills_index.TOOL_SCHEMAS)
    tools = list(TOOLS) + skill_schemas + mcp_schemas
    toolbox = ToolBox(repo, policy, extra_tools=skill_schemas + mcp_schemas,
                      mcp=hub, skills=catalog)

    file_list = toolbox.list_files() if policy.include_file_list else None
    initial_tests = toolbox.run_tests() if policy.include_initial_tests else None
    toolbox.actions.clear()  # the setup probes are not part of the trajectory

    system_text = system_prompt(policy, file_list, initial_tests)
    head: list[dict] = [
        {"role": "system", "content": system_text},
        {"role": "user", "content": task["prompt"]},
    ]
    # History as whole blocks (an assistant turn with its tool results, a nudge,
    # ...). A step records how many blocks existed when it was sent, so the
    # replay judge can rebuild that exact context instead of guessing an offset.
    blocks: list[list[dict]] = []
    steps: list[dict] = []
    served_models: list[str] = []
    tokens = {"input": 0, "output": 0, "reasoning": 0, "cache_read": 0,
              "cache_write": 0, "total": 0}
    nudges = 0
    pending_nudge = False
    started = time.time()
    stop_reason = "max_steps"
    error = None

    def context() -> list[dict]:
        """The messages this policy would send right now."""
        if policy.context_mode == "window":
            kept = [m for block in blocks[-max(1, policy.window_steps):] for m in block]
        else:
            kept = [m for block in blocks for m in block]
        return head + kept

    try:
        for index in range(max(1, policy.max_steps)):
            if time.time() - started > timeout:
                stop_reason = "timeout"
                break
            request_messages = context()
            call_started = time.time()
            message, usage = provider.chat(request_messages, tools)
            latency = round(time.time() - call_started, 2)
            served_models.append(provider.served_provider or provider.served)
            step_tokens = _usage_tokens(usage)
            for key in tokens:
                tokens[key] += step_tokens[key]

            calls = message.get("tool_calls") or []
            block: list[dict] = [message]
            step = {
                "index": len(steps),
                "kind": "tool" if calls else "text",
                "served": provider.served_provider or provider.served,
                "history_len": len(blocks),
                "prompt_chars": sum(len(m.get("content") or "") for m in request_messages),
                "latency": latency,
                "tokens": step_tokens,
            }
            if calls:
                step["tools"] = [c["function"]["name"] for c in calls]
            else:
                step["text"] = (message.get("content") or "")[:400]
            if pending_nudge:
                step["nudged"] = True
                pending_nudge = False

            for call in calls:
                name = call["function"]["name"]
                try:
                    args = json.loads(call["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                observation = toolbox.execute(name, args)
                block.append({"role": "tool", "tool_call_id": call.get("id"),
                              "content": observation})
                step.setdefault("observations", []).append(observation[:400])

            steps.append(step)
            blocks.append(block)

            if not calls:
                tail = toolbox.run_tests()
                if policy.verify_before_finish and nudges < policy.max_verify_nudges:
                    nudges += 1
                    nudge = ("The tests still fail. Here is the current output:\n"
                             f"{toolbox._clip(tail)}\nContinue until they pass.")
                    blocks.append([{"role": "user", "content": nudge}])
                    pending_nudge = True
                    continue
                stop_reason = "finished"
                break
        else:
            stop_reason = "max_steps"
    except Exception as exc:  # record the failure, never lose the episode
        error = f"{exc.__class__.__name__}: {exc}"
        stop_reason = "error"
    finally:
        if hub is not None:
            # Read the evidence before the shelf closes: the call count lives
            # in the open sessions.
            mcp_evidence = hub.evidence()
            hub.close()

    wall = round(time.time() - started, 2)
    result = runner.evaluate(scratch, task_id)

    record = {
        "schema": 1,
        "task": task["id"],
        "title": task.get("title", ""),
        "kind": task.get("kind", ""),
        "label": label,
        "agent": "ours",
        "policy": policy.descriptor(),
        "model": model,
        # The alias can be served by more than one upstream over a long episode;
        # the set is recorded so a comparison can never mix two models unseen.
        "served_models": sorted(set(served_models)),
        "prompt": task["prompt"],
        "wall_seconds": wall,
        "stop_reason": stop_reason,
        "error": error,
        "solved": result["solved"],
        "tests": result,
        "tools": {},
        # What the shelf gave the episode, and what it cost to open it.
        "mcp": (mcp_evidence if mcp_evidence is not None
                else {"servers_requested": list(mcp_servers),
                      "failures": [{"error": m} for m in mcp_missing] if mcp_missing else []}),
        # What the catalog gave the episode: which queries were asked, which
        # contracts were opened, and how many characters that cost. A lookup
        # that never paid for itself shows up here as cost without a hit.
        "skills": {**skills_index.evidence(toolbox.actions, catalog),
                   **({"failures": [catalog_missing]} if catalog_missing else {})},
        "tool_calls": len([s for s in steps if s.get("kind") == "tool"]),
        "tokens": tokens,
        "steps": steps,
        # Raw material for the replay judge: the prompts as assembled, every
        # message verbatim, and the unclipped tool observations. Without these
        # a candidate policy could only be guessed at, never recomputed.
        "system_prompt": system_text,
        "user_prompt": task["prompt"],
        "setup": {"file_list": file_list, "initial_tests": initial_tests},
        "blocks": blocks,
        "trajectory": [
            {"tool": a["tool"], "args": a["args"], "observation": a["observation"]}
            for a in toolbox.actions
        ],
        "scratch": str(scratch),
        "final_text": (steps[-1].get("text") if steps else "") or "",
    }
    counts: dict = {}
    for action in toolbox.actions:
        counts[action["tool"]] = counts.get(action["tool"], 0) + 1
    record["tools"] = counts

    (scratch / "record.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record
