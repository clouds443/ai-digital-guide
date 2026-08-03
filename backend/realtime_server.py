# -*- coding: utf-8 -*-
import asyncio
import base64
import json
import os
import re
import sys
import time
import traceback
from functools import partial
from typing import AsyncGenerator, Dict, List, Optional
from urllib.request import Request, urlopen


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BACKEND_DIR, ".env")

if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from knowledge_base import DEFAULT_DOCS_DIR, get_digital_human_config, init_knowledge_base  # noqa: E402
from rag_service import EMOTION_LABELS, RAGService, classify_emotion, classify_turn_emotion  # noqa: E402
from asr_service import apply_asr_hotword_corrections, asr_hotword_prompt  # noqa: E402
from asr_correction_service import correct_asr_text  # noqa: E402
from tts_service import synthesize_speech, tts_status  # noqa: E402


def load_env() -> None:
    if not os.path.exists(ENV_PATH):
        return
    with open(ENV_PATH, encoding="utf-8") as env_file:
        for raw in env_file:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env()
init_knowledge_base(DEFAULT_DOCS_DIR)
rag = RAGService()


def import_status(name: str) -> bool:
    try:
        import importlib.util

        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


async def run_blocking(func, *args, **kwargs):
    if hasattr(asyncio, "to_thread"):
        return await asyncio.to_thread(func, *args, **kwargs)
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, partial(func, *args, **kwargs))


async def correct_realtime_asr_query(query: str, history: Optional[List[Dict]] = None) -> Dict:
    result = await run_blocking(correct_asr_text, query, history=history or [], realtime=True)
    text = str(result.get("text") or query or "").strip()
    result["text"] = text
    result.setdefault("corrected_text", text)
    result["correction_required"] = True
    result["correction_failed"] = bool(result.get("correction_error")) and not (
        result.get("llm_corrected") or result.get("leading_noise_removed")
    )
    return {"text": text, "asr": result}


def runtime_python() -> str:
    return sys.executable


def model_path_from_env(env_name: str, default: str) -> str:
    value = os.getenv(env_name, "").strip()
    return value or default


FUNASR_ROOT = os.path.join(ROOT_DIR, "models", "FunASR")
DEFAULT_FUNASR_MODEL = os.path.join(FUNASR_ROOT, "paraformer-zh-streaming")
DEFAULT_FUNASR_VAD = os.path.join(FUNASR_ROOT, "fsmn-vad")
DEFAULT_FUNASR_PUNC = os.path.join(FUNASR_ROOT, "ct-punc")
DEFAULT_GPT_SOVITS_API_URL = "http://127.0.0.1:9880"


def funasr_model_name() -> str:
    local_model = model_path_from_env("FUNASR_STREAMING_MODEL_DIR", DEFAULT_FUNASR_MODEL)
    if os.path.isdir(local_model):
        return local_model
    return os.getenv("FUNASR_STREAMING_MODEL", "paraformer-zh-streaming").strip()


def funasr_vad_name() -> str:
    value = model_path_from_env("FUNASR_VAD_MODEL_DIR", DEFAULT_FUNASR_VAD)
    if os.path.isdir(value):
        return value
    return os.getenv("FUNASR_VAD_MODEL", "fsmn-vad").strip()


