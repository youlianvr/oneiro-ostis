@echo off
rem One click, one program. The desktop shortcut points here; this shim exists
rem because cmd.exe passes the environment through untouched, while Git Bash
rem rewrites a value like /oneiro=http://... into a Windows path (measured: it
rem arrives as C:\Program Files\Git\oneiro=http;\...), and the console then
rem correctly refuses to mount a spec it cannot parse.
setlocal
set "PYTHON=%~dp0..\..\..\..\tools\upstream\cowagent\.venv\Scripts\python.exe"
"%PYTHON%" "%~dp0oneiro-app.py" %*
rem A window that closes on a failure tells the owner nothing, so a failure
rem keeps it open with the reason on screen.
if errorlevel 1 pause
