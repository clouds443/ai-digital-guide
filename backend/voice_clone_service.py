# -*- coding: utf-8 -*-
import json
import os
import re
import subprocess
import time
import uuid
import wave

from runtime_paths import asset_path, runtime_path, seed_runtime_tree


ROOT_DIR = asset_path()
DATA_DIR = runtime_path("knowledge")
VOICE_CLONES_FILE = os.path.join(DATA_DIR, "voice_clones.json")
VOICE_CLONE_DIR = runtime_path("uploads", "voice_clones")
ALLOWED_EXTS = {".wav", ".webm", ".mp3", ".m4a", ".ogg", ".flac"}
REFERENCE_MIN_SECONDS = 3.0
REFERENCE_SAFE_MAX_SECONDS = 9.8
PROMPT_CHARS_PER_SECOND = 6.0
PROMPT_CHAR_MARGIN = 6


def _ensure_dirs():
    seed_runtime_tree("knowledge")
    seed_runtime_tree(os.path.join("uploads", "voice_clones"))
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(VOICE_CLONE_DIR, exist_ok=True)


def _read_json(path, default):
    _ensure_dirs()
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json(path, data):
    _ensure_dirs()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _ffmpeg_path():
    configured = os.getenv("FFMPEG_PATH", "").strip()
    if configured and os.path.exists(configured):
        return configured
    bundled = asset_path("bin", "ffmpeg.exe")
    if os.path.exists(bundled):
        return bundled
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _reference_max_seconds():
    raw_value = os.getenv("VOICE_CLONE_REFERENCE_MAX_SECONDS", str(REFERENCE_SAFE_MAX_SECONDS))
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        value = REFERENCE_SAFE_MAX_SECONDS
    return max(REFERENCE_MIN_SECONDS, min(value, REFERENCE_SAFE_MAX_SECONDS))


def _wav_duration_seconds(path):
    try:
        with wave.open(path, "rb") as wav:
            rate = wav.getframerate()
            if rate <= 0:
                return None
            return wav.getnframes() / float(rate)
    except Exception:
        return None


def _probe_audio_duration_seconds(path):
    cmd = [_ffmpeg_path(), "-hide_banner", "-i", path]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    except Exception:
        return None
    text = (proc.stdout or b"") + (proc.stderr or b"")
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text.decode("utf-8", "ignore"))
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _round_duration(value):
    if value is None:
        return None
    return round(float(value), 2)


def _prompt_char_limit(reference_duration_seconds):
    try:
        duration = float(reference_duration_seconds or 0)
    except (TypeError, ValueError):
        duration = 0.0
    if duration <= 0:
        return 0
    return max(18, int(duration * PROMPT_CHARS_PER_SECOND) + PROMPT_CHAR_MARGIN)


def _sentence_prefix_within_limit(text, limit):
    result = ""
    for match in re.finditer(r"[^。！？!?；;\n]+[。！？!?；;]?", text):
        sentence = match.group(0).strip()
        if not sentence:
            continue
        candidate = result + sentence
        if len(candidate) > limit:
            break
        result = candidate
    return result.strip()


def trim_prompt_text_to_reference(prompt_text, reference_duration_seconds=None, force=False):
    text = re.sub(r"\s+", " ", str(prompt_text or "")).strip()
    if not text:
        return ""
    duration = reference_duration_seconds
    if not duration and force:
        duration = REFERENCE_SAFE_MAX_SECONDS
    limit = _prompt_char_limit(duration)
    if not limit or len(text) <= limit + PROMPT_CHAR_MARGIN:
        return text

    # GSV 的 prompt_text 必须只描述实际参考片段；超长文本会让模型把参考内容串进播报。
    sentence_prefix = _sentence_prefix_within_limit(text, limit)
    if sentence_prefix:
        return sentence_prefix
    return text[:limit].rstrip("，,、；;：: ")


def resolve_packaged_clone_path(path):
    if path and os.path.exists(path):
        return path
    basename = os.path.basename(path or "")
    if not basename:
        return path
    candidate = os.path.join(VOICE_CLONE_DIR, basename)
    return candidate if os.path.exists(candidate) else path


