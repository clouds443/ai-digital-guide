# -*- coding: utf-8 -*-
import os
import re
import subprocess
import threading
import uuid

from runtime_paths import asset_path, runtime_path

ROOT_DIR = asset_path()
FRONTEND_DIR = asset_path("frontend")
UPLOAD_DIR = runtime_path("uploads", "voice")
BIN_DIR = asset_path("bin")
RUNTIME_BIN_DIR = runtime_path("bin")
DEFAULT_SENSEVOICE_MODEL = runtime_path("models", "SenseVoiceSmall")

_ASR_MODEL = None
_ASR_LOCK = threading.Lock()
_ASR_ERROR = ""

ASR_HOTWORD_REPLACEMENTS = [
    ("九龙观浴", "九龙灌浴"),
    ("九龙观玉", "九龙灌浴"),
    ("九龙惯浴", "九龙灌浴"),
    ("九龙灌玉", "九龙灌浴"),
    ("灵山饭宫", "灵山梵宫"),
    ("灵山凡宫", "灵山梵宫"),
    ("灵山梵工", "灵山梵宫"),
    ("天下第一章", "天下第一掌"),
    ("天下第1章", "天下第一掌"),
    ("天下第一张", "天下第一掌"),
    ("五知门", "五智门"),
    ("五指门", "五智门"),
    ("无进意斋", "无尽意斋"),
    ("无尽一斋", "无尽意斋"),
    ("五音坛城", "五印坛城"),
    ("满飞龙塔", "曼飞龙塔"),
    ("香符禅寺", "祥符禅寺"),
    ("阿玉王柱", "阿育王柱"),
    ("阿玉王住", "阿育王柱"),
    ("阿玉王注", "阿育王柱"),
    ("阿育王住", "阿育王柱"),
    ("阿育王注", "阿育王柱"),
]

ASR_HOTWORDS = [
    "灵山胜境",
    "灵山大照壁",
    "五明桥",
    "佛足坛",
    "五智门",
    "菩提大道",
    "九龙灌浴",
    "降魔浮雕",
    "阿育王柱",
    "天下第一掌",
    "百子戏弥勒",
    "祥符禅寺",
    "灵山大佛",
    "灵山梵宫",
    "五印坛城",
    "曼飞龙塔",
    "无尽意斋",
]


def asr_hotword_prompt():
    return " ".join(ASR_HOTWORDS)


def ensure_ffmpeg_on_path():
    ffmpeg_target = os.path.join(BIN_DIR, "ffmpeg.exe")
    if not os.path.exists(ffmpeg_target):
        os.makedirs(RUNTIME_BIN_DIR, exist_ok=True)
        ffmpeg_target = os.path.join(RUNTIME_BIN_DIR, "ffmpeg.exe")
    if not os.path.exists(ffmpeg_target):
        try:
            import imageio_ffmpeg
            import shutil

            shutil.copyfile(imageio_ffmpeg.get_ffmpeg_exe(), ffmpeg_target)
        except Exception:
            pass
    if os.path.exists(ffmpeg_target):
        ffmpeg_dir = os.path.dirname(ffmpeg_target)
        path = os.environ.get("PATH", "")
        if ffmpeg_dir.lower() not in path.lower():
            os.environ["PATH"] = ffmpeg_dir + os.pathsep + path


ensure_ffmpeg_on_path()


def _clean_asr_text(text):
    text = re.sub(r"<\|[^>]+?\|>", "", text or "")
    text = text.replace("<|", "").replace("|>", "")
    text = re.sub(r"\s+", "", text).strip()
    return apply_asr_hotword_corrections(text)


def apply_asr_hotword_corrections(text):
    value = str(text or "")
    value = normalize_asr_disfluency(value)
    for wrong, right in ASR_HOTWORD_REPLACEMENTS:
        value = value.replace(wrong, right)
    value = normalize_asr_disfluency(value)
    return value


