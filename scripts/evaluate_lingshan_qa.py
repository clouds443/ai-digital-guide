# -*- coding: utf-8 -*-
import argparse
import json
import os
import re
import sys
import time
import unicodedata
from urllib.request import Request, urlopen


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")
ENV_PATH = os.path.join(BACKEND_DIR, ".env")
DEFAULT_DATASET = os.path.join(ROOT_DIR, "tests", "fixtures", "lingshan_qa_100.jsonl")

if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from runtime_paths import asset_path, runtime_path  # noqa: E402
from knowledge_base import init_knowledge_base  # noqa: E402
from rag_service import RAGService  # noqa: E402

ROOT_DIR = asset_path()
BACKEND_DIR = asset_path("backend")
ENV_PATH = runtime_path("backend", ".env")
ASSET_ENV_PATH = asset_path("backend", ".env")
DEFAULT_DATASET = asset_path("tests", "fixtures", "lingshan_qa_100.jsonl")
SCORING_VERSION = "relaxed_keyword_v3"
SEMANTIC_REVIEW_VERSION = "llm_low_score_review_v1"


class EvaluationCancelled(Exception):
    pass


def load_backend_env(env_path=ENV_PATH):
    selected_path = env_path if os.path.exists(env_path) else ASSET_ENV_PATH
    if not os.path.exists(selected_path):
        return
    with open(selected_path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key or key in os.environ:
                continue
            os.environ[key] = value.strip().strip('"').strip("'")


def load_cases(dataset_path=DEFAULT_DATASET):
    cases = []
    with open(dataset_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def _basic_match_text(value):
    text = unicodedata.normalize("NFKC", str(value or "")).lower()
    text = text.replace("＋", "+")
    text = re.sub(r"[‐‑‒–—―~～－]", "-", text)
    text = re.sub(r"\s+", "", text)
    return text


def _normalize_units(text):
    text = re.sub(r"(\d+(?:\.\d+)?)周岁", r"\1岁", text)
    text = re.sub(r"(\d+(?:\.\d+)?)元[/／](人|位)", r"\1元每人", text)
    text = re.sub(r"(\d+(?:\.\d+)?)元(一人|每位)", r"\1元每人", text)
    text = re.sub(r"国家(\d+)a级", r"国家\1a级", text)
    return text


def _normalize_ranges(text):
    text = re.sub(r"(\d{1,2})月(?:到|至|-)(\d{1,2})月", r"\1-\2月", text)
    text = re.sub(r"(\d+(?:\.\d+)?)(年|月|点)(?:到|至|-)(\d+(?:\.\d+)?)\2", r"\1-\3\2", text)
    text = re.sub(r"(\d{1,2})点(?:到|至|-)(\d{1,2})点", r"\1-\2点", text)
    text = re.sub(r"(\d{1,2}:\d{2})(?:到|至|-)(\d{1,2}:\d{2})", r"\1-\2", text)
    text = re.sub(r"(\d+(?:\.\d+)?)(?:到|至|-)(\d+(?:\.\d+)?)(分钟|小时|元|岁|米|月|年)", r"\1-\2\3", text)
    return text


def _include_match_text(value):
    text = _normalize_ranges(_normalize_units(_basic_match_text(value)))
    text = re.sub(r"(以及|和|与|及|并|同|、|,|，|/|／|\+|;|；)", "", text)
    return text


def _keyword_matches(answer, keyword, relaxed=True):
    if not str(keyword or "").strip():
        return False
    if relaxed:
        return _include_match_text(keyword) in _include_match_text(answer)
    return _normalize_units(_basic_match_text(keyword)) in _normalize_units(_basic_match_text(answer))


def _contains_all(answer, words):
    return all(_keyword_matches(answer, word, relaxed=True) for word in words)


def _matched_count(answer, words):
    return sum(1 for word in words if _keyword_matches(answer, word, relaxed=True))


def _classify_failures(case, answer, include_hits, forbidden_hits):
    failures = []
    must_include = case.get("must_include") or []
    if forbidden_hits:
        if case.get("category") in ("performance", "comparison") or any(word in answer for word in ["九龙灌浴", "吉祥颂"]):
            failures.append("intent_misroute")
        else:
            failures.append("hallucination")
    if include_hits < len(must_include):
        failures.append("missing_fact")
    if answer.startswith("我给您提炼一下"):
        failures.append("retrieval_mismatch")
    if len(answer) > 520 and case.get("category") in ("small_talk", "performance", "opening", "ticket"):
        failures.append("too_verbose_or_irrelevant")
    return list(dict.fromkeys(failures))


def score_case(case, answer, semantic_covered_include=None):
    answer = str(answer or "")
    must_include = [str(word) for word in case.get("must_include") or []]
    must_not_include = [str(word) for word in case.get("must_not_include") or []]
    semantic_covered = {str(word) for word in (semantic_covered_include or []) if str(word).strip()}
    matched_include = [
        word for word in must_include
        if _keyword_matches(answer, word, relaxed=True) or word in semantic_covered
    ]
    missing_include = [
        word for word in must_include
        if word and not _keyword_matches(answer, word, relaxed=True) and word not in semantic_covered
    ]
    include_hits = len(matched_include)
    forbidden_hits = [word for word in must_not_include if _keyword_matches(answer, word, relaxed=False)]

    fact_score = 5.0 * (include_hits / float(len(must_include) or 1))
    intent_score = 2.0 if not forbidden_hits else 0.0
    completeness_score = 1.5 if include_hits == len(must_include) else 1.5 * (include_hits / float(len(must_include) or 1))
    expression_score = 1.0 if 8 <= len(answer) <= 520 and not answer.startswith("我给您提炼一下") else 0.3
    grounding_score = 0.5 if not forbidden_hits else 0.0
    score = fact_score + intent_score + completeness_score + expression_score + grounding_score

    failure_types = _classify_failures(case, answer, include_hits, forbidden_hits)
    if forbidden_hits and case.get("category") in ("performance", "comparison"):
        score = min(score, 3.0)
    elif forbidden_hits:
        score = min(score, 4.0)
    if "retrieval_mismatch" in failure_types:
        score = min(score, 6.0)

    return {
        "score": round(max(0.0, min(10.0, score)), 2),
        "include_hits": include_hits,
        "include_total": len(must_include),
        "matched_include": matched_include,
        "missing_include": missing_include,
        "forbidden_hits": forbidden_hits,
        "failure_types": failure_types if score < 8.0 else [],
    }


def _case_from_item(item):
    expected = dict((item or {}).get("expected") or {})
    return {
        "id": str((item or {}).get("id", "")),
        "category": str((item or {}).get("category", "")),
        "question": str((item or {}).get("question", "")),
        "must_include": [str(word) for word in expected.get("must_include") or []],
        "must_not_include": [str(word) for word in expected.get("must_not_include") or []],
        "source_doc": str(expected.get("source_doc", "")),
        "weight": expected.get("weight", 1),
    }


def _semantic_review_default():
    return {
        "reviewed": False,
        "adjusted": False,
        "covered_include": [],
        "evidence": "",
        "confidence": 0.0,
        "error": "",
    }


def _semantic_review_candidate(item):
    hit = dict((item or {}).get("hit_detail") or {})
    failures = item.get("failure_types") or []
    return (
        str(item.get("answer_provider") or "") == "deepseek"
        and float(item.get("score") or 0) < 8.0
        and "missing_fact" in failures
        and bool(hit.get("missing_include"))
    )


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
    raise ValueError("LLM 返回非 JSON")


class DeepSeekSemanticReviewer(object):
    def __init__(self, service=None):
        self.service = service or RAGService()

    def __call__(self, case, item):
        hit = item.get("hit_detail") or {}
        prompt = (
            "你是问答评测语义裁判。请只判断“当前未命中的预期包含项”是否已经被实际回答用等价表达明确覆盖。\n"
            "严禁因为回答流畅就放宽标准；严禁移除或忽略不应出现项。不要重新回答问题。\n"
            "必须只输出 JSON，不要 Markdown。\n\n"
            "输出格式：{{\"covered_include\":[\"...\"],\"evidence\":\"一句话证据\",\"confidence\":0.0}}\n\n"
            "测试问题：{question}\n"
            "预期应包含：{must_include}\n"
            "预期不应出现：{must_not_include}\n"
            "当前未命中项：{missing_include}\n"
            "实际回答：{answer}\n"
        ).format(
            question=case.get("question", ""),
            must_include=json.dumps(case.get("must_include") or [], ensure_ascii=False),
            must_not_include=json.dumps(case.get("must_not_include") or [], ensure_ascii=False),
            missing_include=json.dumps(hit.get("missing_include") or [], ensure_ascii=False),
            answer=item.get("answer", ""),
        )
        content = self._chat_json(prompt)
        return _extract_json_object(content)

    def _chat_json(self, prompt):
        api_key = getattr(self.service, "api_key", "") or os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise ValueError("未配置 DeepSeek API Key，无法进行语义复核。")
        api_base = getattr(self.service, "api_base", "") or os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com/v1"
        model = getattr(self.service, "model", "") or os.getenv("DEEPSEEK_MODEL") or "deepseek-chat"
        try:
            timeout_seconds = float(os.getenv("EVALUATION_REVIEW_TIMEOUT_SECONDS", os.getenv("EVALUATION_LLM_TIMEOUT_SECONDS", "30")))
        except Exception:
            timeout_seconds = 30.0
        body = json.dumps({
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "你是严格的中文问答评测语义裁判，只输出 JSON。",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "max_tokens": 500,
        }).encode("utf-8")
        req = Request(api_base.rstrip("/") + "/chat/completions", data=body, headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + api_key.strip(),
        })
        with urlopen(req, timeout=timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"].strip()


def _normalize_review_decision(decision, missing_include):
    if isinstance(decision, str):
        decision = _extract_json_object(decision)
    decision = dict(decision or {})
    missing_set = {str(word) for word in (missing_include or [])}
    covered = []
    for word in decision.get("covered_include") or []:
        text = str(word)
        if text in missing_set and text not in covered:
            covered.append(text)
    try:
        confidence = float(decision.get("confidence", 0) or 0)
    except Exception:
        confidence = 0.0
    return {
        "covered_include": covered,
        "evidence": str(decision.get("evidence", "")),
        "confidence": max(0.0, min(1.0, confidence)),
    }


def semantic_review_low_score_items(items, reviewer=None, progress_callback=None, cancel_checker=None, mode="deepseek"):
    if mode != "deepseek":
        return list(items or []), {"reviewed": 0, "adjusted": 0, "errors": 0}
    reviewed_items = [dict(item or {}) for item in (items or [])]
    candidates = [item for item in reviewed_items if _semantic_review_candidate(item)]
    stats = {"reviewed": 0, "adjusted": 0, "errors": 0}
    if not candidates:
        return reviewed_items, stats
    reviewer = reviewer or DeepSeekSemanticReviewer()

    def emit(event, completed, item=None, error="", message=""):
        if not progress_callback:
            return
        progress_callback({
            "event": event,
            "mode": mode,
            "total": len(candidates),
            "completed": completed,
            "percent": int(round(completed / float(len(candidates) or 1) * 100)),
            "current_case_id": (item or {}).get("id", ""),
            "current_question": (item or {}).get("question", ""),
            "error": str(error or ""),
            "message": str(message or ""),
        })

    for index, item in enumerate(candidates):
        if cancel_checker and cancel_checker():
            emit("cancelled", index, item, message="语义复核已结束，未写入成功缓存。")
            raise EvaluationCancelled("语义复核已由管理员终止。")
        item["semantic_review"] = dict(_semantic_review_default(), reviewed=True)
        emit(
            "semantic_review_started",
            index,
            item,
            message="正在语义复核低分题 {0}".format(item.get("id", "")),
        )
        case = _case_from_item(item)
        hit = item.get("hit_detail") or {}
        missing_include = [str(word) for word in hit.get("missing_include") or []]
        try:
            decision = _normalize_review_decision(reviewer(case, item), missing_include)
            covered = decision["covered_include"]
            if covered:
                scored = score_case(case, item.get("answer", ""), semantic_covered_include=covered)
                item["score"] = scored["score"]
                item["hit_detail"] = {
                    "include_hits": scored["include_hits"],
                    "include_total": scored["include_total"],
                    "matched_include": scored["matched_include"],
                    "missing_include": scored["missing_include"],
                    "forbidden_hits": scored["forbidden_hits"],
                }
                item["failure_types"] = scored["failure_types"]
                stats["adjusted"] += 1
            item["semantic_review"] = {
                "reviewed": True,
                "adjusted": bool(covered),
                "covered_include": covered,
                "evidence": decision["evidence"],
                "confidence": decision["confidence"],
                "error": "",
            }
        except Exception as exc:
            stats["errors"] += 1
            review = dict(_semantic_review_default(), reviewed=True)
            review["error"] = str(exc)
            item["semantic_review"] = review
        stats["reviewed"] += 1
        emit(
            "semantic_review_finished",
            index + 1,
            item,
            message="已完成低分题语义复核 {0}/{1}".format(index + 1, len(candidates)),
        )
        if cancel_checker and cancel_checker():
            emit("cancelled", index + 1, item, message="语义复核已结束，未写入成功缓存。")
            raise EvaluationCancelled("语义复核已由管理员终止。")
    return reviewed_items, stats


def _deepseek_key_configured():
    return bool((os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip())


def evaluate(mode="local", dataset_path=DEFAULT_DATASET, progress_callback=None, cancel_checker=None, semantic_reviewer=None):
    if mode not in ("local", "deepseek"):
        raise ValueError("评测模式仅支持 local 或 deepseek。")
    load_backend_env()
    if mode == "deepseek" and not _deepseek_key_configured():
        raise ValueError("未配置 DeepSeek API Key，请在 backend/.env 中设置 DEEPSEEK_API_KEY。")

    previous_local_only = os.environ.get("LOCAL_RAG_ONLY")
    previous_force_deepseek = os.environ.get("EVALUATION_FORCE_DEEPSEEK")
    if mode == "local":
        os.environ["LOCAL_RAG_ONLY"] = "1"
        os.environ.pop("EVALUATION_FORCE_DEEPSEEK", None)
        service_factory = lambda: RAGService(api_key="")
    else:
        os.environ.pop("LOCAL_RAG_ONLY", None)
        os.environ["EVALUATION_FORCE_DEEPSEEK"] = "1"
        service_factory = lambda: RAGService()

    init_knowledge_base()
    service = service_factory()
    items = []
    total = 0.0
    fact_hits = 0
    provider_stats = {}
    def emit_progress(event, cases, completed=0, current_case=None, error="", message=""):
        if not progress_callback:
            return
        total_cases = len(cases or [])
        progress_callback({
            "event": event,
            "mode": mode,
            "total": total_cases,
            "completed": completed,
            "percent": int(round(completed / float(total_cases) * 100)) if total_cases else 0,
            "current_case_id": (current_case or {}).get("id", ""),
            "current_question": (current_case or {}).get("question", ""),
            "error": str(error or ""),
            "message": str(message or ""),
        })

    def check_cancel(cases, completed=0, current_case=None):
        if cancel_checker and cancel_checker():
            emit_progress(
                "cancelled",
                cases,
                completed=completed,
                current_case=current_case,
                message="评测已结束，未写入成功缓存。",
            )
            raise EvaluationCancelled("评测已由管理员终止。")

    try:
        cases = load_cases(dataset_path)
        for index, case in enumerate(cases):
            check_cancel(cases, completed=index, current_case=case)
            emit_progress("case_started", cases, completed=index, current_case=case)
            started = time.time()
            result = service.chat_detail(
                case["question"],
                history=[],
                interest="",
                force_llm=(mode == "deepseek"),
                evaluation_rag=(mode == "deepseek"),
            )
            answer = result.get("answer", "")
            answer_provider = result.get("answer_provider") or ("unknown" if mode == "deepseek" else "local")
            provider_stats[answer_provider] = provider_stats.get(answer_provider, 0) + 1
            if mode == "deepseek" and answer_provider != "deepseek":
                error = "DeepSeek 评测没有获得真实 DeepSeek 回答（{0} 返回 {1}），请检查网络、API Key 或 DEEPSEEK_BASE_URL 后重跑。".format(
                    case.get("id", "未知题号"),
                    answer_provider,
                )
                emit_progress("case_failed", cases, completed=index, current_case=case, error=error)
                raise ValueError(error)
            scored = score_case(case, answer)
            item = {
                "id": case["id"],
                "category": case.get("category", ""),
                "question": case["question"],
                "expected": {
                    "must_include": [str(word) for word in case.get("must_include") or []],
                    "must_not_include": [str(word) for word in case.get("must_not_include") or []],
                    "source_doc": case.get("source_doc", ""),
                    "weight": case.get("weight", 1),
                },
                "answer": answer,
                "answer_provider": answer_provider,
                "score": scored["score"],
                "hit_detail": {
                    "include_hits": scored["include_hits"],
                    "include_total": scored["include_total"],
                    "matched_include": scored["matched_include"],
                    "missing_include": scored["missing_include"],
                    "forbidden_hits": scored["forbidden_hits"],
                },
                "failure_types": scored["failure_types"],
                "latency_ms": int((time.time() - started) * 1000),
                "sources": result.get("sources", []),
            }
            items.append(item)
            total += scored["score"] * float(case.get("weight", 1))
            if scored["include_hits"] == scored["include_total"] and not scored["forbidden_hits"]:
                fact_hits += 1
            emit_progress("case_finished", cases, completed=index + 1, current_case=case)
            check_cancel(cases, completed=index + 1, current_case=case)
        if mode == "deepseek" and provider_stats.get("deepseek", 0) != len(cases):
            raise ValueError("DeepSeek 评测没有获得真实 DeepSeek 回答，请检查网络、API Key 或 DEEPSEEK_BASE_URL 后重跑。")
        semantic_review_stats = {"reviewed": 0, "adjusted": 0, "errors": 0}
        if mode == "deepseek":
            items, semantic_review_stats = semantic_review_low_score_items(
                items,
                reviewer=semantic_reviewer,
                progress_callback=progress_callback,
                cancel_checker=cancel_checker,
                mode=mode,
            )

        total = 0.0
        fact_hits = 0
        weight_by_id = {case.get("id"): float(case.get("weight", 1) or 1) for case in cases}
        for item in items:
            hit = item.get("hit_detail") or {}
            weight = weight_by_id.get(item.get("id"), 1.0)
            total += float(item.get("score", 0) or 0) * weight
            if hit.get("include_hits") == hit.get("include_total") and not hit.get("forbidden_hits"):
                fact_hits += 1
        max_score = 10.0 * sum(float(case.get("weight", 1)) for case in cases)
        summary = {
            "mode": mode,
            "model": getattr(service, "model", "") if mode == "deepseek" else "local-rag",
            "scoring_version": SCORING_VERSION,
            "semantic_review_version": SEMANTIC_REVIEW_VERSION if mode == "deepseek" else "",
            "semantic_review_stats": semantic_review_stats,
            "case_count": len(cases),
            "score_percent": round(total / max_score * 100, 2) if max_score else 0.0,
            "fact_accuracy": round(fact_hits / float(len(cases) or 1), 4),
            "failed_count": len([item for item in items if item["score"] < 8]),
            "avg_latency_ms": round(sum(item["latency_ms"] for item in items) / float(len(items) or 1), 2),
            "provider_stats": provider_stats,
            "items": items,
        }
        emit_progress("completed", cases, completed=len(cases), message="评测完成")
        return summary
    finally:
        if previous_local_only is None:
            os.environ.pop("LOCAL_RAG_ONLY", None)
        else:
            os.environ["LOCAL_RAG_ONLY"] = previous_local_only
        if previous_force_deepseek is None:
            os.environ.pop("EVALUATION_FORCE_DEEPSEEK", None)
        else:
            os.environ["EVALUATION_FORCE_DEEPSEEK"] = previous_force_deepseek


def main(argv=None):
    parser = argparse.ArgumentParser(description="评测灵山胜境本地问答质量。")
    parser.add_argument("--mode", default="local", choices=["local", "deepseek"])
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--output", default="")
    args = parser.parse_args(argv)
    summary = evaluate(mode=args.mode, dataset_path=args.dataset)
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
    print("score_percent={0} fact_accuracy={1} failed_count={2} avg_latency_ms={3}".format(
        summary["score_percent"],
        summary["fact_accuracy"],
        summary["failed_count"],
        summary["avg_latency_ms"],
    ))
    return 0 if summary["score_percent"] >= 90 and summary["fact_accuracy"] >= 0.9 else 1


if __name__ == "__main__":
    raise SystemExit(main())
