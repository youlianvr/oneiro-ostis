"""What each route is, and the 5 canonical screens built from the declared registry.

Page identity lives here, not in the browser: `web.py` names a page, this module
decides what it says and what it shows. Adding a setting means adding one
`Setting` to `config.SETTINGS`; the form follows, because the form is generated
from that registry rather than hand-written in HTML.

Five canonical screens (§ 3 Master Plan):
1. Conversation: 3 zones (conversations list & search, chat feed with action cards, context inspector).
2. Tasks: list, lifecycle states, cron schedules, run history.
3. Tools: MCP servers, local tools, skills tabs.
4. Settings: tabs for Model, Permissions, MCP, Skills, Language/Theme, Data, About.
5. Memory: curated facts, memory substrate / graph status, history search.

Legacy routes (/setup, /oneiro/) stay mapped and accessible for compatibility.
"""
from __future__ import annotations

import html
from pathlib import Path
from string import Template
from typing import Any

from oneiro import config, i18n

TEMPLATE = Path(__file__).parent / "static" / "page.html"

# route page id -> (document title, heading, what this page is for)
PAGES: dict[str, tuple[str, str, str]] = {
    "chat": (
        "Oneiro — conversation",
        "Conversation",
        "Conversation with your persistent assistant. Action cards show tool calls, "
        "approvals and questions directly in the feed without raw JSON.",
    ),
    "tasks": (
        "Oneiro — tasks",
        "Tasks & Schedules",
        "Independent and scheduled work. See task states, run history and standing schedules.",
    ),
    "tools": (
        "Oneiro — tools",
        "Tools & Capabilities",
        "Three capabilities: connected MCP servers, local system tools, and searchable skills.",
    ),
    "settings": (
        "Oneiro — settings",
        "Oneiro settings",
        "Every setting Oneiro declares, in one place. Values come from this file, "
        "then the environment, then the declared default — the page shows which one "
        "answered. A stored provider key is never sent back to the browser.",
    ),
    "memory": (
        "Oneiro — memory",
        "Memory & Graph",
        "The persistent memory substrate: your curated facts, past conversation search, and OSTIS status.",
    ),
    # Legacy routes mapped to their screens
    "setup": (
        "Oneiro — setup",
        "Setup",
        "Setup reads the real state of this machine: the OSTIS server, the provider "
        "key, the dependencies the memory layer needs. It never starts Docker or "
        "changes a setting for you.",
    ),
    "graph": (
        "Oneiro — graph",
        "Graph panel",
        "OSTIS is the memory substrate and the only one. This page reports what "
        "could actually be read from the running server just now — reachability "
        "alone is not counted as success. No substitute memory store exists.",
    ),
}

NAV = (
    ("/", "Chat", "chat"),
    ("/tasks", "Tasks", "tasks"),
    ("/tools", "Tools", "tools"),
    ("/settings", "Settings", "settings"),
    ("/memory", "Memory", "memory"),
    # Compatibility links
    ("/setup", "Setup", "setup"),
    ("/oneiro/", "Graph", "graph"),
)

FORM_PAGES = ("settings", "setup")

#: Where a value came from, said in words the owner can act on.
SOURCES = {
    "file": "this settings file",
    "keys.env": "your keys file",
    "env": "the environment",
    "project .env": "the project .env",
    "default": "the declared default",
}

SECRET_NOTE = "Stored keys are never returned. An empty field leaves the current key unchanged."


def _options(row: dict) -> list[str]:
    """The closed set a choice or boolean setting may take."""
    if row["kind"] == "bool":
        return ["true", "false"]
    return list(row["choices"])


def _select(row: dict, attributes: str) -> str:
    """A closed set is a list, never a text box."""
    current = str(row["value"]).strip().lower()
    rendered = "".join(
        f'<option value="{html.escape(option, quote=True)}"'
        f'{" selected" if option == current else ""}>{html.escape(option)}</option>'
        for option in _options(row)
    )
    return f'<select {attributes}>{rendered}</select>'


def _field(row: dict) -> str:
    """One settings row: label, control, and the sentence that explains it."""
    key = html.escape(row["key"], quote=True)
    label = html.escape(row["label"])
    help_text = html.escape(row["help"])
    value = html.escape(str(row["value"]), quote=True)
    attributes = f'name="{key}" id="f-{key}"' + (" disabled" if row["readonly"] else "")
    if row["kind"] in ("choice", "bool"):
        control = _select(row, attributes)
    elif row["kind"] == "json":
        control = (
            f'<textarea rows="6" spellcheck="false" {attributes}>'
            f'{html.escape(str(row["value"]))}</textarea>'
        )
    elif row["kind"] == "int":
        limit = ' max="65535"' if key.endswith(".port") else ""
        control = f'<input type="number" min="1"{limit} value="{value}" {attributes}>'
    elif row["secret"]:
        state = "not set" if not row["set"] else f"set, answered by the {row['source']}"
        control = (
            f'<input type="password" autocomplete="new-password" {attributes}>'
            f'<small>Currently {html.escape(state)}.</small>'
        )
    else:
        control = f'<input type="text" value="{value}" {attributes}>'
    if row["readonly"]:
        control += "<small>Read-only on this page: it is answered by the environment, not the file.</small>"
    if row["pending"]:
        control += (
            '<small class="pending">Declared here; the part of Oneiro that '
            'acts on it is not in this build yet.</small>'
        )
    source = SOURCES.get(row["source"], row["source"])
    control += f'<small class="source">Value from {html.escape(source)}.</small>'
    return f'<div class="field"><label for="f-{key}">{label}</label>{control}<small>{help_text}</small></div>'