def normalize_asr_disfluency(text):
    value = str(text or "")
    if not value:
        return ""
    value = re.sub(r"\s+", "", value)
    value = re.sub(r"^(?:开|喂){2,}", "", value)
    value = re.sub(r"^(?:开开开|开开|喂喂喂|喂喂)+", "", value)
    if re.fullmatch(r"(?:百|拜)?拜拜+", value) or value in {"百拜拜", "拜拜拜", "拜拜拜拜"}:
        return "拜拜"
    if "听得见吗" in value and re.fullmatch(r"(?:开|喂)*听得见吗", value):
        return "听得见吗"
    value = value.replace("要为介绍绍一", "要我介绍一下")
    value = value.replace("要为介绍一", "要我介绍一下")
    value = value.replace("要我介绍绍一", "要我介绍一下")
    value = value.replace("介绍绍一", "介绍一下")
    for scenic in ["阿育王柱", "九龙灌浴", "天下第一掌", "五智门", "五印坛城", "灵山梵宫"]:
        value = value.replace(scenic + scenic[-1], scenic)
    return value


def asr_model_path():
    configured = os.getenv("SENSEVOICE_MODEL_DIR", "").strip()
    if configured:
        return configured
    return DEFAULT_SENSEVOICE_MODEL


def asr_status():
    try:
        import importlib.util

        funasr_ok = importlib.util.find_spec("funasr") is not None
        model_path = asr_model_path()
        model_ready = os.path.isdir(model_path) or model_path.startswith("iic/")
        return {
            "ok": bool(funasr_ok and model_ready),
            "provider": "SenseVoice",
            "funasr_installed": funasr_ok,
            "model": model_path,
            "model_ready": model_ready,
            "loaded": _ASR_MODEL is not None,
            "error": _ASR_ERROR,
        }
    except Exception as exc:
        return {
            "ok": False,
            "provider": "SenseVoice",
            "error": str(exc),
        }


def get_asr_model():
    global _ASR_MODEL, _ASR_ERROR
    with _ASR_LOCK:
        if _ASR_MODEL is not None:
            return _ASR_MODEL
        try:
            from funasr import AutoModel

            model_path = asr_model_path()
            if not os.path.isdir(model_path) and not model_path.startswith("iic/"):
                raise RuntimeError("未找到 SenseVoiceSmall 模型目录：" + model_path)
            _ASR_MODEL = AutoModel(model=model_path, trust_remote_code=True)
            _ASR_ERROR = ""
            return _ASR_MODEL
        except Exception as exc:
            _ASR_ERROR = str(exc)
            raise


def save_uploaded_audio(file_storage):
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    ext = os.path.splitext(file_storage.filename or "")[1].lower()
    if ext not in [".wav", ".webm", ".mp3", ".m4a", ".ogg"]:
        ext = ".webm"
    filename = "voice_{0}{1}".format(uuid.uuid4().hex, ext)
    path = os.path.join(UPLOAD_DIR, filename)
    file_storage.save(path)
    return path


def normalize_audio_for_asr(audio_path):
    wav_path = os.path.splitext(audio_path)[0] + "_16k.wav"
    try:
        import imageio_ffmpeg

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        ffmpeg = "ffmpeg"

    cmd = [
        ffmpeg,
        "-y",
        "-i",
        audio_path,
        "-ac",
        "1",
        "-ar",
        "16000",
        "-vn",
        wav_path,
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", "ignore") or "音频转码失败。")
    return wav_path


def transcribe_audio(audio_path):
    model = get_asr_model()
    audio_path = normalize_audio_for_asr(audio_path)
    result = model.generate(
        input=audio_path,
        cache={},
        language="auto",
        use_itn=True,
    )
    text = ""
    if isinstance(result, list) and result:
        text = result[0].get("text", "")
    elif isinstance(result, dict):
        text = result.get("text", "")
    return {
        "ok": bool(_clean_asr_text(text)),
        "text": _clean_asr_text(text),
        "raw": result,
        "provider": "SenseVoice",
    }
