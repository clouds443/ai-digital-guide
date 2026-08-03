@echo off
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
"C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" "D:\AIhumannew\scripts\start_services.py" --profile light
echo.
echo Flask:    http://localhost:8000/
echo Realtime: optional, start in Admin service manager
echo TTS:      optional, start in Admin service manager
echo.
pause
