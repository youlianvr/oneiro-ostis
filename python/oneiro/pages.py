"""What each route is, and the 5 canonical screens built from the declared registry.

Page identity lives here, not in the browser: `web.py` names a page, this module
decides what it says and what it shows. Adding a setting means adding one
`Setting` to `config.SETTINGS`; the form follows, because the form is generated
from that registry rather than hand-written in HTML.

Every sentence a person reads comes from `oneiro.i18n` — the screen chrome, the
settings labels and help (declared English in `settings_registry`, translated in the
catalog), the notes about where a value came from, and the client script's keys,
which travel to the browser as one JSON block. A literal sentence in this module
would be a string that can only ever be one language, which is how the settings
screen used to be English on a Russian page.

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
import json
from pathlib import Path
from string import Template
from typing import Any

from oneiro import config, i18n

TEMPLATE = Path(__file__).parent / "static" / "page.html"

# route page id -> href. The words a person reads are `nav.<id>` in the catalog.
NAV = (
    ("/", "chat"),
    ("/tasks", "tasks"),
    ("/tools", "tools"),
    ("/settings", "settings"),
    ("/memory", "memory"),
    # Compatibility links
    ("/setup", "setup"),
    ("/oneiro/", "graph"),
)

FORM_PAGES = ("settings", "setup")

#: Where a value came from, as catalog keys the page renders in the active language.
SOURCES = {
    "file": "source.file",
    "keys.env": "source.keys.env",
    "env": "source.env",
    "project .env": "source.project .env",
    "default": "source.default",
}


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


def _source_phrase(row: dict, lang: str) -> str:
    """The layer that answered, named in the reader's language."""
    key = SOURCES.get(row["source"])
    return i18n.t(key, lang) if key else str(row["source"])


def _field(row: dict, lang: str) -> str:
    """One settings row: label, control, and the sentence that explains it."""
    key = html.escape(row["key"], quote=True)
    label = html.escape(i18n.setting_text(row["key"], "label", row["label"], lang))
    help_text = html.escape(i18n.setting_text(row["key"], "help", row["help"], lang))
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
        state = (i18n.t("setting.state.set", lang, source=_source_phrase(row, lang))
                 if row["set"] else i18n.t("setting.state.unset", lang))
        control = (
            f'<input type="password" autocomplete="new-password" {attributes}>'
            f'<small>{html.escape(i18n.t("setting.current", lang, state=state))}</small>'
        )
    else:
        control = f'<input type="text" value="{value}" {attributes}>'
    if row["readonly"]:
        control += f'<small>{html.escape(i18n.t("setting.note.readonly", lang))}</small>'
    if row["pending"]:
        control += (
            f'<small class="pending">'
            f'{html.escape(i18n.t("setting.note.pending", lang))}</small>'
        )
    control += (
        f'<small class="source">'
        f'{html.escape(i18n.t("setting.source", lang, source=_source_phrase(row, lang)))}'
        f'</small>'
    )
    return (f'<div class="field"><label for="f-{key}">{label}</label>{control}'
            f'<small>{help_text}</small></div>')


def _form(description: dict, lang: str) -> str:
    """The declared settings, grouped, plus the data root and writability."""
    groups: dict[str, list[str]] = {}
    for row in description["settings"]:
        groups.setdefault(row["group"], []).append(_field(row, lang))
    blocks = [
        f'<fieldset><legend>{html.escape(i18n.group_text(group, lang))}</legend>'
        f'{"".join(rows)}</fieldset>'
        for group, rows in groups.items()
    ]
    root = html.escape(description["data_root"], quote=True)
    stored_at = html.escape(description["path"], quote=True)
    if description["writable"]:
        writable = (
            f'<p class="ok">{html.escape(i18n.t("settings.writable", lang))} '
            f'<code>{stored_at}</code></p>'
        )
        disabled = ""
    else:
        writable = (
            f'<p class="bad">'
            f'{html.escape(i18n.t("settings.not_writable", lang, reason=description["writable_error"]))} '
            f'<code>{stored_at}</code></p>'
        )
        disabled = " disabled"
    moved = ""
    if description["migrated_from"]:
        moved = (
            f'<p class="ok">{html.escape(i18n.t("settings.migrated", lang))} '
            f'<code>{html.escape(description["migrated_from"], quote=True)}</code>.</p>'
        )
    return (
        f'{moved}<p class="muted">{html.escape(i18n.t("settings.root_note", lang))} '
        f'<code>{root}</code></p>{writable}'
        f'<p class="muted">{html.escape(i18n.t("settings.secret_note", lang))}</p>'
        f'<form id="settings" method="post" action="/api/settings">'
        f'{"".join(blocks)}<button{disabled}>'
        f'{html.escape(i18n.t("btn.save_settings", lang))}</button>'
        f'<p id="result" role="status"></p></form>'
    )


