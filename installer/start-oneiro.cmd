@echo off
rem Starts Oneiro on loopback. Its data stays in %USERPROFILE%\.oneiro, so
rem uninstalling the program leaves the owner's memory in place.
rem PYTHONNOUSERSITE keeps the packaged runtime from reading packages installed
rem for some other Python on this machine.
set PYTHONNOUSERSITE=1
"%~dp0python\python.exe" -m oneiro serve
