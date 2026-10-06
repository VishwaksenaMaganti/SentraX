@echo off
title SentraX - BLE Signal Diagnostic Tool
color 0B
cd /d "%~dp0"
python scripts\scan_ble.py
echo.
pause
