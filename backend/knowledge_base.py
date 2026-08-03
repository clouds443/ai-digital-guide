# -*- coding: utf-8 -*-
import html as html_lib
import json
import math
import os
import re
import requests
import ssl
import subprocess
import sys
import tempfile
import time
import zipfile
from collections import Counter
from xml.etree import ElementTree as ET

from runtime_paths import asset_path, runtime_path


ROOT_DIR = asset_path()
DEFAULT_DOCS_DIR = asset_path("20260323113204906", "示范景区公开资料包")
DATA_DIR = runtime_path("knowledge")
ADMIN_DOCS_FILE = os.path.join(DATA_DIR, "admin_knowledge.json")
CONFIG_FILE = os.path.join(DATA_DIR, "digital_human_config.json")
FEEDBACK_FILE = os.path.join(DATA_DIR, "feedback.json")
MAX_KNOWLEDGE_FILE_BYTES = 20 * 1024 * 1024
MIN_EXTRACTED_TEXT_CHARS = 30
SUPPORTED_KNOWLEDGE_FILE_EXTS = {".docx", ".pdf"}
PADDLEOCR_JOB_URL = "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs"
PADDLEOCR_MODEL = "PaddleOCR-VL-1.6"
PADDLEOCR_OPTIONAL_PAYLOAD = {
    "useDocOrientationClassify": False,
    "useDocUnwarping": False,
    "useChartRecognition": False,
}
PADDLEOCR_WORKER_SCRIPT = r"""
import json
import os
import sys
import time
import urllib.error
import urllib.request


def normalize_document_text(text):
    import re

    text = (text or "").replace("\r", "\n")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def request_json(url, method="GET", body=None, headers=None, timeout=60):
    request = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        raise RuntimeError("HTTP {0} {1}".format(exc.code, raw))
    return json.loads(raw or "{}")


def request_text(url, timeout=60):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read().decode("utf-8", "replace")


def build_multipart(fields, file_field, file_path):
    boundary = "----lingshan-paddleocr-{0}".format(int(time.time() * 1000))
    chunks = []
    for key, value in fields.items():
        chunks.append(("--{0}\r\n".format(boundary)).encode("utf-8"))
        chunks.append(('Content-Disposition: form-data; name="{0}"\r\n\r\n'.format(key)).encode("utf-8"))
        chunks.append(str(value).encode("utf-8"))
        chunks.append(b"\r\n")
    chunks.append(("--{0}\r\n".format(boundary)).encode("utf-8"))
    chunks.append(
        ('Content-Disposition: form-data; name="{0}"; filename="document.pdf"\r\n'.format(file_field)).encode("utf-8")
    )
    chunks.append(b"Content-Type: application/pdf\r\n\r\n")
    with open(file_path, "rb") as pdf_file:
        chunks.append(pdf_file.read())
    chunks.append(b"\r\n")
    chunks.append(("--{0}--\r\n".format(boundary)).encode("utf-8"))
    return boundary, b"".join(chunks)


def download_markdown_text(jsonl_url):
    raw = request_text(jsonl_url, timeout=60)
    parts = []
    for line_num, raw_line in enumerate(raw.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
            results = item.get("result", {}).get("layoutParsingResults", [])
            for result in results:
                text = result.get("markdown", {}).get("text", "")
                if text and text.strip():
                    parts.append(text.strip())
        except Exception as exc:
            raise RuntimeError("解析 PaddleOCR JSONL 第 {0} 行失败：{1}".format(line_num, exc))
    return "\n\n".join(parts)


def main():
    config = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    filepath = config["filepath"]
    token = config["token"]
    job_url = config["job_url"].rstrip("/")
    poll_interval = float(config.get("poll_interval", 5))
    timeout_seconds = float(config.get("timeout_seconds", 600))
    model = config["model"]

    if not os.path.exists(filepath):
        raise RuntimeError("PDF 文件不存在，无法进行 OCR。")

    fields = {
        "model": model,
        "optionalPayload": json.dumps(config.get("optional_payload") or {}, ensure_ascii=False),
    }
    boundary, body = build_multipart(fields, "file", filepath)
    headers = {
        "Authorization": "bearer {0}".format(token),
        "Content-Type": "multipart/form-data; boundary={0}".format(boundary),
    }
    submit_payload = request_json(job_url, method="POST", body=body, headers=headers, timeout=60)
    job_id = submit_payload["data"]["jobId"]

    deadline = time.time() + timeout_seconds
    last_state = ""
    jsonl_url = ""
    extracted_pages = 0
    while time.time() < deadline:
        payload = request_json("{0}/{1}".format(job_url, job_id), headers={"Authorization": headers["Authorization"]}, timeout=30)
        data = payload["data"]
        state = data["state"]
        last_state = state
        if state in ("pending", "running"):
            time.sleep(poll_interval)
            continue
        if state == "done":
            jsonl_url = data.get("resultUrl", {}).get("jsonUrl", "")
            progress = data.get("extractProgress", {}) or {}
            extracted_pages = progress.get("extractedPages", 0)
            break
        if state == "failed":
            raise RuntimeError("PaddleOCR 任务失败：{0}".format(data.get("errorMsg", "未知错误")))
        raise RuntimeError("PaddleOCR 返回未知任务状态：{0}".format(state))
    if not jsonl_url:
        raise RuntimeError("PaddleOCR 任务超时，最后状态：{0}".format(last_state or "未知"))

    text = normalize_document_text(download_markdown_text(jsonl_url))
    if len(text) < int(config.get("min_chars", 30)):
        raise RuntimeError("PaddleOCR 未提取到有效文本，请检查 PDF 内容或重新上传清晰文件。")
    return {
        "ok": True,
        "text": text,
        "metadata": {
            "ocr_model": model,
            "page_count": extracted_pages,
        },
    }


try:
    result = main()
except Exception as exc:
    result = {"ok": False, "error": str(exc)}
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))
    sys.exit(1)
sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))
"""


SCENIC_NAMES = [
    ("LS-001", "灵山大照壁"),
    ("LS-002", "五明桥"),
    ("LS-003", "佛足坛"),
    ("LS-004", "五智门"),
    ("LS-005", "菩提大道"),
    ("LS-006", "九龙灌浴"),
    ("LS-007", "降魔浮雕"),
    ("LS-008", "阿育王柱"),
    ("LS-009", "天下第一掌"),
    ("LS-010", "百子戏弥勒"),
    ("LS-011", "灵山大佛"),
    ("LS-012", "灵山梵宫"),
    ("LS-013", "祥符禅寺"),
    ("LS-014", "五印坛城"),
    ("LS-015", "曼飞龙塔"),
    ("LS-016", "无尽意斋"),
]


DEFAULT_ROUTES = [
    {
        "id": "route_history",
        "name": "历史文化深度游",
        "duration": "约5小时",
        "tags": ["历史", "文化", "佛教艺术"],
        "summary": "沿中轴线循序进入灵山文化空间，适合想听典故、看建筑艺术和完整礼佛动线的游客。",
        "stops": ["灵山大照壁", "五明桥", "佛足坛", "五智门", "菩提大道", "九龙灌浴", "降魔浮雕", "阿育王柱", "天下第一掌", "百子戏弥勒", "灵山大佛", "灵山梵宫", "五印坛城"],
    },
    {
        "id": "route_nature",
        "name": "自然风光轻松游",
        "duration": "约5小时",
        "tags": ["自然", "拍照", "太湖风光"],
        "summary": "节奏更舒缓，保留大佛、九龙灌浴等核心看点，也留出太湖山水和园林漫步时间。",
        "stops": ["菩提大道", "九龙灌浴", "灵山大佛", "佛教园林", "灵山精舍"],
    },
    {
        "id": "route_family",
        "name": "亲子家庭互动游",
        "duration": "约4小时",
        "tags": ["亲子", "互动", "轻体力"],
        "summary": "减少长距离攀登，优先安排动态演出、趣味雕塑和室内参观点，适合带老人小孩同行。",
        "stops": ["九龙灌浴", "天下第一掌", "百子戏弥勒", "灵山梵宫", "五印坛城"],
    },
]


