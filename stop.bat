@echo off

rem voice-code stop: kill by lock pid + anchors, then assert zero residue (exit 5 if not clean).

cd /d "%~dp0"

".venv\Scripts\python.exe" -X utf8 main.py --sweep --expect-clean
