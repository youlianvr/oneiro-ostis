"""Localization and internationalization dictionary for Oneiro.

Provides full RU and EN translation catalogs with 100% key parity across:
- Navigation and screen titles
- Actions, buttons, labels and notices
- Action cards (tool executions, approvals, questions, refusals)
- Error states and status phrases
"""
from __future__ import annotations

from typing import Any

from oneiro import config

DEFAULT_LANGUAGE = "ru"
SUPPORTED_LANGUAGES = ("ru", "en")

CATALOG: dict[str, dict[str, str]] = {
    "ru": {
        # App & navigation
        "app.name": "Oneiro",
        "app.tagline": "Автономный ассистент на базе OSTIS",
        "nav.chat": "Диалог",
        "nav.tasks": "Задачи",
        "nav.tools": "Инструменты",
        "nav.settings": "Настройки",
        "nav.memory": "Память",
        "nav.setup": "Установка",
        "nav.graph": "Граф",
        # Screen titles & descriptions
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
        # Common controls & buttons
        "btn.send": "Отправить",
        "btn.attach": "Прикрепить файл",
        "btn.new_conversation": "+ Новый",
        "btn.find": "Найти",
        "btn.save_settings": "Сохранить настройки",
        "btn.queue_task": "В очередь",
        "btn.save_schedule": "Сохранить расписание",
        "btn.add_fact": "Добавить факт",
        "placeholder.message": "Напишите сообщение или прикрепите файл...",
        "placeholder.search": "Поиск по сообщениям...",
        "placeholder.task_title": "Что нужно сделать?",
        "placeholder.schedule_title": "Название задачи",
        "placeholder.new_fact": "Новый факт...",
        # Tool and action card labels
        "action.tool": "Инструмент",
        "action.executed": "Выполнен успешно",
        "action.refused": "Отклонён политикой",
        "action.args": "Параметры",
        "action.result": "Результат",
        "action.approvals_title": "Ожидает вашего подтверждения",
        "action.questions_title": "Вопрос от Oneiro",
        # Status phrases
        "status.ready": "Готов к работе.",
        "status.not_ready": "Не готов — см. ниже.",
        "status.memory_ok": "Память (OSTIS) доступна для чтения.",
        "status.memory_unreachable": "Память (OSTIS) недоступна. Она обязательна и не имеет заменителей.",
        "status.model_ok": "Настроенная модель ответила на реальный запрос.",
        "status.model_unverified": "Модель ещё не верифицирована.",
        "status.prerequisites": "Проверка готовности системы...",
        "footer.note": "Без автозапуска ОС. OSTIS обязателен. Корень данных: ",
    },
    "en": {
        # App & navigation
        "app.name": "Oneiro",
        "app.tagline": "Standalone assistant with OSTIS memory",
        "nav.chat": "Chat",
        "nav.tasks": "Tasks",
        "nav.tools": "Tools",
        "nav.settings": "Settings",
        "nav.memory": "Memory",
        "nav.setup": "Setup",
        "nav.graph": "Graph",
        # Screen titles & descriptions
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
        "notice.settings": "Every setting Oneiro declares, in one place. Values come from this file, then environment, then default. Provider keys are never sent back to the browser.",
        "title.memory": "Oneiro — memory",
        "heading.memory": "Memory & Graph",
        "notice.memory": "The persistent memory substrate: your curated facts, past conversation search, and OSTIS status.",
        "title.setup": "Oneiro — setup",
        "heading.setup": "Setup",
        "notice.setup": "Setup reads the real state of this machine: the OSTIS server, model key, dependencies.",
        "title.graph": "Oneiro — graph",
        "heading.graph": "Graph panel",
        "notice.graph": "OSTIS is the memory substrate and the only one. Reachability and traversal check in real-time.",
        # Common controls & buttons
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
        # Tool and action card labels
        "action.tool": "Tool",
        "action.executed": "Executed successfully",
        "action.refused": "Refused by policy",
        "action.args": "Arguments",
        "action.result": "Result",
        "action.approvals_title": "Awaiting your approval",
        "action.questions_title": "Question from Oneiro",
        # Status phrases
        "status.ready": "Ready to work.",
        "status.not_ready": "Not ready yet — see below.",
        "status.memory_ok": "Memory (OSTIS) is readable.",
        "status.memory_unreachable": "Memory (OSTIS) is not reachable. It is required and has no substitute.",
        "status.model_ok": "The configured model answered a real call.",
        "status.model_unverified": "The model is not verified yet.",
        "status.prerequisites": "Checking runtime prerequisites...",
        "footer.note": "No system autostart. OSTIS remains required. Data root: ",
    },
}


def current_language() -> str:
    """The language currently active from settings or default."""
    try:
        val = str(config.value("ui.language") or DEFAULT_LANGUAGE).strip().lower()
        return val if val in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
    except Exception:
        return DEFAULT_LANGUAGE


def t(key: str, lang: str | None = None) -> str:
    """Translate a dictionary key into the given or configured language."""
    active_lang = (lang or current_language()).strip().lower()
    if active_lang not in CATALOG:
        active_lang = DEFAULT_LANGUAGE
    catalog = CATALOG[active_lang]
    if key in catalog:
        return catalog[key]
    # Fallback to English catalog then default
    if key in CATALOG["en"]:
        return CATALOG["en"][key]
    return key