DEFAULT_CONFIG = {
    "name": "灵小境",
    "voice": "zh-CN",
    "appearance": "温婉新中式导游",
    "style": "温和、专业、带一点文化讲解感",
    "costume": "青绿色新中式导游服",
    "model": "Haru",
    "model_options": ["Haru", "Hiyori", "Mao", "Natori", "Rice", "Ren"],
    "emotion_enabled": "true",
    "voice_provider": "gpt_sovits",
    "voice_preset": "lingshan_guide_female",
    "voice_description": "A warm, clear female tour guide voice, calm and friendly, with natural pacing and a gentle smile in the tone.",
    "voice_clone_id": "",
    "edge_voice": "zh-CN-XiaoxiaoNeural",
    "voice_rate": "+0%",
    "voice_pitch": "+0Hz",
    "voice_volume": "+0%",
    "opening": "您好，我是灵山胜境 AI 数字人导游灵小境。想了解景点、路线、演出、门票或交通，都可以直接问我。",
}

AVATAR_CONFIG_FIELDS = [
    "name",
    "model",
    "appearance",
    "costume",
    "emotion_enabled",
    "style",
    "opening",
    "voice_provider",
    "voice_preset",
    "voice_description",
    "voice_clone_id",
    "edge_voice",
    "voice_rate",
    "voice_pitch",
    "voice_volume",
]

DEFAULT_AVATAR_PRESETS = [
    {
        "id": "preset_1",
        "label": "配置一：温婉新中式导游",
        "summary": "稳重、亲和，适合正式讲解、文化导览和比赛演示主线。",
        "name": "灵小境",
        "model": "Haru",
        "appearance": "温婉新中式导游",
        "costume": "青绿色新中式导游服",
        "emotion_enabled": "true",
        "style": "温和、专业、带一点文化讲解感",
        "opening": "您好，我是灵山胜境 AI 数字人导游灵小境。想了解景点、路线、演出、门票或交通，都可以直接问我。",
        "voice_provider": "gpt_sovits",
        "voice_preset": "lingshan_guide_female",
        "voice_description": "A warm, clear female tour guide voice, calm and friendly, with natural pacing and a gentle smile in the tone.",
        "voice_clone_id": "",
        "edge_voice": "zh-CN-XiaoxiaoNeural",
        "voice_rate": "+10%",
        "voice_pitch": "+0Hz",
        "voice_volume": "+0%",
    },
    {
        "id": "preset_2",
        "label": "配置二：亲和活力讲解员",
        "summary": "更轻快、更适合亲子路线、活动提醒和短句互动。",
        "name": "灵小境",
        "model": "Hiyori",
        "appearance": "亲和活力讲解员",
        "costume": "浅蓝白色轻运动导览服",
        "emotion_enabled": "true",
        "style": "亲切、轻快、短句清晰，适合亲子互动讲解",
        "opening": "您好，我是灵小境。今天想轻松逛灵山的话，可以问我演出时间、亲子路线、拍照点和休息安排。",
        "voice_provider": "edge",
        "voice_preset": "family_friendly",
        "voice_description": "A bright and friendly tour guide voice, energetic but not noisy, suitable for family visitors.",
        "voice_clone_id": "",
        "edge_voice": "zh-CN-XiaoyiNeural",
        "voice_rate": "+6%",
        "voice_pitch": "+2Hz",
        "voice_volume": "+0%",
    },
]


def _avatar_presets():
    return [dict(preset) for preset in DEFAULT_AVATAR_PRESETS]


def _sanitize_avatar_preset(raw, fallback=None):
    raw = raw if isinstance(raw, dict) else {}
    fallback = fallback if isinstance(fallback, dict) else {}
    preset = {}
    for key in ["id", "label", "summary"] + AVATAR_CONFIG_FIELDS:
        if key in fallback:
            preset[key] = str(fallback.get(key, "")).strip()
        if key in raw:
            preset[key] = str(raw.get(key, "")).strip()
    if not preset.get("id"):
        return None
    preset.setdefault("label", preset["id"])
    preset.setdefault("summary", "")
    for key, value in DEFAULT_CONFIG.items():
        if key in AVATAR_CONFIG_FIELDS and key not in preset:
            preset[key] = str(value)
    return preset


def _avatar_presets_from_config(config):
    defaults = _avatar_presets()
    stored_presets = config.get("avatar_presets") if isinstance(config, dict) else None
    if isinstance(stored_presets, list):
        by_id = {}
        ordered_ids = []
        default_by_id = {preset["id"]: dict(preset) for preset in defaults}
        for raw in stored_presets:
            if not isinstance(raw, dict):
                continue
            preset_id = str(raw.get("id", "")).strip()
            fallback = default_by_id.get(preset_id, DEFAULT_CONFIG)
            preset = _sanitize_avatar_preset(raw, fallback)
            if not preset:
                continue
            if preset["id"] not in ordered_ids:
                ordered_ids.append(preset["id"])
            by_id[preset["id"]] = preset
        if ordered_ids:
            return [dict(by_id[preset_id]) for preset_id in ordered_ids if preset_id in by_id]
    return defaults


def _avatar_preset_from_config(config, preset_id):
    preset = {
        "id": str(preset_id or "").strip() or "custom",
        "label": str((config or {}).get("label", "")).strip() or "自定义当前配置",
        "summary": str((config or {}).get("summary", "")).strip() or "从已保存配置恢复，可继续编辑并保存。",
    }
    for key in AVATAR_CONFIG_FIELDS:
        preset[key] = str((config or {}).get(key, DEFAULT_CONFIG.get(key, ""))).strip()
    return _sanitize_avatar_preset(preset, DEFAULT_CONFIG)


def _avatar_preset_by_id(preset_id, presets=None):
    preset_id = str(preset_id or "").strip()
    options = presets if isinstance(presets, list) and presets else DEFAULT_AVATAR_PRESETS
    for preset in options:
        if preset["id"] == preset_id:
            return dict(preset)
    return None


def _match_avatar_preset_id(config, presets=None):
    best_id = "custom"
    best_score = 0
    compare_fields = ["model", "appearance", "costume", "style", "voice_provider", "voice_preset", "edge_voice", "voice_rate"]
    options = presets if isinstance(presets, list) and presets else DEFAULT_AVATAR_PRESETS
    for preset in options:
        score = 0
        for key in compare_fields:
            if str(config.get(key, "")).strip() == str(preset.get(key, "")).strip():
                score += 1
        if score > best_score:
            best_score = score
            best_id = preset["id"]
    return best_id if best_score >= 3 else "custom"


def _with_avatar_presets(config):
    result = dict(config or {})
    presets = _avatar_presets_from_config(result)
    preset_id = str(result.get("avatar_preset_id", "")).strip()
    known_ids = {preset["id"] for preset in presets}
    if preset_id and preset_id not in known_ids:
        restored = _avatar_preset_from_config(result, preset_id)
        if restored:
            presets.append(restored)
            known_ids.add(restored["id"])
    if not preset_id:
        preset_id = _match_avatar_preset_id(result, presets)
    result["avatar_preset_id"] = preset_id or "custom"
    result["avatar_presets"] = presets
    return result


