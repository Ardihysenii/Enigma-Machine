@echo off
setlocal
cd /d "%~dp0"
title ENIGMA - Local Python Server
if not exist ".venv\Scripts\python.exe" (
  echo ENIGMA's Python environment is missing. See README.md for setup.
  pause
  exit /b 1
)
echo ENIGMA - http://127.0.0.1:5000
echo Keep this window open while using the dashboard.
echo To stop the server, press Ctrl+C.
echo.
".venv\Scripts\python.exe" app.py
echo.
echo The ENIGMA server has stopped.
pause
