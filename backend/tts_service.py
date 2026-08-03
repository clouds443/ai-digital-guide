# -*- coding: utf-8 -*-
import asyncio
import importlib.util
import json
import os
import re
import subprocess
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from runtime_paths import asset_path, runtime_path
from voice_clone_service import get_voice_clone, trim_prompt_text_to_reference


ROOT_DIR = asset_path()
BACKEND_DIR = asset_path("backend")
FRONTEND_DIR = asset_path("frontend")
TTS_AUDIO_DIR = runtime_path("frontend", "audio", "tts")
DEFAULT_GPT_SOVITS_API_URL = "http://127.0.0.1:9880"
DEFAULT_GSV_TTS_LITE_API_URL = "http://127.0.0.1:9880"


EDGE_VOICE_PRESETS = [
    {
        "id": "lingshan_guide_female",
        "name": "灵山女导游",
        "edge_voice": "zh-CN-XiaoxiaoNeural",
        "rate": "+0%",
        "pitch": "+0Hz",
        "volume": "+0%",
        "description": "温和、清晰、适合景区导览的普通话女声。",
    },
    {
        "id": "cultural_narrator_male",
        "name": "文化讲解男声",
        "edge_voice": "zh-CN-YunxiNeural",
        "rate": "-5%",
        "pitch": "-2Hz",
        "volume": "+0%",
        "description": "沉稳、有讲解感的中文男声，适合历史文化内容。",
    },
    {
        "id": "family_friendly",
        "name": "亲子活泼声线",
        "edge_voice": "zh-CN-XiaoyiNeural",
        "rate": "+8%",
        "pitch": "+3Hz",
        "volume": "+0%",
        "description": "明亮、亲和，适合亲子游客的中文女声。",
    },
    {
        "id": "custom",
        "name": "自定义音色",
        "edge_voice": "zh-CN-XiaoxiaoNeural",
        "rate": "+0%",
        "pitch": "+0Hz",
        "volume": "+0%",
        "description": "可自定义 Edge-TTS voice/rate/pitch/volume。",
    },
]


GPT_SOVITS_PRESETS = [
    {
        "id": "gpt_sovits_clone",
        "name": "GSV-TTS-Lite 克隆音色",
        "description": "管理员上传参考音频后，调用 GSV-TTS-Lite 进行低延迟音色克隆和语音合成；配置值 gpt_sovits 仅用于兼容旧接口。",
    }
]


def get_voice_presets():
    return GPT_SOVITS_PRESETS + EDGE_VOICE_PRESETS


def normalize_edge_value(value, default):
    value = str(value or "").strip()
    return value or default


def get_edge_voice_config(config):
    config = config or {}
    preset_id = config.get("voice_preset") or "lingshan_guide_female"
    preset = next((item for item in EDGE_VOICE_PRESETS if item["id"] == preset_id), EDGE_VOICE_PRESETS[0])
    return {
        "voice": normalize_edge_value(config.get("edge_voice") or config.get("voice_name"), preset["edge_voice"]),
        "rate": normalize_edge_value(config.get("voice_rate"), preset["rate"]),
        "pitch": normalize_edge_value(config.get("voice_pitch"), preset["pitch"]),
        "volume": normalize_edge_value(config.get("voice_volume"), preset["volume"]),
        "preset": preset,
    }


def tts_provider(config=None):
    config = config or {}
    provider = (config.get("voice_provider") or os.getenv("OPEN_SOURCE_TTS_PROVIDER") or "gpt_sovits").strip().lower()
    aliases = {
        "gptsovits": "gpt_sovits",
        "gpt-sovits": "gpt_sovits",
        "sovits": "gpt_sovits",
        "gsv": "gpt_sovits",
        "gsv_tts": "gpt_sovits",
        "gsv_tts_lite": "gpt_sovits",
        "gsv-tts-lite": "gpt_sovits",
    }
    return aliases.get(provider, provider)


