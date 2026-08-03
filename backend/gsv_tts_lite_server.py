# -*- coding: utf-8 -*-
import asyncio
import importlib.util
import json
import os
import shutil
import sys
import threading
import time
import uuid
from functools import partial
from pathlib import Path
from typing import Any, Dict, List


ROOT_DIR = Path(__file__).resolve().parents[1]
FRONTEND_TTS_DIR = ROOT_DIR / "frontend" / "audio" / "tts"


def _env_path(name: str, default: Path) -> Path:
    value = os.getenv(name, "").strip()
    return Path(value) if value else default


OUTPUT_DIR = _env_path("GSV_TTS_LITE_OUTPUT_DIR", FRONTEND_TTS_DIR)
_TTS = None
_LOAD_ERROR = ""
_WARMING = False
_DEVICE_REQUESTED = ""
_EFFECTIVE_DEVICE = ""
_DEVICE_WARNING = ""
_LOAD_LOCK = threading.Lock()
_INFER_LOCK = threading.RLock()


def preload_enabled() -> bool:
    return os.getenv("GSV_TTS_LITE_PRELOAD", "0").strip().lower() in {"1", "true", "yes", "on"}


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _resolve_device(device: str) -> str:
    global _DEVICE_REQUESTED, _EFFECTIVE_DEVICE, _DEVICE_WARNING
    requested = str(device or "").strip()
    _DEVICE_REQUESTED = requested
    _EFFECTIVE_DEVICE = requested
    _DEVICE_WARNING = ""
    if requested.lower().startswith("cuda"):
        try:
            import torch

            if not torch.cuda.is_available():
                _EFFECTIVE_DEVICE = "cpu"
                _DEVICE_WARNING = "CUDA requested but torch.cuda.is_available() is false; falling back to CPU."
                return _EFFECTIVE_DEVICE
        except Exception as exc:
            _EFFECTIVE_DEVICE = "cpu"
            _DEVICE_WARNING = "CUDA requested but torch check failed: {0}; falling back to CPU.".format(exc)
            return _EFFECTIVE_DEVICE
    return requested


def _subtitle_segments(text: str, duration_s: float = 0.0) -> List[Dict[str, Any]]:
    text = str(text or "").strip()
    if not text:
        return []
    duration = max(float(duration_s or 0.0), min(12.0, max(1.2, len(text) / 5.0)))
    return [{"start_s": 0.0, "end_s": round(duration, 2), "text": text}]


def _subtitle_text(item: Dict[str, Any]) -> str:
    return str(item.get("text") or item.get("word") or "").strip()


def _subtitle_start(item: Dict[str, Any]) -> float:
    return float(item.get("start_s", item.get("start", 0)) or 0)


def _subtitle_end(item: Dict[str, Any]) -> float:
    return float(item.get("end_s", item.get("end", 0)) or 0)


def _merge_phrase_subtitles(items: List[Dict[str, Any]], text: str, duration_s: float = 0.0) -> List[Dict[str, Any]]:
    if not items:
        return _subtitle_segments(text, duration_s)
    punctuation = set("。！？!?；;，,：:")
    max_chars = 28
    min_chars = 8
    max_seconds = 4.0
    gap_seconds = 0.45
    merged = []
    current = None

    def flush():
        nonlocal current
        if not current:
            return
        current["text"] = current["text"].strip()
        if current["text"]:
            current["start_s"] = round(current["start_s"], 3)
            current["end_s"] = round(max(current["end_s"], current["start_s"] + 0.1), 3)
            merged.append(current)
        current = None

    for raw in items:
        piece = _subtitle_text(raw)
        if not piece:
            continue
        start = _subtitle_start(raw)
        end = _subtitle_end(raw)
        if current is None:
            current = {"start_s": start, "end_s": end, "text": piece}
            continue
        gap = start - current["end_s"]
        next_text = current["text"] + piece
        too_long = len(next_text) > max_chars
        enough_for_punctuation = len(current["text"]) >= min_chars and current["text"][-1:] in punctuation
        long_duration = end - current["start_s"] > max_seconds
        if gap > gap_seconds or too_long or enough_for_punctuation or long_duration:
            flush()
            current = {"start_s": start, "end_s": end, "text": piece}
        else:
            current["text"] = next_text
            current["end_s"] = end
    flush()

    if len(merged) <= 1 and text:
        return _subtitle_segments(text, duration_s)
    return merged or _subtitle_segments(text, duration_s)


def _coerce_subtitles(raw: Any, text: str, duration_s: float = 0.0) -> List[Dict[str, Any]]:
    if not raw:
        return _subtitle_segments(text, duration_s)
    result = []
    if isinstance(raw, dict):
        raw = raw.get("subtitles") or raw.get("segments") or []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, dict):
            subtitle_text = _subtitle_text(item)
            if not subtitle_text:
                continue
            result.append(
                {
                    "start_s": _subtitle_start(item),
                    "end_s": _subtitle_end(item),
                    "text": subtitle_text,
                }
            )
    return _merge_phrase_subtitles(result, text, duration_s)