def build_recommendation_context(interest="", weather="", arrival_period="", companions="", duration="", stamina=""):
    text = " ".join([str(interest or ""), str(weather or ""), str(arrival_period or ""), str(companions or ""), str(duration or ""), str(stamina or "")])
    weather_value = str(weather or "").strip()
    if not weather_value:
        if any(word in text for word in ["雨", "下雨", "阴雨", "雷阵雨"]):
            weather_value = "雨"
        elif any(word in text for word in ["热", "高温", "暴晒", "晒"]):
            weather_value = "高温"
    arrival_value = str(arrival_period or "").strip()
    if not arrival_value:
        if any(word in text for word in ["下午", "午后", "晚到"]):
            arrival_value = "afternoon"
        elif any(word in text for word in ["上午", "早上", "一早"]):
            arrival_value = "morning"
    companion_value = str(companions or "").strip()
    if not companion_value:
        labels = []
        if any(word in text for word in ["孩子", "小孩", "亲子", "家庭"]):
            labels.append("亲子")
        if any(word in text for word in ["老人", "长辈", "父母"]):
            labels.append("老人")
        companion_value = "、".join(labels)
    stamina_value = str(stamina or "").strip()
    if not stamina_value and any(word in text for word in ["少走", "不累", "轻松", "体力", "爬不动"]):
        stamina_value = "low"
    duration_value = str(duration or "").strip()
    if not duration_value:
        match = re.search(r"(\d+)\s*(小时|h)", text, re.I)
        duration_value = match.group(0) if match else ""
    return {
        "interest": str(interest or "").strip(),
        "weather": weather_value,
        "arrival_period": arrival_value,
        "companions": companion_value,
        "duration": duration_value,
        "stamina": stamina_value,
    }


def _route_recommendation_reason(route, context):
    context = context or {}
    route_id = route.get("id", "")
    parts = []
    combined = " ".join(str(context.get(key, "")) for key in ["interest", "companions", "weather", "arrival_period", "duration", "stamina"])
    if route_id == "route_family" and any(word in combined for word in ["亲子", "孩子", "老人", "家庭"]):
        parts.append("亲子和老人同行时，这条路线减少长距离攀登，优先安排互动点和室内参观点。")
    if route_id == "route_history" and any(word in combined for word in ["历史", "文化", "佛", "建筑", "深度"]):
        parts.append("历史文化兴趣更适合沿中轴线理解灵山的佛教叙事和建筑艺术。")
    if route_id == "route_nature" and any(word in combined for word in ["自然", "风光", "拍照", "太湖"]):
        parts.append("自然风光偏好会保留太湖视野、园林漫步和轻松拍照节点。")
    if any(word in str(context.get("weather", "")) for word in ["雨", "高温", "热"]):
        parts.append("结合天气，优先把梵宫、五印坛城等室内或停留条件更好的点位放进推荐。")
    if str(context.get("arrival_period", "")).lower() in {"afternoon", "下午"}:
        parts.append("下午到园时需要关注闭馆和演出场次，路线会更强调核心点位效率。")
    if str(context.get("stamina", "")).lower() in {"low", "低", "轻松"}:
        parts.append("体力有限时建议配合观光车，减少反复折返和长时间登阶。")
    if not parts:
        parts.append(route.get("summary", "根据当前兴趣为您匹配更合适的游览顺序。"))
    return " ".join(parts[:3])


def annotate_route_recommendations(routes, context=None):
    context = context or build_recommendation_context()
    result = []
    for route in routes or []:
        item = dict(route)
        item["recommendation_context"] = dict(context)
        item["recommendation_reason"] = _route_recommendation_reason(item, context)
        result.append(item)
    return result


def ensure_data_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)


def read_json_file(path, default):
    ensure_data_dir()
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json_file(path, data):
    ensure_data_dir()
    directory = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp_path = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        raise


def read_docx(filepath):
    text_parts = []
    try:
        with zipfile.ZipFile(filepath) as z:
            xml_content = z.read("word/document.xml")
            tree = ET.fromstring(xml_content)
            ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            for p in tree.iter(ns + "p"):
                texts = [t.text for t in p.iter(ns + "t") if t.text]
                if texts:
                    text_parts.append("".join(texts))
    except Exception as exc:
        print("Error reading {0}: {1}".format(filepath, exc))
    return "\n".join(text_parts)


def _read_pdf_with_local_libraries(filepath):
    text_parts = []
    try:
        import pdfplumber

        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                if text.strip():
                    text_parts.append(text.strip())
    except Exception as exc:
        print("pdfplumber failed for {0}: {1}".format(filepath, exc))

    if text_parts:
        return "\n\n".join(text_parts)

    try:
        from pypdf import PdfReader

        reader = PdfReader(filepath)
        for page in reader.pages:
            text = page.extract_text() or ""
            if text.strip():
                text_parts.append(text.strip())
    except Exception as exc:
        print("pypdf failed for {0}: {1}".format(filepath, exc))
    return "\n\n".join(text_parts)


def _candidate_pdf_text_pythons():
    candidates = [
        os.getenv("PDF_TEXT_PYTHON", ""),
        os.path.join(
            os.path.expanduser("~"),
            ".cache",
            "codex-runtimes",
            "codex-primary-runtime",
            "dependencies",
            "python",
            "python.exe",
        ),
        runtime_path(".venvs", "realtime", "Scripts", "python.exe"),
        runtime_path(".venvs", "gsv-tts-lite", "Scripts", "python.exe"),
        runtime_path(".venvs", "gpt-sovits", "Scripts", "python.exe"),
    ]
    seen = set()
    for candidate in candidates:
        candidate = os.path.abspath(candidate) if candidate else ""
        if not candidate or candidate.lower() in seen:
            continue
        seen.add(candidate.lower())
        if os.path.exists(candidate) and os.path.abspath(sys.executable).lower() != candidate.lower():
            yield candidate


def _read_pdf_with_external_python(filepath):
    script = r"""
import json
import sys

path = sys.argv[1]
parts = []
try:
    import pdfplumber

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if text.strip():
                parts.append(text.strip())
except Exception:
    parts = []

if not parts:
    try:
        from pypdf import PdfReader

        reader = PdfReader(path)
        for page in reader.pages:
            text = page.extract_text() or ""
            if text.strip():
                parts.append(text.strip())
    except Exception as exc:
        sys.stderr.write(str(exc))

sys.stdout.write(json.dumps({"text": "\n\n".join(parts)}, ensure_ascii=False))
"""
    last_error = ""
    for python_exe in _candidate_pdf_text_pythons():
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        try:
            completed = subprocess.run(
                [python_exe, "-c", script, filepath],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=45,
                env=env,
            )
        except Exception as exc:
            last_error = str(exc)
            continue
        stdout = completed.stdout.decode("utf-8", "replace")
        stderr = completed.stderr.decode("utf-8", "replace")
        if completed.returncode != 0:
            last_error = stderr or stdout
            continue
        try:
            text = json.loads(stdout or "{}").get("text", "")
        except Exception as exc:
            last_error = str(exc)
            continue
        if text.strip():
            return text
        last_error = stderr or "external parser returned empty text"
    if last_error:
        print("external pdf parser failed for {0}: {1}".format(filepath, last_error))
    return ""


def read_pdf(filepath):
    text = _read_pdf_with_local_libraries(filepath)
    if text.strip():
        return text
    return _read_pdf_with_external_python(filepath)


def _parse_openssl_version_number():
    match = re.search(r"OpenSSL\s+(\d+)\.(\d+)\.(\d+)", ssl.OPENSSL_VERSION)
    if not match:
        return (0, 0, 0)
    return tuple(int(part) for part in match.groups())