def gsv_tts_lite_api_url():
    return (
        os.getenv("GSV_TTS_LITE_API_URL")
        or os.getenv("GPT_SOVITS_API_URL")
        or DEFAULT_GSV_TTS_LITE_API_URL
    ).strip().rstrip("/")


def gpt_sovits_api_url():
    return gsv_tts_lite_api_url()


def gsv_tts_lite_timeout():
    try:
        return int(os.getenv("GSV_TTS_LITE_TIMEOUT_SECONDS") or os.getenv("GPT_SOVITS_TIMEOUT_SECONDS", "120"))
    except ValueError:
        return 120


def gpt_sovits_timeout():
    return gsv_tts_lite_timeout()


def gpt_sovits_text_lang():
    return (os.getenv("GPT_SOVITS_TEXT_LANG") or "zh").strip() or "zh"


def gpt_sovits_prompt_lang():
    return (os.getenv("GPT_SOVITS_PROMPT_LANG") or "zh").strip() or "zh"


def gpt_sovits_allow_edge_fallback():
    return str(os.getenv("GPT_SOVITS_ALLOW_EDGE_FALLBACK", "true")).strip().lower() in {"1", "true", "yes", "on"}


def is_narration_first_request(config):
    value = str((config or {}).get("purpose") or "").strip().lower()
    if value == "narration_first":
        return True
    return str((config or {}).get("fast_first") or "").strip().lower() in {"1", "true", "yes", "on"}


def clone_voice_selected(config):
    return bool(str((config or {}).get("voice_clone_id") or "").strip())


STAGE_DIRECTION_WORDS = (
    "微微",
    "语气",
    "笑",
    "欠身",
    "点头",
    "摇头",
    "挥手",
    "停顿",
    "温和",
    "庄重",
    "轻声",
    "认真",
    "调皮",
    "开心",
    "惊讶",
    "疑惑",
    "表情",
    "动作",
    "看向",
    "眨眼",
    "鞠躬",
    "合掌",
    "手势",
    "俏皮",
    "害羞",
    "低头",
    "抬头",
    "沉思",
)


