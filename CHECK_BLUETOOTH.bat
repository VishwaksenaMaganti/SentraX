@echo off
title SentraX - BLE Signal Diagnostic Tool
color 0B
cd /d "%~dp0"
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
"%PY%" scripts\scan_ble.py
echo.
pause
