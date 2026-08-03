@echo off
setlocal
set "ROOT=D:\AIhumannew"
set "TEMP=%ROOT%\.cache\tmp"
set "TMP=%ROOT%\.cache\tmp"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PATH=%ROOT%\bin;%PATH%"
if not exist "%TEMP%" mkdir "%TEMP%"
set "ENV_FILE=%ROOT%\backend\.env"
if exist "%ENV_FILE%" (
  for /f "usebackq tokens=1,* delims==" %%A in ("%ENV_FILE%") do (
    if /i "%%A"=="GSV_TTS_LITE_PYTHON" set "GSV_TTS_LITE_PYTHON=%%B"
    if /i "%%A"=="GPT_SOVITS_PYTHON" set "GPT_SOVITS_PYTHON=%%B"
  )
)
if "%GSV_TTS_LITE_PYTHON%"=="" (
  if not "%GPT_SOVITS_PYTHON%"=="" set "GSV_TTS_LITE_PYTHON=%GPT_SOVITS_PYTHON%"
)
if "%GSV_TTS_LITE_PYTHON%"=="" (
  echo Please set GSV_TTS_LITE_PYTHON to the python.exe from your GSV-TTS-Lite environment.
  echo Example:
  echo   set GSV_TTS_LITE_PYTHON=D:\AIhumannew\.venvs\gsv-tts-lite\Scripts\python.exe
  echo.
  pause
  exit /b 1
)
if not exist "%ROOT%\backend\gsv_tts_lite_server.py" (
  echo GSV-TTS-Lite wrapper not found at:
  echo   %ROOT%\backend\gsv_tts_lite_server.py
  echo.
  pause
  exit /b 1
)
cd /d "%ROOT%\backend"
echo Starting GSV-TTS-Lite compatible API on http://127.0.0.1:9880 ...
"%GSV_TTS_LITE_PYTHON%" "%ROOT%\backend\gsv_tts_lite_server.py"
pause
