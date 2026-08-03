# -*- coding: utf-8 -*-
import os
import re
import sys
import time
import importlib.util
from io import BytesIO
from urllib.request import urlopen

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_cors import CORS

from asr_service import asr_status, save_uploaded_audio, transcribe_audio
from asr_correction_service import correct_asr_text
from auth_service import check_auth_db, get_current_user, init_auth_db, is_demo_auth_fallback_enabled, login_user, register_user, require_role
from knowledge_base import (
    DEFAULT_DOCS_DIR,
    add_admin_document,
    add_admin_document_from_file,
    add_feedback,
    build_admin_knowledge_view,
    build_analytics,
    build_recommendation_context,
    delete_admin_document,
    get_digital_human_config,
    get_knowledge_base,
    init_knowledge_base,
    list_admin_documents,
    list_feedback,
    update_digital_human_config,
)
from evaluation_service import (
    cancel_evaluation_job,
    export_evaluation_docx,
    get_evaluation_progress,
    get_evaluation_snapshot,
    latest_evaluation_summary,
    run_evaluation_for_admin,
    start_evaluation_job,
    start_semantic_review_job,
)
from map_service import attach_route_maps, build_route_map_by_id, list_map_scenics, map_config
from amap_service import weather as map_weather
from operation_ai_service import generate_operation_ai_analysis
from panorama_service import list_panorama_scenics, panorama_detail, panorama_overview
from rag_service import EMOTION_LABELS, RAGService, classify_turn_emotion
from service_manager import ServiceManager
from tts_service import get_voice_presets, synthesize_speech, tts_status
from voice_clone_service import delete_voice_clone, list_voice_clones, save_voice_clone
from runtime_paths import asset_path, ensure_runtime_dirs, runtime_path


ensure_runtime_dirs()
ROOT_DIR = asset_path()
FRONTEND_DIR = asset_path("frontend")
ENV_PATHS = [
    runtime_path("backend", ".env"),
    asset_path("backend", ".env"),
]


def load_env():
    for env_path in ENV_PATHS:
        if not os.path.exists(env_path):
            continue
        with open(env_path, encoding="utf-8") as env_file:
            for raw in env_file:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env()
init_knowledge_base(DEFAULT_DOCS_DIR)
init_auth_db()
rag = RAGService()
chat_log = []
service_manager = ServiceManager()