def _graph_section(facts: Any, lang: str) -> str:
    """What the probe could read, and what it could not."""
    heading = f'<h2>{html.escape(i18n.t("graph.heading", lang))}</h2>'
    if facts is None:
        return (
            f'<section>{heading}<p class="bad">'
            f'{html.escape(i18n.t("graph.not_probed", lang))}</p></section>'
        )
    if not facts.reachable:
        reasons = "".join(f"<li>{html.escape(said)}</li>"
                          for said in i18n.reasons(facts.blocked, lang))
        return (
            f'<section>{heading}<p class="bad">'
            f'{html.escape(i18n.t("graph.unreachable", lang))}</p><ul>{reasons}</ul></section>'
        )
    if not facts.verified:
        reasons = "".join(f"<li>{html.escape(said)}</li>"
                          for said in i18n.reasons(facts.blocked, lang))
        return (
            f'<section>{heading}<p class="bad">'
            f'{html.escape(i18n.t("graph.unverified", lang))}</p><ul>{reasons}</ul></section>'
        )
    rows = "".join(
        f"<li><code>{html.escape(identifier)}</code></li>" for identifier in facts.identifiers
    )
    readable = i18n.t(
        "graph.readable", lang, arcs=facts.arcs_found,
        anchor=f'<code>{html.escape(facts.anchor)}</code>', elapsed=facts.elapsed_ms,
    )
    return (
        f'<section>{heading}'
        f'<p class="ok">{readable}</p>'
        f'<p class="muted">'
        f'{html.escape(i18n.t("graph.checked", lang, at=facts.checked_at))}</p>'
        f'<ul>{rows}</ul></section>'
    )


def _conversation_screen(lang: str) -> str:
    t = lambda key: html.escape(i18n.t(key, lang))  # noqa: E731 - a screen reads many keys
    return (
        '<div class="screen-grid conversation-layout">'
        '  <aside class="panel-left">'
        f'    <h3>{t("panel.conversations")}</h3>'
        f'    <label for="conversation-select" class="sr-only">{t("label.conversation")}</label>'
        '    <select id="conversation-select"></select>'
        f'    <button type="button" id="new-conversation" class="btn-subtle">'
        f'{t("btn.new_conversation")}</button>'
        '    <form id="search">'
        f'      <label for="search-text" class="sr-only">{t("label.search")}</label>'
        f'      <input id="search-text" type="search" placeholder="{t("placeholder.search")}"'
        ' maxlength="200" required>'
        f'      <button type="submit" class="btn-subtle">{t("btn.find")}</button>'
        '    </form>'
        '    <p class="muted" id="search-note" role="status"></p>'
        '    <ol id="search-results" class="clean-list"></ol>'
        '  </aside>'
        '  <section class="panel-center">'
        f'    <div id="approvals" class="action-feed" role="region" aria-label="{t("region.approvals")}"></div>'
        f'    <div id="questions" class="action-feed" role="region" aria-label="{t("region.questions")}"></div>'
        '    <ol id="transcript" class="transcript-feed" aria-live="polite"></ol>'
        '    <form id="chat" class="composer">'
        f'      <label for="message">{t("label.message")}</label>'
        f'      <textarea id="message" name="message" rows="3" maxlength="4000"'
        f' placeholder="{t("placeholder.message")}" required></textarea>'
        '      <div class="composer-bar">'
        '        <input type="file" id="attachment-file" class="sr-only" multiple>'
        f'        <button type="button" id="btn-attach" class="btn-subtle">{t("btn.attach")}</button>'
        '        <span id="attachment-chip" class="pill" hidden></span>'
        f'        <button type="submit" class="btn-primary">{t("btn.send")}</button>'
        '      </div>'
        '      <p class="bad" id="chat-error" hidden></p>'
        '    </form>'
        '  </section>'
        '  <aside class="panel-right" id="inspector">'
        f'    <h3>{t("inspector.title")}</h3>'
        f'    <div id="inspector-content" class="inspector-box"><p class="muted">'
        f'{t("inspector.empty")}</p></div>'
        '  </aside>'
        '</div>'
    )


