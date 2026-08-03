# 实时语音导览服务配置

本项目保留 Flask 主站 `http://localhost:8000/`，并新增实时语音服务 `http://localhost:8010/`。

## 启动

```powershell
D:\AIhumannew\start_all_services.bat
```

也可以分别启动：

```powershell
D:\AIhumannew\start_server.bat
D:\AIhumannew\start_realtime_server.bat
```

## Python 依赖

实时服务使用主后端 Python：

```powershell
C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pip install -r D:\AIhumannew\backend\requirements-realtime.txt
```

当前环境需要 FunASR、FastAPI、uvicorn。TTS 使用独立 GPT-SoVITS API，不在实时服务 Python 中加载大模型。

## 模型目录

FunASR 实时 ASR：

```text
D:\AIhumannew\models\FunASR\paraformer-zh-streaming
D:\AIhumannew\models\FunASR\fsmn-vad
D:\AIhumannew\models\FunASR\ct-punc
```

如果不放本地目录，服务会尝试使用 FunASR 的模型别名：

```env
FUNASR_STREAMING_MODEL=paraformer-zh-streaming
FUNASR_VAD_MODEL=fsmn-vad
FUNASR_PUNC_MODEL=ct-punc
```

GPT-SoVITS 独立服务：

```text
http://127.0.0.1:9880
```

可在 `backend\.env` 中配置：

```env
REALTIME_TTS_PROVIDER=gpt_sovits
GPT_SOVITS_API_URL=http://127.0.0.1:9880
GPT_SOVITS_TEXT_LANG=zh
GPT_SOVITS_PROMPT_LANG=zh
REALTIME_LLM_PROVIDER=deepseek
REALTIME_LLM_MODEL=deepseek-chat
REALTIME_PORT=8010
```

## 验证

```text
http://localhost:8010/api/realtime/status
```

重点检查：

- `asr.funasr_installed=true`
- `llm.configured=true`
- `tts.gpt_sovits_api_ready=true`，未启动 GPT-SoVITS 时可临时依赖 `tts.edge_available=true` 兜底

前端麦克风按钮会优先连接 `ws://localhost:8010/ws/realtime-guide`。连接失败时会退回原来的普通录音模式。