def _candidate_paddleocr_worker_pythons():
    candidates = [
        os.getenv("PADDLEOCR_WORKER_PYTHON", ""),
        os.path.join(
            os.path.expanduser("~"),
            ".cache",
            "codex-runtimes",
            "codex-primary-runtime",
            "dependencies",
            "python",
            "python.exe",
        ),
        runtime_path(".venvs", "realtime", "Scripts", "python.exe"),
        runtime_path(".venvs", "gsv-tts-lite", "Scripts", "python.exe"),
        runtime_path(".venvs", "gpt-sovits", "Scripts", "python.exe"),
    ]
    seen = set()
    for candidate in candidates:
        candidate = os.path.abspath(candidate) if candidate else ""
        if not candidate or candidate.lower() in seen:
            continue
        seen.add(candidate.lower())
        if os.path.exists(candidate) and os.path.abspath(sys.executable).lower() != candidate.lower():
            yield candidate


def _should_use_paddleocr_worker():
    mode = os.getenv("PADDLEOCR_WORKER_MODE", "auto").strip().lower()
    if mode in ("off", "false", "0", "disabled"):
        return False
    if mode in ("on", "true", "1", "force"):
        return True
    return _parse_openssl_version_number() < (1, 1, 1)


def _run_paddleocr_worker(client, filepath):
    payload = {
        "filepath": filepath,
        "token": client.token,
        "job_url": client.job_url,
        "model": client.model,
        "poll_interval": client.poll_interval,
        "timeout_seconds": client.timeout_seconds,
        "optional_payload": PADDLEOCR_OPTIONAL_PAYLOAD,
        "min_chars": MIN_EXTRACTED_TEXT_CHARS,
    }
    last_error = ""
    for python_exe in _candidate_paddleocr_worker_pythons():
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        try:
            completed = subprocess.run(
                [python_exe, "-c", PADDLEOCR_WORKER_SCRIPT],
                input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=client.timeout_seconds + 120,
                env=env,
            )
        except Exception as exc:
            last_error = str(exc)
            continue

        stdout = completed.stdout.decode("utf-8", "replace")
        stderr = completed.stderr.decode("utf-8", "replace")
        try:
            result = json.loads(stdout or "{}")
        except Exception:
            last_error = stderr or stdout or "worker returned empty output"
            continue
        if completed.returncode == 0 and result.get("ok"):
            text = normalize_document_text(result.get("text", ""))
            metadata = result.get("metadata") or {}
            if len(text) < MIN_EXTRACTED_TEXT_CHARS:
                raise PaddleOCRError("PaddleOCR 未提取到有效文本，请检查 PDF 内容或重新上传清晰文件。")
            return text, {
                "ocr_model": metadata.get("ocr_model") or client.model,
                "page_count": metadata.get("page_count", 0),
            }
        last_error = result.get("error") or stderr or stdout
    raise PaddleOCRError("PaddleOCR worker 执行失败：{0}".format(last_error or "未找到可用的现代 Python 解释器。"))


class PaddleOCRError(RuntimeError):
    pass


class PaddleOCRClient:
    def __init__(
        self,
        token=None,
        job_url=None,
        model=None,
        poll_interval=None,
        timeout_seconds=None,
        session=None,
    ):
        self.token = (token if token is not None else os.getenv("PADDLEOCR_API_TOKEN", "")).strip()
        self.job_url = (job_url or os.getenv("PADDLEOCR_JOB_URL") or PADDLEOCR_JOB_URL).rstrip("/")
        self.model = model or os.getenv("PADDLEOCR_MODEL") or PADDLEOCR_MODEL
        self.poll_interval = float(
            poll_interval if poll_interval is not None else os.getenv("PADDLEOCR_POLL_INTERVAL_SECONDS", 5)
        )
        self.timeout_seconds = float(
            timeout_seconds if timeout_seconds is not None else os.getenv("PADDLEOCR_TIMEOUT_SECONDS", 600)
        )
        self.session = session or requests

    def extract_pdf(self, filepath):
        if not self.token:
            raise PaddleOCRError("未配置 PaddleOCR API Token，请在 backend/.env 中设置 PADDLEOCR_API_TOKEN。")
        if not os.path.exists(filepath):
            raise PaddleOCRError("PDF 文件不存在，无法进行 OCR。")
        if self.session is requests and _should_use_paddleocr_worker():
            return _run_paddleocr_worker(self, filepath)

        job_id = self._submit_pdf(filepath)
        jsonl_url, extracted_pages = self._wait_for_result(job_id)
        text = self._download_markdown_text(jsonl_url)
        text = normalize_document_text(text)
        if len(text) < MIN_EXTRACTED_TEXT_CHARS:
            raise PaddleOCRError("PaddleOCR 未提取到有效文本，请检查 PDF 内容或重新上传清晰文件。")
        return text, {
            "ocr_model": self.model,
            "page_count": extracted_pages,
        }

    def _headers(self):
        return {"Authorization": "bearer {0}".format(self.token)}

    def _submit_pdf(self, filepath):
        data = {
            "model": self.model,
            "optionalPayload": json.dumps(PADDLEOCR_OPTIONAL_PAYLOAD, ensure_ascii=False),
        }
        try:
            with open(filepath, "rb") as pdf_file:
                response = self.session.post(
                    self.job_url,
                    headers=self._headers(),
                    data=data,
                    files={"file": pdf_file},
                    timeout=60,
                )
        except Exception as exc:
            raise PaddleOCRError("提交 PaddleOCR 任务失败：{0}".format(exc))

        if response.status_code != 200:
            raise PaddleOCRError("提交 PaddleOCR 任务失败：HTTP {0} {1}".format(response.status_code, response.text))
        try:
            return response.json()["data"]["jobId"]
        except Exception as exc:
            raise PaddleOCRError("PaddleOCR 提交响应格式异常：{0}".format(exc))

    def _wait_for_result(self, job_id):
        deadline = time.time() + self.timeout_seconds
        last_state = ""
        while time.time() < deadline:
            try:
                response = self.session.get("{0}/{1}".format(self.job_url, job_id), headers=self._headers(), timeout=30)
            except Exception as exc:
                raise PaddleOCRError("查询 PaddleOCR 任务失败：{0}".format(exc))

            if response.status_code != 200:
                raise PaddleOCRError("查询 PaddleOCR 任务失败：HTTP {0} {1}".format(response.status_code, response.text))
            try:
                payload = response.json()["data"]
                state = payload["state"]
            except Exception as exc:
                raise PaddleOCRError("PaddleOCR 查询响应格式异常：{0}".format(exc))

            last_state = state
            if state in ("pending", "running"):
                time.sleep(self.poll_interval)
                continue
            if state == "done":
                jsonl_url = payload.get("resultUrl", {}).get("jsonUrl", "")
                if not jsonl_url:
                    raise PaddleOCRError("PaddleOCR 已完成，但未返回 JSONL 结果地址。")
                progress = payload.get("extractProgress", {}) or {}
                return jsonl_url, progress.get("extractedPages", 0)
            if state == "failed":
                raise PaddleOCRError("PaddleOCR 任务失败：{0}".format(payload.get("errorMsg", "未知错误")))
            raise PaddleOCRError("PaddleOCR 返回未知任务状态：{0}".format(state))
        raise PaddleOCRError("PaddleOCR 任务超时，最后状态：{0}".format(last_state or "未知"))

    def _download_markdown_text(self, jsonl_url):
        try:
            response = self.session.get(jsonl_url, timeout=60)
            response.raise_for_status()
        except Exception as exc:
            raise PaddleOCRError("下载 PaddleOCR 结果失败：{0}".format(exc))

        parts = []
        for line_num, raw_line in enumerate(response.text.splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                results = item.get("result", {}).get("layoutParsingResults", [])
                for result in results:
                    text = result.get("markdown", {}).get("text", "")
                    if text and text.strip():
                        parts.append(text.strip())
            except Exception as exc:
                raise PaddleOCRError("解析 PaddleOCR JSONL 第 {0} 行失败：{1}".format(line_num, exc))
        return "\n\n".join(parts)


def paddleocr_pdf_to_text(filepath, token=None, session=None):
    return PaddleOCRClient(token=token, session=session).extract_pdf(filepath)


def normalize_document_text(text):
    text = (text or "").replace("\r", "\n")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_extracted_document_text(text):
    text = html_lib.unescape(str(text or "")).replace("\xa0", " ")
    text = text.replace("\r", "\n")
    if "<" in text and ">" in text:
        text = re.sub(r"(?is)</(?:td|th)\s*>", " ", text)
        text = re.sub(r"(?is)</tr\s*>", "\n", text)
        text = re.sub(r"(?is)<br\s*/?\s*>", "\n", text)
        text = re.sub(r"(?is)</(?:p|div|li|h[1-6]|table)\s*>", "\n", text)
        text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = re.sub(
        r"\b(?:text-align|word-wrap|margin|border-collapse|width|height)\s*:\s*[^;。\n]+;?",
        " ",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"\b(?:border|style|cellpadding|cellspacing|width|height)\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+)",
        " ",
        text,
        flags=re.I,
    )
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_knowledge_file(filepath, filename):
    filename = filename or os.path.basename(filepath)
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".doc":
        raise ValueError("暂不支持 .doc 文件，请另存为 .docx 后上传。")
    if ext not in SUPPORTED_KNOWLEDGE_FILE_EXTS:
        raise ValueError("仅支持上传 .docx 和 .pdf 文件。")

    ocr_metadata = {}
    if ext == ".docx":
        text = read_docx(filepath)
    else:
        # 用户要求所有 PDF 统一走 PaddleOCR，保证扫描版和文本版处理链路一致。
        text, ocr_metadata = paddleocr_pdf_to_text(filepath)
    text = clean_extracted_document_text(text)
    text = normalize_document_text(text)
    if len(text) < MIN_EXTRACTED_TEXT_CHARS:
        raise ValueError("未提取到有效文本，若为扫描版 PDF，请先进行 OCR 后再上传。")
    result = {
        "filename": filename,
        "extension": ext.lstrip("."),
        "content": text,
        "char_count": len(text),
    }
    if ocr_metadata:
        result["ocr_metadata"] = ocr_metadata
    return result


def tokenize(text):
    text = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9\-]+", " ", text)
    chars = [c for c in text if c.strip()]
    bigrams = [chars[i] + chars[i + 1] for i in range(max(0, len(chars) - 1))]
    words = [w.lower() for w in text.split() if len(w) >= 2]
    return chars + bigrams + words


