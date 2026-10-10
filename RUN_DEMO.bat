@echo off
title SentraX - Automated Expo Demo
color 0B
setlocal

:: Ensure current working directory is the project root
cd /d "%~dp0"

echo =========================================================================
echo    SENTRAX - AUTOMATED 8-STEP EXPO DEMO
echo =========================================================================
echo.

:: Prefer the project virtual environment, fall back to the system Python
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"

"%PY%" --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python was not found. Install Python 3.10+ or create .venv first.
    pause
    exit /b 1
)

:: 1. Start the server unless one is already answering on port 8000
curl -s -o nul http://localhost:8000/api/health
if %ERRORLEVEL% EQU 0 (
    echo [1/3] SentraX server already running on http://localhost:8000
) else (
    echo [1/3] Starting SentraX server in a new window...
    start "SentraX Server" cmd /k ""%PY%" scripts\run_backend.py"
)

:: 2. Wait until the API responds (up to 60 seconds)
echo [2/3] Waiting for the server to come online...
set /a WAITED=0
:wait_loop
curl -s -o nul http://localhost:8000/api/health
if %ERRORLEVEL% EQU 0 goto server_ready
set /a WAITED+=1
if %WAITED% GEQ 60 (
    echo [ERROR] Server did not respond within 60 seconds. Check the "SentraX Server" window.
    pause
    exit /b 1
)
timeout /t 1 /nobreak >nul
goto wait_loop

:server_ready
echo        Server online. Opening the dashboard...
start "" http://localhost:8000

:: 3. Run the demo each time a key is pressed
:demo_prompt
echo.
echo =========================================================================
echo   [3/3] Press any key to start the 8-step demo.
echo         Normal road, toy car, overspeed, congestion, wet road,
echo         collision, emergency vehicle, risk rise (about 40 s).
echo         Close this window to finish.
echo =========================================================================
pause >nul

curl -s -o nul -X POST http://localhost:8000/api/simulation/start
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Could not start the demo. Is the server still running?
    goto demo_prompt
)
echo   Demo running on the dashboard...
timeout /t 42 /nobreak >nul
echo   Demo finished.
goto demo_prompt
