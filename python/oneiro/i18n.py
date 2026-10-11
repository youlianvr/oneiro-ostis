"""Localization: one catalog for every string a person can read, in RU and EN.

The rule this module exists to keep: **a screen shows text from here and nowhere
else**. Templates (`pages.py`), the page shell (`static/page.html`) and the client
script (`static/app.js`) carry markup and behaviour, never sentences — a literal
there is a string that can only ever be English, which is how the settings screen
ended up 95% English on a Russian page.

Two sources feed the catalog:

* the **chrome** below — navigation, screens, notices, buttons, the client script's
  sentences, the graph panel — written out in both languages;
* the **settings declarations** in `settings_registry.Setting`. Their `label`, `help`
  and `group` are the declaration's own English wording; `_assemble()` lifts them into
  the `en` catalog and pairs them with the Russian written in `_SETTINGS_RU` below, so
  a setting's visible text has one owner per language and no third copy exists to
  drift. A setting with no Russian is a defect the parity test names, not a silent
  English string on a Russian page.

Interpolation is `{name}`, replaced literally (never `str.format`), so a brace in a
value or a path can never break a sentence.
"""
from __future__ import annotations

from typing import Any

from oneiro import config

DEFAULT_LANGUAGE = "ru"
SUPPORTED_LANGUAGES = ("ru", "en")

#: Reasons a backend reports, as codes. A backend hands over *data*, never a sentence:
#: prose composed on the server is prose in the server's language on every screen, which
#: is how the readiness panel came to print `run \`oneiro verify-model\` ...` inside a
#: Russian sentence while two checks compared that screen and called it translated
#: (measured 2026-10-11). Each code below is a sentence in both catalogs, and the data a
#: reason needs is interpolated into it.
REASON_KEYS: tuple[str, ...] = (
    "reason.verify_model",
    "blocked.client_absent", "blocked.graph_unreachable", "blocked.arcs_unresolved",
    "blocked.graph_empty", "blocked.identifiers_unreadable", "blocked.probe_failed",
    "blocked.adapter_absent", "blocked.model_unverified",
)

#: Keys the client script renders. `app.js` reads text only through these, and the
#: i18n test asserts that every key it asks for is in this list — including the reason
#: codes it renders from `/api/status`, which is why they are listed here by name.
CLIENT_KEYS: tuple[str, ...] = (
    *REASON_KEYS,
    "status.ready", "status.not_ready", "status.phase", "status.memory_ok",
    "status.memory_readback", "status.memory_unreachable", "status.model_ok",
    "status.model_ok_tools", "status.model_unverified",
    "status.blocked_title", "status.unavailable",
    "error.refused_title", "error.cross_origin", "error.bad_token", "error.back",
    "action.tool", "action.executed", "action.refused", "action.args", "action.result",
    "action.unnamed",
    "inspector.heading", "inspector.role", "inspector.text", "inspector.steps",
    "inspector.attachments",
    "chat.turn_refused", "chat.server_failure",
    "tasks.none", "tasks.load_failed", "tasks.status_label", "tasks.active", "tasks.disabled",
    "schedules.none", "schedules.load_failed",
    "mcp.none", "mcp.offline", "mcp.enabled", "mcp.disabled",
    "skills.none", "skills.offline",
    "settings.client.nothing_changed", "settings.client.saved",
    "settings.client.unavailable",
)

#: A reason's sentence, per language. `REASON_KEYS` names them; this is where they are
#: written. A code with no entry here renders as the code itself, which the parity test
#: turns into a failure rather than a silent English line.
_REASONS: dict[str, tuple[str, str]] = {
    "reason.verify_model": (
        "проверьте настроенную модель реальным вызовом: `oneiro verify-model`",
        "run `oneiro verify-model` to check the configured model with a real call",
    ),
    "blocked.client_absent": (
        "sc_client не установлен, поэтому до памяти не добраться",
        "sc_client is not installed; the memory backend cannot be reached",
    ),
    "blocked.graph_unreachable": (
        "сервер OSTIS недоступен по адресу {host}:{port}",
        "OSTIS server is unreachable at {host}:{port}",
    ),
    "blocked.arcs_unresolved": (
        "все дуги шаблона {anchor} ({arcs}) имеют неразрешённые концы, поэтому за ними нет "
        "содержимого: граф отвечает по протоколу, но обходимой базы знаний в нём нет",
        "the {arcs} arc(s) matching {anchor} all have unresolved wildcard endpoints, so no "
        "content hangs off them: the graph answers the protocol but holds no traversable "
        "knowledge base",
    ),
    "blocked.graph_empty": (
        "ни одна дуга в графе не использует {anchor}; база знаний выглядит пустой",
        "no arc in the graph uses {anchor}; the knowledge base appears empty",
    ),
    "blocked.identifiers_unreadable": (
        "дуги-идентификаторы есть, но их содержимое не читается обратно",
        "identifier arcs exist but their content could not be read back",
    ),
    "blocked.probe_failed": (
        "чтение графа прервано: {exception}",
        "reading the graph stopped: {exception}",
    ),
    "blocked.adapter_absent": (
        "типовой адаптер OSTIS не подключён, поэтому память не проверена",
        "the typed OSTIS adapter is not integrated, so memory is not verified",
    ),
    "blocked.model_unverified": (
        "настроенная модель не проверена",
        "the configured model is not verified",
    ),
}

