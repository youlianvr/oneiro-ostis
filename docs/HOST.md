# Хост: CowAgent как наш процесс, граф как его память

Состояние на 2026-09-22, 17:05. Всё ниже проверено выводом команд, а не замыслом.

## Что стоит и где

| Что | Где | Как проверено |
|---|---|---|
| Исходники хоста | `tools/upstream/cowagent` (zipball релиза 2.1.9, MIT, в git воркспейса не кладём: это чужая кодовая база) | скачано и распаковано, `app.py` запускается |
| Окружение хоста | `tools/upstream/cowagent/.venv` (с `--system-site-packages`, чтобы видеть `sc_client`) | `import croniter, json_repair, numpy, requests, aiohttp, yaml` проходит |
| Данные и конфиг хоста | `~/cow/instance/config.json` (`COW_DATA_DIR`), рабочая папка агента `~/cow` | лог инициализации читает именно этот конфиг |
| Наш MCP-сервер в хосте | `~/cow/mcp.json`, запись `oneiro` → `projects/ostis/oneiro-ostis/host/ostis_mcp.py` | хост пишет `[MCP] Server 'oneiro' ready — 5 tool(s)` |
| Консоль хоста | http://localhost:9899 (только 127.0.0.1) | `/api/health` отвечает `{"status": "ok"}` |
| Процессы сейчас | хост pid 23416 (слушает 9899), наш MCP-сервер pid 27020 (дочерний у хоста) | `netstat` и список процессов |

Модель хоста идёт через локальный прокси: `bot_type: "custom:oneiro"`, база
`http://127.0.0.1:20128/v1`, модель `auto/coding`. Ключ лежит в конфиге хоста,
он же берётся из `OMNIROUTE_API_KEY` в `.env` воркспейса.

## Как это поднимается с нуля

```bash
# 1. исходники релиза
cd tools/upstream && curl -sL -o cowagent.zip \
  "https://api.github.com/repos/zhayujie/CowAgent/zipball/2.1.9" && unzip -q cowagent.zip \
  && mv zhayujie-CowAgent-* cowagent

# 2. окружение (то, что нужно для веб-канала и агентского режима)
cd cowagent && python -m venv --system-site-packages .venv
./.venv/Scripts/python.exe -m pip install numpy markdown-it-py "aiohttp>=3.10" requests \
  chardet Pillow python-dotenv PyYAML croniter click qrcode json-repair regex \
  websocket-client legacy-cgi "web.py @ git+https://github.com/webpy/webpy.git"

# 3. подключить нашу память и вопрос человеку (в том же формате, что читает хост)
cd <проект>/oneiro-ostis && python scripts/host-wire.py --apply

# 4. запуск и остановка
cd tools/upstream/cowagent && COW_DATA_DIR="$HOME/cow/instance" ./.venv/Scripts/python.exe app.py
# остановка: закрыть процесс, который слушает 9899 (pid виден в netstat)
```

## Что уже доказано

- Наш MCP-сервер работает сам по себе: `python scripts/mcp-smoke.py` поднимает его
  как настоящий клиент по stdio, читает хвост графа с происхождением, записывает
  заметку и находит её же поиском. Никаких заглушек.
- Хост поднимается на нашей модели и **загружает наш сервер**: в логе пять
  инструментов (`memory_search`, `memory_record`, `memory_tail`, `ask_human`,
  `check_answer`), и дочерний процесс `ostis_mcp.py` видно в списке процессов.
- Подключение идемпотентно и не рушит чужой конфиг: `host-wire.py` делает копию
  `mcp.json` перед записью, повторный прогон пишет `already current`.
- Веб-канал требует `web.py` (в Python 3.13+ ставится из их репозитория) и
  `legacy-cgi`; без них хост пишет `No module named 'web'` и продолжает без консоли.

## Что ещё не доказано (не выдавать за сделанное)

- **Ни один ход агента через консоль хоста не прогнан**: точка входа чата в
  `web_channel.py` работает по веб-сокету, и я её пока не подключил; `/api/tools`
  показывает 16 встроенных инструментов и не показывает наши (наши живут в
  MCP-слое и агент их видит, но этот эндпоинт их не перечисляет).
- Терминальный канал при перенаправленном вводе сразу выходит (`input()` получает
  конец файла), поэтому для проверки через консоль он не годится.
- Абсолютное подтверждение сквозного пути (агент сам зовущий `ask_human`, кнопка в
  Telegram, запись решения в граф) ещё не снято: сделана и проверена каждая
  половина по отдельности, вместе — нет.

## Следующий шаг

Подключить чат-вход хоста (веб-сокет консоли или его же планировщик задач) и
прогнать один настоящий ход: агент читает хвост графа через `memory_tail`,
находит письмо, отправляет `ask_human`, владелец нажимает кнопку, и вердикт с
записью в графе возвращается агенту. Это и будет сквозной путь «хост + граф +
человек».
