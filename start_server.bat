@echo off
echo Starting Lingshan AI Guide Server...
echo.
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d D:\AIhumannew
python scripts\start_services.py --profile light
pause
