@echo off
setlocal DisableDelayedExpansion
set "PYTHONUTF8=1"
pushd "%~dp0"
if errorlevel 1 exit /b 1
echo Modelli ufficiali Live2D. Termini e fonti: licenses\THIRD_PARTY.md
if exist ".venv\Scripts\python.exe" goto local
where py >nul 2>nul
if errorlevel 1 goto python
py -3 tools\prepare_avatar.py
goto done
:python
python tools\prepare_avatar.py
goto done
:local
".venv\Scripts\python.exe" tools\prepare_avatar.py
:done
set "auraExit=%errorlevel%"
if not "%auraExit%"=="0" if not defined JARVIS_NO_PAUSE pause
popd
exit /b %auraExit%
