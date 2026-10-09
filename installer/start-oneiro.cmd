@echo off
rem Starts Oneiro: the memory graph in Docker Desktop, then the web app on loopback.
rem The launcher is start-oneiro.ps1. Data stays in %USERPROFILE%\.oneiro and in the
rem Docker volume oneiro-graph-kb-v1, so uninstalling the program leaves the memory in place.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-oneiro.ps1"