def funasr_punc_name() -> str:
    value = model_path_from_env("FUNASR_PUNC_MODEL_DIR", DEFAULT_FUNASR_PUNC)
    if os.path.isdir(value):
        return value
    return os.getenv("FUNASR_PUNC_MODEL", "ct-punc").strip()


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(float(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


def requested_funasr_device() -> str:
    return os.getenv("FUNASR_DEVICE", "cuda:0").strip() or "cuda:0"


def resolve_funasr_device() -> Dict:
    requested = requested_funasr_device()
    if not requested.lower().startswith("cuda"):
        return {
            "requested": requested,
            "selected": requested,
            "cuda_available": False,
            "fallback_reason": "",
        }
    try:
        import torch

        cuda_available = bool(torch.cuda.is_available())
    except Exception as exc:
        return {
            "requested": requested,
            "selected": "cpu",
            "cuda_available": False,
            "fallback_reason": "PyTorch CUDA 检测失败，已回退 CPU：" + str(exc),
        }
    if cuda_available:
        return {
            "requested": requested,
            "selected": requested,
            "cuda_available": True,
            "fallback_reason": "",
        }
    return {
        "requested": requested,
        "selected": "cpu",
        "cuda_available": False,
        "fallback_reason": "当前 Python 环境未检测到 CUDA，已回退 CPU。",
    }


def selected_funasr_device() -> str:
    return str(resolve_funasr_device()["selected"])


def realtime_silence_ms() -> int:
    return max(200, _env_int("REALTIME_SILENCE_END_MS", 600))


def realtime_min_speech_ms() -> int:
    return max(100, _env_int("REALTIME_MIN_SPEECH_MS", 300))


def realtime_max_listen_ms() -> int:
    return max(1000, _env_int("REALTIME_MAX_LISTEN_MS", 15000))


def realtime_silence_rms_threshold() -> float:
    return max(0.001, _env_float("REALTIME_SILENCE_RMS_THRESHOLD", 0.012))


def realtime_speech_rms_threshold() -> float:
    return max(realtime_silence_rms_threshold(), _env_float("REALTIME_SPEECH_RMS_THRESHOLD", 0.025))


def realtime_partial_interval_ms() -> int:
    return max(500, _env_int("REALTIME_PARTIAL_INTERVAL_MS", 1000))


def realtime_final_fast_mode() -> bool:
    value = os.getenv("REALTIME_FINAL_FAST_MODE", "1").strip().lower()
    return value not in {"0", "false", "no", "off"}


def pcm16_stats(audio_bytes: bytes) -> Dict:
    import math

    sample_count = len(audio_bytes) // 2
    if sample_count <= 0:
        return {"samples": 0, "duration_ms": 0.0, "rms": 0.0, "is_above_silence": False, "is_speech": False}
    view = memoryview(audio_bytes)[: sample_count * 2]
    total = 0.0
    for index in range(0, len(view), 2):
        value = int.from_bytes(view[index : index + 2], "little", signed=True) / 32768.0
        total += value * value
    rms = math.sqrt(total / sample_count)
    return {
        "samples": sample_count,
        "duration_ms": sample_count / 16.0,
        "rms": rms,
        "is_above_silence": rms >= realtime_silence_rms_threshold(),
        "is_speech": rms >= realtime_speech_rms_threshold(),
    }


class FunASRStreamingRecognizer:
    _model = None
    _punc_model = None
    _load_error = ""
    _warming = False
    _warm_error = ""
    _lock = asyncio.Lock()

    @classmethod
    def status(cls) -> Dict:
        installed = import_status("funasr")
        model = funasr_model_name()
        vad = funasr_vad_name()
        punc = funasr_punc_name()
        model_is_local = os.path.isdir(model)
        vad_is_local = os.path.isdir(vad)
        punc_is_local = os.path.isdir(punc)
        device = resolve_funasr_device()
        ready = bool(installed and model_is_local and vad_is_local and punc_is_local and not cls._load_error)
        return {
            "ok": ready,
            "ready": ready,
            "provider": "FunASR",
            "python": runtime_python(),
            "funasr_installed": installed,
            "model": model,
            "model_local": model_is_local,
            "vad_model": vad,
            "vad_model_local": vad_is_local,
            "punc_model": punc,
            "punc_model_local": punc_is_local,
            "requested_device": device["requested"],
            "device": device["selected"],
            "cuda_available": device["cuda_available"],
            "device_fallback_reason": device["fallback_reason"],
            "silence_end_ms": realtime_silence_ms(),
            "min_speech_ms": realtime_min_speech_ms(),
            "max_listen_ms": realtime_max_listen_ms(),
            "silence_rms_threshold": realtime_silence_rms_threshold(),
            "speech_rms_threshold": realtime_speech_rms_threshold(),
            "partial_interval_ms": realtime_partial_interval_ms(),
            "final_fast_mode": realtime_final_fast_mode(),
            "warming": cls._warming,
            "loaded": cls._model is not None,
            "error": cls._load_error or cls._warm_error,
            "hint": ""
            if ready
            else (
                "请先下载 FunASR 流式模型、VAD 和标点模型到 D:\\AIhumannew\\models\\FunASR。"
                if installed
                else "Install FunASR in the realtime Python environment."
            ),
        }

    @classmethod
    async def load_model(cls):
        async with cls._lock:
            if cls._model is not None:
                return cls._model
            try:
                cls._warming = True
                from funasr import AutoModel

                kwargs = {
                    "model": funasr_model_name(),
                    "disable_update": True,
                    "device": selected_funasr_device(),
                }
                cls._model = await run_blocking(AutoModel, **kwargs)
                cls._load_error = ""
                cls._warm_error = ""
                return cls._model
            except Exception as exc:
                cls._load_error = str(exc)
                raise
            finally:
                cls._warming = False

    @classmethod
    async def warmup(cls):
        if cls._model is not None or cls._warming:
            return
        try:
            await cls.load_model()
        except Exception as exc:
            cls._warm_error = str(exc)

    @classmethod
    async def load_punc_model(cls):
        if cls._punc_model is not None:
            return cls._punc_model
        try:
            from funasr import AutoModel

            cls._punc_model = await run_blocking(
                AutoModel,
                model=funasr_punc_name(),
                disable_update=True,
                device=selected_funasr_device(),
            )
            return cls._punc_model
        except Exception:
            return None

    def __init__(self):
        self.cache: Dict = {}
        self.full_text = ""
        self.last_text = ""
        self.chunk_size = [0, 10, 5]
        self.encoder_chunk_look_back = 4
        self.decoder_chunk_look_back = 1

    @staticmethod
    def _pcm16_to_float32(audio_bytes: bytes):
        import numpy as np

        if not audio_bytes:
            return np.zeros((0,), dtype="float32")
        pcm = np.frombuffer(audio_bytes, dtype="<i2")
        return pcm.astype("float32") / 32768.0

    @staticmethod
    def _extract_text(result) -> str:
        if isinstance(result, list) and result:
            return str(result[0].get("text") or "").strip()
        if isinstance(result, dict):
            return str(result.get("text") or "").strip()
        return ""

    async def feed(self, audio_bytes: bytes, is_final: bool = False) -> str:
        model = await self.load_model()
        audio = self._pcm16_to_float32(audio_bytes)
        if audio.size == 0 and not is_final:
            return self.last_text

        def _generate():
            return model.generate(
                input=audio,
                cache=self.cache,
                is_final=is_final,
                chunk_size=self.chunk_size,
                encoder_chunk_look_back=self.encoder_chunk_look_back,
                decoder_chunk_look_back=self.decoder_chunk_look_back,
                hotword=asr_hotword_prompt(),
            )

        result = await run_blocking(_generate)
        text = self._extract_text(result)
        if text:
            self.last_text = text
        return self.last_text

    async def finalize(self, audio_bytes: bytes) -> str:
        text = await self.feed(audio_bytes, is_final=True)
        text = self.clean_text(text)
        if text and not realtime_final_fast_mode():
            punc = await self.add_punctuation(text)
            return punc or text
        return text

    @staticmethod
    def clean_text(text: str) -> str:
        text = re.sub(r"<\|[^>]+?\|>", "", text or "")
        text = re.sub(r"\s+", "", text)
        return apply_asr_hotword_corrections(text.strip())

    @classmethod
    async def add_punctuation(cls, text: str) -> str:
        model = await cls.load_punc_model()
        if model is None or not text:
            return text

        def _generate():
            return model.generate(input=text)

        try:
            result = await run_blocking(_generate)
            punctuated = cls._extract_text(result)
            return punctuated or text
        except Exception:
            return text


class LLMGateway:
    def __init__(self):
        self.provider = os.getenv("REALTIME_LLM_PROVIDER", "deepseek").strip().lower()
        self.api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY", "")
        self.api_base = os.getenv("REALTIME_LLM_BASE_URL") or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        self.model = os.getenv("REALTIME_LLM_MODEL") or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    def status(self) -> Dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "base_url": self.api_base,
            "configured": bool(self.api_key and len(self.api_key) > 12),
        }

    async def stream_answer(self, query: str, history: Optional[List[Dict]] = None, interest: str = "") -> AsyncGenerator[str, None]:
        if self.provider in {"deepseek", "openai_compatible", "vllm", "astrbot_proxy"} and self.api_key:
            async for delta in self._stream_openai_compatible(query, history or [], interest):
                yield delta
            return
        answer = await run_blocking(rag.chat, query, history or [], interest)
        for part in split_text_for_stream(answer):
            yield part
            await asyncio.sleep(0.015)

    async def _stream_openai_compatible(self, query: str, history: List[Dict], interest: str) -> AsyncGenerator[str, None]:
        context = rag.kb.get_context_string(query, n_results=8)
        config = get_digital_human_config()
        system_prompt = (
            "你是{0}，灵山胜境景区AI数字人导游。用中文回答，语气{1}。"
            "必须基于知识库回答，可以合理提炼，但不要编造。"
            "实时语音模式下回答要先给结论，再给关键提醒，控制在120字左右。"
        ).format(config.get("name", "灵小境"), config.get("style", "温和、专业"))
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history[-6:])
        if interest:
            messages.append({"role": "system", "content": "游客兴趣偏好：" + str(interest)})
        if context:
            messages.append({"role": "system", "content": "知识库片段：\n" + context[:3500]})
        messages.append({"role": "user", "content": query})

        body = json.dumps(
            {
                "model": self.model,
                "messages": messages,
                "temperature": 0.45,
                "max_tokens": 420,
                "stream": True,
            }
        ).encode("utf-8")
        req = Request(
            self.api_base.rstrip("/") + "/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + self.api_key.strip(),
            },
        )

        try:
            response = await run_blocking(urlopen, req, timeout=45)
            while True:
                line = await run_blocking(response.readline)
                if not line:
                    break
                text = line.decode("utf-8", "ignore").strip()
                if not text.startswith("data:"):
                    continue
                payload = text[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    data = json.loads(payload)
                    delta = data["choices"][0].get("delta", {}).get("content", "")
                except Exception:
                    delta = ""
                if delta:
                    yield delta
        except Exception:
            answer = await run_blocking(rag.chat, query, history, interest)
            for part in split_text_for_stream(answer):
                yield part


def split_text_for_stream(text: str) -> List[str]:
    text = str(text or "")
    if not text:
        return []
    return [text[i : i + 12] for i in range(0, len(text), 12)]


def sentence_chunks(text: str) -> List[str]:
    pieces = [p.strip() for p in re.split(r"(?<=[。！？!?；;])", text or "") if p.strip()]
    if not pieces and text.strip():
        pieces = [text.strip()]
    return pieces


def public_realtime_sources(query: str) -> List[Dict]:
    sources = rag.kb.search(query or "", n_results=5)
    result = []
    for item in sources[:5]:
        result.append(
            {
                "id": item.get("id", ""),
                "title": item.get("title") or item.get("source", ""),
                "source": item.get("source", ""),
                "excerpt": item.get("excerpt", ""),
                "score": item.get("score", 0),
            }
        )
    return result


def build_realtime_done_event(
    query: str,
    answer: str,
    started_at: float,
    finished_at: Optional[float] = None,
    interrupted: bool = False,
    reason: str = "",
    continue_listening: bool = False,
) -> Dict:
    emotion = classify_turn_emotion(query or "", answer or "")
    finished = time.time() if finished_at is None else finished_at
    latency_ms = max(0, int((finished - started_at) * 1000))
    return {
        "type": "done",
        "query": query,
        "answer": answer,
        "emotion": emotion,
        "emotion_label": EMOTION_LABELS.get(emotion, "自然"),
        "sources": public_realtime_sources(query),
        "latency_ms": latency_ms,
        "interrupted": interrupted,
        "reason": reason,
        "continue_listening": bool(continue_listening),
        "next_state": "listening" if continue_listening else "closed",
    }


def build_realtime_turn_cancelled_event(reason: str = "barge_in") -> Dict:
    return {
        "type": "turn_cancelled",
        "reason": reason or "barge_in",
        "continue_listening": True,
        "next_state": "listening",
    }


def decode_realtime_audio_frame(value: str) -> bytes:
    if not value:
        return b""
    try:
        return base64.b64decode(str(value), validate=True)
    except Exception:
        return b""


def _realtime_segment_emotion(query: str, answer_so_far: str, sentence: str) -> str:
    return classify_turn_emotion(query or "", "{0}\n{1}".format(answer_so_far or "", sentence or ""))


def build_realtime_tts_start_event(query: str, answer_so_far: str, sentence: str) -> Dict:
    emotion = _realtime_segment_emotion(query, answer_so_far, sentence)
    return {
        "type": "tts_start",
        "text": sentence,
        "emotion": emotion,
        "emotion_label": EMOTION_LABELS.get(emotion, "自然"),
    }


def build_realtime_audio_chunk_event(sentence: str, emotion: str, result: Dict) -> Dict:
    emotion = emotion or "neutral"
    return {
        "type": "audio_chunk",
        "format": "url",
        "audio_url": result.get("audio_url"),
        "text": sentence,
        "emotion": emotion,
        "emotion_label": EMOTION_LABELS.get(emotion, "自然"),
        "tts": {k: v for k, v in result.items() if k not in {"worker"}},
    }


class PartialRecognitionScheduler:
    def __init__(self, interval_ms=None):
        self.interval_ms = int(interval_ms if interval_ms is not None else realtime_partial_interval_ms())
        self.last_run_ms = 0.0
        self.running = False

    async def maybe_recognize(self, now_ms, recognize):
        if self.running:
            return None
        if self.last_run_ms and now_ms - self.last_run_ms < self.interval_ms:
            return None
        self.running = True
        self.last_run_ms = now_ms
        try:
            return await recognize()
        finally:
            self.running = False

    def schedule(self, now_ms, recognize, on_result, on_error):
        if self.running:
            return False
        if self.last_run_ms and now_ms - self.last_run_ms < self.interval_ms:
            return False
        self.running = True
        self.last_run_ms = now_ms

        async def runner():
            try:
                text = await recognize()
                if text:
                    await on_result(text)
            except Exception as exc:
                await on_error(exc)
            finally:
                self.running = False

        asyncio.ensure_future(runner())
        return True


class RealtimeTTS:
    def __init__(self):
        self.provider = os.getenv("REALTIME_TTS_PROVIDER", "gpt_sovits").strip().lower()
        if self.provider in {"gptsovits", "gpt-sovits", "sovits"}:
            self.provider = "gpt_sovits"

    def status(self) -> Dict:
        edge_available = import_status("edge_tts")
        base = {
            "provider": self.provider,
            "gpt_sovits_api_url": os.getenv("GPT_SOVITS_API_URL", DEFAULT_GPT_SOVITS_API_URL),
            "gpt_sovits_api_ready": False,
            "engine": "gsv_tts_lite" if self.provider == "gpt_sovits" else self.provider,
            "gsv_tts_lite": {
                "provider": "gsv_tts_lite",
                "api_url": os.getenv("GSV_TTS_LITE_API_URL") or os.getenv("GPT_SOVITS_API_URL", DEFAULT_GPT_SOVITS_API_URL),
                "hint": "实时服务状态接口使用轻量检查，不探测 GSV-TTS-Lite；合成时会按需调用。",
            },
            "gpt_sovits": {
                "provider": "gpt_sovits",
                "engine": "gsv_tts_lite",
                "api_url": os.getenv("GPT_SOVITS_API_URL", DEFAULT_GPT_SOVITS_API_URL),
                "hint": "旧配置值 gpt_sovits 仅用于兼容，实际引擎为 GSV-TTS-Lite。",
            },
            "edge_available": edge_available,
            "lightweight_status": True,
        }
        base["ok"] = bool(edge_available or self.provider == "gpt_sovits")
        return base

    async def synthesize_url(self, text: str) -> Dict:
        config = dict(get_digital_human_config())
        if self.provider in {"gpt_sovits", "edge"}:
            config["voice_provider"] = self.provider
        else:
            config["voice_provider"] = "gpt_sovits"

        result = await run_blocking(synthesize_speech, text, config)
        allow_edge_fallback = str(os.getenv("GPT_SOVITS_ALLOW_EDGE_FALLBACK", "false")).strip().lower() in {"1", "true", "yes", "on"}
        if allow_edge_fallback and not result.get("ok") and config.get("voice_provider") != "edge":
            fallback = dict(config)
            fallback["voice_provider"] = "edge"
            edge = await run_blocking(synthesize_speech, text, fallback)
            if edge.get("ok"):
                edge["fallback_provider"] = "edge"
                edge["primary_error"] = result.get("error", "")
                return edge
        return result


llm_gateway = LLMGateway()
tts_gateway = RealtimeTTS()


def realtime_status() -> Dict:
    return {
        "ok": True,
        "service": "lingshan-realtime-guide",
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "python": runtime_python(),
        "fastapi": import_status("fastapi"),
        "pipecat": import_status("pipecat"),
        "asr": FunASRStreamingRecognizer.status(),
        "llm": llm_gateway.status(),
        "tts": tts_gateway.status(),
        "protocol": {
            "sample_rate": 16000,
            "channels": 1,
            "format": "pcm_s16le",
            "client_events": ["start", "audio(binary)", "stop", "interrupt", "end_session", "barge_in"],
            "server_events": ["ready", "listening", "asr_partial", "speech_end", "asr_final", "llm_delta", "tts_start", "audio_chunk", "done", "turn_cancelled", "error"],
            "continuous_mode": True,
            "barge_in_supported": True,
            "asr_correction_required": True,
            "asr_correction_uses_deepseek": True,
        },
    }


try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI(title="Lingshan realtime guide")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def warmup_realtime_asr():
        asyncio.create_task(FunASRStreamingRecognizer.warmup())

    @app.get("/api/realtime/status")
    async def api_realtime_status():
        return realtime_status()

    @app.websocket("/ws/realtime-guide")
    async def websocket_realtime_guide(websocket: WebSocket):
        await websocket.accept()
        session = FunASRStreamingRecognizer()
        audio_parts: List[bytes] = []
        history: List[Dict] = []
        interest = ""
        interrupted = False
        session_active = False
        continuous_mode = False
        answer_task: Optional[asyncio.Task] = None
        turn_finalizing = False
        speech_ms = 0.0
        silence_ms = 0.0
        total_audio_ms = 0.0
        has_speech = False
        partial_scheduler = PartialRecognitionScheduler()
        send_lock = asyncio.Lock()

        async def send(event: Dict):
            async with send_lock:
                await websocket.send_text(json.dumps(event, ensure_ascii=False))

        async def send_listening() -> None:
            await send({
                "type": "listening",
                "sample_rate": 16000,
                "silence_end_ms": realtime_silence_ms(),
                "min_speech_ms": realtime_min_speech_ms(),
                "max_listen_ms": realtime_max_listen_ms(),
                "speech_rms_threshold": realtime_speech_rms_threshold(),
                "partial_interval_ms": realtime_partial_interval_ms(),
            })

        async def reset_turn_state(reset_session: bool = False) -> None:
            nonlocal audio_parts, speech_ms, silence_ms, total_audio_ms, has_speech, turn_finalizing, session, partial_scheduler
            audio_parts = []
            speech_ms = 0.0
            silence_ms = 0.0
            total_audio_ms = 0.0
            has_speech = False
            turn_finalizing = False
            if reset_session:
                session = FunASRStreamingRecognizer()
                partial_scheduler = PartialRecognitionScheduler()

        async def finalize_turn(reason: str, continue_listening: bool = False) -> None:
            nonlocal audio_parts, interrupted, turn_finalizing, speech_ms, silence_ms, total_audio_ms, has_speech
            if turn_finalizing:
                return
            turn_finalizing = True
            audio = b"".join(audio_parts)
            audio_parts = []
            if not audio:
                await send({"type": "error", "stage": "asr", "error": "No audio was received.", "reason": reason})
                turn_finalizing = False
                return

            try:
                query = await session.finalize(audio)
            except Exception as exc:
                await send({"type": "error", "stage": "asr", "error": str(exc), "traceback": traceback.format_exc()[-1200:], "reason": reason})
                turn_finalizing = False
                return
            if not query:
                await send({"type": "error", "stage": "asr", "error": "FunASR did not recognize valid speech.", "reason": reason})
                turn_finalizing = False
                return

            corrected_query = await correct_realtime_asr_query(query, history)
            query = corrected_query["text"]
            asr_correction = corrected_query["asr"]
            if asr_correction.get("correction_failed"):
                await send({
                    "type": "error",
                    "stage": "asr_correction",
                    "error": "语音纠错失败，请重试：" + (asr_correction.get("correction_error") or "DeepSeek 未返回可靠纠错结果。"),
                    "reason": reason,
                    "asr": asr_correction,
                })
                await reset_turn_state(reset_session=True)
                return
            await send({"type": "asr_final", "text": query, "reason": reason, "asr": asr_correction})
            answer_started_at = time.time()
            full_answer = ""
            sentence_buffer = ""
            async for delta in llm_gateway.stream_answer(query, history, interest):
                if interrupted:
                    break
                full_answer += delta
                sentence_buffer += delta
                await send({"type": "llm_delta", "text": delta})
                chunks = sentence_chunks(sentence_buffer)
                if len(chunks) > 1 or re.search(r"[。！？!?；;]$", sentence_buffer.strip()):
                    ready_sentences = chunks if re.search(r"[。！？!?；;]$", sentence_buffer.strip()) else chunks[:-1]
                    sentence_buffer = "" if ready_sentences == chunks else chunks[-1]
                    for sentence in ready_sentences:
                        if interrupted:
                            break
                        await emit_tts_sentence(send, query, full_answer, sentence)

            if not interrupted and sentence_buffer.strip():
                await emit_tts_sentence(send, query, full_answer, sentence_buffer.strip())
            await send(
                build_realtime_done_event(
                    query=query,
                    answer=full_answer,
                    started_at=answer_started_at,
                    interrupted=interrupted,
                    reason=reason,
                    continue_listening=continue_listening,
                )
            )
            await reset_turn_state(reset_session=True)

        await send({"type": "ready", "status": realtime_status()})
        try:
            while True:
                message = await websocket.receive()
                if "bytes" in message and message["bytes"] is not None:
                    if not session_active or turn_finalizing:
                        continue
                    chunk = message["bytes"]
                    audio_parts.append(chunk)
                    stats = pcm16_stats(chunk)
                    total_audio_ms += stats["duration_ms"]
                    if stats["is_speech"]:
                        speech_ms += stats["duration_ms"]
                        silence_ms = 0.0
                        if speech_ms >= realtime_min_speech_ms():
                            has_speech = True
                    elif has_speech:
                        silence_ms += stats["duration_ms"]
                    if len(chunk) > 0 and has_speech:
                        async def recognize_partial():
                            return await session.feed(chunk, is_final=False)

                        async def send_partial(text):
                            await send({"type": "asr_partial", "text": text})

                        async def send_partial_error(exc):
                            await send({"type": "error", "stage": "asr", "error": str(exc)})

                        partial_scheduler.schedule(time.time() * 1000.0, recognize_partial, send_partial, send_partial_error)
                    if has_speech and silence_ms >= realtime_silence_ms():
                        await send({"type": "speech_end", "reason": "silence", "silence_ms": round(silence_ms)})
                        if continuous_mode:
                            if answer_task and not answer_task.done():
                                answer_task.cancel()
                            answer_task = asyncio.create_task(finalize_turn("silence", continue_listening=True))
                        else:
                            await finalize_turn("silence", continue_listening=False)
                        continue
                    if total_audio_ms >= realtime_max_listen_ms():
                        await send({"type": "speech_end", "reason": "max_listen", "audio_ms": round(total_audio_ms)})
                        if continuous_mode:
                            if answer_task and not answer_task.done():
                                answer_task.cancel()
                            answer_task = asyncio.create_task(finalize_turn("max_listen", continue_listening=True))
                        else:
                            await finalize_turn("max_listen", continue_listening=False)
                    continue

                raw = message.get("text")
                if raw is None:
                    continue
                data = json.loads(raw)
                event_type = data.get("type")
                if event_type == "start":
                    if answer_task and not answer_task.done():
                        answer_task.cancel()
                    await reset_turn_state(reset_session=True)
                    history = data.get("history") or []
                    interest = data.get("interest") or ""
                    interrupted = False
                    session_active = True
                    continuous_mode = data.get("mode") == "continuous"
                    await send_listening()
                    continue
                if event_type == "interrupt":
                    interrupted = True
                    session_active = False
                    if answer_task and not answer_task.done():
                        answer_task.cancel()
                    await reset_turn_state(reset_session=True)
                    await send({"type": "interrupted"})
                    continue
                if event_type == "end_session":
                    interrupted = True
                    session_active = False
                    if answer_task and not answer_task.done():
                        answer_task.cancel()
                        await send(build_realtime_turn_cancelled_event("end_session"))
                    await reset_turn_state(reset_session=True)
                    await send({"type": "interrupted", "reason": "end_session"})
                    continue
                if event_type == "barge_in":
                    interrupted = True
                    if answer_task and not answer_task.done():
                        answer_task.cancel()
                    await reset_turn_state(reset_session=True)
                    barge_in_audio = decode_realtime_audio_frame(data.get("audio", ""))
                    if barge_in_audio:
                        audio_parts.append(barge_in_audio)
                        stats = pcm16_stats(barge_in_audio)
                        total_audio_ms = stats["duration_ms"]
                        speech_ms = stats["duration_ms"] if stats["is_speech"] else 0.0
                        has_speech = stats["is_speech"] and speech_ms >= realtime_min_speech_ms()
                    session_active = True
                    interrupted = False
                    await send(build_realtime_turn_cancelled_event("barge_in"))
                    await send_listening()
                    continue
                if event_type != "stop":
                    continue

                await finalize_turn("manual_stop", continue_listening=continuous_mode)
        except WebSocketDisconnect:
            if answer_task and not answer_task.done():
                answer_task.cancel()
            return
        except Exception as exc:
            try:
                await send({"type": "error", "stage": "server", "error": str(exc), "traceback": traceback.format_exc()[-1600:]})
            except Exception:
                pass


    async def emit_tts_sentence(send, query: str, answer_so_far: str, sentence: str) -> None:
        if not sentence:
            return
        start_event = build_realtime_tts_start_event(query, answer_so_far, sentence)
        await send(start_event)
        result = await tts_gateway.synthesize_url(sentence)
        if result.get("audio_url"):
            await send(build_realtime_audio_chunk_event(sentence, start_event.get("emotion", "neutral"), result))
            return
        await send({"type": "error", "stage": "tts", "error": result.get("error", "TTS failed."), "text": sentence})

except Exception:
    app = None


if __name__ == "__main__":
    if app is None:
        print(json.dumps({"ok": False, "error": "fastapi/uvicorn is not installed."}, ensure_ascii=False))
        raise SystemExit(1)
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("REALTIME_PORT", "8010")))
