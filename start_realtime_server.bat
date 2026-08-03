@echo off
cd /d D:\AIhumannew\backend
echo Starting Lingshan realtime voice service on http://localhost:8010 ...
echo.
set FUNASR_STREAMING_MODEL_DIR=D:\AIhumannew\models\FunASR\paraformer-zh-streaming
set FUNASR_VAD_MODEL_DIR=D:\AIhumannew\models\FunASR\fsmn-vad
set FUNASR_PUNC_MODEL_DIR=D:\AIhumannew\models\FunASR\ct-punc
set FUNASR_DEVICE=cuda:0
set REALTIME_SILENCE_END_MS=800
set REALTIME_MIN_SPEECH_MS=500
set REALTIME_MAX_LISTEN_MS=15000
"C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" realtime_server.py
pause
