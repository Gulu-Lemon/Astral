@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Astral

echo.
echo   Astral v1.1.0-alpha
echo.

echo   检查 Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   [错误] 未检测到 Python
    echo   请安装 Python 3.10+: https://www.python.org/downloads/
    pause
    exit
)

echo   检查依赖...
pip show flask >nul 2>&1 || set NEED=1
pip show httpx >nul 2>&1 || set NEED=1
pip show flask-socketio >nul 2>&1 || set NEED=1
pip show simple-websocket >nul 2>&1 || set NEED=1

if defined NEED (
    echo   正在安装依赖...
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo   [错误] 安装失败，请检查网络
        echo   手动执行: pip install -r requirements.txt
        pause
        exit
    )
)

echo   [就绪] http://127.0.0.1:8640
echo.
start "" http://127.0.0.1:8640
python server.py
pause
