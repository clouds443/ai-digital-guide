@echo off
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
"C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" "D:\AIhumannew\scripts\start_services.py" --profile light
echo.
echo Flask:    http://localhost:8000/
echo Optional services can be started from Admin > Service Management.
echo.
pause
