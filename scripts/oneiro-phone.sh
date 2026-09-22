#!/usr/bin/env bash
# The phone path in one command: the bot that takes the owner's words, and the
# runner that works them up to a question with buttons. Two ordinary processes,
# deliberately not an autostart entry: nothing here starts by itself.
#
#   bash scripts/oneiro-phone.sh start    # start whatever is not running
#   bash scripts/oneiro-phone.sh status   # what is running, and the last log lines
#   bash scripts/oneiro-phone.sh stop     # stop both
#
# Output is Russian because the person who runs this is the owner, not a
# programmer; the comments stay English like the rest of the code.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE="$HERE/state"
PYTHON="${PYTHON:-python}"
mkdir -p "$STATE"

# Windows has no pgrep for a command line match, so the process table is asked
# through PowerShell. An empty answer is normal: the process is simply not up.
pids_of() {
    local pattern="$1"
    powershell -NoProfile -Command \
        "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | Where-Object { \$_.CommandLine -like '*${pattern}*' } | ForEach-Object { \$_.ProcessId }" \
        2>/dev/null | tr -d '\r' | tr '\n' ' ' || true
}

start_one() {
    local script="$1" stem="$2" label="$3"
    local running
    running="$(pids_of "$script")"
    if [ -n "${running// /}" ]; then
        echo "Уже работает: $label (номер процесса $running)"
        return 0
    fi
    ( cd "$HERE" && nohup "$PYTHON" -u "python/$script" >> "$STATE/$stem.log" 2>&1 & )
    sleep 2
    local started
    started="$(pids_of "$script")"
    if [ -n "${started// /}" ]; then
        echo "Запущен: $label (номер процесса $started)"
    else
        echo "Не поднялся: $label — смотри $STATE/$stem.log"
        return 1
    fi
}

case "${1:-status}" in
    start)
        start_one telegram_entry.py telegram_entry "приём задач с телефона"
        start_one task_runner.py task_runner "работа над задачами"
        echo "Готово. Напиши помощнику в телеграме простыми словами."
        ;;
    status)
        for pair in "telegram_entry.py:приём задач с телефона" \
                    "task_runner.py:работа над задачами"; do
            pattern="${pair%%:*}"
            label="${pair##*:}"
            running="$(pids_of "$pattern")"
            if [ -n "${running// /}" ]; then
                echo "Работает: $label (номер процесса $running)"
            else
                echo "Не работает: $label"
            fi
        done
        echo "--- последние строки приёма задач ---"
        tail -3 "$STATE/telegram_entry.log" 2>/dev/null || echo "записей нет"
        echo "--- последние строки работы ---"
        tail -5 "$STATE/task_runner.log" 2>/dev/null || echo "записей нет"
        ;;
    stop)
        for pattern in "telegram_entry.py" "task_runner.py"; do
            for pid in $(pids_of "$pattern"); do
                taskkill //PID "$pid" //F >/dev/null 2>&1 || true
                echo "Остановлен: $pattern (номер процесса $pid)"
            done
        done
        ;;
    *)
        echo "Как пользоваться: bash scripts/oneiro-phone.sh start|status|stop"
        exit 2
        ;;
esac
