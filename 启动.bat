@echo off
cd /d "%~dp0"
title Astral

echo.
echo   Astral v1.1.0-alpha
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   [ERROR] Python not found
    echo   Install Python 3.10+: https://www.python.org/downloads/
    pause
    exit
)

pip show flask      >nul 2>&1 || set NEED=1
pip show httpx      >nul 2>&1 || set NEED=1
pip show flask-socketio    >nul 2>&1 || set NEED=1
pip show simple-websocket  >nul 2>&1 || set NEED=1

if defined NEED (
    echo   Installing dependencies...
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo   [ERROR] pip install failed
        echo   Run manually: pip install -r requirements.txt
        pause
        exit
    )
)

echo   [OK] http://127.0.0.1:8640
echo.
start "" http://127.0.0.1:8640
python server.py
pause