def normalize_reference_audio(source_path, clone_id):
    target_path = os.path.join(VOICE_CLONE_DIR, "{0}_16k.wav".format(clone_id))
    max_seconds = _reference_max_seconds()
    cmd = [
        _ffmpeg_path(),
        "-y",
        "-i",
        source_path,
        "-t",
        "{0:.3f}".format(max_seconds),
        "-ac",
        "1",
        "-ar",
        "16000",
        "-vn",
        target_path,
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", "ignore") or "参考音频转码失败。")
    reference_duration = _wav_duration_seconds(target_path)
    if reference_duration is not None and reference_duration < REFERENCE_MIN_SECONDS:
        try:
            os.remove(target_path)
        except OSError:
            pass
        raise ValueError("参考音频有效时长不足 3 秒，请上传 3 秒以上、普通话清晰且无背景音乐的音频。")
    source_duration = _probe_audio_duration_seconds(source_path)
    return {
        "audio_path": target_path,
        "source_duration_seconds": _round_duration(source_duration),
        "reference_duration_seconds": _round_duration(reference_duration),
        "reference_max_seconds": max_seconds,
        "trimmed": bool(source_duration and source_duration > max_seconds + 0.2),
    }


def _refresh_clone_audio_metadata(item):
    audio_path = resolve_packaged_clone_path(item.get("audio_path", ""))
    source_path = resolve_packaged_clone_path(item.get("source_path", ""))
    changed = False
    if audio_path and audio_path != item.get("audio_path", ""):
        item["audio_path"] = audio_path
        changed = True
    if source_path and source_path != item.get("source_path", ""):
        item["source_path"] = source_path
        changed = True
    if not audio_path or not os.path.exists(audio_path):
        return changed
    duration = _wav_duration_seconds(audio_path)
    if duration is not None:
        rounded = _round_duration(duration)
        if item.get("reference_duration_seconds") != rounded:
            item["reference_duration_seconds"] = rounded
            changed = True
        if duration > REFERENCE_SAFE_MAX_SECONDS + 0.05:
            if source_path and os.path.exists(source_path):
                audio_info = normalize_reference_audio(source_path, item.get("id"))
                item.update(audio_info)
                changed = True
    trimmed_prompt = trim_prompt_text_to_reference(
        item.get("prompt_text", ""),
        item.get("reference_duration_seconds"),
        force=bool(item.get("trimmed")),
    )
    if trimmed_prompt and trimmed_prompt != item.get("prompt_text", ""):
        item.setdefault("original_prompt_text", item.get("prompt_text", ""))
        item["prompt_text"] = trimmed_prompt
        item["prompt_text_trimmed"] = True
        changed = True
    return changed


def list_voice_clones():
    clones = _read_json(VOICE_CLONES_FILE, [])
    changed = False
    for item in clones:
        changed = _refresh_clone_audio_metadata(item) or changed
        audio_path = item.get("audio_path", "")
        item["audio_exists"] = bool(audio_path and os.path.exists(audio_path))
        item["audio_size"] = os.path.getsize(audio_path) if item["audio_exists"] else 0
    if changed:
        _write_json(VOICE_CLONES_FILE, clones)
    return clones


def get_voice_clone(clone_id):
    clone_id = (clone_id or "").strip()
    for item in list_voice_clones():
        if item.get("id") == clone_id:
            return item
    return None


def save_voice_clone(file_storage, name, prompt_text):
    _ensure_dirs()
    if not file_storage:
        raise ValueError("请上传参考音频。")
    prompt_text = (prompt_text or "").strip()
    if not prompt_text:
        raise ValueError("请填写参考音频中实际朗读的文本，GSV-TTS-Lite 克隆需要这段文本对齐音色。")

    clone_id = "clone-{0}".format(uuid.uuid4().hex[:12])
    ext = os.path.splitext(file_storage.filename or "")[1].lower()
    if ext not in ALLOWED_EXTS:
        ext = ".wav"
    original_path = os.path.join(VOICE_CLONE_DIR, "{0}_source{1}".format(clone_id, ext))
    file_storage.save(original_path)
    audio_info = normalize_reference_audio(original_path, clone_id)
    trimmed_prompt = trim_prompt_text_to_reference(
        prompt_text,
        audio_info.get("reference_duration_seconds"),
        force=bool(audio_info.get("trimmed")),
    )

    item = {
        "id": clone_id,
        "name": (name or "").strip() or "未命名克隆音色",
        "prompt_text": trimmed_prompt,
        "audio_path": audio_info["audio_path"],
        "source_path": original_path,
        "original_filename": file_storage.filename or "",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    if trimmed_prompt != prompt_text:
        item["original_prompt_text"] = prompt_text
        item["prompt_text_trimmed"] = True
    item.update({key: value for key, value in audio_info.items() if key != "audio_path"})
    clones = list_voice_clones()
    clones.insert(0, item)
    _write_json(VOICE_CLONES_FILE, clones)
    return item


def delete_voice_clone(clone_id):
    clones = list_voice_clones()
    removed = None
    kept = []
    for item in clones:
        if item.get("id") == clone_id:
            removed = item
        else:
            kept.append(item)
    if not removed:
        return False

    for key in ["audio_path", "source_path"]:
        path = removed.get(key)
        if path and os.path.abspath(path).startswith(os.path.abspath(VOICE_CLONE_DIR)) and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
    _write_json(VOICE_CLONES_FILE, kept)
    return True