def _form(description: dict) -> str:
    """The declared settings, grouped, plus the data root and writability."""
    groups: dict[str, list[str]] = {}
    for row in description["settings"]:
        groups.setdefault(row["group"], []).append(_field(row))
    blocks = [
        f'<fieldset><legend>{html.escape(group)}</legend>{"".join(rows)}</fieldset>'
        for group, rows in groups.items()
    ]
    root = html.escape(description["data_root"], quote=True)
    stored_at = html.escape(description["path"], quote=True)
    if description["writable"]:
        writable = (
            '<p class="ok">Settings file is writable. '
            f'File: <code>{stored_at}</code></p>'
        )
        disabled = ""
    else:
        reason = html.escape(description["writable_error"])
        writable = (
            f'<p class="bad">Settings cannot be saved: {reason}. '
            f'File: <code>{stored_at}</code></p>'
        )
        disabled = " disabled"
    moved = ""
    if description["migrated_from"]:
        moved = (
            '<p class="ok">Settings were migrated from '
            f'<code>{html.escape(description["migrated_from"], quote=True)}</code>.</p>'
        )
    return (
        f"{moved}<p class=\"muted\">One data root: <code>{root}</code></p>{writable}"
        f"<p class=\"muted\">{SECRET_NOTE}</p>"
        f'<form id="settings" method="post" action="/api/settings">'
        f'{"".join(blocks)}<button{disabled}>Save settings</button>'
        f'<p id="result" role="status"></p></form>'
    )


def _graph_section(facts: Any) -> str:
    """What the probe could read, and what it could not."""
    if facts is None:
        return (
            '<section><h2>Memory substrate</h2>'
            '<p class="bad">The graph was not probed for this page.</p></section>'
        )
    if not facts.reachable:
        reasons = "".join(f"<li>{html.escape(reason)}</li>" for reason in facts.blocked)
        return (
            '<section><h2>Memory substrate</h2>'
            '<p class="bad">Unreachable. OSTIS is required; there is no substitute '
            'store, so nothing is shown in its place.</p><ul>{reasons}</ul></section>'
        )
    if not facts.verified:
        reasons = "".join(f"<li>{html.escape(reason)}</li>" for reason in facts.blocked)
        return (
            '<section><h2>Memory substrate</h2>'
            '<p class="bad">Reachable, but nothing could be read back out of the '
            'graph.</p><ul>{reasons}</ul></section>'
        )
    rows = "".join(
        f"<li><code>{html.escape(identifier)}</code></li>" for identifier in facts.identifiers
    )
    return (
        '<section><h2>Memory substrate</h2>'
        f'<p class="ok">Readable. {facts.arcs_found} anchor arc(s) traversable via '
        f'<code>{html.escape(facts.anchor)}</code>; identifier strings read back out '
        f'of the graph in {facts.elapsed_ms} ms.</p>'
        f'<p class="muted">Checked {html.escape(facts.checked_at)}. This is a '
        f'reachability-and-traversal check, not a memory benchmark.</p>'
        f'<ul>{rows}</ul></section>'
    )


_CONVERSATION_SCREEN = (
    '<div class="screen-grid conversation-layout">'
    '  <aside class="panel-left">'
    '    <h3>Conversations</h3>'
    '    <label for="conversation-select" class="sr-only">Conversation</label>'
    '    <select id="conversation-select"></select>'
    '    <button type="button" id="new-conversation" class="btn-subtle">+ New</button>'
    '    <form id="search">'
    '      <label for="search-text" class="sr-only">Search</label>'
    '      <input id="search-text" type="search" placeholder="Search messages..." maxlength="200" required>'
    '      <button type="submit" class="btn-subtle">Find</button>'
    '    </form>'
    '    <p class="muted" id="search-note" role="status"></p>'
    '    <ol id="search-results" class="clean-list"></ol>'
    '  </aside>'
    '  <section class="panel-center">'
    '    <div id="approvals" class="action-feed" role="region" aria-label="Approvals"></div>'
    '    <div id="questions" class="action-feed" role="region" aria-label="Questions"></div>'
    '    <ol id="transcript" class="transcript-feed" aria-live="polite"></ol>'
    '    <form id="chat" class="composer">'
    '      <label for="message">Message</label>'
    '      <textarea id="message" name="message" rows="3" maxlength="4000" placeholder="Type a message or attach a file..." required></textarea>'
    '      <div class="composer-bar">'
    '        <input type="file" id="attachment-file" class="sr-only" multiple>'
    '        <button type="button" id="btn-attach" class="btn-subtle">Attach file</button>'
    '        <span id="attachment-chip" class="pill" hidden></span>'
    '        <button type="submit" class="btn-primary">Send</button>'
    '      </div>'
    '      <p class="bad" id="chat-error" hidden></p>'
    '    </form>'
    '  </section>'
    '  <aside class="panel-right" id="inspector">'
    '    <h3>Turn Inspector</h3>'
    '    <div id="inspector-content" class="inspector-box"><p class="muted">Select a message to view touched memory, tools and context.</p></div>'
    '  </aside>'
    '</div>'
)


