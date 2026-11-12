@echo off
setlocal
cd /d "%~dp0"
title AURA - Preparazione Qwen TTS
echo Preparazione della voce Qwen sul PC.
echo I modelli vengono salvati nei dati locali di AURA, fuori da OneDrive.
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "tools\setup_qwen_voice.py"
) else (
  py -3 "tools\setup_qwen_voice.py"
)
if errorlevel 1 echo La preparazione non e' stata completata. Puoi riprovare.
pause