def _runtime_identity() -> Dict[str, Any]:
    # Windows venv 的 python.exe 可能是转发启动器，命令行会显示基础解释器；
    # 这里暴露 sys.prefix 和包路径，方便确认实际使用的是项目内虚拟环境。
    def safe_find_spec(name: str):
        try:
            return importlib.util.find_spec(name)
        except Exception:
            return None

    gsv_spec = safe_find_spec("gsv_tts")
    torch_spec = safe_find_spec("torch")
    torch_version = ""
    cuda_available = False
    cuda_device = ""
    if torch_spec:
        try:
            import torch

            torch_version = str(getattr(torch, "__version__", ""))
            cuda_available = bool(torch.cuda.is_available())
            if cuda_available:
                cuda_device = str(torch.cuda.get_device_name(0))
        except Exception:
            pass
    return {
        "python_executable": sys.executable,
        "python_base_executable": str(getattr(sys, "_base_executable", "")),
        "python_prefix": sys.prefix,
        "python_base_prefix": sys.base_prefix,
        "gsv_tts_module": str(gsv_spec.origin) if gsv_spec and gsv_spec.origin else "",
        "torch_module": str(torch_spec.origin) if torch_spec and torch_spec.origin else "",
        "torch_version": torch_version,
        "cuda_available": cuda_available,
        "cuda_device": cuda_device,
    }


def _load_tts():
    global _TTS, _LOAD_ERROR
    if _TTS is not None:
        return _TTS
    with _LOAD_LOCK:
        if _TTS is not None:
            return _TTS
        try:
            from gsv_tts import TTS

            kwargs: Dict[str, Any] = {}
            model_dir = os.getenv("GSV_TTS_LITE_MODEL_DIR", "").strip()
            device = _resolve_device(os.getenv("GSV_TTS_LITE_DEVICE", "").strip())
            if model_dir:
                kwargs["models_dir"] = model_dir
            if device:
                kwargs["device"] = device
            kwargs["auto_bert"] = _env_bool("GSV_TTS_LITE_AUTO_BERT", False)
            kwargs["use_bert"] = _env_bool("GSV_TTS_LITE_USE_BERT", False)
            _TTS = TTS(**kwargs)
            _LOAD_ERROR = ""
            return _TTS
        except Exception as exc:
            _LOAD_ERROR = str(exc)
            raise


def _save_audio_bytes(data: bytes, suffix: str = ".wav") -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / ("gsv_{0}{1}".format(uuid.uuid4().hex, suffix))
    path.write_bytes(data)
    return path


def _new_audio_path(suffix: str = ".wav") -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR / ("gsv_{0}{1}".format(uuid.uuid4().hex, suffix))


def _save_audio_file(path_like: Any) -> Path:
    source = Path(str(path_like))
    if not source.exists():
        raise RuntimeError("GSV-TTS-Lite 返回的音频文件不存在：" + str(source))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    target = OUTPUT_DIR / ("gsv_{0}{1}".format(uuid.uuid4().hex, source.suffix or ".wav"))
    if source.resolve() != target.resolve():
        shutil.copyfile(source, target)
    return target


def _save_audio_clip(clip: Any) -> Path:
    path = _new_audio_path(".wav")
    if hasattr(clip, "save"):
        clip.save(str(path), is_save_subtitles=False)
        return path
    raise RuntimeError("GSV-TTS-Lite 返回的 AudioClip 无法保存。")