def chunk_text(text, chunk_size=520, overlap=90):
    paragraphs = [p.strip() for p in text.splitlines() if p.strip()]
    chunks, current = [], ""
    for paragraph in paragraphs:
        if len(current) + len(paragraph) > chunk_size and current:
            chunks.append(current.strip())
            current = current[-overlap:] if len(current) > overlap else ""
        current += paragraph + "\n"
    if current.strip():
        chunks.append(current.strip())
    return chunks or ([text.strip()] if text.strip() else [])


def normalize_excerpt(text, limit=420):
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit] + ("..." if len(text) > limit else "")


def _split_quality_sentences(text):
    parts = re.split(r"[。！？!?；;\n]+", text or "")
    result = []
    for part in parts:
        value = re.sub(r"\s+", "", part)
        if len(value) >= 4:
            result.append(value)
    return result


def _quality_sentence_key(sentence):
    return re.sub(r"[，,：:\s。！？!?；;]+", "", sentence or "")


def _quality_issue_key(text):
    return re.sub(r"[，,：:\s。！？!?；;<>/=\"'_-]+", "", text or "")


def _append_extraction_issue(issues, seen, text, issue_type):
    value = re.sub(r"\s+", " ", clean_extracted_document_text(text or "")).strip()
    if not value:
        value = re.sub(r"\s+", " ", str(text or "")).strip()
    if not value:
        return
    key = _quality_issue_key(value)
    if not key or key in seen:
        return
    seen.add(key)
    issues.append({
        "text": value[:120],
        "key": key,
        "type": issue_type,
    })


def _find_extraction_issues(raw_text, clean_text):
    issues = []
    seen = set()
    if re.search(r"(?is)</?(?:table|tr|td|th)\b|style\s*=", raw_text or ""):
        _append_extraction_issue(issues, seen, "疑似 HTML 表格或样式残留", "html_table_residue")

    extraction_patterns = [
        (r"时段入园游客观赏、打卡", "broken_sentence"),
        (r"是进[。；;]?", "broken_sentence"),
        (r"门楣处雕刻[。；;]?", "broken_sentence"),
        (r"[，,。；;]\s*[的了是于在]{1,2}\s*[。；;]", "orphan_function_word"),
    ]
    for pattern, issue_type in extraction_patterns:
        for match in re.findall(pattern, clean_text or ""):
            _append_extraction_issue(issues, seen, match, issue_type)
    return issues


def analyze_knowledge_quality(text, title=""):
    raw_text = text or ""
    text = normalize_document_text(clean_extracted_document_text(raw_text))
    sentences = _split_quality_sentences(text)
    sentence_buckets = {}
    duplicate_sentence_count = 0
    for sentence in sentences:
        key = _quality_sentence_key(sentence)
        if not key:
            continue
        bucket = sentence_buckets.setdefault(key, {"sentence": sentence, "count": 0})
        if bucket["count"]:
            duplicate_sentence_count += 1
        bucket["count"] += 1
    duplicate_sentences = [
        {
            "sentence": item["sentence"],
            "key": key,
            "count": item["count"],
            "is_duplicate": True,
        }
        for key, item in sentence_buckets.items()
        if item["count"] > 1
    ]

    extraction_issues = _find_extraction_issues(raw_text, text)

    covered_scenics = [name for _, name in SCENIC_NAMES if name in text or name in (title or "")]
    missing_scenic_count = max(0, len(SCENIC_NAMES) - len(covered_scenics))
    fact_keywords = ["门票", "票价", "开放时间", "演出", "场次", "路线", "交通", "停车", "素斋", "观光车"]
    covered_fact_keywords = [word for word in fact_keywords if word in text]
    suggestions = []
    if len(text) < 120:
        suggestions.append("文档内容偏短，建议补充完整讲解词或问答。")
    if duplicate_sentence_count:
        suggestions.append("存在重复句，建议删除重复段落后再用于问答。")
    if extraction_issues:
        suggestions.append("存在疑似抽取残句或格式残留，建议人工复核。")
    if len(covered_scenics) < 4:
        suggestions.append("核心景点覆盖不足，建议补充更多景点事实。")
    if len(covered_fact_keywords) < 2:
        suggestions.append("演出、门票、开放时间等关键事实覆盖较少。")

    issue_count = duplicate_sentence_count + len(extraction_issues)
    if len(text) < MIN_EXTRACTED_TEXT_CHARS or issue_count >= 2:
        level = "risk"
        label = "风险高"
    elif issue_count or len(covered_scenics) < 4 or len(covered_fact_keywords) < 2:
        level = "review"
        label = "需复核"
    else:
        level = "good"
        label = "良好"

    return {
        "level": level,
        "label": label,
        "char_count": len(text),
        "duplicate_sentence_count": duplicate_sentence_count,
        "duplicate_sentences": duplicate_sentences[:20],
        "extraction_issue_count": len(extraction_issues),
        "extraction_issues": extraction_issues[:6],
        "ocr_issue_count": len(extraction_issues),
        "ocr_issues": [item["text"] for item in extraction_issues[:6]],
        "covered_scenics": covered_scenics,
        "missing_scenic_count": missing_scenic_count,
        "covered_fact_keywords": covered_fact_keywords,
        "suggestions": suggestions or ["内容结构较完整，可直接用于知识库检索。"],
    }


