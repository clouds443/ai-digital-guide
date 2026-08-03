# -*- coding: utf-8 -*-
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from unittest import mock


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_PATH = os.path.join(ROOT_DIR, "scripts", "evaluate_lingshan_qa.py")
DATASET_PATH = os.path.join(ROOT_DIR, "tests", "fixtures", "lingshan_qa_100.jsonl")


def load_eval_module():
    spec = importlib.util.spec_from_file_location("evaluate_lingshan_qa", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LingshanEvalContractTests(unittest.TestCase):
    def test_dataset_contains_exactly_100_lingshan_cases_with_required_fields(self):
        self.assertTrue(os.path.exists(DATASET_PATH))
        with open(DATASET_PATH, "r", encoding="utf-8") as f:
            cases = [json.loads(line) for line in f if line.strip()]

        self.assertEqual(100, len(cases))
        self.assertEqual("Q001", cases[0]["id"])
        self.assertEqual("Q100", cases[-1]["id"])
        ids = [case["id"] for case in cases]
        self.assertEqual(len(ids), len(set(ids)))
        for case in cases:
            self.assertIn("question", case)
            self.assertIn("must_include", case)
            self.assertIn("must_not_include", case)
            self.assertIn("source_doc", case)
            self.assertIn("category", case)
            self.assertGreater(len(case["must_include"]), 0)
            self.assertIn("拈花湾", case["must_not_include"])

    def test_score_case_penalizes_wrong_performance_template(self):
        module = load_eval_module()
        case = {
            "id": "Q022",
            "category": "performance",
            "question": "《吉祥颂》每天什么时间演出？",
            "must_include": ["吉祥颂", "10:35", "11:30", "14:00", "16:00", "20分钟"],
            "must_not_include": ["拈花湾", "13:30", "九龙灌浴"],
            "source_doc": "灵山胜境：历史、文化、景点特色与个性化游览指南.docx",
            "weight": 1,
        }

        wrong = module.score_case(case, "九龙灌浴常见场次为 10:00、11:30、13:30、15:00，每场约 15 分钟。")
        right = module.score_case(case, "《灵山吉祥颂》演出时间为 10:35、11:30、14:00、16:00，每场约 20分钟。")

        self.assertLessEqual(wrong["score"], 3)
        self.assertIn("intent_misroute", wrong["failure_types"])
        self.assertGreaterEqual(right["score"], 9)
        self.assertEqual([], right["failure_types"])

    def test_score_case_reports_keyword_hit_details_for_admin_visualization(self):
        module = load_eval_module()
        case = {
            "id": "QX03",
            "category": "performance",
            "question": "《吉祥颂》每天什么时间演出？",
            "must_include": ["吉祥颂", "10:35", "11:30", "14:00"],
            "must_not_include": ["拈花湾", "九龙灌浴"],
            "source_doc": "unit-test",
            "weight": 1,
        }

        scored = module.score_case(case, "吉祥颂通常在10:35和11:30演出，不要和九龙灌浴混淆。")

        self.assertEqual(["吉祥颂", "10:35", "11:30"], scored["matched_include"])
        self.assertEqual(["14:00"], scored["missing_include"])
        self.assertEqual(["九龙灌浴"], scored["forbidden_hits"])
        self.assertEqual(3, scored["include_hits"])
        self.assertEqual(4, scored["include_total"])

    def test_score_case_accepts_equivalent_keyword_formatting_without_overmatching(self):
        module = load_eval_module()
        ticket_case = {
            "id": "Q013",
            "category": "ticket",
            "question": "观光车联票多少钱？",
            "must_include": ["225元", "门票+观光车"],
            "must_not_include": ["拈花湾"],
            "source_doc": "unit-test",
            "weight": 1,
        }
        season_case = {
            "id": "Q015",
            "category": "visit_time",
            "question": "灵山胜境最佳游览季节是什么时候？",
            "must_include": ["3-5月", "9-11月"],
            "must_not_include": ["拈花湾"],
            "source_doc": "unit-test",
            "weight": 1,
        }

        ticket = module.score_case(ticket_case, "观光车联票的价格是225元。这个联票包含了景区门票和观光车。")
        season = module.score_case(season_case, "最推荐的季节是春秋两季，也就是每年的3月到5月，以及9月到11月。")
        negative = module.score_case(ticket_case, "225元只包含景区门票不含观光车，观光车需要另买，费用请以现场公告为准。")
        forbidden = module.score_case(ticket_case, "225 元的门票和观光车联票不适用于拈花湾。")

        self.assertEqual(["225元", "门票+观光车"], ticket["matched_include"])
        self.assertEqual([], ticket["missing_include"])
        self.assertGreaterEqual(ticket["score"], 9)
        self.assertEqual(["3-5月", "9-11月"], season["matched_include"])
        self.assertEqual([], season["missing_include"])
        self.assertGreaterEqual(season["score"], 9)
        self.assertEqual(["门票+观光车"], negative["missing_include"])
        self.assertEqual(["拈花湾"], forbidden["forbidden_hits"])

    def test_score_case_accepts_year_range_with_repeated_year_unit(self):
        module = load_eval_module()
        case = {
            "id": "Q007",
            "category": "history",
            "question": "祥符禅寺什么时候得名？",
            "must_include": ["北宋", "大中祥符", "1008-1016"],
            "must_not_include": ["拈花湾"],
            "source_doc": "unit-test",
            "weight": 1,
        }

        scored = module.score_case(case, "祥符禅寺得名于北宋大中祥符年间，具体时间约为公元1008年至1016年。")

        self.assertEqual(["北宋", "大中祥符", "1008-1016"], scored["matched_include"])
        self.assertEqual([], scored["missing_include"])
        self.assertGreaterEqual(scored["score"], 9)

    def test_default_semantic_reviewer_calls_deepseek_with_valid_json_prompt(self):
        module = load_eval_module()
        case = {
            "id": "Q007",
            "category": "history",
            "question": "祥符禅寺什么时候得名？",
            "must_include": ["北宋", "大中祥符", "1008-1016"],
            "must_not_include": ["拈花湾"],
            "source_doc": "unit-test",
            "weight": 1,
        }
        item = {
            "id": "Q007",
            "category": "history",
            "question": case["question"],
            "expected": {
                "must_include": case["must_include"],
                "must_not_include": case["must_not_include"],
                "source_doc": case["source_doc"],
                "weight": case["weight"],
            },
            "answer": "祥符禅寺得名于北宋大中祥符年间，具体时间约为公元1008年至1016年。",
            "answer_provider": "deepseek",
            "score": 7.83,
            "hit_detail": {
                "include_hits": 2,
                "include_total": 3,
                "matched_include": ["北宋", "大中祥符"],
                "missing_include": ["1008-1016"],
                "forbidden_hits": [],
            },
            "failure_types": ["missing_fact"],
        }
        captured = {}

        class FakeService(object):
            api_key = "sk-deepseek-unit-test-key"
            api_base = "https://unit.test/v1"
            model = "deepseek-chat"

        class FakeResponse(object):
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps({
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps({
                                    "covered_include": ["1008-1016"],
                                    "evidence": "回答中的1008年至1016年覆盖预期年份段。",
                                    "confidence": 0.96,
                                }, ensure_ascii=False)
                            }
                        }
                    ]
                }, ensure_ascii=False).encode("utf-8")

        def fake_urlopen(request, timeout=None):
            captured["timeout"] = timeout
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse()

        with mock.patch.object(module, "urlopen", side_effect=fake_urlopen):
            decision = module.DeepSeekSemanticReviewer(service=FakeService())(case, item)

        self.assertEqual(["1008-1016"], decision["covered_include"])
        prompt = captured["body"]["messages"][1]["content"]
        self.assertIn('"covered_include"', prompt)
        self.assertIn("1008年至1016年", prompt)

    def test_semantic_review_marks_equivalent_missing_include_without_touching_forbidden(self):
        module = load_eval_module()
        case = {
            "id": "Q010",
            "category": "culture",
            "question": "灵山梵宫的核心价值是什么？",
            "must_include": ["世界佛教论坛永久会址"],
            "must_not_include": ["拈花湾"],
            "source_doc": "unit-test",
            "weight": 1,
        }
        answer = "它的核心在于这里是世界佛教论坛的永久会址，同时别把它和拈花湾混在一起。"
        scored = module.score_case(case, answer)
        item = {
            "id": case["id"],
            "category": case["category"],
            "question": case["question"],
            "expected": {
                "must_include": case["must_include"],
                "must_not_include": case["must_not_include"],
                "source_doc": case["source_doc"],
                "weight": case["weight"],
            },
            "answer": answer,
            "answer_provider": "deepseek",
            "score": scored["score"],
            "hit_detail": {
                "include_hits": scored["include_hits"],
                "include_total": scored["include_total"],
                "matched_include": scored["matched_include"],
                "missing_include": scored["missing_include"],
                "forbidden_hits": scored["forbidden_hits"],
            },
            "failure_types": scored["failure_types"],
            "latency_ms": 1200,
            "sources": [],
        }

        def fake_reviewer(review_case, review_item):
            self.assertEqual("Q010", review_case["id"])
            self.assertEqual(["世界佛教论坛永久会址"], review_item["hit_detail"]["missing_include"])
            return {
                "covered_include": ["世界佛教论坛永久会址"],
                "evidence": "回答中的“世界佛教论坛的永久会址”与预期事实等价。",
                "confidence": 0.94,
            }

        reviewed_items, stats = module.semantic_review_low_score_items([item], reviewer=fake_reviewer)
        reviewed = reviewed_items[0]

        self.assertEqual("llm_low_score_review_v1", module.SEMANTIC_REVIEW_VERSION)
        self.assertEqual(1, stats["reviewed"])
        self.assertEqual(1, stats["adjusted"])
        self.assertEqual(["世界佛教论坛永久会址"], reviewed["hit_detail"]["matched_include"])
        self.assertEqual([], reviewed["hit_detail"]["missing_include"])
        self.assertEqual(["拈花湾"], reviewed["hit_detail"]["forbidden_hits"])
        self.assertIn("hallucination", reviewed["failure_types"])
        self.assertLessEqual(reviewed["score"], 4.0)
        self.assertTrue(reviewed["semantic_review"]["reviewed"])
        self.assertTrue(reviewed["semantic_review"]["adjusted"])
        self.assertEqual(["世界佛教论坛永久会址"], reviewed["semantic_review"]["covered_include"])
        self.assertIn("永久会址", reviewed["semantic_review"]["evidence"])

    def test_semantic_review_can_cover_open_close_time_and_records_reviewer_errors(self):
        module = load_eval_module()
        case = {
            "id": "Q030",
            "category": "service",
            "question": "灵山胜境开放时间是什么？",
            "must_include": ["9:00-17:00"],
            "must_not_include": ["拈花湾"],
            "source_doc": "unit-test",
            "weight": 1,
        }
        answer = "游客可在上午9:00入园，下午17:00闭园前完成游览。"
        scored = module.score_case(case, answer)
        item = {
            "id": case["id"],
            "category": case["category"],
            "question": case["question"],
            "expected": {
                "must_include": case["must_include"],
                "must_not_include": case["must_not_include"],
                "source_doc": case["source_doc"],
                "weight": case["weight"],
            },
            "answer": answer,
            "answer_provider": "deepseek",
            "score": scored["score"],
            "hit_detail": {
                "include_hits": scored["include_hits"],
                "include_total": scored["include_total"],
                "matched_include": scored["matched_include"],
                "missing_include": scored["missing_include"],
                "forbidden_hits": scored["forbidden_hits"],
            },
            "failure_types": scored["failure_types"],
            "latency_ms": 980,
            "sources": [],
        }

        reviewed_items, stats = module.semantic_review_low_score_items(
            [item],
            reviewer=lambda review_case, review_item: {
                "covered_include": ["9:00-17:00"],
                "evidence": "9:00入园、17:00闭园覆盖开放时间段。",
                "confidence": 0.91,
            },
        )

        self.assertEqual(1, stats["adjusted"])
        self.assertGreaterEqual(reviewed_items[0]["score"], 8.0)
        self.assertEqual(["9:00-17:00"], reviewed_items[0]["hit_detail"]["matched_include"])
        self.assertEqual([], reviewed_items[0]["hit_detail"]["missing_include"])

        error_items, error_stats = module.semantic_review_low_score_items(
            [item],
            reviewer=lambda review_case, review_item: (_ for _ in ()).throw(ValueError("LLM 返回非 JSON")),
        )

        self.assertEqual(scored["score"], error_items[0]["score"])
        self.assertEqual(["9:00-17:00"], error_items[0]["hit_detail"]["missing_include"])
        self.assertEqual(1, error_stats["errors"])
        self.assertIn("LLM 返回非 JSON", error_items[0]["semantic_review"]["error"])

    def test_deepseek_evaluation_runs_low_score_semantic_review_after_rule_scoring(self):
        module = load_eval_module()
        case = {
            "id": "QX_REVIEW",
            "category": "culture",
            "question": "灵山梵宫的核心价值是什么？",
            "must_include": ["世界佛教论坛永久会址"],
            "must_not_include": ["拈花湾"],
            "source_doc": "unit-test",
            "weight": 1,
        }

        class FakeRAGService(object):
            def __init__(self, api_key=None, api_base=None):
                self.model = "deepseek-chat"

            def chat_detail(self, query, history=None, interest=None, force_llm=False, evaluation_rag=False):
                return {
                    "answer": "灵山梵宫的核心价值在于它是世界佛教论坛的永久会址。",
                    "answer_provider": "deepseek",
                    "sources": [],
                }

        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", suffix=".jsonl") as f:
            f.write(json.dumps(case, ensure_ascii=False) + "\n")
            dataset = f.name
        try:
            with mock.patch.object(module, "init_knowledge_base", return_value=None), mock.patch.object(
                module, "RAGService", FakeRAGService
            ), mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-deepseek-unit-test-key"}, clear=False):
                summary = module.evaluate(
                    mode="deepseek",
                    dataset_path=dataset,
                    semantic_reviewer=lambda review_case, review_item: {
                        "covered_include": ["世界佛教论坛永久会址"],
                        "evidence": "语义等价覆盖。",
                        "confidence": 0.93,
                    },
                )
        finally:
            os.remove(dataset)

        self.assertEqual("llm_low_score_review_v1", summary["semantic_review_version"])
        self.assertEqual(1, summary["semantic_review_stats"]["reviewed"])
        self.assertEqual(1, summary["semantic_review_stats"]["adjusted"])
        self.assertGreaterEqual(summary["score_percent"], 90)
        self.assertEqual(0, summary["failed_count"])
        self.assertEqual(["世界佛教论坛永久会址"], summary["items"][0]["hit_detail"]["matched_include"])
        self.assertEqual([], summary["items"][0]["hit_detail"]["missing_include"])

    def test_local_evaluation_reaches_ninety_percent_after_rag_optimization(self):
        module = load_eval_module()

        summary = module.evaluate(mode="local", dataset_path=DATASET_PATH)

        self.assertGreaterEqual(summary["score_percent"], 90.0)
        self.assertGreaterEqual(summary["fact_accuracy"], 0.9)
        high_risk_failures = [
            item for item in summary["items"]
            if item["id"] in {"Q021", "Q022", "Q023", "Q027", "Q051", "Q058", "Q086"} and item["score"] < 8
        ]
        self.assertEqual([], high_risk_failures)

    def test_deepseek_evaluation_uses_llm_provider_and_clears_local_only_flag(self):
        module = load_eval_module()
        case = {
            "id": "QX01",
            "category": "scenic",
            "question": "灵山大佛有多高？",
            "must_include": ["灵山大佛", "88米"],
            "must_not_include": ["拈花湾"],
            "source_doc": "unit-test",
            "weight": 1,
        }

        seen = {}

        class FakeRAGService(object):
            def __init__(self, api_key=None, api_base=None):
                seen["api_key"] = api_key
                seen["local_only"] = os.environ.get("LOCAL_RAG_ONLY", "")
                self.model = os.getenv("DEEPSEEK_MODEL", "")

            def chat_detail(self, query, history=None, interest=None, force_llm=False, evaluation_rag=False):
                seen["force_llm"] = force_llm
                seen["evaluation_rag"] = evaluation_rag
                return {
                    "answer": "灵山大佛佛像高88米，是灵山胜境的核心地标。",
                    "answer_provider": "deepseek",
                    "sources": [],
                }

        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", suffix=".jsonl") as f:
            f.write(json.dumps(case, ensure_ascii=False) + "\n")
            dataset = f.name
        try:
            with mock.patch.object(module, "init_knowledge_base", return_value=None), mock.patch.object(
                module, "RAGService", FakeRAGService
            ), mock.patch.dict(
                os.environ,
                {
                    "LOCAL_RAG_ONLY": "1",
                    "DEEPSEEK_API_KEY": "sk-deepseek-unit-test-key",
                    "DEEPSEEK_MODEL": "deepseek-chat",
                },
                clear=False,
            ):
                summary = module.evaluate(mode="deepseek", dataset_path=dataset)
        finally:
            os.remove(dataset)

        self.assertEqual(summary["mode"], "deepseek")
        self.assertEqual(summary["model"], "deepseek-chat")
        self.assertGreaterEqual(summary["score_percent"], 90)
        self.assertEqual(1, summary["provider_stats"]["deepseek"])
        self.assertEqual(seen["api_key"], None)
        self.assertNotEqual(seen["local_only"], "1")
        self.assertIs(seen["force_llm"], True)
        self.assertIs(seen["evaluation_rag"], True)

    def test_deepseek_evaluation_reports_case_progress_for_admin_ui(self):
        module = load_eval_module()
        case = {
            "id": "QX_PROGRESS",
            "category": "route",
            "question": "历史文化爱好者怎么游灵山？",
            "must_include": ["6小时", "灵山大照壁"],
            "must_not_include": ["拈花湾"],
            "source_doc": "unit-test",
            "weight": 1,
        }
        progress_events = []

        class FakeRAGService(object):
            def __init__(self, api_key=None, api_base=None):
                self.model = os.getenv("DEEPSEEK_MODEL", "")

            def chat_detail(self, query, history=None, interest=None, force_llm=False, evaluation_rag=False):
                return {
                    "answer": "历史文化爱好者可以安排6小时深度游，从灵山大照壁开始慢慢参访。",
                    "answer_provider": "deepseek",
                    "sources": [],
                }

        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", suffix=".jsonl") as f:
            f.write(json.dumps(case, ensure_ascii=False) + "\n")
            dataset = f.name
        try:
            with mock.patch.object(module, "init_knowledge_base", return_value=None), mock.patch.object(
                module, "RAGService", FakeRAGService
            ), mock.patch.dict(
                os.environ,
                {
                    "DEEPSEEK_API_KEY": "sk-deepseek-unit-test-key",
                    "DEEPSEEK_MODEL": "deepseek-chat",
                },
                clear=False,
            ):
                summary = module.evaluate(
                    mode="deepseek",
                    dataset_path=dataset,
                    progress_callback=lambda event: progress_events.append(dict(event)),
                )
        finally:
            os.remove(dataset)

        self.assertEqual(1, summary["case_count"])
        self.assertIn("case_started", [event["event"] for event in progress_events])
        self.assertIn("case_finished", [event["event"] for event in progress_events])
        self.assertEqual("QX_PROGRESS", progress_events[0]["current_case_id"])
        self.assertEqual(1, progress_events[-1]["completed"])
        self.assertEqual(100, progress_events[-1]["percent"])

    def test_deepseek_evaluation_loads_backend_env_when_cli_env_is_empty(self):
        module = load_eval_module()
        case = {
            "id": "QX02",
            "category": "scenic",
            "question": "灵山大佛有多高？",
            "must_include": ["灵山大佛", "88米"],
            "must_not_include": ["拈花湾"],
            "source_doc": "unit-test",
            "weight": 1,
        }

        class FakeRAGService(object):
            def __init__(self, api_key=None, api_base=None):
                self.model = os.getenv("DEEPSEEK_MODEL", "")

            def chat_detail(self, query, history=None, interest=None, force_llm=False, evaluation_rag=False):
                return {
                    "answer": "灵山大佛佛像高88米，是灵山胜境的核心地标。",
                    "answer_provider": "deepseek",
                    "sources": [],
                }

        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", suffix=".jsonl") as f:
            f.write(json.dumps(case, ensure_ascii=False) + "\n")
            dataset = f.name
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", suffix=".env") as f:
            f.write("DEEPSEEK_API_KEY=sk-from-backend-env\nDEEPSEEK_MODEL=deepseek-chat\n")
            env_path = f.name
        try:
            with mock.patch.object(module, "init_knowledge_base", return_value=None), mock.patch.object(
                module, "RAGService", FakeRAGService
            ), mock.patch.object(module, "ENV_PATH", env_path), mock.patch.dict(os.environ, {}, clear=True):
                summary = module.evaluate(mode="deepseek", dataset_path=dataset)
        finally:
            os.remove(dataset)
            os.remove(env_path)

        self.assertEqual(summary["mode"], "deepseek")
        self.assertEqual(summary["model"], "deepseek-chat")
        self.assertGreaterEqual(summary["score_percent"], 90)
        self.assertEqual(1, summary["provider_stats"]["deepseek"])

    def test_deepseek_evaluation_rejects_all_local_fallback_answers(self):
        module = load_eval_module()
        case = {
            "id": "QX04",
            "category": "scenic",
            "question": "灵山大佛有多高？",
            "must_include": ["灵山大佛", "88米"],
            "must_not_include": ["拈花湾"],
            "source_doc": "unit-test",
            "weight": 1,
        }

        class FakeRAGService(object):
            def __init__(self, api_key=None, api_base=None):
                self.model = os.getenv("DEEPSEEK_MODEL", "")

            def chat_detail(self, query, history=None, interest=None, force_llm=False, evaluation_rag=False):
                return {
                    "answer": "灵山大佛佛像高88米，是灵山胜境的核心地标。",
                    "answer_provider": "local_fallback_after_llm_error",
                    "sources": [],
                }

        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", suffix=".jsonl") as f:
            f.write(json.dumps(case, ensure_ascii=False) + "\n")
            dataset = f.name
        try:
            with mock.patch.object(module, "init_knowledge_base", return_value=None), mock.patch.object(
                module, "RAGService", FakeRAGService
            ), mock.patch.dict(
                os.environ,
                {
                    "DEEPSEEK_API_KEY": "sk-deepseek-unit-test-key",
                    "DEEPSEEK_MODEL": "deepseek-chat",
                },
                clear=False,
            ):
                with self.assertRaisesRegex(ValueError, "没有获得真实 DeepSeek 回答"):
                    module.evaluate(mode="deepseek", dataset_path=dataset)
        finally:
            os.remove(dataset)

    def test_deepseek_evaluation_rejects_mixed_direct_fact_answers(self):
        module = load_eval_module()
        cases = [
            {
                "id": "QX05",
                "category": "overview",
                "question": "灵山胜境在哪里？",
                "must_include": ["无锡"],
                "must_not_include": ["拈花湾"],
                "source_doc": "unit-test",
                "weight": 1,
            },
            {
                "id": "QX06",
                "category": "scenic",
                "question": "灵山大佛有多高？",
                "must_include": ["88米"],
                "must_not_include": ["拈花湾"],
                "source_doc": "unit-test",
                "weight": 1,
            },
        ]

        class FakeRAGService(object):
            def __init__(self, api_key=None, api_base=None):
                self.model = os.getenv("DEEPSEEK_MODEL", "")
                self.calls = 0

            def chat_detail(self, query, history=None, interest=None, force_llm=False, evaluation_rag=False):
                self.calls += 1
                if self.calls == 1:
                    return {
                        "answer": "灵山胜境位于无锡。",
                        "answer_provider": "deepseek",
                        "sources": [],
                    }
                return {
                    "answer": "灵山大佛高88米。",
                    "answer_provider": "direct_fact",
                    "sources": [],
                }

        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", suffix=".jsonl") as f:
            for case in cases:
                f.write(json.dumps(case, ensure_ascii=False) + "\n")
            dataset = f.name
        try:
            with mock.patch.object(module, "init_knowledge_base", return_value=None), mock.patch.object(
                module, "RAGService", FakeRAGService
            ), mock.patch.dict(
                os.environ,
                {
                    "DEEPSEEK_API_KEY": "sk-deepseek-unit-test-key",
                    "DEEPSEEK_MODEL": "deepseek-chat",
                },
                clear=False,
            ):
                with self.assertRaisesRegex(ValueError, "没有获得真实 DeepSeek 回答"):
                    module.evaluate(mode="deepseek", dataset_path=dataset)
        finally:
            os.remove(dataset)

    def test_deepseek_evaluation_requires_configured_api_key(self):
        module = load_eval_module()

        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "", "OPENAI_API_KEY": ""}, clear=False):
            with self.assertRaisesRegex(ValueError, "未配置 DeepSeek API Key"):
                module.evaluate(mode="deepseek", dataset_path=DATASET_PATH)

    def test_deepseek_evaluation_cancel_checker_stops_before_next_case(self):
        module = load_eval_module()
        cases = [
            {
                "id": "QX_CANCEL_1",
                "category": "overview",
                "question": "灵山胜境在哪里？",
                "must_include": ["无锡"],
                "must_not_include": ["拈花湾"],
                "source_doc": "unit-test",
                "weight": 1,
            },
            {
                "id": "QX_CANCEL_2",
                "category": "scenic",
                "question": "灵山大佛有多高？",
                "must_include": ["88米"],
                "must_not_include": ["拈花湾"],
                "source_doc": "unit-test",
                "weight": 1,
            },
        ]
        answered = []

        class FakeRAGService(object):
            def __init__(self, api_key=None, api_base=None):
                self.model = "deepseek-chat"

            def chat_detail(self, query, history=None, interest=None, force_llm=False, evaluation_rag=False):
                answered.append(query)
                return {
                    "answer": "灵山胜境位于无锡，灵山大佛高88米。",
                    "answer_provider": "deepseek",
                    "sources": [],
                }

        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", suffix=".jsonl") as f:
            for case in cases:
                f.write(json.dumps(case, ensure_ascii=False) + "\n")
            dataset = f.name
        try:
            with mock.patch.object(module, "init_knowledge_base", return_value=None), mock.patch.object(
                module, "RAGService", FakeRAGService
            ), mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-deepseek-unit-test-key"}, clear=False):
                with self.assertRaises(module.EvaluationCancelled):
                    module.evaluate(
                        mode="deepseek",
                        dataset_path=dataset,
                        cancel_checker=lambda: len(answered) >= 1,
                    )
        finally:
            os.remove(dataset)

        self.assertEqual(1, len(answered))


if __name__ == "__main__":
    unittest.main()
