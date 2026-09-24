@echo off
setlocal
cd /d "%~dp0"
title Phira PP Web UI

set PYTHONPATH=.

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] .venv not found. Set it up first:
  echo   python -m venv .venv
  echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
  echo.
  pause
  exit /b 1
)

echo Starting Phira PP web UI ...
echo   - The page opens automatically in your browser: http://127.0.0.1:8000/
echo   - To stop the server: type "off" and press Enter (no confirmation)
echo.

".venv\Scripts\python.exe" scripts\serve.py %*

if errorlevel 1 (
  echo.
  echo [Server did NOT start] See the message above ^(port already in use is the usual cause^).
  echo Close this window when done.
  pause
)
