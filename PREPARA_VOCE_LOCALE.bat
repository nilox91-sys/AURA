@echo off
setlocal
title AURA - Preparazione voce locale
cd /d "%~dp0"
echo Preparazione della voce gratuita locale. Serve solo la prima volta.
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" "tools\setup_local_voice.py" %*
) else (
    py -3 "tools\setup_local_voice.py" %*
)
exit /b %errorlevel%
