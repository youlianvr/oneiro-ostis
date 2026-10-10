"""The declared settings catalog: the owner's answer, in one place.

Every setting Oneiro reads is declared exactly once in `SETTINGS`: the key a
human sees, the environment variable, the older names still honoured, the type,
the default, and the sentence that explains it. `python/oneiro/config.py` is what
*resolves* those declarations (the file, the keys file, the environment, the
project `.env`, the default), validates them and writes them; this module is only
the catalog itself, so the whole product surface can be read top to bottom
without reading any logic, and a new setting is one entry here and nothing else.

Two fields carry meaning beyond the type:

* ``readonly``  — resolved by code, never stored in the file (a value that would
  move the file it is written to, like the data root, or one the code fixes, like
  the loopback address).
* ``pending``   — declared and visible in the settings page, but the part of the
  product that acts on it is not in this build yet. Saying so is the difference
  between a catalog and a promise.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# One root for the product. The old settings directory sat inside the agent
# workspace's parent (``~/.openclaw``), which coupled a standalone product to
# where it happened to be developed; ``~/.oneiro`` is outside it.
DEFAULT_DATA_DIR = "~/.oneiro"

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
    kind: str = "str"           # str | int | bool | path | secret | choice | json
    aliases: tuple[str, ...] = ()
    readonly: bool = False      # resolved by code, never stored in the file
    choices: tuple[str, ...] = ()   # allowed values for kind="choice"
    pending: bool = False       # declared, not yet in force in this build

    @property
    def secret(self) -> bool:
        return self.kind == "secret"

    @property
    def empty_means_unset(self) -> bool:
        """Paths fall back to their default when blank; a secret falls to env."""
        return self.kind in ("path", "secret", "json")


#: The provider list a fresh install reads, in the shape OpenCode and Hermes use:
#: `base_url` plus the *name* of an environment variable holding the key, never the
#: key itself. `oneiro/models.py` (W4) is what reads this.
DEFAULT_PROVIDERS: list[dict[str, Any]] = [
    {"name": "local", "base_url": "http://127.0.0.1:20128/v1",
     "key_env": "OMNIROUTE_API_KEY", "discover_models": True},
]
#: Structured settings whose value is a plain list of non-empty strings.
JSON_LISTS = ("models.fallback", "skills.paths", "research.sources")

SETTINGS: tuple[Setting, ...] = (
    Setting("web.host", "ONEIRO_WEB_HOST", "127.0.0.1", "Web address",
            "Fixed to loopback: Oneiro is not reachable from the network.",
            "Interface", readonly=True),
    Setting("web.port", "ONEIRO_WEB_PORT", 9899, "Web port",
            "One origin for chat, settings and /oneiro/.", "Interface", kind="int"),
    Setting("runtime.data_dir", "ONEIRO_DATA_DIR", DEFAULT_DATA_DIR, "Runtime data",
            "Where Oneiro keeps its own files. Read-only here: changing it moves "
            "the settings file, so it is set with ONEIRO_DATA_DIR before first start.",
            "Work", kind="path", readonly=True),
    Setting("llm.manager_model", "ONEIRO_MANAGER_MODEL", "main", "Legacy manager model",
            "The retired alias for the manager's model. The per-role models are declared as "
            "models.roles.manager; nothing acts on this key, so it is declared only and goes "
            "with the name it replaces.",
            "Model", pending=True),
    Setting("llm.researcher_model", "ONEIRO_RESEARCHER_MODEL", "auto/coding",
            "Legacy researcher model",
            "The retired alias for the researcher's model; models.roles.researcher is the "
            "declared one and nothing acts on this key.",
            "Model", pending=True),
    Setting("llm.executor_model", "ONEIRO_EXECUTOR_MODEL", "auto/coding",
            "Legacy executor model",
            "The retired alias for the executor's model; models.roles.executor is the "
            "declared one and nothing acts on this key.",
            "Model", pending=True),
    Setting(
        "llm.base_url", "ONEIRO_LLM_BASE_URL", "http://127.0.0.1:20128/v1",
        "Provider address",
        "Address of an OpenAI-compatible provider. Any one that understands /chat/completions. "
        "This is the pre-registry name for that address: while models.providers is still the "
        "shipped list, this value decides where the provider named local points.",
        "Model", aliases=("ONEIRO_BASE_URL",),
    ),
    Setting(
        "llm.api_key", "ONEIRO_LLM_API_KEY", "",
        "Provider key",
        "Empty — looked up in ~/.config/keys.env, the environment, and the project .env. This "
        "is the pre-registry key: it answers for the first provider of the list when that "
        "provider's key_env finds nothing, and no other provider ever borrows it.",
        "Model", kind="secret", aliases=("ONEIRO_API_KEY", "OMNIROUTE_API_KEY"),
    ),
    Setting(
        "llm.model", "ONEIRO_LLM_MODEL", "auto/coding",
        "Default model",
        "The pre-registry name for the default model. It decides which model is used while "
        "models.default was never set, which is how an install keeps its choice.",
        "Model",
    ),
    Setting(
        "chat.history_messages", "ONEIRO_CHAT_HISTORY", 10,
        "Earlier messages sent",
        "How many earlier messages of the open conversation go to the model with each reply. At least 1.",
        "Model", kind="int",
    ),
    Setting(
        "chat.context_chars", "ONEIRO_CHAT_CONTEXT_CHARS", 6000,
        "Earlier-message size limit",
        "The most characters of earlier messages sent with each reply. Older ones are left out, and the reply says so.",
        "Model", kind="int",
    ),
    Setting(
        # 127.0.0.1, not localhost: on Windows localhost resolves to ::1 first, and a
        # Docker port published on IPv4 only stalls every connect ~2 s, which
        # sc-client then reports as an unresponsive server.
        "graph.host", "ONEIRO_HOST", "127.0.0.1",
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
        "Legacy panel port",
        "The port of the old dashboard server, which is not part of this build. Nothing "
        "acts on this key: it is declared only, and it goes with that server.",
        "Interface", kind="int", pending=True,
    ),
    Setting(
        "world.seed", "ONEIRO_SEED", "oneiro-0",
        "Legacy island-world seed",
        "The seed of the island-world experiment, which is out of v1 and read only by the "
        "science scripts. Nothing in this build acts on it: it is declared only here.",
        "World", pending=True,
    ),
    Setting(
        "loop.rounds", "ONEIRO_ROUNDS", 4,
        "Legacy rounds per run",
        "How many self-improvement rounds one cycle run made. That cycle is out of v1 and "
        "nothing reads this key any more: it is declared only.",
        "Cycle", kind="int", pending=True,
    ),
    Setting(
        "series.seeds", "ONEIRO_SEEDS", 5,
        "Legacy seeds in a series",
        "How many seeds one series run walked through. That series runner is out of v1 and "
        "nothing reads this key any more: it is declared only.",
        "Cycle", kind="int", pending=True,
    ),
    Setting(
        "workspace", "ONEIRO_WORKSPACE", "~/.openclaw/workspace",
        "Legacy working folder",
        "The retired name for the folder the agent works in. This build uses tools.workspace "
        "instead, so nothing acts on this key: it is declared only, and it goes with the "
        "name it replaces.",
        "Work", kind="path", pending=True,
    ),
    Setting(
        "bench.dir", "ONEIRO_BENCH_DIR", "~/.openclaw/bench-memory",
        "Legacy measurements folder",
        "Where the memory benchmark runs are written. That benchmark is not part of this "
        "build and only its own script reads this key: it is declared only here.",
        "Measurements", kind="path", pending=True,
    ),
    Setting(
        "bench.lme_dir", "ONEIRO_LME_DIR", "~/.openclaw/datasets/longmemeval",
        "Legacy LongMemEval dataset",
        "Where that dataset lived. It is not in the repository — it is too large — and the "
        "benchmark that used it is not part of this build, so nothing acts on this key.",
        "Measurements", kind="path", pending=True,
    ),
    Setting(
        "mcp.source", "ONEIRO_MCP_SOURCE", "~/.openclaw/workspace/.mcp.json",
        "Legacy MCP list",
        "The list the retired harness read its MCP servers from. Oneiro reads its own "
        "list (mcp.file) and surveys the other clients' files read-only, so nothing "
        "acts on this key: it is declared only, and it goes with that harness in W9.",
        "Harness", kind="path", pending=True,
    ),
    # ---------- appearance ----------
    Setting(
        "ui.language", "ONEIRO_UI_LANGUAGE", "ru",
        "Language",
        "The language of the interface and of what Oneiro says back. Russian or English.",
        "Appearance", kind="choice", choices=("ru", "en"), pending=False,
    ),
    Setting(
        "ui.theme", "ONEIRO_UI_THEME", "night",
        "Theme",
        "Which theme the window uses. Verified for contrast in every one of them.",
        "Appearance", kind="choice",
        choices=("night", "paper", "editorial", "cosmic", "agentic"), pending=False,
    ),
    Setting(
        "ui.density", "ONEIRO_UI_DENSITY", "comfortable",
        "List density",
        "How tightly lists and cards are packed: comfortable, or compact to fit more on screen.",
        "Appearance", kind="choice", choices=("comfortable", "compact"), pending=True,
    ),
    Setting(
        "ui.window", "ONEIRO_UI_WINDOW", "window",
        "How Oneiro opens",
        "Its own window, a browser tab, or either. A window that cannot start falls back to the browser and says so.",
        "Window", kind="choice", choices=("window", "browser", "both"), pending=False,
    ),
    Setting(
        "ui.tray", "ONEIRO_UI_TRAY", False,
        "Close to tray",
        "Whether closing the window hides Oneiro instead of stopping it. Off means closing stops it, graph included.",
        "Window", kind="bool", pending=True,
    ),
    # ---------- initiative ----------
    Setting(
        "initiative.level", "ONEIRO_INITIATIVE_LEVEL", "scheduled",
        "How much Oneiro starts on its own",
        "off: nothing without you. on_command: only what you ask for. scheduled: also the tasks you put on a "
        "schedule. proactive: it may also speak up from memory and open tasks on its own.",
        "Initiative", kind="choice",
        choices=("off", "on_command", "scheduled", "proactive"),
    ),
    Setting(
        "initiative.suggestions", "ONEIRO_INITIATIVE_SUGGESTIONS", True,
        "Suggestions from memory",
        "Whether unfinished work and things you asked to revisit may come back as a suggestion.",
        "Initiative", kind="bool",
    ),
    Setting(
        "initiative.quiet_hours", "ONEIRO_INITIATIVE_QUIET", "22:00-09:00",
        "Quiet hours",
        "A window in which Oneiro does not interrupt you with notifications. Empty means never quiet.",
        "Initiative",
    ),
    # ---------- permissions ----------
    Setting(
        "permissions.mode", "ONEIRO_PERMISSIONS_MODE", "workspace",
        "Default permissions",
        "strict: confirm anything outside the memory. workspace: free inside the working folder and free web reads. "
        "trusted: confirm only what is refused below.",
        "Permissions", kind="choice", choices=("strict", "workspace", "trusted"),
    ),
    Setting(
        "permissions.web_read", "ONEIRO_PERM_WEB_READ", "allow",
        "Read web pages",
        "Whether Oneiro may read a public address it asks for.",
        "Permissions", kind="choice", choices=("allow", "ask", "deny"),
    ),
    Setting(
        "permissions.write_workspace", "ONEIRO_PERM_WRITE_WORKSPACE", "allow",
        "Write in the working folder",
        "Whether Oneiro may write files where it is allowed to work.",
        "Permissions", kind="choice", choices=("allow", "ask", "deny"),
    ),
    Setting(
        "permissions.write_outside", "ONEIRO_PERM_WRITE_OUTSIDE", "ask",
        "Write outside the working folder",
        "ask: anything outside the working folder needs your confirmation first, and the "
        "confirmation covers exactly that path and that text. allow: it writes there "
        "freely. deny: it never writes outside the folder.",
        "Permissions", kind="choice", choices=("allow", "ask", "deny"),
    ),
    Setting(
        "permissions.delete", "ONEIRO_PERM_DELETE", "ask",
        "Delete files",
        "Removal always goes to the trash; this is whether it needs your confirmation first.",
        "Permissions", kind="choice", choices=("allow", "ask", "deny"),
    ),
    Setting(
        "permissions.install", "ONEIRO_PERM_INSTALL", "ask",
        "Install packages",
        "Whether Oneiro may install software it needs, and whether it asks first.",
        "Permissions", kind="choice", choices=("allow", "ask", "deny"),
    ),
    Setting(
        "permissions.exec", "ONEIRO_PERM_EXEC", "ask",
        "Run commands",
        "Whether Oneiro may run a local command, and whether it asks first.",
        "Permissions", kind="choice", choices=("allow", "ask", "deny"),
    ),
    Setting(
        "permissions.send_publish", "ONEIRO_PERM_SEND", "deny",
        "Send or publish for you",
        "Messages and publications in your name stay refused unless you allow them here.",
        "Permissions", kind="choice", choices=("allow", "ask", "deny"),
    ),
    Setting(
        "agent.max_turns", "ONEIRO_AGENT_MAX_TURNS", 12,
        "Tool steps per turn",
        "How many model turns that call tools one reply may take before it stops and says so.",
        "Agent", kind="int", aliases=("ONEIRO_AGENT_MAX_STEPS",),
    ),
    Setting(
        "agent.step_timeout", "ONEIRO_AGENT_STEP_TIMEOUT", 60,
        "Model call timeout",
        "Seconds allowed for one model call, its repeats and checks included. Tool calls "
        "have their own limit.",
        "Agent", kind="int",
    ),
    Setting(
        "agent.tool_timeout", "ONEIRO_AGENT_TOOL_TIMEOUT", 30,
        "Tool call timeout",
        "Seconds allowed for one tool call. A write that runs longer is uncertain, not retried.",
        "Agent", kind="int",
    ),
    Setting(
        "agent.show_steps", "ONEIRO_AGENT_SHOW_STEPS", True,
        "Show tool steps",
        "Whether every tool call, refusal and approval request appears in the conversation as it happens.",
        "Agent", kind="bool", pending=True,
    ),
    # ---------- providers and models ----------
    Setting(
        "models.providers", "ONEIRO_MODELS_PROVIDERS", DEFAULT_PROVIDERS,
        "Providers",
        "The providers Oneiro may call, in the shape OpenCode and Hermes use: name, base_url, "
        "key_env, discover_models, models, enabled. A key is named by the environment variable "
        "that holds it and is never stored here; a provider with enabled false is skipped. "
        "They are used in the order given, and the first is the default one.",
        "Providers", kind="json",
    ),
    Setting(
        "models.default", "ONEIRO_MODELS_DEFAULT", "auto/coding",
        "Default model",
        "The model every role uses unless a role says otherwise. The name asked for may be a "
        "routing alias; the model that actually answered is named in the accounting.",
        "Providers",
    ),
    Setting(
        "models.roles.manager", "ONEIRO_MODEL_MANAGER", "",
        "Manager model",
        "The model for conversation and coordination. Empty means the default model.",
        "Providers",
    ),
    Setting(
        "models.roles.researcher", "ONEIRO_MODEL_RESEARCHER", "",
        "Researcher model",
        "The model for independent research. Empty means the default model.",
        "Providers",
    ),
    Setting(
        "models.roles.executor", "ONEIRO_MODEL_EXECUTOR", "",
        "Executor model",
        "The model for verified task execution. Empty means the default model.",
        "Providers",
    ),
    Setting(
        "models.fallback", "ONEIRO_MODELS_FALLBACK", [],
        "Fallback models",
        "Models it may fall back to, in order, and only where a real call showed the "
        "capability matches. Each entry is a model name or provider/model, and at most three "
        "are tried. Empty falls back nowhere.",
        "Providers", kind="json",
    ),
    Setting(
        "models.accounting", "ONEIRO_MODELS_ACCOUNTING", True,
        "Count every call",
        "Whether every provider call — its role, model, attempt, outcome, latency, tokens and "
        "cost — is recorded, and readable with `oneiro verify-model`. Off records nothing, "
        "and the report says so instead of looking empty.",
        "Providers", kind="bool",
    ),
    # ---------- tools ----------
    Setting(
        "tools.workspace", "ONEIRO_TOOLS_WORKSPACE", "~/.oneiro/workspace",
        "Tool workspace",
        "The folder the file tools may write inside. The default is Oneiro's own folder; "
        "`permissions.write_workspace` decides whether a write still asks first.",
        "Tools", kind="path",
    ),
    Setting(
        "tools.internet", "ONEIRO_TOOLS_INTERNET", True,
        "Tool web access",
        "Whether the agent may read a public URL it asks for. `permissions.web_read` decides whether it asks first.",
        "Tools", kind="bool",
    ),
    Setting(
        "tools.max_file_bytes", "ONEIRO_TOOLS_MAX_FILE", 120000,
        "Tool file size limit",
        "The most bytes one tool reads or writes in a single call.",
        "Tools", kind="int",
    ),
    # ---------- MCP ----------
    Setting(
        "mcp.file", "ONEIRO_MCP_FILE", "~/.oneiro/mcp.json",
        "MCP server list",
        "Where Oneiro keeps its own list of MCP servers, in the shape other clients already use.",
        "MCP", kind="path",
    ),
    Setting(
        "mcp.autostart", "ONEIRO_MCP_AUTOSTART", True,
        "Start enabled servers at launch",
        "Whether the servers you enabled are started when Oneiro starts.",
        "MCP", kind="bool",
    ),
    # ---------- skills ----------
    Setting(
        "skills.catalog", "ONEIRO_SKILLS_CATALOG", "",
        "Skills catalog",
        "Your own catalog file, in the shape of the one that ships with Oneiro. Empty uses "
        "the shipped catalog. A file that is missing, is not valid JSON or holds no "
        "records is named as such, never quietly ignored.",
        "Skills", kind="path",
    ),
    Setting(
        "skills.paths", "ONEIRO_SKILLS_PATHS", [],
        "Your skill folders",
        "Extra folders with skills, searched in addition to the shipped catalog. A folder "
        "may be the folder of skills itself or a parent that keeps them under "
        ".agents/skills. A skill found in one of them is searchable and readable too, and "
        "says so when it was never reviewed.",
        "Skills", kind="json",
    ),
    Setting(
        "skills.auto_use", "ONEIRO_SKILLS_AUTO_USE", "ask",
        "Use a found skill",
        "ask: Oneiro says which skill it found and waits. auto: it uses the skill and says "
        "so afterwards. Nothing in this build acts on this key yet: the two skill tools "
        "are offered and the model decides when to look, so no choice is made here for the "
        "owner.",
        "Skills", kind="choice", choices=("ask", "auto"), pending=True,
    ),
    # ---------- memory, research, attachments ----------
    Setting(
        "memory.facts_budget", "ONEIRO_FACTS_BUDGET", 2000,
        "Curated facts budget",
        "How many characters of your own facts Oneiro keeps in mind for every reply. A fact "
        "that would push the saved set past this is refused with the limit in the reason.",
        "Memory", kind="int",
    ),
    Setting(
        "research.sources", "ONEIRO_RESEARCH_SOURCES", ["web"],
        "Research sources",
        "Which sources research may use. `web` is the public web.",
        "Research", kind="json", pending=False,
    ),
    Setting(
        "attachments.max_bytes", "ONEIRO_ATTACH_MAX_BYTES", 20000000,
        "Attachment size limit",
        "The largest file you may attach in one message in bytes.",
        "Attachments", kind="int", pending=False,
    ),
    Setting(
        "attachments.max_pages", "ONEIRO_ATTACH_MAX_PAGES", 50,
        "Attachment page limit",
        "How many pages of a PDF are read in one message.",
        "Attachments", kind="int", pending=False,
    ),
    # ---------- operations ----------
    Setting(
        "logging.level", "ONEIRO_LOG_LEVEL", "info",
        "Log detail",
        "How much Oneiro writes to its own log: debug, info, warning or error.",
        "Operations", kind="choice", choices=("debug", "info", "warning", "error"),
        pending=True,
    ),
    Setting(
        "backup.mode", "ONEIRO_BACKUP_MODE", "manual",
        "Memory backup",
        "manual: you take a backup when you want one. scheduled: Oneiro also does it on its own schedule.",
        "Operations", kind="choice", choices=("manual", "scheduled"), pending=True,
    ),
)

#: The catalog by key, and the attribute spelling of the `settings` object
#: (`graph_port` -> `graph.port`). Both derived here so no other module has to
#: rebuild them and disagree.
_BY_KEY: dict[str, Setting] = {s.key: s for s in SETTINGS}
_ATTR: dict[str, str] = {s.key.replace(".", "_"): s.key for s in SETTINGS}
