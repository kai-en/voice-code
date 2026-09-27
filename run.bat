@echo off

rem voice-code start: sweep old tree to zero (lock pid + anchors + assert), then hidden start.

cd /d "%~dp0"

if not exist logs mkdir logs
set "TQDM_DISABLE=1"

rem keywords: vox -> tts backend voxcpm (default wintts, see src/orchestrator/main.py); unknown args ignored.
set "VOX="
:parse_args
if "%~1"=="" goto args_done
if /i "%~1"=="vox" set "VOX=1"
shift
goto :parse_args
:args_done
if defined VOX set "VOICECODE_TTS_BACKEND=voxcpm"

".venv\Scripts\python.exe" -X utf8 main.py --sweep --expect-clean
if errorlevel 1 (
  echo [run] old processes not fully cleaned, refuse to start.
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "$p=Start-Process cmd -ArgumentList '/c (echo ==== starting ==== & "%~dp0.venv\Scripts\python.exe" -u -X utf8 "%~dp0main.py" & echo ==== exited ==== ) > logs\voice-code.log 2>&1' -WorkingDirectory '%~dp0.' -WindowStyle Hidden -PassThru; Set-Content -Path 'logs\voice-code.pid' -Value $p.Id"

echo voice-code started. log: logs\voice-code.log  console: ws://127.0.0.1:8765  tail: log.bat