def _tasks_screen(lang: str) -> str:
    t = lambda key: html.escape(i18n.t(key, lang))  # noqa: E731
    return (
        '<div class="screen-container">'
        '  <div class="split-view">'
        '    <section class="panel">'
        f'      <h2>{t("heading.active_tasks")}</h2>'
        f'      <div id="task-list" class="cards-list"><p class="muted">{t("tasks.loading")}</p></div>'
        f'      <h3>{t("heading.add_task")}</h3>'
        '      <form id="task-add" class="inline-form">'
        f'        <input id="task-title" placeholder="{t("placeholder.task_title")}" required>'
        f'        <button type="submit">{t("btn.queue_task")}</button>'
        '      </form>'
        '    </section>'
        '    <section class="panel">'
        f'      <h2>{t("heading.schedules")}</h2>'
        f'      <div id="schedule-list" class="cards-list"><p class="muted">{t("schedules.loading")}</p></div>'
        f'      <h3>{t("heading.add_schedule")}</h3>'
        '      <form id="schedule-add" class="inline-form">'
        f'        <input id="sched-title" placeholder="{t("placeholder.schedule_title")}" required>'
        f'        <input id="sched-cron" placeholder="{t("placeholder.cron")}" required>'
        f'        <button type="submit">{t("btn.save_schedule")}</button>'
        '      </form>'
        '    </section>'
        '  </div>'
        '</div>'
    )


_TOOL_ROWS = (
    ("read_file", "tool.read_file"), ("write_file", "tool.write_file"),
    ("list_files", "tool.list_files"), ("web_search", "tool.web_search"),
    ("read_attachment", "tool.read_attachment"),
)


def _tools_screen(lang: str) -> str:
    t = lambda key: html.escape(i18n.t(key, lang))  # noqa: E731
    tools = "".join(
        f'<li><strong>{name}</strong> — {t(key)}</li>' for name, key in _TOOL_ROWS
    )
    return (
        '<div class="screen-container">'
        '  <div class="tabs-bar">'
        f'    <button type="button" class="tab-btn active" data-tab="tab-mcp">{t("tab.mcp")}</button>'
        f'    <button type="button" class="tab-btn" data-tab="tab-skills">{t("tab.skills")}</button>'
        f'    <button type="button" class="tab-btn" data-tab="tab-local">{t("tab.local")}</button>'
        '  </div>'
        '  <div id="tab-mcp" class="tab-panel active">'
        f'    <h2>{t("heading.connected_mcp")}</h2>'
        f'    <div id="mcp-servers-list" class="cards-list"><p class="muted">{t("mcp.checking")}</p></div>'
        '  </div>'
        '  <div id="tab-skills" class="tab-panel">'
        f'    <h2>{t("heading.available_skills")}</h2>'
        f'    <div id="skills-list" class="cards-list"><p class="muted">{t("skills.loading")}</p></div>'
        '  </div>'
        '  <div id="tab-local" class="tab-panel">'
        f'    <h2>{t("heading.local_tools")}</h2>'
        f'    <ul class="clean-list">{tools}</ul>'
        '  </div>'
        '</div>'
    )


