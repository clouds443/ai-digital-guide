@echo off
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
"C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" "D:\AIhumannew\scripts\start_services.py" --profile full
echo.
echo Flask:    http://localhost:8000/
echo Realtime: http://localhost:8010/api/realtime/status
echo TTS:      http://127.0.0.1:9880/control?command=ping
echo.
pause