_TASKS_SCREEN = (
    '<div class="screen-container">'
    '  <div class="split-view">'
    '    <section class="panel">'
    '      <h2>Active & Queued Tasks</h2>'
    '      <div id="task-list" class="cards-list"><p class="muted">Loading tasks...</p></div>'
    '      <h3>Add Task</h3>'
    '      <form id="task-add" class="inline-form">'
    '        <input id="task-title" placeholder="What should be done?" required>'
    '        <button type="submit">Queue task</button>'
    '      </form>'
    '    </section>'
    '    <section class="panel">'
    '      <h2>Standing Schedules</h2>'
    '      <div id="schedule-list" class="cards-list"><p class="muted">Loading schedules...</p></div>'
    '      <h3>Add Schedule</h3>'
    '      <form id="schedule-add" class="inline-form">'
    '        <input id="sched-title" placeholder="Task title" required>'
    '        <input id="sched-cron" placeholder="0 9 * * *" required>'
    '        <button type="submit">Save schedule</button>'
    '      </form>'
    '    </section>'
    '  </div>'
    '</div>'
)


_TOOLS_SCREEN = (
    '<div class="screen-container">'
    '  <div class="tabs-bar">'
    '    <button type="button" class="tab-btn active" data-tab="tab-mcp">MCP Servers</button>'
    '    <button type="button" class="tab-btn" data-tab="tab-skills">Skills Catalog</button>'
    '    <button type="button" class="tab-btn" data-tab="tab-local">Local Tools</button>'
    '  </div>'
    '  <div id="tab-mcp" class="tab-panel active">'
    '    <h2>Connected MCP Servers</h2>'
    '    <div id="mcp-servers-list" class="cards-list"><p class="muted">Checking MCP servers...</p></div>'
    '  </div>'
    '  <div id="tab-skills" class="tab-panel">'
    '    <h2>Available Skills</h2>'
    '    <div id="skills-list" class="cards-list"><p class="muted">Loading skills catalog...</p></div>'
    '  </div>'
    '  <div id="tab-local" class="tab-panel">'
    '    <h2>Local Safe Tools</h2>'
    '    <ul class="clean-list">'
    '      <li><strong>read_file</strong> — Read local file within workspace.</li>'
    '      <li><strong>write_file</strong> — Write file with permission review.</li>'
    '      <li><strong>list_files</strong> — List workspace directory.</li>'
    '      <li><strong>web_search</strong> — Source-backed web research.</li>'
    '      <li><strong>read_attachment</strong> — Read uploaded text or PDF.</li>'
    '    </ul>'
    '  </div>'
    '</div>'
)


_FACTS_BODY = (
    '<section id="facts"><h2>Curated memory</h2>'
    '<p class="muted">Short facts Oneiro keeps in mind for every reply, written by you. '
    'They are your statements, not verified observations. Changing one keeps its history.</p>'
    '<p class="muted" id="facts-meter" role="status"></p>'
    '<ul id="facts-list"></ul>'
    '<form id="fact-add"><label for="fact-text">New fact</label>'
    '<textarea id="fact-text" name="fact" rows="2" maxlength="2000"></textarea>'
    '<button type="submit">Add fact</button></form>'
    '<p class="bad" id="facts-error" hidden></p></section>'
)


def render(page: str, description: dict, error: str = "", facts: Any = None, lang: str | None = None) -> str:
    """The complete HTML document for one route."""
    lang = lang or i18n.current_language()
    title = i18n.t(f"title.{page}", lang)
    heading = i18n.t(f"heading.{page}", lang)
    notice = i18n.t(f"notice.{page}", lang)

    nav = "".join(
        f'<a href="{href}"{" aria-current=page" if active == page else ""}>{html.escape(i18n.t(f"nav.{active}", lang))}</a>'
        for href, _, active in NAV
    )
    if page == "chat":
        body = _CONVERSATION_SCREEN
    elif page == "tasks":
        body = _TASKS_SCREEN
    elif page == "tools":
        body = _TOOLS_SCREEN
    elif page == "settings":
        body = _form(description) + _FACTS_BODY
    elif page in ("memory", "graph"):
        body = _FACTS_BODY + _graph_section(facts)
    elif page in FORM_PAGES:
        body = _form(description)
    else:
        body = ""

    return Template(TEMPLATE.read_text(encoding="utf-8")).safe_substitute(
        title=html.escape(title),
        heading=html.escape(heading),
        nav=nav,
        notice=html.escape(notice),
        body=body,
        error=html.escape(error),
        root=html.escape(description["data_root"], quote=True),
        language=html.escape(str(lang), quote=True),
        theme=html.escape(str(config.value("ui.theme")), quote=True),
    )
