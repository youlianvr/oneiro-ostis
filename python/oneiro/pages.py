"""What each route is, and the settings form built from the declared registry.

Page identity lives here, not in the browser: `web.py` names a page, this module
decides what it says and what it shows. Adding a setting means adding one
`Setting` to `config.SETTINGS`; the form follows, because the form is generated
from that registry rather than hand-written in HTML.

The four routes are honest about what is not integrated yet. Nothing here
pretends an agent or a graph exists.
"""
from __future__ import annotations

import html
from pathlib import Path
from string import Template
from typing import Any

TEMPLATE = Path(__file__).parent / "static" / "page.html"

# route page id -> (document title, heading, what this page is for)
PAGES: dict[str, tuple[str, str, str]] = {
    "chat": ("Oneiro — chat", "Conversation",
             "One message, one model reply. Both are stored before they are shown. If the "
             "model is unreachable, your message is kept and the error says why."),
    "settings": ("Oneiro — settings", "Oneiro settings",
                 "Every setting Oneiro declares, in one place. Values come from this file, "
                 "then the environment, then the declared default — the page shows which one "
                 "answered. A stored provider key is never sent back to the browser."),
    "setup": ("Oneiro — setup", "Setup",
              "Setup reads the real state of this machine: the OSTIS server, the provider "
              "key, the dependencies the memory layer needs. It never starts Docker or "
              "changes a setting for you."),
    "graph": ("Oneiro — graph", "Graph panel",
              "OSTIS is the memory substrate and the only one. This page reports what "
              "could actually be read from the running server just now — reachability "
              "alone is not counted as success. No substitute memory store exists."),
}

NAV = (("/", "Chat", "chat"), ("/settings", "Oneiro settings", "settings"),
       ("/setup", "Setup", "setup"), ("/oneiro/", "Graph", "graph"))

FORM_PAGES = ("settings", "setup")   # the two pages that offer the form

SECRET_NOTE = "Stored keys are never returned. An empty field leaves the current key unchanged."


def _field(row: dict) -> str:
    """One settings row: label, control, and the sentence that explains it."""
    key = html.escape(row["key"], quote=True)
    label = html.escape(row["label"])
    help_text = html.escape(row["help"])
    value = html.escape(str(row["value"]), quote=True)
    # A read-only setting is rendered as a disabled control: the value is shown,
    # but the page must not invite a write the server will refuse.
    attributes = f'name="{key}" id="f-{key}"' + (" disabled" if row["readonly"] else "")
    if row["kind"] == "int":
        limit = ' max="65535"' if key.endswith(".port") else ""
        control = f'<input type="number" min="1"{limit} value="{value}" {attributes}>'
    elif row["secret"]:
        # No value attribute at all: a key must never travel back to the page.
        state = "not set" if not row["set"] else f"set, answered by the {row['source']}"
        control = (f'<input type="password" autocomplete="new-password" {attributes}>'
                   f'<small>Currently {html.escape(state)}.</small>')
    else:
        control = f'<input type="text" value="{value}" {attributes}>'
    if row["readonly"]:
        control += "<small>Read-only on this page: it is answered by the environment, not the file.</small>"
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
        writable = ('<p class="ok">Settings file is writable. '
                    f'File: <code>{stored_at}</code></p>')
        disabled = ""
    else:
        reason = html.escape(description["writable_error"])
        writable = (f'<p class="bad">Settings cannot be saved: {reason}. '
                    f'File: <code>{stored_at}</code></p>')
        disabled = " disabled"
    moved = ""
    if description["migrated_from"]:
        moved = (f'<p class="ok">Settings were migrated from '
                 f'<code>{html.escape(description["migrated_from"], quote=True)}</code>.</p>')
    return (f"{moved}<p class=\"muted\">One data root: <code>{root}</code></p>{writable}"
            f"<p class=\"muted\">{SECRET_NOTE}</p>"
            f'<form id="settings" method="post" action="/api/settings">'
            f'{"".join(blocks)}<button{disabled}>Save settings</button>'
            f'<p id="result" role="status"></p></form>')


def _graph_section(facts: Any) -> str:
    """What the probe could read, and what it could not. Nothing is inferred."""
    if facts is None:
        return ('<section><h2>Memory substrate</h2>'
                '<p class="bad">The graph was not probed for this page.</p></section>')
    if not facts.reachable:
        reasons = "".join(f"<li>{html.escape(reason)}</li>" for reason in facts.blocked)
        return ('<section><h2>Memory substrate</h2>'
                f'<p class="bad">Unreachable. OSTIS is required; there is no substitute '
                f'store, so nothing is shown in its place.</p><ul>{reasons}</ul></section>')
    if not facts.verified:
        reasons = "".join(f"<li>{html.escape(reason)}</li>" for reason in facts.blocked)
        return ('<section><h2>Memory substrate</h2>'
                f'<p class="bad">Reachable, but nothing could be read back out of the '
                f'graph.</p><ul>{reasons}</ul></section>')
    rows = "".join(
        f"<li><code>{html.escape(identifier)}</code></li>" for identifier in facts.identifiers
    )
    return ('<section><h2>Memory substrate</h2>'
            f'<p class="ok">Readable. {facts.arcs_found} anchor arc(s) traversable via '
            f'<code>{html.escape(facts.anchor)}</code>; identifier strings read back out '
            f'of the graph in {facts.elapsed_ms} ms.</p>'
            f'<p class="muted">Checked {html.escape(facts.checked_at)}. This is a '
            f'reachability-and-traversal check, not a memory benchmark.</p>'
            f'<ul>{rows}</ul></section>')


_CHAT_BODY = (
    '<section><h2>Conversations</h2>'
    '<label for="conversation-select">Conversation</label>'
    '<select id="conversation-select"></select>'
    '<button type="button" id="new-conversation">New conversation</button>'
    '<form id="search"><label for="search-text">Search your messages</label>'
    '<input id="search-text" type="search" maxlength="200" required>'
    '<button type="submit">Search</button></form>'
    '<p class="muted" id="search-note" role="status"></p>'
    '<ol id="search-results"></ol></section>'
    '<section><h2>Chat</h2>'
    '<ol id="transcript" aria-live="polite"></ol>'
    '<form id="chat"><label for="message">Message</label>'
    '<textarea id="message" name="message" rows="3" maxlength="4000" required></textarea>'
    '<button type="submit">Send</button></form>'
    '<p class="bad" id="chat-error" hidden></p></section>'
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


def render(page: str, description: dict, error: str = "", facts: Any = None) -> str:
    """The complete HTML document for one route."""
    title, heading, notice = PAGES[page]
    nav = "".join(
        f'<a href="{href}"{" aria-current=page" if active == page else ""}>{html.escape(label)}</a>'
        for href, label, active in NAV
    )
    if page == "settings":
        body = _form(description) + _FACTS_BODY
    elif page in FORM_PAGES:
        body = _form(description)
    elif page == "graph":
        body = _graph_section(facts)
    elif page == "chat":
        body = _CHAT_BODY
    else:
        body = ""
    return Template(TEMPLATE.read_text(encoding="utf-8")).safe_substitute(
        title=html.escape(title), heading=html.escape(heading), nav=nav,
        notice=html.escape(notice), body=body,
        error=html.escape(error),
        root=html.escape(description["data_root"], quote=True),
    )