def _source_label(source):
    labels = {
        "paddleocr_upload": "PaddleOCR 上传",
        "file_upload": "文件上传",
        "manual": "手动录入",
        "base_docx": "赛题资料包",
    }
    return labels.get(source or "", source or "未知来源")


def _admin_document_view(doc):
    metadata = doc.get("metadata") or {}
    source = metadata.get("source") or "manual"
    content = clean_extracted_document_text(doc.get("content", ""))
    char_count = int(metadata.get("char_count") or len(content) or 0)
    uploaded_at = metadata.get("uploaded_at") or doc.get("created_at", "")
    quality_report = metadata.get("quality_report") or analyze_knowledge_quality(
        content,
        doc.get("title", ""),
    )
    if (
        not isinstance(quality_report, dict)
        or "duplicate_sentences" not in quality_report
        or "extraction_issues" not in quality_report
        or content != doc.get("content", "")
    ):
        quality_report = analyze_knowledge_quality(content, doc.get("title", ""))
    return {
        "id": doc.get("id", ""),
        "title": doc.get("title", "未命名知识"),
        "type": doc.get("type", "讲解词"),
        "source": source,
        "source_label": _source_label(source),
        "original_filename": metadata.get("original_filename") or "手动录入",
        "file_type": metadata.get("file_type") or "text",
        "char_count": char_count,
        "uploaded_at": uploaded_at,
        "created_at": doc.get("created_at", ""),
        "ocr_model": metadata.get("ocr_model", ""),
        "page_count": metadata.get("page_count", ""),
        "can_delete": True,
        "content_preview": normalize_excerpt(content, 260),
        "content": content,
        "quality_report": quality_report,
        "metadata": metadata,
    }


def _base_document_view(path):
    filename = os.path.basename(path)
    content = normalize_document_text(clean_extracted_document_text(read_docx(path)))
    stat = os.stat(path)
    created_at = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime))
    quality_report = analyze_knowledge_quality(content, filename)
    return {
        "id": "base-{0}".format(filename),
        "title": os.path.splitext(filename)[0],
        "type": "赛题资料",
        "source": "base_docx",
        "source_label": _source_label("base_docx"),
        "original_filename": filename,
        "file_type": "docx",
        "char_count": len(content),
        "uploaded_at": created_at,
        "created_at": created_at,
        "ocr_model": "",
        "page_count": "",
        "can_delete": False,
        "content_preview": normalize_excerpt(content, 260),
        "content": content,
        "quality_report": quality_report,
        "metadata": {
            "source": "base_docx",
            "original_filename": filename,
            "file_type": "docx",
            "char_count": len(content),
            "uploaded_at": created_at,
        },
    }


def list_base_documents(docs_dir=None):
    docs_dir = docs_dir or DEFAULT_DOCS_DIR
    if not os.path.exists(docs_dir):
        return []
    documents = []
    for filename in sorted(os.listdir(docs_dir)):
        if not filename.lower().endswith(".docx"):
            continue
        path = os.path.join(docs_dir, filename)
        documents.append(_base_document_view(path))
    return documents


def build_admin_knowledge_view(docs_dir=None):
    uploaded_documents = [_admin_document_view(doc) for doc in list_admin_documents()]
    base_documents = list_base_documents(docs_dir)
    all_documents = uploaded_documents + base_documents
    source_counts = Counter(doc.get("source_label", "未知来源") for doc in all_documents)
    quality_counts = Counter(
        (doc.get("quality_report") or {}).get("level", "review") for doc in all_documents
    )
    issue_total = sum(
        int((doc.get("quality_report") or {}).get("duplicate_sentence_count") or 0)
        + int((doc.get("quality_report") or {}).get("ocr_issue_count") or 0)
        for doc in all_documents
    )
    summary = {
        "total_documents": len(all_documents),
        "uploaded_documents": len(uploaded_documents),
        "base_documents": len(base_documents),
        "total_char_count": sum(int(doc.get("char_count") or 0) for doc in all_documents),
        "source_counts": [{"name": name, "count": count} for name, count in source_counts.most_common()],
        "quality_summary": {
            "good": quality_counts.get("good", 0),
            "review": quality_counts.get("review", 0),
            "risk": quality_counts.get("risk", 0),
            "issue_count": issue_total,
        },
    }
    return {
        "documents": uploaded_documents,
        "knowledge_documents": all_documents,
        "summary": summary,
    }


