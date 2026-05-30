@echo off
cd /d "%~dp0"
echo.
echo   Astral v0.5 - Multi-Scenario Interactive Novel Engine
echo   3 Scenarios: Sky Maze / Cloud Holiday / Snow Train
echo.
echo   http://127.0.0.1:8640
echo   Click [Exit] in the top bar to shut down.
echo.
start "" http://127.0.0.1:8640
python server.py
exit
