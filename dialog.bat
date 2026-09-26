@echo off

rem voice-code dialog view: two-party transcript from the console WS. Ctrl-C to exit.

cd /d "%~dp0"

".venv\Scripts\python.exe" -X utf8 src\console\dialog.py