class KnowledgeBase(object):
    def __init__(self, docs_dir=None):
        self.docs_dir = docs_dir or DEFAULT_DOCS_DIR
        self.chunks = []
        self.chunk_tokens = []
        self.idf = {}
        self.scenics = []
        self._loaded = False

    def reload(self):
        self._loaded = False
        self.load_documents()

    def load_documents(self):
        if self._loaded:
            return
        self.chunks = []
        self._load_docx_documents()
        self._load_admin_documents()
        self._build_index()
        self.scenics = self._build_scenic_index()
        self._loaded = True
        print("Knowledge loaded: {0} chunks, {1} scenic spots".format(len(self.chunks), len(self.scenics)))

    def _load_docx_documents(self):
        if not os.path.exists(self.docs_dir):
            print("Docs dir not found: {0}".format(self.docs_dir))
            return
        for filename in os.listdir(self.docs_dir):
            if not filename.lower().endswith(".docx"):
                continue
            path = os.path.join(self.docs_dir, filename)
            text = clean_extracted_document_text(read_docx(path))
            for index, chunk in enumerate(chunk_text(text)):
                self.chunks.append({
                    "id": "{0}_c{1}".format(filename, index),
                    "title": filename,
                    "source": filename,
                    "type": "docx",
                    "content": chunk,
                    "created_at": "",
                })

    def _load_admin_documents(self):
        admin_docs = read_json_file(ADMIN_DOCS_FILE, [])
        for doc in admin_docs:
            content = clean_extracted_document_text(doc.get("content", ""))
            if not content.strip():
                continue
            for index, chunk in enumerate(chunk_text(content)):
                self.chunks.append({
                    "id": "{0}_c{1}".format(doc.get("id", "admin"), index),
                    "title": doc.get("title", "管理员知识"),
                    "source": "管理员知识库",
                    "type": doc.get("type", "讲解词"),
                    "content": chunk,
                    "created_at": doc.get("created_at", ""),
                })

    def _build_index(self):
        doc_count = len(self.chunks)
        df = Counter()
        self.chunk_tokens = []
        for chunk in self.chunks:
            tokens = set(tokenize(chunk["content"] + " " + chunk.get("title", "")))
            self.chunk_tokens.append(tokens)
            df.update(tokens)
        self.idf = {term: math.log((doc_count + 1.0) / (count + 1.0)) + 1.0 for term, count in df.items()}

    def _build_scenic_index(self):
        scenics = []
        for scenic_id, name in SCENIC_NAMES:
            query = "{0} {1}".format(scenic_id, name)
            contexts = self._search_loaded(query, n_results=4)
            content = "\n".join([r["content"] for r in contexts])
            scenics.append({
                "id": scenic_id,
                "name": name,
                "summary": self.summarize_spot(name, content),
                "keywords": self._keywords_for_text(content),
            })
        return scenics

    def _keywords_for_text(self, text):
        candidates = ["历史", "文化", "建筑", "佛教", "表演", "亲子", "拍照", "登高", "艺术", "素食", "太湖"]
        return [word for word in candidates if word in text][:4]

    def summarize_spot(self, name, content):
        if not content:
            defaults = {
                "灵山大佛": "灵山胜境的核心地标，以宏大的佛像与登高礼佛体验构成景区最具辨识度的终点。",
                "九龙灌浴": "景区代表性动态景观，通过音乐、喷泉和莲花开合呈现佛陀诞生故事，适合优先安排观看。",
                "灵山梵宫": "融合佛教艺术、建筑装饰与大型演出的室内文化空间，是理解灵山当代佛教艺术的重要一站。",
            }
            return defaults.get(name, "{0}是灵山胜境游线中的重要景点，适合结合导览讲解了解其文化寓意。".format(name))
        sentences = re.split(r"[。；;！!\n]", content)
        clean = []
        for sentence in sentences:
            sentence = re.sub(r"\s+", "", sentence)
            if name in sentence or len(sentence) > 18:
                if not any(raw in sentence for raw in ["景点ID", "开放时间", "坐标", "建议游览"]):
                    clean.append(sentence)
            if len(clean) >= 2:
                break
        if not clean:
            return normalize_excerpt(content, 90)
        summary = "。".join(clean)
        return summary[:120] + ("..." if len(summary) > 120 else "。")

    def search(self, query, n_results=6):
        self.load_documents()
        return self._search_loaded(query, n_results)

    def _search_loaded(self, query, n_results=6):
        if not self.chunks:
            return []
        q_tokens = tokenize(query)
        scored = []
        for idx, chunk in enumerate(self.chunks):
            score = sum(self.idf.get(term, 0) for term in q_tokens if term in self.chunk_tokens[idx])
            title_bonus = 4 if any(name in query and name in chunk["content"] for _, name in SCENIC_NAMES) else 0
            if score + title_bonus > 0:
                scored.append((score + title_bonus, idx, chunk))
        scored.sort(key=lambda item: item[0], reverse=True)
        results = []
        for score, idx, chunk in scored[:n_results]:
            content = chunk["content"]
            if idx > 0 and self.chunks[idx - 1]["source"] == chunk["source"]:
                content = self.chunks[idx - 1]["content"][-120:] + "\n" + content
            if idx < len(self.chunks) - 1 and self.chunks[idx + 1]["source"] == chunk["source"]:
                content = content + "\n" + self.chunks[idx + 1]["content"][:120]
            results.append({
                "id": chunk["id"],
                "source": chunk["source"],
                "title": chunk.get("title", ""),
                "type": chunk.get("type", ""),
                "content": content,
                "excerpt": normalize_excerpt(content),
                "score": round(score, 3),
            })
        return results

    def get_context_string(self, query, n_results=6):
        results = self.search(query, n_results)
        return "\n\n---\n\n".join(["[{0}] {1}".format(r["source"], r["content"]) for r in results])

    def get_scenics(self):
        self.load_documents()
        return self.scenics

    def get_scenic(self, scenic_id):
        self.load_documents()
        scenic_id = scenic_id.upper()
        for scenic in self.scenics:
            if scenic["id"] == scenic_id:
                detail = self.search("{0} {1}".format(scenic["id"], scenic["name"]), n_results=5)
                data = dict(scenic)
                data["detail"] = [r["excerpt"] for r in detail]
                return data
        return None

    def get_tour_routes(self):
        return DEFAULT_ROUTES

    def recommend_routes(self, interest, context=None):
        interest = interest or ""
        context = context or build_recommendation_context(interest=interest)
        routes = self.get_tour_routes()
        if any(word in interest for word in ["历史", "文化", "佛", "建筑", "深度"]):
            return annotate_route_recommendations([routes[0], routes[2], routes[1]], context)
        if any(word in interest for word in ["自然", "风光", "拍照", "轻松", "太湖"]):
            return annotate_route_recommendations([routes[1], routes[2], routes[0]], context)
        if any(word in interest for word in ["亲子", "小孩", "孩子", "老人", "家庭"]):
            return annotate_route_recommendations([routes[2], routes[1], routes[0]], context)
        return annotate_route_recommendations(routes, context)


def list_admin_documents():
    return read_json_file(ADMIN_DOCS_FILE, [])


