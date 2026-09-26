@echo off
rem voice-code log viewer: tail last 40 lines, then follow (Ctrl-C exit).
cd /d "%~dp0"
if not exist logs\voice-code.log (echo logs\voice-code.log not found & exit /b 1)
powershell -NoProfile -Command "Get-Content -LiteralPath '%~dp0logs\voice-code.log' -Encoding UTF8 -Wait -Tail 40"
