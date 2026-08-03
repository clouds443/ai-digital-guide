# -*- coding: utf-8 -*-
import json
import os
import re
from difflib import SequenceMatcher
from urllib.request import Request, urlopen

from asr_service import apply_asr_hotword_corrections, asr_hotword_prompt


DEEPSEEK_BASE = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-chat"


def _env_bool(name, default=True):
    value = os.getenv(name, "1" if default else "0").strip().lower()
    return value not in {"0", "false", "no", "off"}


def _env_float(name, default):
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return float(default)


_LEADING_NOISE_WORDS = ["那个", "这个", "就是", "然后", "嗯", "呃", "额", "啊", "喂"]
_LEADING_STRAY_CHARS = "客课克咳导到道岛"
_GENERIC_INTENT_MARKERS = [
    "讲的什么东西",
    "讲得什么东西",
    "说的什么东西",
    "回答的什么东西",
    "解释的什么东西",
    "播报的什么东西",
    "讲解一下",
    "介绍一下",
    "重新讲",
    "重新说",
]
_MEANINGFUL_PREFIX_WORDS = [
    "我",
    "请",
    "帮",
    "想",
    "问",
    "麻烦",
    "能不能",
    "能否",
    "可以",
    "可不可以",
    "灵山",
    "九龙",
    "五智",
    "五印",
    "佛足",
    "大佛",
    "梵宫",
]
_LEADING_OPENERS = [
    "我",
    "请",
    "帮",
    "想",
    "问",
    "介绍",
    "讲",
    "说",
    "能",
    "要",
    "再",
    "给",
    "灵山",
    "九龙",
    "五智",
    "五印",
    "天下",
    "阿育",
    "百子",
    "祥符",
    "曼飞",
    "无尽",
]


def _fallback_result(
    text,
    error="",
    provider="",
    original_text=None,
    pre_llm_text=None,
    leading_noise_removed=False,
    leading_noise_reason="",
):
    value = str(text or "").strip()
    original_value = str(original_text if original_text is not None else value).strip()
    pre_llm_value = str(pre_llm_text if pre_llm_text is not None else value).strip()
    return {
        "ok": bool(value),
        "text": value,
        "original_text": original_value,
        "corrected_text": value,
        "pre_llm_text": pre_llm_value,
        "leading_noise_removed": bool(leading_noise_removed),
        "leading_noise_reason": leading_noise_reason,
        "llm_corrected": False,
        "correction_provider": provider,
        "correction_confidence": 0.0,
        "correction_reason": "",
        "correction_error": error,
    }


def _looks_like_leading_body(text):
    value = str(text or "")
    return any(value.startswith(opener) for opener in _LEADING_OPENERS)


def _starts_with_noise_word(text):
    value = str(text or "")
    return any(value.startswith(word) for word in _LEADING_NOISE_WORDS)


def _looks_like_meaningful_prefix(prefix):
    value = str(prefix or "")
    return any(word in value for word in _MEANINGFUL_PREFIX_WORDS)


def _extract_generic_intent_prefix(text):
    value = str(text or "")
    for marker in _GENERIC_INTENT_MARKERS:
        index = value.find(marker)
        if index < 2 or index > 10:
            continue
        prefix = value[:index]
        if _looks_like_meaningful_prefix(prefix):
            continue
        return {
            "text": value[index:],
            "removed": True,
            "reason": "移除意图前无意义识别片段“{0}”".format(prefix),
        }
    return {"text": value, "removed": False, "reason": ""}


def _normalize_asr_leading_noise_detail(text):
    original = re.sub(r"\s+", "", str(text or "").strip())
    value = original
    reasons = []
    changed = True
    while changed and value:
        changed = False
        for word in sorted(_LEADING_NOISE_WORDS, key=len, reverse=True):
            if not value.startswith(word):
                continue
            rest = value[len(word):]
            if rest and (_looks_like_leading_body(rest) or _starts_with_noise_word(rest)):
                value = rest
                reasons.append("移除开头语气词“{0}”".format(word))
                changed = True
                break
        if changed:
            continue
        if len(value) >= 2 and value[0] in _LEADING_STRAY_CHARS and _looks_like_leading_body(value[1:]):
            removed = value[0]
            value = value[1:]
            reasons.append("移除开头误识别字“{0}”".format(removed))
            changed = True
            continue
        match = re.match(r"^(请问){2,}(.+)$", value)
        if match:
            value = "请问" + match.group(2)
            reasons.append("合并重复开头“请问”")
            changed = True
    intent_detail = _extract_generic_intent_prefix(value)
    if intent_detail["removed"]:
        value = intent_detail["text"]
        reasons.append(intent_detail["reason"])
    return {
        "text": value,
        "removed": value != original,
        "reason": "；".join(reasons),
    }


def normalize_asr_leading_noise(text):
    return _normalize_asr_leading_noise_detail(text)["text"]


def _recent_history_text(history):
    lines = []
    for item in (history or [])[-4:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip()
        content = re.sub(r"\s+", " ", str(item.get("content") or "")).strip()
        if content:
            lines.append("{0}: {1}".format(role or "message", content[:120]))
    return "\n".join(lines)


def _extract_json_object(content):
    value = str(content or "").strip()
    value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.I)
    value = re.sub(r"\s*```$", "", value)
    try:
        return json.loads(value)
    except Exception:
        match = re.search(r"\{[\s\S]*\}", value)
        if not match:
            raise ValueError("DeepSeek 纠错返回不是 JSON。")
        try:
            return json.loads(match.group(0))
        except Exception as exc:
            raise ValueError("DeepSeek 纠错返回不是 JSON：{0}".format(exc))