def _int_to_chinese(number, use_liang=False):
    try:
        value = int(number)
    except (TypeError, ValueError):
        return str(number)
    digits = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九"]
    if value == 0:
        return "零"
    if use_liang and value == 2:
        return "两"
    if value < 10:
        return digits[value]
    if value < 20:
        return "十" + (digits[value % 10] if value % 10 else "")
    if value < 100:
        return digits[value // 10] + "十" + (digits[value % 10] if value % 10 else "")
    if value < 1000:
        hundreds = value // 100
        rest = value % 100
        text = digits[hundreds] + "百"
        if rest == 0:
            return text
        if rest < 10:
            return text + "零" + digits[rest]
        if rest < 20:
            return text + "一" + _int_to_chinese(rest)
        return text + _int_to_chinese(rest)
    return str(value)


def _time_to_speech(match):
    hour = int(match.group(1))
    minute = int(match.group(2))
    text = _int_to_chinese(hour) + "点"
    if minute == 0:
        return text
    if minute == 30:
        return text + "半"
    if minute < 10:
        return text + "零" + _int_to_chinese(minute) + "分"
    return text + _int_to_chinese(minute) + "分"


def _time_range_to_speech(match):
    start = _time_to_speech(match)
    end_match = re.match(r"(\d{1,2}):(\d{2})", match.group(3))
    if not end_match:
        return match.group(0)
    return start + "到" + _time_to_speech(end_match)


def _decimal_to_speech(match):
    integer = _int_to_chinese(match.group(1))
    fraction = "".join(_int_to_chinese(digit) for digit in match.group(2))
    return integer + "点" + fraction


def _looks_like_stage_direction(text):
    value = re.sub(r"\s+", "", str(text or ""))
    if not value:
        return False
    if len(value) <= 32 and any(word in value for word in STAGE_DIRECTION_WORDS):
        return True
    return False


def strip_stage_directions_for_speech(text):
    value = str(text or "")

    def replace_parenthetical(match):
        content = match.group(1) if match.group(1) is not None else match.group(2)
        is_leading = not value[: match.start()].strip()
        if (is_leading and len(content) <= 60) or _looks_like_stage_direction(content):
            return ""
        return match.group(0)

    value = re.sub(r"（([^（）]{0,80})）|\(([^()]{0,80})\)", replace_parenthetical, value)
    return value


def normalize_time_for_speech(text):
    value = str(text or "")
    value = re.sub(r"(?<!\d)(\d{1,3})\.(\d+)(?!\d)", _decimal_to_speech, value)
    value = re.sub(
        r"(\d{1,2}):(\d{2})\s*[-~—－至到]\s*((?:\d{1,2}):(?:\d{2}))",
        _time_range_to_speech,
        value,
    )
    value = re.sub(r"(\d{1,2}):(\d{2})", _time_to_speech, value)
    value = re.sub(
        r"(\d{1,2})\s*[-~—－至到]\s*(\d{1,2})\s*(分钟|分)",
        lambda m: _int_to_chinese(m.group(1)) + "到" + _int_to_chinese(m.group(2)) + m.group(3),
        value,
    )
    value = re.sub(
        r"(?<!\d)(\d{1,2})\s*(分钟|分)",
        lambda m: _int_to_chinese(m.group(1)) + m.group(2),
        value,
    )
    value = re.sub(
        r"(?<!\d)(\d{1,2})\s*(小时|个小时)",
        lambda m: _int_to_chinese(m.group(1), use_liang=True) + m.group(2),
        value,
    )
    value = re.sub(
        r"(?<![\dA-Za-z])(\d{1,3})(?![\dA-Za-z])",
        lambda m: _int_to_chinese(m.group(1)),
        value,
    )
    return value


def normalize_polyphonic_chinese_for_speech(text):
    value = str(text or "")
    replacements = (
        ("汉藏", "汉臧"),
        ("藏传", "臧传"),
        ("藏式", "臧式"),
        ("藏香", "臧香"),
        ("藏族", "臧族"),
        ("藏文", "臧文"),
        ("藏语", "臧语"),
        ("藏历", "臧历"),
        ("藏地", "臧地"),
        ("藏区", "臧区"),
        ("藏文化", "臧文化"),
        ("藏传坛城", "臧传坛城"),
    )
    for source, target in replacements:
        value = value.replace(source, target)
    # TTS 容易把“同行”读成行业的“同杭”，旅行陪伴语境改成更明确的“同游”。
    value = re.sub(r"同行(?=有|的|人|游客|老人|孩子|小孩|家人|朋友|的话|时|就|可以|不必|，|。|；|、)", "同游", value)
    value = re.sub(r"(?<=[老小孩友人客])同行", "同游", value)
    # “全长”后面紧跟长度数值时，容易被读成长大的“长”，改成“总长度”稳定引导读音。
    value = re.sub(
        r"全长(?=(?:约为|约|为|达|大约|近|将近|超过)?[零〇一二两三四五六七八九十百千万点\d]+\s*(?:米|公里|千米|厘米|毫米|m|km|cm|mm))",
        "总长度",
        value,
        flags=re.IGNORECASE,
    )
    # “桥身长9米”里的“长”是长度读音，改写为“桥身长度”避免被读成“长大”的长。
    value = re.sub(
        r"桥身长(?=(?:约为|约|为|达|大约|近|将近|超过)?[零〇一二两三四五六七八九十百千万点\d]+\s*(?:米|公里|千米|厘米|毫米|m|km|cm|mm))",
        "桥身长度",
        value,
        flags=re.IGNORECASE,
    )
    # “桥长”在长度语境里容易被读成成长的“长”，播报时改成更明确的“桥的长度”。
    value = re.sub(r"桥的桥长", "桥的长度", value)
    value = re.sub(r"桥长(?=，|。|；|、|和|与|而|不|是|约|有|为|在|$)", "桥的长度", value)
    # 用户验收要求所有“长”默认按 cháng 播报，TTS 专用文本用同音字“常”强制引导读音。
    value = value.replace("长", "常")
    return value


def prepare_tts_text(text):
    value = strip_stage_directions_for_speech(text)
    value = normalize_time_for_speech(value)
    value = normalize_polyphonic_chinese_for_speech(value)
    value = re.sub(r"[*#>`_~]", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    if value.endswith(("，", ",", "、", "：", ":")):
        value = value[:-1].rstrip() + "。"
    return value


def normalize_text_for_gpt_sovits(text):
    replacements = {
        "GPT-SoVITS": "\u514b\u9686\u8bed\u97f3\u5f15\u64ce",
        "DeepSeek": "\u6df1\u5ea6\u6c42\u7d22",
        "Live2D": "\u52a8\u6001\u6570\u5b57\u4eba",
        "AIGC": "\u4eba\u5de5\u667a\u80fd\u751f\u6210\u5185\u5bb9",
        "RAG": "\u77e5\u8bc6\u5e93\u68c0\u7d22\u589e\u5f3a",
        "TTS": "\u8bed\u97f3\u5408\u6210",
        "ASR": "\u8bed\u97f3\u8bc6\u522b",
        "GPT": "\u8bed\u8a00\u6a21\u578b",
        "AI": "\u4eba\u5de5\u667a\u80fd",
    }
    value = prepare_tts_text(text)
    for key in sorted(replacements, key=len, reverse=True):
        value = re.sub(re.escape(key), replacements[key], value, flags=re.IGNORECASE)
    value = re.sub(r"[A-Za-z_][A-Za-z0-9_+./#-]*", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def gpt_sovits_required_paths():
    repo = os.getenv("GSV_TTS_LITE_REPO_DIR", runtime_path("third_party", "GSV-TTS-Lite"))
    pretrained = os.path.join(repo, "GPT_SoVITS", "pretrained_models")
    v2_pretrained = os.path.join(pretrained, "gsv-v2final-pretrained")
    return {
        "repo_dir": repo,
        "api_v2": os.path.join(BACKEND_DIR, "gsv_tts_lite_server.py"),
        "tts_config": os.path.join(repo, "GPT_SoVITS", "configs", "tts_infer.yaml"),
        "pretrained_dir": pretrained,
        "v2_gpt": os.path.join(v2_pretrained, "s1bert25hz-5kh-longer-epoch=12-step=369668.ckpt"),
        "v2_sovits": os.path.join(v2_pretrained, "s2G2333k.pth"),
        "bert": os.path.join(pretrained, "chinese-roberta-wwm-ext-large"),
        "hubert": os.path.join(pretrained, "chinese-hubert-base"),
        "g2pw": os.path.join(repo, "GPT_SoVITS", "text", "G2PWModel"),
        "api_url": gsv_tts_lite_api_url(),
    }


def cleanup_audio(max_age_seconds=3600):
    if not os.path.isdir(TTS_AUDIO_DIR):
        return
    now = time.time()
    for name in os.listdir(TTS_AUDIO_DIR):
        path = os.path.join(TTS_AUDIO_DIR, name)
        if os.path.isfile(path) and now - os.path.getmtime(path) > max_age_seconds:
            try:
                os.remove(path)
            except OSError:
                pass


def _run_async(coro):
    return asyncio.run(coro)


def external_edge_python():
    env_python = str(os.getenv("EDGE_TTS_PYTHON") or "").strip()
    candidates = []
    if env_python:
        candidates.append(env_python)
    candidates.append(runtime_path(".venvs", "realtime", "Scripts", "python.exe"))
    for python_exe in candidates:
        if not python_exe or not os.path.isfile(python_exe):
            continue
        try:
            code = "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('edge_tts') else 1)"
            subprocess.check_call([python_exe, "-c", code], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return python_exe
        except Exception:
            continue
    return ""


async def _edge_save(text, output_path, voice_config):
    import edge_tts

    communicate = edge_tts.Communicate(
        text=text,
        voice=voice_config["voice"],
        rate=voice_config["rate"],
        pitch=voice_config["pitch"],
        volume=voice_config["volume"],
    )
    await communicate.save(output_path)


def _edge_save_external(text, output_path, voice_config, python_exe):
    script = (
        "import asyncio, edge_tts, sys\n"
        "text, output_path, voice, rate, pitch, volume = sys.argv[1:7]\n"
        "async def main():\n"
        "    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch, volume=volume)\n"
        "    await communicate.save(output_path)\n"
        "asyncio.run(main())\n"
    )
    subprocess.check_call(
        [
            python_exe,
            "-c",
            script,
            text,
            output_path,
            voice_config["voice"],
            voice_config["rate"],
            voice_config["pitch"],
            voice_config["volume"],
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def synthesize_edge(text, config):
    text = prepare_tts_text(text)
    local_edge = importlib.util.find_spec("edge_tts") is not None
    edge_python = "" if local_edge else external_edge_python()
    if not local_edge and not edge_python:
        return {"ok": False, "provider": "edge", "error": "未安装 edge-tts，请先安装依赖。"}
    os.makedirs(TTS_AUDIO_DIR, exist_ok=True)
    cleanup_audio()
    output_name = "tts_{0}.mp3".format(uuid.uuid4().hex)
    output_path = os.path.join(TTS_AUDIO_DIR, output_name)
    voice_config = get_edge_voice_config(config)
    started_at = time.time()
    if local_edge:
        _run_async(_edge_save(text[:2000], output_path, voice_config))
        runtime = "local"
    else:
        _edge_save_external(text[:2000], output_path, voice_config, edge_python)
        runtime = edge_python
    return {
        "ok": True,
        "audio_url": "/audio/tts/" + output_name,
        "provider": "edge",
        "runtime": runtime,
        "voice": voice_config["voice"],
        "rate": voice_config["rate"],
        "pitch": voice_config["pitch"],
        "volume": voice_config["volume"],
        "synthesis_seconds": round(time.time() - started_at, 2),
    }


def _http_json(url, timeout=5):
    req = Request(url, headers={"Accept": "application/json"})
    with urlopen(req, timeout=timeout) as response:
        raw = response.read()
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8", "ignore"))
    except Exception:
        return {"raw": raw.decode("utf-8", "ignore")[:1000]}


def gsv_tts_lite_status():
    paths = gpt_sovits_required_paths()
    wrapper_ready = os.path.isfile(paths["api_v2"])
    api_reachable = False
    api_error = ""
    api_payload = {}
    for endpoint in ["/control?command=ping"]:
        try:
            api_payload = _http_json(urljoin(paths["api_url"] + "/", endpoint.lstrip("/")), timeout=3)
            if isinstance(api_payload, dict) and (
                api_payload.get("provider") == "gsv_tts_lite"
                or api_payload.get("engine") == "gsv_tts_lite"
            ):
                api_reachable = True
                break
            api_error = "9880 端口响应不是 GSV-TTS-Lite 包装服务，请停止旧服务后重新启动 GSV-TTS-Lite。"
        except HTTPError as exc:
            api_error = "HTTP {0}: {1}".format(exc.code, exc.reason)
        except (URLError, TimeoutError, OSError) as exc:
            api_error = str(exc)
        except Exception as exc:
            api_error = str(exc)

    return {
        "ok": api_reachable,
        "provider": "gsv_tts_lite",
        "engine": "gsv_tts_lite",
        "api_url": paths["api_url"],
        "repo_dir": paths["repo_dir"],
        "wrapper": paths["api_v2"],
        "wrapper_ready": wrapper_ready,
        "repo_ready": os.path.isdir(paths["repo_dir"]),
        "model_status": {"wrapper": wrapper_ready},
        "missing_assets": [] if wrapper_ready else ["gsv_tts_lite_server.py"],
        "api_reachable": api_reachable,
        "api_payload": api_payload,
        "text_lang": gpt_sovits_text_lang(),
        "prompt_lang": gpt_sovits_prompt_lang(),
        "error": "" if api_reachable else (api_error or ("GSV-TTS-Lite 包装服务未就绪。" if wrapper_ready else "缺少 GSV-TTS-Lite 包装服务。")),
        "hint": ""
        if api_reachable
        else (
            "请先运行 scripts\\install_gsv_tts_lite_env.ps1，然后在服务管理启动 GSV-TTS-Lite 克隆音色服务。"
            if wrapper_ready
            else "缺少 backend\\gsv_tts_lite_server.py，请检查项目文件完整性。"
        ),
    }


def gpt_sovits_status():
    status = dict(gsv_tts_lite_status())
    hint = status.get("hint") or "GSV-TTS-Lite 克隆音色服务已通过 gpt_sovits 兼容入口提供。"
    status.update(
        {
            "provider": "gpt_sovits",
            "engine": "gsv_tts_lite",
            "compat_provider": "gpt_sovits",
            "hint": "兼容 gpt_sovits 配置值；实际引擎为 GSV-TTS-Lite。" if status.get("ok") else hint + " 旧配置值 gpt_sovits 仅用于兼容。",
        }
    )
    return status


def _build_gsv_tts_lite_payload(text, clone):
    prompt_text = trim_prompt_text_to_reference(
        clone.get("prompt_text", ""),
        clone.get("reference_duration_seconds"),
        force=bool(clone.get("trimmed")),
    )
    payload = {
        "text": normalize_text_for_gpt_sovits(text)[:1200],
        "text_lang": gpt_sovits_text_lang(),
        "ref_audio_path": clone.get("audio_path", ""),
        "prompt_lang": gpt_sovits_prompt_lang(),
        "prompt_text": prompt_text,
        "top_k": int(os.getenv("GPT_SOVITS_TOP_K", "5")),
        "top_p": float(os.getenv("GPT_SOVITS_TOP_P", "1.0")),
        "temperature": float(os.getenv("GPT_SOVITS_TEMPERATURE", "1.0")),
        "speed_factor": float(os.getenv("GPT_SOVITS_SPEED_FACTOR", "1.0")),
        "media_type": "wav",
        "return_subtitles": True,
    }
    aux_ref_audio_paths = [p.strip() for p in str(clone.get("aux_ref_audio_paths") or "").split(";") if p.strip()]
    if aux_ref_audio_paths:
        payload["aux_ref_audio_paths"] = aux_ref_audio_paths
    return payload


def _build_gpt_sovits_payload(text, clone):
    return _build_gsv_tts_lite_payload(text, clone)


def _post_gsv_tts_lite_tts(payload):
    url = gsv_tts_lite_api_url() + "/tts"
    body = json.dumps(payload, ensure_ascii=True).encode("ascii")
    req = Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=gsv_tts_lite_timeout()) as response:
            data = response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", "ignore")
        raise RuntimeError("GSV-TTS-Lite API returned HTTP {0}: {1}".format(exc.code, detail[:1200]))
    if not data:
        raise RuntimeError("GSV-TTS-Lite API returned empty response.")
    try:
        result = json.loads(data.decode("utf-8", "ignore"))
    except Exception as exc:
        raise RuntimeError("GSV-TTS-Lite API returned invalid JSON: " + str(exc))
    if not result.get("ok", False):
        raise RuntimeError(result.get("error") or result.get("message") or "GSV-TTS-Lite synthesis failed.")
    return result


def _post_gpt_sovits_tts(payload, output_path):
    result = _post_gsv_tts_lite_tts(payload)
    audio_path = result.get("audio_path", "")
    if not audio_path or not os.path.isfile(audio_path):
        raise RuntimeError("GSV-TTS-Lite did not return a valid audio_path.")
    with open(audio_path, "rb") as source, open(output_path, "wb") as target:
        data = source.read()
        target.write(data)
    return len(data)


def _gpt_sovits_fallback_edge(text, config, reason):
    if clone_voice_selected(config):
        return {
            "ok": False,
            "provider": "gpt_sovits",
            "engine": "gsv_tts_lite",
            "fallback_provider": "",
            "voice_clone_id": str((config or {}).get("voice_clone_id") or "").strip(),
            "gpt_sovits_error": str(reason),
            "gsv_tts_lite_error": str(reason),
            "error": "GSV-TTS-Lite 克隆音色合成失败，已保留克隆音色设置，不自动切换到 Edge-TTS。原因：" + str(reason),
        }
    if not gpt_sovits_allow_edge_fallback():
        return {
            "ok": False,
            "provider": "gpt_sovits",
            "engine": "gsv_tts_lite",
            "fallback_provider": "",
            "gpt_sovits_error": str(reason),
            "gsv_tts_lite_error": str(reason),
            "error": "GSV-TTS-Lite 克隆音色合成失败，已停止自动切换到 Edge-TTS。原因：" + str(reason),
        }
    fallback_config = dict(config or {})
    fallback_config["voice_provider"] = "edge"
    speech = synthesize_edge(text, fallback_config)
    if speech.get("ok"):
        return {
            **speech,
            "provider": "gpt_sovits",
            "engine": "gsv_tts_lite",
            "fallback_provider": "edge",
            "gpt_sovits_error": str(reason),
            "gsv_tts_lite_error": str(reason),
            "error": "",
        }
    return {
        **speech,
        "ok": False,
        "provider": "gpt_sovits",
        "engine": "gsv_tts_lite",
        "fallback_provider": "edge",
        "gpt_sovits_error": str(reason),
        "gsv_tts_lite_error": str(reason),
        "error": "GSV-TTS-Lite failed and Edge-TTS fallback also failed: " + (speech.get("error") or ""),
    }


def synthesize_gpt_sovits(text, config):
    clone_id = (config or {}).get("voice_clone_id", "").strip()
    clone = get_voice_clone(clone_id)
    if not clone:
        return {
            "ok": False,
            "provider": "gpt_sovits",
            "engine": "gsv_tts_lite",
            "error": "请先在管理端上传参考音频，并选择一个 GSV-TTS-Lite 克隆音色。",
        }
    if not clone.get("audio_exists"):
        return {
            "ok": False,
            "provider": "gpt_sovits",
            "engine": "gsv_tts_lite",
            "error": "所选克隆音色的参考音频不存在，请重新上传。",
            "voice_clone_id": clone_id,
        }
    if not clone.get("prompt_text"):
        return {
            "ok": False,
            "provider": "gpt_sovits",
            "engine": "gsv_tts_lite",
            "error": "所选克隆音色缺少参考文本，请重新上传并填写音频中实际朗读的内容。",
            "voice_clone_id": clone_id,
        }

    status = gpt_sovits_status()
    if not status.get("ok"):
        return _gpt_sovits_fallback_edge(
            text,
            config,
            status.get("error") or status.get("hint") or "GSV-TTS-Lite API is not ready.",
        )

    os.makedirs(TTS_AUDIO_DIR, exist_ok=True)
    cleanup_audio()
    output_name = "tts_{0}.wav".format(uuid.uuid4().hex)
    output_path = os.path.join(TTS_AUDIO_DIR, output_name)
    payload = _build_gsv_tts_lite_payload(text, clone)
    started_at = time.time()
    try:
        gsv_result = _post_gsv_tts_lite_tts(payload)
        audio_path = gsv_result.get("audio_path", "")
        direct_audio_url = gsv_result.get("audio_url", "")
        if (not audio_path or not os.path.isfile(audio_path)) and not direct_audio_url:
            raise RuntimeError("GSV-TTS-Lite did not generate a valid audio file.")
        if direct_audio_url:
            bytes_written = int(gsv_result.get("bytes") or 0)
            audio_url = direct_audio_url
        elif audio_path and os.path.isfile(audio_path):
            with open(audio_path, "rb") as source, open(output_path, "wb") as target:
                data = source.read()
                target.write(data)
            bytes_written = len(data)
            audio_url = "/audio/tts/" + output_name
        else:
            raise RuntimeError("GSV-TTS-Lite did not generate a valid audio file.")
    except Exception as exc:
        return _gpt_sovits_fallback_edge(text, config, exc)

    if not audio_url:
        return _gpt_sovits_fallback_edge(text, config, "GSV-TTS-Lite did not generate a valid audio file.")

    return {
        "ok": True,
        "audio_url": audio_url,
        "provider": "gpt_sovits",
        "engine": "gsv_tts_lite",
        "api_url": gsv_tts_lite_api_url(),
        "voice_clone_id": clone_id,
        "voice_clone_name": clone.get("name"),
        "text_lang": payload["text_lang"],
        "prompt_lang": payload["prompt_lang"],
        "bytes": bytes_written,
        "subtitles": gsv_result.get("subtitles") or [],
        "synthesis_seconds": gsv_result.get("synthesis_seconds") or round(time.time() - started_at, 2),
    }


def tts_status(config=None):
    provider = tts_provider(config)
    edge_ok = importlib.util.find_spec("edge_tts") is not None
    edge_python = "" if edge_ok else external_edge_python()
    edge_available = bool(edge_ok or edge_python)
    gsv_status = gsv_tts_lite_status()
    gpt_status = gpt_sovits_status()
    provider_ok = edge_available if provider == "edge" else bool(gsv_status.get("ok"))
    status = {
        "ok": provider_ok,
        "provider": provider,
        "engine": "edge" if provider == "edge" else "gsv_tts_lite",
        "provider_ready": provider_ok,
        "edge_tts_installed": edge_ok,
        "edge_tts_external": bool(edge_python),
        "fallback_available": edge_available,
        "voices": get_voice_presets(),
        "edge": {
            "ok": edge_available,
            "installed": edge_ok,
            "external_python": edge_python,
            "voices": EDGE_VOICE_PRESETS,
        },
        "gsv_tts_lite": gsv_status,
        "gpt_sovits": gpt_status,
    }
    if provider == "edge" and not edge_available:
        status["ok"] = False
        status["error"] = "未安装 edge-tts。"
    if provider == "gpt_sovits":
        status["ok"] = bool(gsv_status.get("ok"))
        status["provider_ready"] = bool(gsv_status.get("ok"))
        status["error"] = "" if gsv_status.get("ok") else (gsv_status.get("error") or gsv_status.get("hint", "GSV-TTS-Lite 未就绪。"))
        status["fallback_available"] = edge_available
    return status


def synthesize_speech(text, config):
    provider = tts_provider(config)
    text = prepare_tts_text(text)
    if not text:
        return {"ok": False, "error": "语音文本不能为空。", "provider": provider}
    try:
        if provider == "gpt_sovits" and is_narration_first_request(config) and not clone_voice_selected(config):
            speech = synthesize_edge(text, config)
            if speech.get("ok"):
                return {
                    **speech,
                    "provider": "gpt_sovits",
                    "fallback_provider": "edge",
                    "fast_first": True,
                    "error": "",
                }
            return {
                **speech,
                "ok": False,
                "provider": "gpt_sovits",
                "fallback_provider": "edge",
                "fast_first": True,
                "error": "景点首段快语音不可用：" + (speech.get("error") or "Edge-TTS 未就绪。"),
            }
        if provider == "gpt_sovits":
            return synthesize_gpt_sovits(text, config)
        return synthesize_edge(text, config)
    except Exception as exc:
        return {
            "ok": False,
            "provider": provider,
            "error": str(exc),
        }