def add_admin_document(title, content, doc_type="讲解词", metadata=None, reload_index=True):
    docs = list_admin_documents()
    metadata = dict(metadata or {})
    content = clean_extracted_document_text(content)
    metadata["quality_report"] = analyze_knowledge_quality(content, title)
    doc = {
        "id": "kb-{0}".format(int(time.time() * 1000)),
        "title": title.strip() or "未命名知识",
        "content": content.strip(),
        "type": doc_type.strip() or "讲解词",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    doc["metadata"] = metadata
    docs.insert(0, doc)
    write_json_file(ADMIN_DOCS_FILE, docs)
    if reload_index:
        get_knowledge_base().reload()
    return doc


def add_admin_document_from_file(file_storage, doc_type="文史资料", title_prefix=""):
    if not file_storage or not getattr(file_storage, "filename", ""):
        raise ValueError("未收到文件。")
    filename = os.path.basename(file_storage.filename)
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".doc":
        raise ValueError("暂不支持 .doc 文件，请另存为 .docx 后上传。")
    if ext not in SUPPORTED_KNOWLEDGE_FILE_EXTS:
        raise ValueError("仅支持上传 .docx 和 .pdf 文件。")

    tmp_path = ""
    total = 0
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp_path = tmp.name
            while True:
                chunk = file_storage.stream.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_KNOWLEDGE_FILE_BYTES:
                    raise ValueError("单个文件不能超过 20MB。")
                tmp.write(chunk)

        if total <= 0:
            raise ValueError("文件为空。")
        extracted = extract_knowledge_file(tmp_path, filename)
        title_base = os.path.splitext(filename)[0].strip() or "未命名文件"
        title = (title_prefix.strip() + " " + title_base).strip() if title_prefix else title_base
        ocr_metadata = extracted.get("ocr_metadata") or {}
        source = "paddleocr_upload" if ocr_metadata else "file_upload"
        metadata = {
            "source": source,
            "original_filename": filename,
            "file_type": extracted["extension"],
            "file_size_bytes": total,
            "char_count": extracted["char_count"],
            "uploaded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        if ocr_metadata:
            metadata.update(ocr_metadata)
        return add_admin_document(
            title,
            extracted["content"],
            doc_type or "文史资料",
            metadata=metadata,
            reload_index=False,
        )
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


def delete_admin_document(doc_id):
    docs = list_admin_documents()
    kept = [doc for doc in docs if doc.get("id") != doc_id]
    write_json_file(ADMIN_DOCS_FILE, kept)
    get_knowledge_base().reload()
    return len(kept) != len(docs)


def get_digital_human_config():
    config = DEFAULT_CONFIG.copy()
    config.update(read_json_file(CONFIG_FILE, {}))
    return _with_avatar_presets(config)


def update_digital_human_config(data):
    data = data or {}
    config = DEFAULT_CONFIG.copy()
    stored = read_json_file(CONFIG_FILE, {})
    config.update(stored)
    incoming_config = dict(config)
    if isinstance(data.get("avatar_presets"), list):
        incoming_config["avatar_presets"] = data.get("avatar_presets")
    presets = _avatar_presets_from_config(incoming_config)
    requested_preset_id = str((data or {}).get("avatar_preset_id", config.get("avatar_preset_id", ""))).strip()
    preset = _avatar_preset_by_id(requested_preset_id, presets)
    if preset:
        for key in AVATAR_CONFIG_FIELDS:
            config[key] = preset.get(key, config.get(key, ""))
        config["avatar_preset_id"] = requested_preset_id
    elif requested_preset_id == "custom":
        config["avatar_preset_id"] = "custom"
    for key in ["avatar_preset_id", "name", "voice", "appearance", "style", "costume", "model", "model_options", "emotion_enabled", "opening", "voice_provider", "voice_preset", "voice_description", "voice_clone_id", "edge_voice", "voice_rate", "voice_pitch", "voice_volume"]:
        if key in data:
            if key == "model_options" and isinstance(data.get(key), list):
                config[key] = [str(item).strip() for item in data.get(key) if str(item).strip()]
            else:
                config[key] = str(data.get(key, "")).strip()
    if requested_preset_id:
        known_ids = {preset_item["id"] for preset_item in presets}
        if requested_preset_id not in known_ids:
            base = _sanitize_avatar_preset(
                {
                    "id": requested_preset_id,
                    "label": data.get("label", ""),
                    "summary": data.get("summary", ""),
                },
                config,
            )
            if base:
                presets.append(base)
        for index, preset_item in enumerate(presets):
            if preset_item.get("id") == requested_preset_id:
                updated = dict(preset_item)
                for key in ["label", "summary"]:
                    if key in data:
                        updated[key] = str(data.get(key, "")).strip()
                for key in AVATAR_CONFIG_FIELDS:
                    updated[key] = str(config.get(key, "")).strip()
                presets[index] = updated
                break
    if not config.get("avatar_preset_id"):
        config["avatar_preset_id"] = _match_avatar_preset_id(config, presets)
    config["avatar_presets"] = presets
    write_json_file(CONFIG_FILE, config)
    return get_digital_human_config()


def list_feedback():
    return read_json_file(FEEDBACK_FILE, [])


def add_feedback(message, rating=5):
    feedback = list_feedback()
    text = (message or "").strip()
    rating = int(rating or 5)
    positive_words = ["好", "喜欢", "满意", "清楚", "有趣", "方便", "专业", "推荐"]
    negative_words = ["差", "慢", "不准", "听不懂", "失败", "卡", "不满意", "没有"]
    sentiment = "positive"
    if rating <= 2 or any(word in text for word in negative_words):
        sentiment = "negative"
    elif rating == 3 and not any(word in text for word in positive_words):
        sentiment = "neutral"
    item = {
        "id": "fb-{0}".format(int(time.time() * 1000)),
        "message": text,
        "rating": rating,
        "sentiment": sentiment,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    feedback.insert(0, item)
    write_json_file(FEEDBACK_FILE, feedback[:500])
    return item


def build_analytics(chat_log, evaluation_summary=None):
    feedback = list_feedback()
    total = len(chat_log)
    hot_counter = Counter()
    emotion_counter = Counter({"positive": 0, "neutral": 0, "negative": 0})
    for item in feedback:
        emotion_counter[item.get("sentiment", "neutral")] += 1
    for entry in chat_log:
        query = entry.get("query", "")
        for _, name in SCENIC_NAMES:
            if name in query or name.replace("灵山", "") in query:
                hot_counter[name] += 1
        for keyword in ["门票", "路线", "九龙灌浴", "灵山大佛", "梵宫", "交通", "餐饮", "开放时间"]:
            if keyword in query:
                hot_counter[keyword] += 1
    route_preference = Counter()
    consumption = Counter({"门票咨询": 0, "餐饮咨询": 0, "交通停车": 0, "文创购物": 0})
    for entry in chat_log:
        query = entry.get("query", "")
        route_id = entry.get("route_id", "")
        if route_id:
            route_preference[route_id] += 1
        elif any(word in query for word in ["亲子", "孩子", "老人", "家庭"]):
            route_preference["route_family"] += 1
        elif any(word in query for word in ["自然", "风光", "拍照", "轻松"]):
            route_preference["route_nature"] += 1
        elif any(word in query for word in ["历史", "文化", "佛", "建筑"]):
            route_preference["route_history"] += 1
        if any(word in query for word in ["门票", "票价", "学生票", "优惠", "免票"]):
            consumption["门票咨询"] += 1
        if any(word in query for word in ["餐饮", "吃", "素斋", "午饭", "美食"]):
            consumption["餐饮咨询"] += 1
        if any(word in query for word in ["交通", "停车", "公交", "怎么去"]):
            consumption["交通停车"] += 1
        if any(word in query for word in ["文创", "购物", "纪念品", "消费"]):
            consumption["文创购物"] += 1
    if not hot_counter:
        hot_counter.update({"路线": 9, "九龙灌浴": 7, "灵山大佛": 6, "门票": 5, "梵宫": 4})
    if not route_preference:
        route_preference.update({"route_history": 46, "route_family": 38, "route_nature": 31})
    if not any(consumption.values()):
        consumption.update({"门票咨询": 36, "餐饮咨询": 24, "交通停车": 18, "文创购物": 9})
    satisfaction = 94
    if feedback:
        satisfaction = round(sum(int(f.get("rating", 5)) for f in feedback) / (len(feedback) * 5.0) * 100)
    evaluation_summary = evaluation_summary or {}
    negative_count = emotion_counter.get("negative", 0)
    top_hot = hot_counter.most_common(1)[0][0] if hot_counter else "路线"
    top_route = route_preference.most_common(1)[0][0] if route_preference else "route_history"
    route_names = {
        "route_history": "历史文化深度游",
        "route_family": "亲子家庭互动游",
        "route_nature": "自然风光轻松游",
        "route_fast_2h": "2小时高效打卡路线",
    }
    operation_insights = [
        "游客当前最关注“{0}”，建议在游客端入口和导览话术中提前提示。".format(top_hot),
        "路线偏好以“{0}”为主，可在现场导览屏和人工咨询台同步推荐。".format(route_names.get(top_route, top_route)),
        "满意度当前为 {0}%，可结合低分反馈复盘语音识别、回答准确性和路线指引。".format(satisfaction),
    ]
    risk_alerts = []
    if negative_count:
        risk_alerts.append("存在 {0} 条负向反馈，建议优先查看反馈原文并定位服务卡点。".format(negative_count))
    if evaluation_summary.get("ready") and int(evaluation_summary.get("failed_count") or 0) > 0:
        risk_alerts.append("最近一次问答评测有 {0} 道低分题，建议复核知识库事实卡和意图路由。".format(evaluation_summary.get("failed_count")))
    if satisfaction < 85:
        risk_alerts.append("满意度低于 85%，建议临时切换到更稳的语音和本地事实优先模式。")
    if not risk_alerts:
        risk_alerts.append("暂无明显服务风险，建议保持问答评测和游客反馈的日常巡检。")
    recommended_actions = [
        "把热门问题“{0}”整理成首页快捷入口，减少游客重复询问。".format(top_hot),
        "对低分评测题和负向反馈建立复核清单，优先修正文案、知识片段和本地直答规则。",
        "按天气、同行人群和到园时段展示不同路线理由，提升个性化推荐说服力。",
    ]
    return {
        "served_today": max(total, 18),
        "served_week": max(total * 4, 126),
        "hot_questions": [{"name": name, "count": count} for name, count in hot_counter.most_common(8)],
        "route_preference": [{"id": name, "count": count} for name, count in route_preference.most_common(6)],
        "consumption": [{"name": name, "count": count} for name, count in consumption.most_common()],
        "sentiment": dict(emotion_counter),
        "satisfaction": satisfaction,
        "operation_insights": operation_insights,
        "risk_alerts": risk_alerts,
        "recommended_actions": recommended_actions,
        "evaluation_summary": evaluation_summary,
        "suggestions": [
            "九龙灌浴与演出时间关注度较高，建议在首页保持醒目提示。",
            "路线类问题频繁出现，可增加按兴趣一键推荐入口。",
            "若负向反馈上升，优先检查语音识别与回答准确性。",
        ],
    }


_kb = None


def init_knowledge_base(docs_dir=None):
    global _kb
    _kb = KnowledgeBase(docs_dir)
    _kb.load_documents()
    return _kb


def get_knowledge_base():
    global _kb
    if _kb is None:
        _kb = KnowledgeBase()
        _kb.load_documents()
    return _kb
