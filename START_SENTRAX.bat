@echo off
title SentraX - Road Safety ^& Smart Infrastructure Platform
color 0B

echo =========================================================================
echo    SENTRAX - INTELLIGENT ROAD SAFETY ^& SMART INFRASTRUCTURE PLATFORM
echo =========================================================================
echo.

:: Ensure current working directory is the project root
cd /d "%~dp0"

:: Prefer the project virtual environment (it has bleak, fastapi, pyserial), fall back to system Python
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"

"%PY%" --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python was not found. Install Python 3.10+ or create .venv first.
    echo.
    pause
    exit /b 1
)

echo [1/2] Opening SentraX Command Center Dashboard in default browser...
start "" cmd /c "timeout /t 2 /nobreak >nul & start http://localhost:8000"

echo [2/2] Launching SentraX Server ^& Telemetry Engine...
echo.
echo =========================================================================
echo   Dashboard URL:    http://localhost:8000
echo   API Docs / REST:  http://localhost:8000/docs
echo   WebSocket Stream: ws://localhost:8000/ws/telemetry
echo.
echo   Press [Ctrl + C] in this terminal window anytime to stop the server.
echo =========================================================================
echo.

"%PY%" scripts\run_backend.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] SentraX server exited with an error code.
    pause
)
