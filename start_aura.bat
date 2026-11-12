@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
title AURA 2.0 - Il tuo spazio AI
set "PYTHONUTF8=1"
pushd "%~dp0"
if errorlevel 1 goto folder_error
if not exist "run.py" goto missing_files
echo.
echo  AURA 2.0 - Il tuo spazio AI - Assistente personale
echo  Preparazione ambiente e controllo avvio...
echo.
if not exist ".venv\Scripts\python.exe" goto try_launcher
".venv\Scripts\python.exe" -c "import sys; raise SystemExit(sys.version_info[:2] < (3,10))" >nul 2>nul
if not errorlevel 1 goto local_python
:try_launcher
where py >nul 2>nul
if errorlevel 1 goto try_python
py -3 -c "import sys; raise SystemExit(sys.version_info[:2] < (3,10))" >nul 2>nul
if not errorlevel 1 goto python_launcher
:try_python
where python >nul 2>nul
if errorlevel 1 goto missing_python
python -c "import sys; raise SystemExit(sys.version_info[:2] < (3,10))" >nul 2>nul
if errorlevel 1 goto missing_python
python "run.py" %*
goto finished
:local_python
".venv\Scripts\python.exe" "run.py" %*
goto finished
:python_launcher
py -3 "run.py" %*
goto finished
:finished
set "jarvisExit=%errorlevel%"
if "%jarvisExit%"=="0" goto done
echo.
echo  Aura non e stato avviato. Leggi il messaggio qui sopra.
if not defined JARVIS_NO_PAUSE pause
:done
popd
exit /b %jarvisExit%
:missing_python
echo  Serve Python 3.10 o successivo. Installa Python da python.org.
echo  Sono supportati sia il comando py sia python.
if not defined JARVIS_NO_PAUSE pause
popd
exit /b 1
:missing_files
echo  File run.py non trovato. Avvia questo BAT dalla cartella completa di Aura.
if not defined JARVIS_NO_PAUSE pause
popd
exit /b 1
:folder_error
echo  Impossibile aprire la cartella di Aura.
if not defined JARVIS_NO_PAUSE pause
exit /b 1
