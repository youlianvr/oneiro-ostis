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

TEMPLATE = Path(__file__).parent / "static" / "page.html"

# route page id -> (document title, heading, what this page is for)
PAGES: dict[str, tuple[str, str, str]] = {
    "chat": ("Oneiro — chat", "Conversation",
             "Conversation is not integrated in this foundation. The prerequisites below "
             "and the settings page are live; /api/message answers 503 by design."),
    "settings": ("Oneiro — settings", "Oneiro settings",
                 "Every setting Oneiro declares, in one place. Values come from this file, "
                 "then the environment, then the declared default — the page shows which one "
                 "answered. A stored provider key is never sent back to the browser."),
    "setup": ("Oneiro — setup", "Setup",
              "Setup reads the real state of this machine: the OSTIS server, the provider "
              "key, the dependencies the memory layer needs. It never starts Docker or "
              "changes a setting for you."),
    "graph": ("Oneiro — graph", "Graph panel",
              "The graph panel is not integrated in this foundation. /api/graph answers 503 "
              "by design; no graph is faked and no substitute memory store is used."),
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


def render(page: str, description: dict, error: str = "") -> str:
    """The complete HTML document for one route."""
    title, heading, notice = PAGES[page]
    nav = "".join(
        f'<a href="{href}"{" aria-current=page" if active == page else ""}>{html.escape(label)}</a>'
        for href, label, active in NAV
    )
    body = _form(description) if page in FORM_PAGES else ""
    return Template(TEMPLATE.read_text(encoding="utf-8")).safe_substitute(
        title=html.escape(title), heading=html.escape(heading), nav=nav,
        notice=html.escape(notice), body=body,
        error=html.escape(error),
        root=html.escape(description["data_root"], quote=True),
    )
