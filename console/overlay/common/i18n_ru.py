# encoding:utf-8

"""Russian (ru) message catalog.

Keyed by the **English** source text of ``i18n.t(zh, en)`` call sites, so
localizing the runtime never touches a call site: anything missing here simply
falls back to English. To translate more of the runtime, add a line —
nothing else has to change.
"""

MESSAGES = {
    # Progress cards and status lines (Feishu card, chat stream).
    "Working": "В работе",
    "Done": "Готово",
    "Stopped": "Остановлено",
    "Error": "Ошибка",
    "Thinking": "Думаю",
    "Tools": "Инструменты",
    "turn": "ход",
    "turns": "ходов",
    "running": "выполняется",
    "error": "ошибка",
    "done": "готово",
    # Attachments quoted back inside a user message.
    "Workspace directory": "Папка рабочей области",
    "Workspace file": "Файл рабочей области",
    "Image": "Изображение",
    "Video": "Видео",
    "Directory": "Папка",
    "File": "Файл",
    # Fallback shown when the model answered with nothing at all.
    "(The model returned no content. Please retry or rephrase your request.)":
        "(Модель не вернула ответ. Повторите запрос или переформулируйте его.)",
}
