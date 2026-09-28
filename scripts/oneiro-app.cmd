@echo off
rem One click, one program. The desktop shortcut points here; this shim exists
rem because cmd.exe passes the environment through untouched, while Git Bash
rem rewrites a value like /oneiro=http://... into a Windows path (measured: it
rem arrives as C:\Program Files\Git\oneiro=http;\...), and the console then
rem correctly refuses to mount a spec it cannot parse.
rem
rem The interpreter is the installed console's own virtualenv, not a path
rem pinned to this machine: `scripts\install.py` builds it inside the project
rem (.runtime\cowagent), which is what makes a fresh clone work on its own.
setlocal
set "PROJECT=%~dp0.."
set "PYTHON=%PROJECT%\.runtime\cowagent\.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=%PROJECT%\..\..\..\..\tools\upstream\cowagent\.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    echo Oneiro ещё не установлен в этой копии проекта.
    echo Запустите один раз:  python scripts\install.py
    pause
    exit /b 1
)
"%PYTHON%" "%~dp0oneiro-app.py" %*
rem A window that closes on a failure tells the owner nothing, so a failure
rem keeps it open with the reason on screen.
if errorlevel 1 pause
