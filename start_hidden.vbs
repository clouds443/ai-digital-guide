Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd /c cd /d D:\AIhumannew && set PYTHONUTF8=1 && set PYTHONIOENCODING=utf-8 && python scripts\start_services.py --profile light", 0, False