_RU: dict[str, str] = {
    # ---- shell ----
    "app.name": "Oneiro",
    "app.tagline": "Автономный ассистент на базе OSTIS",
    "heading.prerequisites": "Готовность системы",
    "footer.note": "Без автозапуска ОС. OSTIS обязателен, заменителя памяти нет. Корень данных: ",
    # ---- navigation & screens ----
    "nav.chat": "Диалог",
    "nav.tasks": "Задачи",
    "nav.tools": "Инструменты",
    "nav.settings": "Настройки",
    "nav.memory": "Память",
    "nav.setup": "Установка",
    "nav.graph": "Граф",
    "title.chat": "Oneiro — диалог",
    "heading.chat": "Диалог",
    "notice.chat": "Общение с постоянным ассистентом. Карточки действий отображают вызовы инструментов и подтверждения прямо в ленте без сырого JSON.",
    "title.tasks": "Oneiro — задачи",
    "heading.tasks": "Задачи и расписания",
    "notice.tasks": "Автономная и запланированная работа. Отслеживайте статусы задач, историю запусков и регулярные расписания.",
    "title.tools": "Oneiro — инструменты",
    "heading.tools": "Инструменты и возможности",
    "notice.tools": "Три категории возможностей: внешние MCP-серверы, локальные инструменты и каталог навыков.",
    "title.settings": "Oneiro — настройки",
    "heading.settings": "Настройки Oneiro",
    "notice.settings": "Все объявленные параметры Oneiro. Значения читаются из файла, затем переменных окружения, затем значений по умолчанию. Ключи провайдеров не отправляются обратно в браузер.",
    "title.memory": "Oneiro — память",
    "heading.memory": "Память и граф",
    "notice.memory": "Постоянная память: курируемые факты, поиск по истории диалогов и статус подложки OSTIS.",
    "title.setup": "Oneiro — установка",
    "heading.setup": "Установка",
    "notice.setup": "Проверка готовности машины: сервер OSTIS, ключи моделей, зависимости памяти.",
    "title.graph": "Oneiro — граф",
    "heading.graph": "Панель графа",
    "notice.graph": "OSTIS является обязательной подложкой памяти. Проверка чтения и обхода графа в реальном времени.",
    # ---- conversation screen ----
    "panel.conversations": "Диалоги",
    "label.conversation": "Диалог",
    "label.search": "Поиск",
    "region.approvals": "Подтверждения",
    "region.questions": "Вопросы",
    "label.message": "Сообщение",
    "inspector.title": "Разбор хода",
    "inspector.empty": "Выберите сообщение, чтобы увидеть затронутую память, инструменты и контекст.",
    # ---- tasks screen ----
    "heading.active_tasks": "Активные и ожидающие задачи",
    "tasks.loading": "Загрузка задач…",
    "heading.add_task": "Новая задача",
    "heading.schedules": "Постоянные расписания",
    "schedules.loading": "Загрузка расписаний…",
    "heading.add_schedule": "Новое расписание",
    # ---- tools screen ----
    "tab.mcp": "MCP-серверы",
    "tab.skills": "Каталог навыков",
    "tab.local": "Локальные инструменты",
    "heading.connected_mcp": "Подключённые MCP-серверы",
    "mcp.checking": "Проверка MCP-серверов…",
    "heading.available_skills": "Доступные навыки",
    "skills.loading": "Загрузка каталога навыков…",
    "heading.local_tools": "Локальные безопасные инструменты",
    "tool.read_file": "Чтение локального файла внутри рабочей папки.",
    "tool.write_file": "Запись файла с проверкой разрешений.",
    "tool.list_files": "Список файлов рабочей папки.",
    "tool.web_search": "Поиск в сети с указанием источников.",
    "tool.read_attachment": "Чтение приложенного текста или PDF.",
    # ---- curated memory ----
    "heading.curated_memory": "Курируемая память",
    "notice.curated_memory": "Короткие факты, которые Oneiro держит в уме для каждого ответа, написанные вами. Это ваши утверждения, а не проверенные наблюдения. Изменение сохраняет историю.",
    "label.new_fact": "Новый факт",
    # ---- settings form ----
    "settings.root_note": "Единый корень данных:",
    "settings.writable": "Файл настроек доступен для записи. Файл:",
    "settings.not_writable": "Настройки нельзя сохранить: {reason}. Файл:",
    "settings.migrated": "Настройки перенесены из",
    "settings.secret_note": "Сохранённые ключи никогда не возвращаются. Пустое поле оставляет текущий ключ без изменений.",
    "setting.note.readonly": "Только для чтения здесь: значение отвечается окружением, а не файлом.",
    "setting.note.pending": "Объявлено здесь; часть Oneiro, которая им управляет, ещё не в этой сборке.",
    "setting.current": "Сейчас: {state}.",
    "setting.state.unset": "не задано",
    "setting.state.set": "задано, отвечает: {source}",
    "setting.source": "Значение из {source}.",
    "source.file": "этого файла настроек",
    "source.keys.env": "вашего файла ключей",
    "source.env": "окружения",
    "source.project .env": "проектного .env",
    "source.default": "объявленного значения по умолчанию",
    # ---- graph / memory substrate ----
    "graph.heading": "Подложка памяти",
    "graph.not_probed": "Граф для этой страницы не опрашивался.",
    "graph.unreachable": "Недоступен. OSTIS обязателен; заменителя хранилища нет, поэтому вместо него ничего не показывается.",
    "graph.unverified": "Доступен, но из графа ничего не удалось прочитать обратно.",
    "graph.readable": "Читается. Обходимых якорных дуг: {arcs}, через {anchor}; строки идентификаторов прочитаны из графа за {elapsed} мс.",
    "graph.checked": "Проверено {at}. Это проверка доступности и обхода, а не замер памяти.",
    # ---- client script ----
    "status.ready": "Готов к работе.",
    "status.not_ready": "Не готов — см. ниже.",
    "status.phase": "Фаза: {phase}.",
    "status.memory_ok": "Память (OSTIS) доступна для чтения.",
    "status.memory_readback": "Память (OSTIS) отвечает, но из графа ничего не удалось прочитать обратно.",
    "status.memory_unreachable": "Память (OSTIS) недоступна. Она обязательна и не имеет заменителей.",
    "status.model_ok": "Настроенная модель ответила на реальный запрос.",
    "status.model_ok_tools": "Настроенная модель ответила на реальный запрос, включая вызов инструмента.",
    "status.model_unverified": "Модель ещё не верифицирована.",
    "status.blocked_title": "Пока заблокировано:",
    "status.unavailable": "Сервер недоступен. Готовность не подтверждена.",
    # ---- the refusal page a request without JavaScript lands on ----
    "error.refused_title": "Запрос отклонён",
    "error.cross_origin": "Запрос пришёл не с адреса Oneiro, поэтому ничего не сохранено.",
    "error.bad_token": "Форма отправлена без токена этой страницы, поэтому ничего не сохранено. Обновите страницу и попробуйте снова.",
    "error.back": "Вернуться в Oneiro",
    "action.tool": "Инструмент",
    "action.unnamed": "действие без имени",
    "action.executed": "Выполнен успешно",
    "action.refused": "Отклонён политикой",
    "action.args": "Параметры",
    "action.result": "Результат",
    "action.approvals_title": "Ожидает вашего подтверждения",
    "action.questions_title": "Вопрос от Oneiro",
    "inspector.heading": "Подробности сообщения",
    "inspector.role": "Роль",
    "inspector.text": "Текст",
    "inspector.steps": "Шаги",
    "inspector.attachments": "Вложения",
    "chat.turn_refused": "Ход отклонён",
    "chat.server_failure": "Сбой связи с сервером",
    "tasks.none": "Нет активных или завершённых задач.",
    "tasks.load_failed": "Не удалось загрузить задачи.",
    "tasks.status_label": "Статус: {state}",
    "tasks.active": "активно",
    "tasks.disabled": "отключено",
    "schedules.none": "Постоянных расписаний нет.",
    "schedules.load_failed": "Не удалось загрузить расписания.",
    "mcp.none": "MCP-серверы не настроены.",
    "mcp.offline": "Служба MCP недоступна.",
    "mcp.enabled": "включён",
    "mcp.disabled": "выключен",
    "skills.none": "В каталоге нет навыков.",
    "skills.offline": "Каталог навыков недоступен.",
    "settings.client.nothing_changed": "Ничего не изменено; ничего не записано.",
    "settings.client.saved": "Сохранено. Страница перезагрузится и покажет сохранённые значения.",
    "settings.client.unavailable": "Сервер недоступен. Сохранение не подтверждено.",
    # ---- controls ----
    "btn.send": "Отправить",
    "btn.attach": "Прикрепить файл",
    "btn.new_conversation": "+ Новый",
    "btn.find": "Найти",
    "btn.save_settings": "Сохранить настройки",
    "btn.queue_task": "В очередь",
    "btn.save_schedule": "Сохранить расписание",
    "btn.add_fact": "Добавить факт",
    "placeholder.message": "Напишите сообщение или прикрепите файл…",
    "placeholder.search": "Поиск по сообщениям…",
    "placeholder.task_title": "Что нужно сделать?",
    "placeholder.schedule_title": "Название задачи",
    "placeholder.new_fact": "Новый факт…",
    "placeholder.cron": "0 9 * * *",
    "status.prerequisites": "Проверка готовности системы…",
}