def _facts_body(lang: str) -> str:
    t = lambda key: html.escape(i18n.t(key, lang))  # noqa: E731
    return (
        f'<section id="facts"><h2>{t("heading.curated_memory")}</h2>'
        f'<p class="muted">{t("notice.curated_memory")}</p>'
        '<p class="muted" id="facts-meter" role="status"></p>'
        '<ul id="facts-list"></ul>'
        f'<form id="fact-add"><label for="fact-text">{t("label.new_fact")}</label>'
        '<textarea id="fact-text" name="fact" rows="2" maxlength="2000"></textarea>'
        f'<button type="submit">{t("btn.add_fact")}</button></form>'
        '<p class="bad" id="facts-error" hidden></p></section>'
    )


def _client_i18n(lang: str) -> str:
    """The client script's sentences, as one JSON block.

    `<` is escaped so a translation can never close the script tag early; the script
    itself reads this and holds no sentence of its own.
    """
    payload = json.dumps(i18n.client_catalog(lang), ensure_ascii=False, sort_keys=True)
    return ('<script id="i18n" type="application/json">'
            + payload.replace("<", "\\u003c") + "</script>")


def render_error(message_key: str, lang: str | None = None) -> str:
    """A refusal a person can read, in the active language.

    A JSON body handed to a browser is JSON rendered on screen. Measured 2026-10-11:
    with JavaScript disabled, the settings form's own Save button posted to
    `/api/settings` and the tab showed `{"error": "Cross-origin request refused"}` —
    a reachable raw-JSON screen on a product whose row 15 promises none. A refusal is
    still a page a person reads, so it gets the shell.
    """
    lang = lang or i18n.current_language()
    title = html.escape(i18n.t("error.refused_title", lang))
    theme = html.escape(str(config.value("ui.theme")), quote=True)
    return (
        "<!doctype html>\n"
        f'<html lang="{html.escape(str(lang), quote=True)}" data-theme="{theme}">\n'
        '<head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{title}</title>"
        '<link rel="stylesheet" href="/console.css">'
        '<link rel="stylesheet" href="/style.css"></head>\n'
        "<body><main><header><h1>"
        f'{html.escape(i18n.t("app.name", lang))}</h1>'
        f'<p>{html.escape(i18n.t("app.tagline", lang))}</p></header>'
        f'<section class="notice"><h2>{title}</h2>'
        f'<p class="bad">{html.escape(i18n.t(message_key, lang))}</p>'
        f'<p><a href="/settings">{html.escape(i18n.t("error.back", lang))}</a></p>'
        "</section></main></body></html>\n"
    )


def render(page: str, description: dict, error: str = "", facts: Any = None,
           lang: str | None = None) -> str:
    """The complete HTML document for one route."""
    lang = lang or i18n.current_language()
    title = i18n.t(f"title.{page}", lang)
    heading = i18n.t(f"heading.{page}", lang)
    notice = i18n.t(f"notice.{page}", lang)

    nav = "".join(
        f'<a href="{href}"{" aria-current=page" if active == page else ""}>'
        f'{html.escape(i18n.t(f"nav.{active}", lang))}</a>'
        for href, active in NAV
    )
    if page == "chat":
        body = _conversation_screen(lang)
    elif page == "tasks":
        body = _tasks_screen(lang)
    elif page == "tools":
        body = _tools_screen(lang)
    elif page == "settings":
        body = _form(description, lang) + _facts_body(lang)
    elif page in ("memory", "graph"):
        body = _facts_body(lang) + _graph_section(facts, lang)
    elif page in FORM_PAGES:
        body = _form(description, lang)
    else:
        body = ""

    return Template(TEMPLATE.read_text(encoding="utf-8")).safe_substitute(
        title=html.escape(title),
        app_name=html.escape(i18n.t("app.name", lang)),
        heading=html.escape(heading),
        tagline=html.escape(i18n.t("app.tagline", lang)),
        prerequisites=html.escape(i18n.t("heading.prerequisites", lang)),
        status_checking=html.escape(i18n.t("status.prerequisites", lang)),
        nav=nav,
        notice=html.escape(notice),
        body=body,
        error=html.escape(error),
        root=html.escape(description["data_root"], quote=True),
        footer_note=html.escape(i18n.t("footer.note", lang)),
        language=html.escape(str(lang), quote=True),
        theme=html.escape(str(config.value("ui.theme")), quote=True),
        client_i18n=_client_i18n(lang),
    )
