# -*- coding: utf-8 -*-
import json
import os
import re
import time
from urllib.request import Request, urlopen


def _extract_json_object(text):
    value = str(text or "").strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?", "", value, flags=re.I).strip()
        value = re.sub(r"```$", "", value).strip()
    if value.startswith("{") and value.endswith("}"):
        return json.loads(value)
    match = re.search(r"\{.*\}", value, flags=re.S)
    if match:
        return json.loads(match.group(0))
    raise ValueError("DeepSeek 未返回结构化运营建议。")


def _as_text_list(value, limit=6):
    result = []
    for item in value or []:
        text = str(item).strip()
        if text and text not in result:
            result.append(text[:180])
        if len(result) >= limit:
            break
    return result


def _compact_analytics_snapshot(analytics):
    data = dict(analytics or {})
    recent_queries = []
    for item in data.get("recent_chats") or []:
        query = str((item or {}).get("query", "")).strip()
        if query:
            recent_queries.append(query[:120])
        if len(recent_queries) >= 8:
            break
    low_feedback = []
    for item in data.get("feedback") or []:
        rating = item.get("rating", "")
        message = str(item.get("message", "")).strip()
        if message:
            low_feedback.append("{0}分：{1}".format(rating, message[:120]))
        if len(low_feedback) >= 6:
            break
    return {
        "served_today": data.get("served_today", 0),
        "served_week": data.get("served_week", 0),
        "satisfaction": data.get("satisfaction", 0),
        "hot_questions": data.get("hot_questions", [])[:8],
        "route_preference": data.get("route_preference", [])[:6],
        "consumption": data.get("consumption", [])[:6],
        "sentiment": data.get("sentiment", {}),
        "operation_insights": _as_text_list(data.get("operation_insights")),
        "risk_alerts": _as_text_list(data.get("risk_alerts")),
        "recommended_actions": _as_text_list(data.get("recommended_actions")),
        "evaluation_summary": data.get("evaluation_summary", {}),
        "recent_queries": recent_queries,
        "low_feedback": low_feedback,
    }


def _normalize_analysis(payload, model):
    data = dict(payload or {})
    summary = str(data.get("summary") or data.get("overview") or "").strip()
    focus_points = _as_text_list(data.get("focus_points") or data.get("concerns"), limit=5)
    risks = _as_text_list(data.get("risks") or data.get("risk_alerts"), limit=5)
    actions = _as_text_list(data.get("actions") or data.get("recommended_actions"), limit=6)
    if not summary:
        summary = "DeepSeek 已完成运营数据分析，请结合下方关注点、风险与行动建议复盘。"
    if not actions:
        actions = ["复核热门咨询、低分反馈和问答评测结果，形成当日运营改进清单。"]
    return {
        "provider": "deepseek",
        "model": model,
        "summary": summary[:260],
        "focus_points": focus_points,
        "risks": risks,
        "actions": actions,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def generate_operation_ai_analysis(analytics):
    api_key = (os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise ValueError("未配置 DeepSeek API Key，无法生成 AI 运营分析。")
    api_base = os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com/v1"
    model = os.getenv("DEEPSEEK_MODEL") or "deepseek-chat"
    try:
        timeout_seconds = float(os.getenv("OPERATION_AI_TIMEOUT_SECONDS", os.getenv("EVALUATION_LLM_TIMEOUT_SECONDS", "30")))
    except Exception:
        timeout_seconds = 30.0
    snapshot = _compact_analytics_snapshot(analytics)
    prompt = (
        "你是景区智慧运营顾问，请基于灵山胜境 AI 数字人导游后台的运营数据，给管理方生成辅助建议。"
        "只依据输入数据分析，不编造不存在的投诉、客流或收入。"
        "输出严格 JSON，不要 Markdown。字段必须为：summary、focus_points、risks、actions。"
        "focus_points、risks、actions 都是中文字符串数组，每条不超过 40 字。\n\n"
        "运营数据：{0}"
    ).format(json.dumps(snapshot, ensure_ascii=False))
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": "你是克制、务实的景区运营分析助手，只输出 JSON。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 900,
    }).encode("utf-8")
    req = Request(api_base.rstrip("/") + "/chat/completions", data=body, headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + api_key,
    })
    with urlopen(req, timeout=timeout_seconds) as response:
        result = json.loads(response.read().decode("utf-8"))
    content = result["choices"][0]["message"]["content"].strip()
    return _normalize_analysis(_extract_json_object(content), model)