def synthesize_with_gsv(payload: Dict[str, Any]) -> Dict[str, Any]:
    text = str(payload.get("text") or "").strip()
    ref_audio_path = str(payload.get("ref_audio_path") or "").strip()
    prompt_text = str(payload.get("prompt_text") or "").strip()
    if not text:
        raise ValueError("text 不能为空。")
    if not ref_audio_path or not Path(ref_audio_path).exists():
        raise ValueError("ref_audio_path 不存在。")
    if not prompt_text:
        raise ValueError("prompt_text 不能为空。")

    tts = _load_tts()
    started_at = time.time()
    kwargs = {
        "spk_audio_path": ref_audio_path,
        "prompt_audio_path": ref_audio_path,
        "prompt_audio_text": prompt_text,
        "text": text,
        "return_subtitles": True,
        "speed": float(payload.get("speed_factor") or payload.get("speed") or 1.0),
        "top_k": int(payload.get("top_k") or 5),
        "top_p": float(payload.get("top_p") or 1.0),
        "temperature": float(payload.get("temperature") or 1.0),
    }

    raw_subtitles = []
    output_path = None
    result = None
    with _INFER_LOCK:
        if hasattr(tts, "infer"):
            result = tts.infer(**kwargs)
            raw_subtitles = getattr(result, "subtitles", []) or []
            output_path = _save_audio_clip(result)
        elif hasattr(tts, "infer_stream"):
            chunks = tts.infer_stream(**kwargs)
            audio_parts = []
            for chunk in chunks:
                if hasattr(chunk, "save"):
                    raw_subtitles = getattr(chunk, "subtitles", []) or raw_subtitles
                    output_path = _save_audio_clip(chunk)
                    continue
                if isinstance(chunk, tuple) and len(chunk) >= 2:
                    audio_parts.append(chunk[0])
                    raw_subtitles = chunk[1] or raw_subtitles
                elif isinstance(chunk, (bytes, bytearray)):
                    audio_parts.append(bytes(chunk))
                elif isinstance(chunk, dict):
                    result = chunk
            if audio_parts:
                output_path = _save_audio_bytes(b"".join(audio_parts))
        if output_path is None:
            if hasattr(tts, "__call__"):
                result = tts(**kwargs)
            else:
                raise RuntimeError("当前 gsv_tts.TTS 未提供 infer 或 infer_stream 方法。")

    if output_path is None:
        if isinstance(result, dict):
            raw_subtitles = result.get("subtitles") or result.get("segments") or raw_subtitles
            if result.get("audio_path"):
                output_path = _save_audio_file(result["audio_path"])
            elif isinstance(result.get("audio"), (bytes, bytearray)):
                output_path = _save_audio_bytes(bytes(result["audio"]))
        elif isinstance(result, (bytes, bytearray)):
            output_path = _save_audio_bytes(bytes(result))
        elif result:
            output_path = _save_audio_file(result)
    if output_path is None:
        raise RuntimeError("GSV-TTS-Lite 未返回可保存的音频。")

    synthesis_seconds = round(time.time() - started_at, 2)
    return {
        "ok": True,
        "audio_path": str(output_path),
        "audio_url": "/audio/tts/" + output_path.name,
        "provider": "gsv_tts_lite",
        "engine": "gsv_tts_lite",
        "subtitles": _coerce_subtitles(raw_subtitles, text, synthesis_seconds),
        "synthesis_seconds": synthesis_seconds,
    }


def _control_payload() -> Dict[str, Any]:
    payload = {
        "ok": True,
        "provider": "gsv_tts_lite",
        "engine": "gsv_tts_lite",
        "loaded": _TTS is not None,
        "warming": _WARMING,
        "preload": preload_enabled(),
        "error": _LOAD_ERROR,
        "device_requested": _DEVICE_REQUESTED,
        "effective_device": _EFFECTIVE_DEVICE,
        "device_warning": _DEVICE_WARNING,
    }
    payload.update(_runtime_identity())
    return payload


async def _run_blocking_synthesis(payload: Dict[str, Any]) -> Dict[str, Any]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, partial(_synthesize_with_gsv_locked, payload))


def _synthesize_with_gsv_locked(payload: Dict[str, Any]) -> Dict[str, Any]:
    with _INFER_LOCK:
        return synthesize_with_gsv(payload)


try:
    from fastapi import FastAPI
    from pydantic import BaseModel

    class TTSRequest(BaseModel):
        text: str
        ref_audio_path: str
        prompt_text: str
        speed_factor: float = 1.0
        top_k: int = 5
        top_p: float = 1.0
        temperature: float = 1.0

    app = FastAPI(title="GSV-TTS-Lite compatible service")

    @app.on_event("startup")
    async def warmup_model():
        global _WARMING
        if preload_enabled():
            _WARMING = True
            try:
                _load_tts()
            except Exception:
                pass
            finally:
                _WARMING = False

    @app.get("/control")
    async def control(command: str = "ping"):
        if command != "ping":
            return {"ok": False, "error": "unsupported command"}
        return _control_payload()

    @app.post("/tts")
    async def api_tts(request: TTSRequest):
        try:
            return await _run_blocking_synthesis(request.dict())
        except Exception as exc:
            return {"ok": False, "provider": "gsv_tts_lite", "engine": "gsv_tts_lite", "error": str(exc)}

except Exception as exc:
    app = None
    _LOAD_ERROR = str(exc)


if __name__ == "__main__":
    if app is None:
        print(json.dumps({"ok": False, "error": _LOAD_ERROR or "fastapi/uvicorn 未安装。"}, ensure_ascii=False))
        raise SystemExit(1)
    import uvicorn

    uvicorn.run(app, host=os.getenv("GSV_TTS_LITE_HOST", "127.0.0.1"), port=int(os.getenv("GSV_TTS_LITE_PORT", "9880")))