_EN: dict[str, str] = {
    # ---- shell ----
    "app.name": "Oneiro",
    "app.tagline": "Standalone assistant with OSTIS memory",
    "heading.prerequisites": "Prerequisites",
    "footer.note": "No system autostart. OSTIS remains required; no substitute memory store. Data root: ",
    # ---- navigation & screens ----
    "nav.chat": "Chat",
    "nav.tasks": "Tasks",
    "nav.tools": "Tools",
    "nav.settings": "Settings",
    "nav.memory": "Memory",
    "nav.setup": "Setup",
    "nav.graph": "Graph",
    "title.chat": "Oneiro — conversation",
    "heading.chat": "Conversation",
    "notice.chat": "Conversation with your persistent assistant. Action cards show tool calls and approvals directly in the feed without raw JSON.",
    "title.tasks": "Oneiro — tasks",
    "heading.tasks": "Tasks & Schedules",
    "notice.tasks": "Independent and scheduled work. See task states, run history and standing schedules.",
    "title.tools": "Oneiro — tools",
    "heading.tools": "Tools & Capabilities",
    "notice.tools": "Three capabilities: connected MCP servers, local system tools, and searchable skills.",
    "title.settings": "Oneiro — settings",
    "heading.settings": "Oneiro settings",
    "notice.settings": "Every setting Oneiro declares, in one place. Values come from this file, then the environment, then the declared default — the page shows which one answered. A stored provider key is never sent back to the browser.",
    "title.memory": "Oneiro — memory",
    "heading.memory": "Memory & Graph",
    "notice.memory": "The persistent memory substrate: your curated facts, past conversation search, and OSTIS status.",
    "title.setup": "Oneiro — setup",
    "heading.setup": "Setup",
    "notice.setup": "Setup reads the real state of this machine: the OSTIS server, the provider key, the dependencies the memory layer needs. It never starts Docker or changes a setting for you.",
    "title.graph": "Oneiro — graph",
    "heading.graph": "Graph panel",
    "notice.graph": "OSTIS is the memory substrate and the only one. This page reports what could actually be read from the running server just now — reachability alone is not counted as success. No substitute memory store exists.",
    # ---- conversation screen ----
    "panel.conversations": "Conversations",
    "label.conversation": "Conversation",
    "label.search": "Search",
    "region.approvals": "Approvals",
    "region.questions": "Questions",
    "label.message": "Message",
    "inspector.title": "Turn Inspector",
    "inspector.empty": "Select a message to view touched memory, tools and context.",
    # ---- tasks screen ----
    "heading.active_tasks": "Active & Queued Tasks",
    "tasks.loading": "Loading tasks...",
    "heading.add_task": "Add Task",
    "heading.schedules": "Standing Schedules",
    "schedules.loading": "Loading schedules...",
    "heading.add_schedule": "Add Schedule",
    # ---- tools screen ----
    "tab.mcp": "MCP Servers",
    "tab.skills": "Skills Catalog",
    "tab.local": "Local Tools",
    "heading.connected_mcp": "Connected MCP Servers",
    "mcp.checking": "Checking MCP servers...",
    "heading.available_skills": "Available Skills",
    "skills.loading": "Loading skills catalog...",
    "heading.local_tools": "Local Safe Tools",
    "tool.read_file": "Read local file within workspace.",
    "tool.write_file": "Write file with permission review.",
    "tool.list_files": "List workspace directory.",
    "tool.web_search": "Source-backed web research.",
    "tool.read_attachment": "Read uploaded text or PDF.",
    # ---- curated memory ----
    "heading.curated_memory": "Curated memory",
    "notice.curated_memory": "Short facts Oneiro keeps in mind for every reply, written by you. They are your statements, not verified observations. Changing one keeps its history.",
    "label.new_fact": "New fact",
    # ---- settings form ----
    "settings.root_note": "One data root:",
    "settings.writable": "Settings file is writable. File:",
    "settings.not_writable": "Settings cannot be saved: {reason}. File:",
    "settings.migrated": "Settings were migrated from",
    "settings.secret_note": "Stored keys are never returned. An empty field leaves the current key unchanged.",
    "setting.note.readonly": "Read-only on this page: it is answered by the environment, not the file.",
    "setting.note.pending": "Declared here; the part of Oneiro that acts on it is not in this build yet.",
    "setting.current": "Currently {state}.",
    "setting.state.unset": "not set",
    "setting.state.set": "set, answered by the {source}",
    "setting.source": "Value from {source}.",
    "source.file": "this settings file",
    "source.keys.env": "your keys file",
    "source.env": "the environment",
    "source.project .env": "the project .env",
    "source.default": "the declared default",
    # ---- graph / memory substrate ----
    "graph.heading": "Memory substrate",
    "graph.not_probed": "The graph was not probed for this page.",
    "graph.unreachable": "Unreachable. OSTIS is required; there is no substitute store, so nothing is shown in its place.",
    "graph.unverified": "Reachable, but nothing could be read back out of the graph.",
    "graph.readable": "Readable. {arcs} anchor arc(s) traversable via {anchor}; identifier strings read back out of the graph in {elapsed} ms.",
    "graph.checked": "Checked {at}. This is a reachability-and-traversal check, not a memory benchmark.",
    # ---- client script ----
    "status.ready": "Ready to work.",
    "status.not_ready": "Not ready yet — see below.",
    "status.phase": "Phase: {phase}.",
    "status.memory_ok": "Memory (OSTIS) is readable.",
    "status.memory_readback": "Memory (OSTIS) answers, but nothing could be read back out of the graph.",
    "status.memory_unreachable": "Memory (OSTIS) is not reachable. It is required and has no substitute.",
    "status.model_ok": "The configured model answered a real call.",
    "status.model_ok_tools": "The configured model answered a real call, including a tool call.",
    "status.model_unverified": "The model is not verified yet.",
    "status.blocked_title": "Still blocked:",
    "status.unavailable": "Server unavailable. No readiness confirmed.",
    # ---- the refusal page a request without JavaScript lands on ----
    "error.refused_title": "Request refused",
    "error.cross_origin": "The request did not come from Oneiro's own address, so nothing was saved.",
    "error.bad_token": "The form was sent without this page's token, so nothing was saved. Reload the page and try again.",
    "error.back": "Back to Oneiro",
    "action.tool": "Tool",
    "action.unnamed": "unnamed action",
    "action.executed": "Executed successfully",
    "action.refused": "Refused by policy",
    "action.args": "Arguments",
    "action.result": "Result",
    "action.approvals_title": "Awaiting your approval",
    "action.questions_title": "Question from Oneiro",
    "inspector.heading": "Message Details",
    "inspector.role": "Role",
    "inspector.text": "Text",
    "inspector.steps": "Steps",
    "inspector.attachments": "Attachments",
    "chat.turn_refused": "Turn refused",
    "chat.server_failure": "Server communication failure",
    "tasks.none": "No active or completed tasks.",
    "tasks.load_failed": "Failed to load tasks.",
    "tasks.status_label": "Status: {state}",
    "tasks.active": "Active",
    "tasks.disabled": "Disabled",
    "schedules.none": "No standing schedules configured.",
    "schedules.load_failed": "Failed to load schedules.",
    "mcp.none": "No MCP servers configured.",
    "mcp.offline": "MCP service offline.",
    "mcp.enabled": "enabled",
    "mcp.disabled": "disabled",
    "skills.none": "No skills in catalog.",
    "skills.offline": "Skills catalog offline.",
    "settings.client.nothing_changed": "Nothing changed; nothing written.",
    "settings.client.saved": "Saved. Reloading to show the stored values.",
    "settings.client.unavailable": "Server unavailable. No successful save confirmed.",
    # ---- controls ----
    "btn.send": "Send",
    "btn.attach": "Attach file",
    "btn.new_conversation": "+ New",
    "btn.find": "Find",
    "btn.save_settings": "Save settings",
    "btn.queue_task": "Queue task",
    "btn.save_schedule": "Save schedule",
    "btn.add_fact": "Add fact",
    "placeholder.message": "Type a message or attach a file...",
    "placeholder.search": "Search messages...",
    "placeholder.task_title": "What should be done?",
    "placeholder.schedule_title": "Task title",
    "placeholder.new_fact": "New fact...",
    "placeholder.cron": "0 9 * * *",
    "status.prerequisites": "Checking runtime prerequisites…",
}