def compact_voice_answer(answer, max_chars=180):
    text = str(answer or "").replace("\r", "\n")
    text = re.sub(r"[*#>`_~]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text

    pieces = re.split(r"(?<=[。！？!?；;])\s*", text)
    result = ""
    for piece in pieces:
        if not piece:
            continue
        if len(result) + len(piece) <= max_chars:
            result += piece
            continue
        break
    if not result:
        result = text[: max_chars - 1].rstrip() + "…"
    elif len(result) < len(text) and not result.endswith(("。", "！", "？", "!", "?")):
        result = result.rstrip("，,；;：:") + "。"
    return result


def voice_correction_failed(correction):
    return bool((correction or {}).get("correction_error")) and not (
        (correction or {}).get("llm_corrected") or (correction or {}).get("leading_noise_removed")
    )


app = Flask(__name__, static_folder=FRONTEND_DIR)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
CORS(app)


def send_static_file(filename, max_age=None):
    try:
        return send_from_directory(app.static_folder, filename, max_age=max_age)
    except TypeError as exc:
        if "max_age" not in str(exc):
            raise
        return send_from_directory(app.static_folder, filename, cache_timeout=max_age)


@app.after_request
def disable_html_cache(response):
    if request.path == "/" or request.path.lower().endswith(".html"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        response.cache_control.no_store = True
        response.cache_control.no_cache = True
        response.cache_control.must_revalidate = True
    return response


@app.route("/")
def index():
    return send_static_file("index.html", max_age=0)


@app.route("/audio/tts/<path:filename>")
def serve_tts_audio(filename):
    runtime_audio_dir = runtime_path("frontend", "audio", "tts")
    if os.path.exists(os.path.join(runtime_audio_dir, filename)):
        return send_from_directory(runtime_path("frontend", "audio", "tts"), filename)
    return send_from_directory(asset_path("frontend", "audio", "tts"), filename)


@app.route("/<path:filename>")
def serve_static(filename):
    max_age = 0 if filename.lower().endswith(".html") else None
    return send_static_file(filename, max_age=max_age)


@app.route("/api/health")
def health():
    asr = asr_status()
    config = get_digital_human_config()
    provider = (config.get("voice_provider") or os.getenv("OPEN_SOURCE_TTS_PROVIDER") or "gpt_sovits").strip().lower()
    edge_ready = importlib.util.find_spec("edge_tts") is not None
    gsv_tts_lite_api = os.getenv("GSV_TTS_LITE_API_URL") or os.getenv("GPT_SOVITS_API_URL", "http://127.0.0.1:9880")
    return jsonify({
        "ok": True,
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "deepseek_configured": bool(os.getenv("DEEPSEEK_API_KEY")),
        "mysql_configured": check_auth_db(),
        "auth_demo_fallback_enabled": is_demo_auth_fallback_enabled(),
        "tts_configured": bool(edge_ready),
        "tts_provider": provider,
        "gpt_sovits_api_url": gsv_tts_lite_api,
        "gsv_tts_lite_api_url": gsv_tts_lite_api,
        "tts_engine": "gsv_tts_lite" if provider in {"gpt_sovits", "gptsovits", "gpt-sovits"} else provider,
        "tts_lightweight": True,
        "asr_configured": bool(asr.get("ok")),
        "asr_provider": asr.get("provider"),
    })


@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    data = request.get_json(silent=True) or {}
    result, error = login_user(data.get("username"), data.get("password"), data.get("role"))
    if error:
        return jsonify({"error": error}), 401
    return jsonify(result)


@app.route("/api/auth/register", methods=["POST"])
def auth_register():
    data = request.get_json(silent=True) or {}
    result, error, status = register_user(
        data.get("username"),
        data.get("password"),
        data.get("display_name"),
        data.get("role"),
    )
    if error:
        return jsonify({"error": error}), status
    return jsonify(result)


@app.route("/api/auth/me")
def auth_me():
    user = get_current_user()
    if not user:
        return jsonify({"authenticated": False}), 401
    return jsonify({"authenticated": True, "user": user})


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    query = (data.get("query") or "").strip()
    if not query:
        return jsonify({"answer": "问题不能为空"}), 400
    result = rag.chat_detail(query, data.get("history") or [], data.get("interest") or "")
    answer = result["answer"]
    chat_log.append({
        "query": query,
        "answer": answer,
        "emotion": result.get("emotion", "neutral"),
        "route_id": (result.get("route_suggestion") or {}).get("id", ""),
        "interest": data.get("interest") or "",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    if len(chat_log) > 1000:
        del chat_log[:-1000]
    return jsonify(result)


@app.route("/api/voice", methods=["POST"])
def voice():
    data = request.get_json(silent=True) or {}
    query = (data.get("text") or data.get("query") or "").strip()
    if not query:
        return jsonify({"answer": "语音文本为空"}), 400
    result = rag.chat_detail(query, data.get("history") or [], data.get("interest") or "")
    answer = result["answer"]
    speech = synthesize_speech(answer, get_digital_human_config())
    result.update({"audio_url": speech.get("audio_url"), "tts": speech})
    return jsonify(result)


@app.route("/api/tts/status")
def api_tts_status():
    return jsonify(tts_status(get_digital_human_config()))


@app.route("/api/tts/voices")
def api_tts_voices():
    return jsonify({"voices": get_voice_presets()})


@app.route("/api/tts/synthesize", methods=["POST"])
def api_tts_synthesize():
    data = request.get_json(silent=True) or {}
    config = get_digital_human_config()
    for key in ["voice_provider", "voice_preset", "voice_description", "voice_clone_id", "edge_voice", "voice_name", "voice_rate", "voice_pitch", "voice_volume", "purpose", "fast_first"]:
        if key in data:
            config[key] = str(data.get(key, "")).strip()
    result = synthesize_speech(data.get("text", ""), config)
    status = 200 if result.get("ok") else 503
    return jsonify(result), status


@app.route("/api/admin/voice-clones", methods=["GET", "POST"])
@require_role("admin")
def admin_voice_clones():
    if request.method == "GET":
        return jsonify({"voices": list_voice_clones()})
    try:
        item = save_voice_clone(
            request.files.get("audio"),
            request.form.get("name", ""),
            request.form.get("prompt_text", ""),
        )
        return jsonify({"voice": item})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/admin/voice-clones/<clone_id>", methods=["DELETE"])
@require_role("admin")
def admin_delete_voice_clone(clone_id):
    return jsonify({"ok": delete_voice_clone(clone_id)})


@app.route("/api/asr/status")
def api_asr_status():
    return jsonify(asr_status())


@app.route("/api/realtime/status")
def api_realtime_status_proxy():
    url = os.getenv("REALTIME_STATUS_URL", "http://127.0.0.1:8010/api/realtime/status")
    try:
        with urlopen(url, timeout=3) as response:
            payload = response.read().decode("utf-8", "ignore")
        return app.response_class(payload, mimetype="application/json")
    except Exception as exc:
        return jsonify({
            "ok": False,
            "service": "lingshan-realtime-guide",
            "asr": {
                "ok": False,
                "ready": False,
                "provider": "FunASR",
                "error": str(exc),
            },
            "hint": "实时语音服务 8010 未就绪，请启动 start_realtime_server.bat。",
        }), 503


@app.route("/api/voice/realtime", methods=["POST"])
def api_voice_realtime():
    if "audio" not in request.files:
        return jsonify({"ok": False, "error": "未收到音频文件。"}), 400
    audio_path = save_uploaded_audio(request.files["audio"])
    try:
        asr_result = transcribe_audio(audio_path)
    except Exception as exc:
        return jsonify({
            "ok": False,
            "error": "语音识别失败：" + str(exc),
            "audio_path": audio_path,
            "asr_status": asr_status(),
        }), 500
    query = (asr_result.get("text") or "").strip()
    if not query:
        return jsonify({"ok": False, "asr": asr_result, "error": "未识别到有效语音，请靠近麦克风后重试。"}), 422

    history = []
    raw_history = request.form.get("history", "")
    if raw_history:
        try:
            import json

            history = json.loads(raw_history)
        except Exception:
            history = []
    interest = request.form.get("interest", "")
    correction = correct_asr_text(query, history=history, realtime=False)
    query = (correction.get("text") or query).strip()
    asr_result.update({
        "text": query,
        "original_text": correction.get("original_text", ""),
        "corrected_text": correction.get("corrected_text", query),
        "pre_llm_text": correction.get("pre_llm_text", query),
        "correction_required": True,
        "correction_failed": voice_correction_failed(correction),
        "leading_noise_removed": bool(correction.get("leading_noise_removed")),
        "leading_noise_reason": correction.get("leading_noise_reason", ""),
        "llm_corrected": bool(correction.get("llm_corrected")),
        "correction_provider": correction.get("correction_provider", ""),
        "correction_confidence": correction.get("correction_confidence", 0.0),
        "correction_reason": correction.get("correction_reason", ""),
        "correction_error": correction.get("correction_error", ""),
    })
    if asr_result["correction_failed"]:
        return jsonify({
            "ok": False,
            "error": "语音纠错失败，请重试：" + (asr_result.get("correction_error") or "DeepSeek 未返回可靠纠错结果。"),
            "query": query,
            "asr": asr_result,
        }), 503
    voice_query = query + "\n请用适合语音播报的方式回答，控制在80到120字，直接给出重点。"
    result = rag.chat_detail(voice_query, history, interest)
    answer = compact_voice_answer(result["answer"])
    turn_emotion = classify_turn_emotion(query, answer)
    turn_emotion_label = EMOTION_LABELS.get(turn_emotion, "自然")
    chat_log.append({
        "query": query,
        "answer": answer,
        "emotion": turn_emotion,
        "route_id": (result.get("route_suggestion") or {}).get("id", ""),
        "interest": interest,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    if len(chat_log) > 1000:
        del chat_log[:-1000]
    speech = synthesize_speech(answer, get_digital_human_config())
    return jsonify({
        "ok": True,
        "query": query,
        "answer": answer,
        "emotion": turn_emotion,
        "emotion_label": turn_emotion_label,
        "route_suggestion": result.get("route_suggestion"),
        "sources": result.get("sources", []),
        "latency_ms": result.get("latency_ms", 0),
        "audio_url": speech.get("audio_url"),
        "asr": asr_result,
        "tts": speech,
    })


@app.route("/api/voice/correct-text", methods=["POST"])
def api_voice_correct_text():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "语音文本为空。"}), 400
    correction = dict(correct_asr_text(
        text,
        history=data.get("history") or [],
        realtime=bool(data.get("realtime")),
    ))
    correction_failed = voice_correction_failed(correction)
    correction["correction_required"] = True
    correction["correction_failed"] = correction_failed
    correction["ok"] = not correction_failed and bool(correction.get("text"))
    if correction_failed:
        correction["error"] = "语音纠错失败，请重试：" + (correction.get("correction_error") or "DeepSeek 未返回可靠纠错结果。")
    status = 503 if correction_failed else 200
    return jsonify(correction), status


@app.route("/api/scenics")
def scenics():
    return jsonify({"scenics": get_knowledge_base().get_scenics()})


@app.route("/api/scenic/<scenic_id>")
def scenic_detail(scenic_id):
    data = get_knowledge_base().get_scenic(scenic_id)
    if not data:
        return jsonify({"error": "景点不存在"}), 404
    return jsonify(data)


@app.route("/api/scenic/<scenic_id>/narration")
def scenic_narration(scenic_id):
    data = rag.scenic_narration(scenic_id)
    if not data:
        return jsonify({"error": "景点不存在"}), 404
    return jsonify(data)


@app.route("/api/routes")
def routes():
    interest = request.args.get("interest", "")
    context = build_recommendation_context(
        interest=interest,
        weather=request.args.get("weather", ""),
        arrival_period=request.args.get("arrival_period", ""),
        companions=request.args.get("companions", ""),
        duration=request.args.get("duration", ""),
        stamina=request.args.get("stamina", ""),
    )
    if interest:
        return jsonify({"routes": attach_route_maps(get_knowledge_base().recommend_routes(interest, context=context))})
    return jsonify({"routes": attach_route_maps(get_knowledge_base().recommend_routes("", context=context))})


@app.route("/api/map/config")
def api_map_config():
    return jsonify(map_config())


@app.route("/api/map/scenics")
def api_map_scenics():
    return jsonify({"points": list_map_scenics(), "center": map_config().get("center")})


@app.route("/api/map/route/<route_id>")
def api_map_route(route_id):
    route = build_route_map_by_id(route_id)
    if not route:
        return jsonify({"error": "路线不存在"}), 404
    return jsonify(route)


@app.route("/api/map/tools/weather")
def api_map_weather():
    result = map_weather(request.args.get("city", "无锡市"))
    status = int(result.pop("status", 200 if result.get("ok") else 502))
    return jsonify(result), status


@app.route("/api/panorama/scenics")
def api_panorama_scenics():
    return jsonify({"scenics": list_panorama_scenics()})


@app.route("/api/panorama/scenic/<scenic_id>")
def api_panorama_scenic(scenic_id):
    return jsonify(panorama_detail(scenic_id))


@app.route("/api/panorama/overview")
def api_panorama_overview():
    return jsonify(panorama_overview())


@app.route("/api/config")
def public_config():
    return jsonify(get_digital_human_config())


@app.route("/api/feedback", methods=["GET", "POST"])
def feedback():
    if request.method == "GET":
        user = get_current_user()
        if not user or user.get("role") != "admin":
            return jsonify({"error": "当前账号无权限访问"}), 403
    if request.method == "GET":
        return jsonify({"feedback": list_feedback()})
    data = request.get_json(silent=True) or {}
    item = add_feedback(data.get("message", ""), data.get("rating", 5))
    return jsonify({"feedback": item})


@app.route("/api/admin/knowledge", methods=["GET", "POST"])
@require_role("admin")
def admin_knowledge():
    if request.method == "GET":
        return jsonify(build_admin_knowledge_view(DEFAULT_DOCS_DIR))
    data = request.get_json(silent=True) or {}
    title = data.get("title", "")
    content = data.get("content", "")
    if not content.strip():
        return jsonify({"error": "知识内容不能为空"}), 400
    doc = add_admin_document(title, content, data.get("type", "讲解词"))
    return jsonify({"document": doc})


@app.route("/api/admin/knowledge/upload", methods=["POST"])
@require_role("admin")
def admin_upload_knowledge():
    files = request.files.getlist("files")
    if not files:
        return jsonify({"ok": False, "error": "请先选择 Word 或 PDF 文件。"}), 400

    doc_type = request.form.get("type", "文史资料")
    title_prefix = request.form.get("title_prefix", "")
    created = []
    errors = []
    for file_storage in files:
        filename = getattr(file_storage, "filename", "") or "未命名文件"
        try:
            created.append(add_admin_document_from_file(file_storage, doc_type, title_prefix))
        except Exception as exc:
            errors.append({"filename": filename, "error": str(exc)})

    if created:
        get_knowledge_base().reload()
    status = 200 if created else 400
    error_message = ""
    if not created and errors:
        first_error = errors[0]
        error_message = "{0}：{1}".format(first_error.get("filename", "文件"), first_error.get("error", "解析失败"))
    return jsonify({
        "ok": bool(created),
        "error": error_message,
        "created": created,
        "errors": errors,
        "created_count": len(created),
        "error_count": len(errors),
    }), status


@app.route("/api/admin/knowledge/<doc_id>", methods=["DELETE"])
@require_role("admin")
def admin_delete_knowledge(doc_id):
    ok = delete_admin_document(doc_id)
    return jsonify({"ok": ok})


@app.route("/api/admin/config", methods=["GET", "POST"])
@require_role("admin")
def admin_config():
    if request.method == "GET":
        return jsonify(get_digital_human_config())
    data = request.get_json(silent=True) or {}
    return jsonify(update_digital_human_config(data))


@app.route("/api/admin/services/status")
@require_role("admin")
def admin_services_status():
    return jsonify(service_manager.status_all())


@app.route("/api/admin/services/start", methods=["POST"])
@require_role("admin")
def admin_services_start():
    data = request.get_json(silent=True) or {}
    service_id = str(data.get("service", "")).strip()
    try:
        return jsonify({"service": service_manager.start_service(service_id)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/admin/services/stop", methods=["POST"])
@require_role("admin")
def admin_services_stop():
    data = request.get_json(silent=True) or {}
    service_id = str(data.get("service", "")).strip()
    try:
        return jsonify({"service": service_manager.stop_service(service_id)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/admin/evaluation")
@require_role("admin")
def admin_evaluation_snapshot():
    mode = request.args.get("mode", "deepseek")
    return jsonify({"evaluation": get_evaluation_snapshot(mode)})


@app.route("/api/admin/evaluation/run", methods=["POST"])
@require_role("admin")
def admin_evaluation_run():
    data = request.get_json(silent=True) or {}
    mode = data.get("mode") or request.args.get("mode", "deepseek")
    job_id = data.get("job_id") or data.get("client_job_id") or request.args.get("job_id")
    return jsonify(start_evaluation_job(mode, job_id=job_id))


@app.route("/api/admin/evaluation/cancel", methods=["POST"])
@require_role("admin")
def admin_evaluation_cancel():
    data = request.get_json(silent=True) or {}
    mode = data.get("mode") or request.args.get("mode", "deepseek")
    job_id = data.get("job_id") or request.args.get("job_id")
    return jsonify({"progress": cancel_evaluation_job(mode, job_id=job_id)})


@app.route("/api/admin/evaluation/review-low-score", methods=["POST"])
@require_role("admin")
def admin_evaluation_review_low_score():
    data = request.get_json(silent=True) or {}
    mode = data.get("mode") or request.args.get("mode", "deepseek")
    job_id = data.get("job_id") or data.get("client_job_id") or request.args.get("job_id")
    try:
        return jsonify(start_semantic_review_job(mode, job_id=job_id))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/admin/evaluation/progress")
@require_role("admin")
def admin_evaluation_progress():
    return jsonify({"progress": get_evaluation_progress(request.args.get("job_id", ""), mode=request.args.get("mode"))})


@app.route("/api/admin/evaluation/export")
@require_role("admin")
def admin_evaluation_export():
    mode = request.args.get("mode", "deepseek")
    try:
        content, filename = export_evaluation_docx(mode)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400
    return send_file(
        BytesIO(content),
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        attachment_filename=filename,
    )


@app.route("/api/analytics")
@require_role("admin")
def analytics():
    data = build_analytics(chat_log, latest_evaluation_summary())
    data["recent_chats"] = chat_log[-12:][::-1]
    return jsonify(data)


@app.route("/api/admin/analytics/ai-analysis", methods=["GET", "POST"])
@require_role("admin")
def admin_analytics_ai_analysis():
    data = build_analytics(chat_log, latest_evaluation_summary())
    data["recent_chats"] = chat_log[-12:][::-1]
    data["feedback"] = list_feedback()[:12]
    try:
        analysis = generate_operation_ai_analysis(data)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"analysis": analysis, "analytics_snapshot": data})


if __name__ == "__main__":
    print("Lingshan AI Digital Human - http://localhost:8000")
    app.run(host="0.0.0.0", port=8000, debug=False, threaded=True)
