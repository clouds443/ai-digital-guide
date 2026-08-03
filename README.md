# 灵山胜境 AI 数字人导游系统

<img width="1848" height="908" alt="屏幕截图 2026-07-20 114522" src="https://github.com/user-attachments/assets/448305bc-c077-4da8-9ec8-48e67a3ce269" />

本项目是基于live2d模型的AI 数字人导游系统，包含游客交互端、管理员后台、RAG本地知识库、Live2D数字人驱动、语音识别与语音合成服务。

## 功能范围

- 游客端：Live2D 数字人展示、文本问答、语音输入、快捷问题、兴趣标签、路线推荐、语音播报、音频能量口型同步、语义情绪表情联动。
- 管理端：知识库增删改查、Word/PDF 上传解析、数字人模型/音色/服装/欢迎语配置、语音克隆管理、服务管理、反馈管理、运营数据看板。
- AI 底座：DeepSeek/OpenAI 兼容 LLM、本地 RAG 兜底、FunASR 实时语音识别、Edge-TTS 稳定兜底、GSV-TTS-Lite 可选低延迟克隆音色增强。
- 交付目标：单景区“灵山胜境”演示，文本交互 5 秒内响应，事实问答通过本地评测集覆盖门票、开放时间、交通、景点、演出、路线和餐饮等高频问题。

## 快速启动

1. 配置 `backend/.env`。可参考 `backend/.env.example`，至少确认 MySQL 连接信息；如不配置 LLM Key，系统会使用本地 RAG 与规则兜底。
2. 运行轻量演示模式：

```bat
start_light.bat
```

3. 打开游客端与管理端入口：

```text
http://localhost:8000/
```

4. 如需启动实时语音与 GSV-TTS-Lite 全量模式：

```bat
start_full_services.bat
```

轻量模式只启动 Flask 主服务，实时语音与 GSV-TTS-Lite 可在管理端“服务管理”中按需启动。

## 可选服务环境

服务管理页会先检查运行环境。若显示“环境未就绪”，按钮会禁用并给出安装提示，避免服务窗口闪退。

GSV-TTS-Lite 克隆音色服务需要单独安装 Python 环境。项目仍保留 `voice_provider=gpt_sovits` 作为兼容配置值，后台展示为 “GSV-TTS-Lite 克隆音色”：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_gsv_tts_lite_env.ps1 -Device CPU
```

RTX 4060 等 NVIDIA 显卡建议使用 CUDA 12.6 版 PyTorch：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_gsv_tts_lite_env.ps1 -Device CU126
```

如果在线下载 PyTorch 大包中断，可先把 `torch-*+cu126-cp*-win_amd64.whl` 和 `torchaudio-*+cu126-cp*-win_amd64.whl` 放到 `D:\AIhumannew\wheelhouse`，安装脚本会优先使用本地 wheel，再回退到 PyTorch 官方源。

实时语音服务需要在主后端使用的 Python 环境中安装依赖：

```powershell
python -m pip install -r backend\requirements-realtime.txt
```

依赖安装完成后，回到管理端“服务管理”点击“重新读取”，状态变为可启动后再启动服务。

## 演示账号

- 普通游客：`user` / `user123456`
- 管理员：`admin` / `admin123456`

账号初始化依赖 MySQL，默认数据库为 `aidigitalhuman`，字符集为 `utf8mb4`。

## 主要接口

- 游客接口：`POST /api/chat`、`POST /api/voice`、`POST /api/voice/realtime`、`GET /api/scenics`、`GET /api/scenic/<id>`、`GET /api/routes`、`GET /api/config`、`POST /api/feedback`
- 管理接口：`POST /api/auth/login`、`GET /api/auth/me`、`GET/POST /api/admin/knowledge`、`POST /api/admin/knowledge/upload`、`DELETE /api/admin/knowledge/<id>`、`GET/POST /api/admin/config`、`GET /api/analytics`、`GET/POST /api/admin/voice-clones`、`GET/POST /api/admin/services/*`

聊天接口返回 `answer`、`emotion`、`route_suggestion`、`sources`、`latency_ms`；语音接口额外返回 `audio_url` 与 `tts` 状态，用于前端驱动表情、口型和性能展示。

## 验证命令

```powershell
chcp 65001
[Console]::OutputEncoding=[System.Text.Encoding]::UTF8
$OutputEncoding=[System.Text.Encoding]::UTF8
python -m unittest discover -s tests -v
```

如需单独验证重点契约：

```powershell
python -m unittest tests.test_rag_metadata tests.test_api_contract tests.test_frontend_contract tests.test_config_contract tests.test_delivery_contract -v
```