#: The group legends of the settings page, by the registry's `group` name.
_GROUPS_RU: dict[str, str] = {
    "Interface": "Интерфейс",
    "Work": "Работа",
    "Model": "Модель",
    "Graph": "Граф",
    "World": "Мир",
    "Cycle": "Цикл",
    "Measurements": "Измерения",
    "Harness": "Харнесс",
    "Appearance": "Внешний вид",
    "Window": "Окно",
    "Initiative": "Инициатива",
    "Permissions": "Разрешения",
    "Agent": "Агент",
    "Providers": "Провайдеры",
    "Tools": "Инструменты",
    "MCP": "MCP",
    "Skills": "Навыки",
    "Memory": "Память",
    "Research": "Исследование",
    "Attachments": "Вложения",
    "Operations": "Обслуживание",
}

#: A setting's Russian label and help, by key. English comes from the declaration
#: itself (`settings_registry.Setting.label` / `.help`), so only one language needs
#: writing here and the two can never drift apart.
_SETTINGS_RU: dict[str, tuple[str, str]] = {
    "web.host": ("Веб-адрес", "Привязан к loopback: Oneiro недоступен из сети."),
    "web.port": ("Веб-порт", "Один источник для диалога, настроек и /oneiro/."),
    "runtime.data_dir": (
        "Данные времени выполнения",
        "Где Oneiro хранит свои файлы. Только для чтения здесь: смена значения переносит "
        "сам файл настроек, поэтому задаётся через ONEIRO_DATA_DIR до первого запуска.",
    ),
    "llm.manager_model": (
        "Устаревшая модель менеджера",
        "Устаревший псевдоним модели менеджера. Объявленная модель — models.roles.manager; "
        "ничего не читает этот ключ, поэтому он только объявлен и уходит вместе с именем, "
        "которое заменяет.",
    ),
    "llm.researcher_model": (
        "Устаревшая модель исследователя",
        "Устаревший псевдоним модели исследователя; объявленная — models.roles.researcher, и "
        "ничего не читает этот ключ.",
    ),
    "llm.executor_model": (
        "Устаревшая модель исполнителя",
        "Устаревший псевдоним модели исполнителя; объявленная — models.roles.executor, и "
        "ничего не читает этот ключ.",
    ),
    "llm.base_url": (
        "Адрес провайдера",
        "Адрес провайдера, совместимого с OpenAI. Подойдёт любой, понимающий "
        "/chat/completions. Это имя адреса до реестра: пока список models.providers остаётся "
        "поставочным, это значение решает, куда указывает провайдер с именем local.",
    ),
    "llm.api_key": (
        "Ключ провайдера",
        "Пусто — значение ищется в ~/.config/keys.env, окружении и проектном .env. Это ключ "
        "до реестра: он отвечает за первого провайдера списка, когда его key_env ничего не "
        "находит, и никакой другой провайдер его не занимает.",
    ),
    "llm.model": (
        "Модель по умолчанию",
        "Имя модели по умолчанию до реестра. Оно решает, какая модель используется, пока "
        "models.default не задан, — так установка сохраняет свой выбор.",
    ),
    "chat.history_messages": (
        "Сколько прошлых сообщений отправлять",
        "Сколько прошлых сообщений открытого диалога уходит модели с каждым ответом. Не меньше 1.",
    ),
    "chat.context_chars": (
        "Предел размера прошлых сообщений",
        "Сколько символов прошлых сообщений уходит с каждым ответом. Более старые опускаются, "
        "и ответ об этом говорит.",
    ),
    "graph.host": ("Адрес графа", "Адрес OSTIS sc-machine."),
    "graph.port": ("Порт графа", "Порт SCTP у OSTIS sc-machine."),
    "dashboard.port": (
        "Устаревший порт панели",
        "Порт старого сервера панели, который не входит в эту сборку. Ничего не читает этот "
        "ключ: он только объявлен и уходит вместе с тем сервером.",
    ),
    "world.seed": (
        "Устаревшее зерно островного мира",
        "Зерно эксперимента с островным миром, который вне v1 и читается только научными "
        "скриптами. В этой сборке им ничто не управляет: он объявлен здесь только.",
    ),
    "loop.rounds": (
        "Устаревшее число раундов за прогон",
        "Сколько раундов самоулучшения делал один прогон цикла. Цикл вне v1, и этот ключ "
        "больше никто не читает: он только объявлен.",
    ),
    "series.seeds": (
        "Устаревшее число зёрен в серии",
        "Сколько зёрен проходил один прогон серии. Запускатор серий вне v1, и этот ключ "
        "больше никто не читает: он только объявлен.",
    ),
    "workspace": (
        "Устаревшая рабочая папка",
        "Прежнее имя папки, в которой работает агент. Эта сборка использует tools.workspace, "
        "поэтому этим ключом ничто не управляет: он только объявлен и уходит вместе с именем, "
        "которое заменяет.",
    ),
    "bench.dir": (
        "Устаревшая папка измерений",
        "Куда записывались прогоны бенчмарка памяти. Бенчмарк не входит в эту сборку, и ключ "
        "читает только его собственный скрипт: здесь он только объявлен.",
    ),
    "bench.lme_dir": (
        "Устаревший датасет LongMemEval",
        "Где лежал этот датасет. Его нет в репозитории — он слишком большой, — а бенчмарк, "
        "который им пользовался, не входит в эту сборку, поэтому этим ключом ничто не управляет.",
    ),
    "mcp.source": (
        "Устаревший список MCP",
        "Список, из которого удалённый харнесс читал свои MCP-серверы. Oneiro читает свой "
        "список (mcp.file) и обозревает файлы других клиентов только для чтения, поэтому этим "
        "ключом ничто не управляет: он только объявлен и уходит вместе с харнессом в W9.",
    ),
    "ui.language": (
        "Язык",
        "Язык интерфейса и того, что Oneiro отвечает. Русский или английский.",
    ),
    "ui.theme": (
        "Тема",
        "Какую тему использует окно. Контраст проверен в каждой из них.",
    ),
    "ui.density": (
        "Плотность списков",
        "Насколько плотно упакованы списки и карточки: comfortable или compact, чтобы "
        "поместилось больше.",
    ),
    "ui.window": (
        "Как открывается Oneiro",
        "Своё окно, вкладка браузера или любое из них. Окно, которое не может запуститься, "
        "переходит в браузер и говорит об этом.",
    ),
    "ui.tray": (
        "Закрывать в трей",
        "Скрывать ли Oneiro при закрытии окна вместо остановки. Выключено — закрытие "
        "останавливает его вместе с графом.",
    ),
    "initiative.level": (
        "Насколько Oneiro действует сам",
        "off: ничего без вас. on_command: только то, о чём попросите. scheduled: ещё и задачи, "
        "поставленные по расписанию. proactive: может сам напомнить из памяти и открыть задачи.",
    ),
    "initiative.suggestions": (
        "Подсказки из памяти",
        "Могут ли незавершённая работа и то, о чём вы просили напомнить, вернуться подсказкой.",
    ),
    "initiative.quiet_hours": (
        "Тихие часы",
        "Окно, в которое Oneiro не прерывает вас уведомлениями. Пусто — значит тихих часов нет.",
    ),
    "permissions.mode": (
        "Разрешения по умолчанию",
        "strict: подтверждать всё вне памяти. workspace: свободно внутри рабочей папки и "
        "свободное чтение сети. trusted: подтверждать только то, что запрещено ниже.",
    ),
    "permissions.web_read": (
        "Читать веб-страницы",
        "Может ли Oneiro прочитать публичный адрес, который сам попросит.",
    ),
    "permissions.write_workspace": (
        "Записывать в рабочей папке",
        "Может ли Oneiro писать файлы там, где ему разрешено работать.",
    ),
    "permissions.write_outside": (
        "Записывать вне рабочей папки",
        "ask: всё вне рабочей папки сначала требует подтверждения, и подтверждение покрывает "
        "ровно этот путь и этот текст. allow: пишет туда свободно. deny: никогда не пишет вне "
        "папки.",
    ),
    "permissions.delete": (
        "Удалять файлы",
        "Удаление всегда идёт в корзину; здесь решается, нужно ли перед этим подтверждение.",
    ),
    "permissions.install": (
        "Устанавливать пакеты",
        "Может ли Oneiro устанавливать нужное ему ПО и спрашивает ли перед этим.",
    ),
    "permissions.exec": (
        "Запускать команды",
        "Может ли Oneiro запускать локальную команду и спрашивает ли перед этим.",
    ),
    "permissions.send_publish": (
        "Отправлять и публиковать за вас",
        "Сообщения и публикации от вашего имени остаются запрещёнными, пока вы не разрешите "
        "это здесь.",
    ),
    "agent.max_turns": (
        "Шагов с инструментами за ответ",
        "Сколько ходов модели с вызовом инструментов может занять один ответ, прежде чем она "
        "остановится и скажет об этом.",
    ),
    "agent.step_timeout": (
        "Таймаут вызова модели",
        "Секунды на один вызов модели, вместе с его повторами и проверками. У вызовов "
        "инструментов свой предел.",
    ),
    "agent.tool_timeout": (
        "Таймаут вызова инструмента",
        "Секунды на один вызов инструмента. Запись, которая идёт дольше, считается "
        "неизвестной, а не повторяется.",
    ),
    "agent.show_steps": (
        "Показывать шаги инструментов",
        "Появляется ли каждый вызов инструмента, отказ и запрос подтверждения в диалоге "
        "сразу, как происходит.",
    ),
    "models.providers": (
        "Провайдеры",
        "Провайдеры, которые Oneiro может вызывать, в той же форме, что у OpenCode и Hermes: "
        "name, base_url, key_env, discover_models, models, enabled. Ключ называется именем "
        "переменной окружения, которая его держит, и никогда не хранится здесь; провайдер с "
        "enabled=false пропускается. Они используются в указанном порядке, первый — по умолчанию.",
    ),
    "models.default": (
        "Модель по умолчанию",
        "Модель, которую использует каждая роль, если роль не сказала иначе. Запрошенное имя "
        "может быть псевдонимом маршрутизации; модель, которая ответила на самом деле, "
        "называется в учёте.",
    ),
    "models.roles.manager": (
        "Модель менеджера",
        "Модель для диалога и координации. Пусто — значит модель по умолчанию.",
    ),
    "models.roles.researcher": (
        "Модель исследователя",
        "Модель для самостоятельного исследования. Пусто — значит модель по умолчанию.",
    ),
    "models.roles.executor": (
        "Модель исполнителя",
        "Модель для проверенного выполнения задач. Пусто — значит модель по умолчанию.",
    ),
    "models.fallback": (
        "Запасные модели",
        "Модели, к которым можно отступить, по порядку и только там, где реальный вызов "
        "показал совпадение возможностей. Каждая запись — имя модели или provider/model, "
        "пробуется не больше трёх. Пусто — отступать некуда.",
    ),
    "models.accounting": (
        "Считать каждый вызов",
        "Записывается ли каждый вызов провайдера — роль, модель, попытка, исход, задержка, "
        "токены и стоимость — и читается ли это через `oneiro verify-model`. Выключено — не "
        "записывается ничего, и отчёт говорит об этом, а не выглядит пустым.",
    ),
    "tools.workspace": (
        "Рабочая папка инструментов",
        "Папка, внутри которой файловые инструменты могут писать. По умолчанию — собственная "
        "папка Oneiro; `permissions.write_workspace` решает, спрашивать ли всё равно.",
    ),
    "tools.internet": (
        "Доступ инструментов в сеть",
        "Может ли агент читать публичный URL, который сам попросит. `permissions.web_read` "
        "решает, спрашивать ли перед этим.",
    ),
    "tools.max_file_bytes": (
        "Предел размера файла для инструмента",
        "Сколько байт инструмент читает или пишет за один вызов.",
    ),
    "mcp.file": (
        "Список MCP-серверов",
        "Где Oneiro хранит свой список MCP-серверов, в форме, которую уже используют другие "
        "клиенты.",
    ),
    "mcp.autostart": (
        "Запускать включённые серверы при старте",
        "Запускаются ли включённые вами серверы при запуске Oneiro.",
    ),
    "skills.catalog": (
        "Каталог навыков",
        "Ваш собственный файл каталога, в форме поставочного. Пусто — используется "
        "поставочный. Отсутствующий файл, неверный JSON или файл без записей называются как "
        "есть и никогда не игнорируются молча.",
    ),
    "skills.paths": (
        "Ваши папки с навыками",
        "Дополнительные папки с навыками, просматриваемые вдобавок к поставочному каталогу. "
        "Папкой может быть сама папка навыков или родительская, хранящая их под .agents/skills. "
        "Навык, найденный в них, тоже доступен для поиска и чтения и говорит, что его никогда "
        "не проверяли.",
    ),
    "skills.auto_use": (
        "Использовать найденный навык",
        "ask: Oneiro называет найденный навык и ждёт. auto: использует навык и говорит об этом "
        "после. В этой сборке этим ключом ещё ничто не управляет: два инструмента навыков "
        "предлагаются, а решает модель, поэтому здесь за владельца выбор не делается.",
    ),
    "memory.facts_budget": (
        "Бюджет курируемых фактов",
        "Сколько символов ваших собственных фактов Oneiro держит в уме для каждого ответа. "
        "Факт, который выведет сохранённый набор за этот предел, отклоняется с указанием "
        "предела в причине.",
    ),
    "research.sources": (
        "Источники исследования",
        "Какие источники может использовать исследование. `web` — открытая сеть.",
    ),
    "attachments.max_bytes": (
        "Предел размера вложения",
        "Наибольший файл, который можно приложить в одном сообщении, в байтах.",
    ),
    "attachments.max_pages": (
        "Предел страниц вложения",
        "Сколько страниц PDF читается в одном сообщении.",
    ),
    "logging.level": (
        "Подробность журнала",
        "Сколько Oneiro пишет в собственный журнал: debug, info, warning или error.",
    ),
    "backup.mode": (
        "Резервная копия памяти",
        "manual: копию делаете вы, когда захотите. scheduled: Oneiro делает её ещё и сам по "
        "своему расписанию.",
    ),
}


