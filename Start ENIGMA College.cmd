@echo off
setlocal
cd /d "%~dp0"
title ENIGMA - College Security Lab - Port 5002
if not exist ".venv\Scripts\python.exe" (
  echo Python environment missing. See README.md.
  pause
  exit /b 1
)
echo ENIGMA Task 01: http://127.0.0.1:5002/#analysis
echo College dashboard: http://127.0.0.1:5002/college
echo Keep this window open. Press Ctrl+C to stop.
".venv\Scripts\python.exe" -u -c "import app; app.app.run(host='127.0.0.1',port=5002,debug=False)"
echo Server stopped. If port 5002 is already in use, use the existing server.
pause