def _compact_for_compare(text):
    value = str(text or "")
    value = re.sub(r"[\s，,。！？!?；;：:“”\"'‘’（）()\[\]{}《》、/\\\-—_+]+", "", value)
    return value


def _is_safe_correction(original, corrected):
    before = _compact_for_compare(original)
    after = _compact_for_compare(corrected)
    if not before or not after:
        return False, "纠错后文本为空。"
    if len(corrected) > max(32, len(original) * 2 + 20):
        return False, "纠错后文本过长，疑似生成回答。"
    if len(after) < max(1, len(before) // 3):
        return False, "纠错后文本过短，可能丢失语义。"
    if before.endswith(after) and len(before) - len(after) <= 8:
        return True, ""
    ratio = SequenceMatcher(None, before, after).ratio()
    shared_hotword = any(word in corrected and word in asr_hotword_prompt() for word in re.findall(r"[\u4e00-\u9fff]{2,8}", corrected))
    if ratio < 0.25 and not shared_hotword:
        return False, "纠错前后差异过大，已保留原识别文本。"
    return True, ""


def correct_asr_text(text, history=None, realtime=False, enabled=None):
    original = str(text or "").strip()
    if not original:
        return _fallback_result("", "")
    leading_detail = _normalize_asr_leading_noise_detail(original)
    pre_llm_text = leading_detail["text"] or original

    flag_name = "REALTIME_ASR_LLM_CORRECTION_ENABLED" if realtime else "ASR_LLM_CORRECTION_ENABLED"
    if enabled is False or (enabled is None and not _env_bool(flag_name, True)):
        return _fallback_result(
            pre_llm_text,
            "ASR 语义纠错已关闭。",
            original_text=original,
            pre_llm_text=pre_llm_text,
            leading_noise_removed=leading_detail["removed"],
            leading_noise_reason=leading_detail["reason"],
        )

    api_key = (os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return _fallback_result(
            pre_llm_text,
            "DeepSeek API Key 未配置，已使用规则清理后的识别文本。",
            original_text=original,
            pre_llm_text=pre_llm_text,
            leading_noise_removed=leading_detail["removed"],
            leading_noise_reason=leading_detail["reason"],
        )

    system_prompt = (
        "你是中文语音识别文本纠错器，需要从整句中提取用户真实意图，只修正 ASR 错字、景点专名、标点和明显误听，尤其要重点检查前 2 到 8 个字。"
        "如果开头出现误入字、唤醒词、语气词或重复片段，可以删除或修正；真实问题主体必须保留。"
        "不要回答问题，不要扩写，不要替用户改语气，不要删除批评或情绪表达。"
        "只能返回 JSON，格式为："
        '{"corrected_text":"纠错后的原问题","changed":true,"confidence":0.0,"reason":"简短原因"}。'
    )
    user_prompt = (
        "ASR原始识别文本：{0}\n"
        "规则清理后待纠错文本：{1}\n"
        "灵山胜境热词：{2}\n"
        "最近对话：{3}\n"
        "请只输出 JSON。"
    ).format(original, pre_llm_text, asr_hotword_prompt(), _recent_history_text(history) or "无")
    body = json.dumps(
        {
            "model": os.getenv("DEEPSEEK_MODEL") or DEEPSEEK_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.0,
            "max_tokens": 180,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = Request(
        (os.getenv("DEEPSEEK_BASE_URL") or DEEPSEEK_BASE).rstrip("/") + "/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + api_key,
        },
    )
    try:
        resp = urlopen(req, timeout=_env_float("ASR_LLM_CORRECTION_TIMEOUT_SECONDS", 3.5))
        data = json.loads(resp.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
        parsed = _extract_json_object(content)
        corrected = apply_asr_hotword_corrections(str(parsed.get("corrected_text") or "").strip())
        safe, error = _is_safe_correction(pre_llm_text, corrected)
        if not safe:
            return _fallback_result(
                pre_llm_text,
                error,
                provider="deepseek",
                original_text=original,
                pre_llm_text=pre_llm_text,
                leading_noise_removed=leading_detail["removed"],
                leading_noise_reason=leading_detail["reason"],
            )
        changed = bool(parsed.get("changed")) or corrected != pre_llm_text
        try:
            confidence = float(parsed.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        return {
            "ok": True,
            "text": corrected,
            "original_text": original,
            "corrected_text": corrected,
            "pre_llm_text": pre_llm_text,
            "leading_noise_removed": leading_detail["removed"],
            "leading_noise_reason": leading_detail["reason"],
            "llm_corrected": changed,
            "correction_provider": "deepseek",
            "correction_confidence": max(0.0, min(confidence, 1.0)),
            "correction_reason": str(parsed.get("reason") or "").strip(),
            "correction_error": "",
        }
    except Exception as exc:
        return _fallback_result(
            pre_llm_text,
            str(exc),
            provider="deepseek",
            original_text=original,
            pre_llm_text=pre_llm_text,
            leading_noise_removed=leading_detail["removed"],
            leading_noise_reason=leading_detail["reason"],
        )