def _assemble() -> dict[str, dict[str, str]]:
    """The catalog: the chrome above, plus every declared setting in both languages."""
    ru = dict(_RU)
    en = dict(_EN)
    for code, (text_ru, text_en) in _REASONS.items():
        ru[code] = text_ru
        en[code] = text_en
    for group, group_ru in _GROUPS_RU.items():
        ru[f"group.{group}"] = group_ru
        en[f"group.{group}"] = group
    for setting in config.SETTINGS:
        label_ru, help_ru = _SETTINGS_RU.get(setting.key, (setting.label, setting.help))
        ru[f"setting.{setting.key}.label"] = label_ru
        ru[f"setting.{setting.key}.help"] = help_ru
        en[f"setting.{setting.key}.label"] = setting.label
        en[f"setting.{setting.key}.help"] = setting.help
    return {"ru": ru, "en": en}


CATALOG: dict[str, dict[str, str]] = _assemble()


def current_language() -> str:
    """The language currently active from settings or default."""
    try:
        val = str(config.value("ui.language") or DEFAULT_LANGUAGE).strip().lower()
        return val if val in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
    except Exception:
        return DEFAULT_LANGUAGE


def _supported(lang: str | None) -> str:
    active = (lang or current_language()).strip().lower()
    return active if active in CATALOG else DEFAULT_LANGUAGE


