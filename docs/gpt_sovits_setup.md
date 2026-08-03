# GPT-SoVITS TTS Setup

The digital human project now uses GPT-SoVITS for voice cloning and speech
synthesis. Flask and the realtime service do not import GPT-SoVITS directly;
they call a separate GPT-SoVITS API service.

## Repository Location

Clone GPT-SoVITS here:

```powershell
git clone https://github.com/RVC-Boss/GPT-SoVITS.git D:\AIhumannew\third_party\GPT-SoVITS
```

Install GPT-SoVITS in its own Python environment. Do not install its heavy model
dependencies into the main Flask Python 3.12 environment.

The current project is configured to use:

```text
D:\AIhumannew\.venvs\gpt-sovits\Scripts\python.exe
```

This is written in `backend\.env` as:

```env
GPT_SOVITS_PYTHON=D:\AIhumannew\.venvs\gpt-sovits\Scripts\python.exe
```

The CUDA PyTorch wheels in `D:\AIhumannew\wheels` have been installed into
that environment:

```text
torch==2.3.1+cu118
torchvision==0.18.1+cu118
torchaudio==2.3.1+cu118
```

Official Windows environment setup from the cloned repo:

```powershell
conda create -n GPTSoVits python=3.10 -y
conda activate GPTSoVits
cd /d D:\AIhumannew\third_party\GPT-SoVITS
powershell -ExecutionPolicy Bypass -File install.ps1 -Device CU126 -Source ModelScope
```

For CPU-only fallback, use `-Device CPU`. For CUDA 12.8, use `-Device CU128`.

## API Service

Start GPT-SoVITS API v2 on port `9880`. The project expects:

```text
GPT_SOVITS_API_URL=http://127.0.0.1:9880
```

After placing the pretrained models, verify assets:

```powershell
powershell -ExecutionPolicy Bypass -File D:\AIhumannew\scripts\check_gpt_sovits_assets.ps1
```

You can also try the project helper script:

```powershell
powershell -ExecutionPolicy Bypass -File D:\AIhumannew\scripts\download_gpt_sovits_assets.ps1 -Source ModelScope
```

If ModelScope is slow or blocked, try `-Source HF-Mirror` or `-Source HF`.

Then start the API:

```powershell
D:\AIhumannew\start_gpt_sovits_api.bat
```

`start_gpt_sovits_api.bat` will read `GPT_SOVITS_PYTHON` from
`backend\.env`, and falls back to `D:\Anaconda\envs\GPTSoVits\python.exe`.

The backend calls:

```text
POST /tts
```

with JSON fields compatible with GPT-SoVITS `api_v2.py`, including:

- `text`
- `text_lang`
- `ref_audio_path`
- `prompt_lang`
- `prompt_text`
- `media_type=wav`

The checked-in GPT-SoVITS repo does not include large pretrained weights. Place
the official pretrained models under:

```text
D:\AIhumannew\third_party\GPT-SoVITS\GPT_SoVITS\pretrained_models
```

For the default v2 config, these paths must exist:

```text
D:\AIhumannew\third_party\GPT-SoVITS\GPT_SoVITS\pretrained_models\chinese-roberta-wwm-ext-large
D:\AIhumannew\third_party\GPT-SoVITS\GPT_SoVITS\pretrained_models\chinese-hubert-base
D:\AIhumannew\third_party\GPT-SoVITS\GPT_SoVITS\pretrained_models\gsv-v2final-pretrained\s1bert25hz-5kh-longer-epoch=12-step=369668.ckpt
D:\AIhumannew\third_party\GPT-SoVITS\GPT_SoVITS\pretrained_models\gsv-v2final-pretrained\s2G2333k.pth
D:\AIhumannew\third_party\GPT-SoVITS\GPT_SoVITS\text\G2PWModel
```

Official model source:

- https://huggingface.co/lj1995/GPT-SoVITS
- https://huggingface.co/XXXXRT/GPT-SoVITS-Pretrained
- https://www.modelscope.cn/models/XXXXRT/GPT-SoVITS-Pretrained
- https://huggingface.co/hfl/chinese-roberta-wwm-ext-large
- https://huggingface.co/lj1995/GPT-SoVITS/tree/main/gsv-v2final-pretrained

For Chinese TTS, also download `G2PWModel.zip`, unzip it as `G2PWModel`, and
place it under:

```text
D:\AIhumannew\third_party\GPT-SoVITS\GPT_SoVITS\text\G2PWModel
```

## Voice Clone Flow

1. Log in as admin.
2. Open `音色克隆`.
3. Upload a clean 10-20 second reference audio file.
4. Fill in the exact text spoken in that audio.
5. Select `GPT-SoVITS 克隆音色`.
6. Click `试听音色`.

If GPT-SoVITS API is not running, the system falls back to Edge-TTS for playback
and reports the GPT-SoVITS error in the UI.

## Current Project Env

`D:\AIhumannew\backend\.env` already contains:

```env
OPEN_SOURCE_TTS_PROVIDER=gpt_sovits
REALTIME_TTS_PROVIDER=gpt_sovits
GPT_SOVITS_API_URL=http://127.0.0.1:9880
GPT_SOVITS_TEXT_LANG=zh
GPT_SOVITS_PROMPT_LANG=zh
GPT_SOVITS_TIMEOUT_SECONDS=120
```