def t(key: str, lang: str | None = None, **values: Any) -> str:
    """Translate a key into the given or configured language.

    `{name}` in the text is replaced by the matching keyword, literally: `str.format`
    would raise on a brace that belongs to the sentence, and a screen must not depend
    on the shape of what it shows.
    """
    active_lang = (lang or current_language()).strip().lower()
    if active_lang not in CATALOG:
        active_lang = DEFAULT_LANGUAGE
    catalog = CATALOG[active_lang]
    text = catalog.get(key)
    if text is None:
        # Fall back to English, then to the key itself, so a missing translation is
        # visible in the page and named by the parity test rather than crashing a screen.
        text = CATALOG["en"].get(key, key)
    for name, value in values.items():
        text = text.replace("{" + name + "}", str(value))
    return text


def setting_text(key: str, part: str, declared: str, lang: str | None = None) -> str:
    """A setting's visible text: the catalog's, or the declaration's own wording.

    The registry keeps its promise that a new setting is one entry and nothing else:
    a key declared a minute ago renders its English `label`/`help` immediately instead
    of a raw key name, and gets its place in both catalogs when it is translated. The
    parity test is what forces that translation to exist in the shipped build.
    """
    full = f"setting.{key}.{part}"
    if full in CATALOG.get(_supported(lang), {}):
        return t(full, lang)
    return declared


def group_text(group: str, lang: str | None = None) -> str:
    """A settings group's legend, falling back to the declared group name.

    Same promise as `setting_text`: a group introduced by a new declaration renders its
    own name until the catalog carries a legend for it, never a raw key.
    """
    full = f"group.{group}"
    return t(full, lang) if full in CATALOG.get(_supported(lang), {}) else group


def reason_data(item: Any) -> tuple[str, dict[str, Any]]:
    """Read a reported reason as (code, data).

    A plain string is accepted as its own code with no data, so a surface that still
    reports a sentence is rendered — visibly untranslated, and named by the parity test —
    instead of crashing the page that shows it.
    """
    if isinstance(item, str):
        return item, {}
    if isinstance(item, dict):
        data = item.get("data")
        return str(item.get("code") or ""), dict(data) if isinstance(data, dict) else {}
    return str(item), {}


def reason(item: Any, lang: str | None = None) -> str:
    """One reported reason as a sentence in `lang`, with its data interpolated."""
    code, data = reason_data(item)
    return t(code, lang, **data)


def reasons(items: Any, lang: str | None = None) -> list[str]:
    """Reported reasons as sentences in `lang`, in the order they were reported."""
    return [reason(item, lang) for item in (items or ())]


def client_catalog(lang: str | None = None) -> dict[str, str]:
    """The subset `static/app.js` renders, so the script holds no sentence of its own."""
    return {key: t(key, lang) for key in CLIENT_KEYS}
