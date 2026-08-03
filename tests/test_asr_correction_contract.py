# -*- coding: utf-8 -*-
import json
import os
import sys
import unittest
from unittest import mock


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import asr_correction_service  # noqa: E402


class AsrCorrectionContractTests(unittest.TestCase):
    def test_leading_noise_cleanup_removes_wrong_opening_fragment_before_llm(self):
        result = asr_correction_service.normalize_asr_leading_noise("客我想问九龙灌浴几点开始")

        self.assertEqual("我想问九龙灌浴几点开始", result)

    def test_leading_noise_cleanup_keeps_real_scenic_question_body(self):
        result = asr_correction_service.normalize_asr_leading_noise("导请介绍灵山大佛")

        self.assertEqual("请介绍灵山大佛", result)
        self.assertIn("灵山大佛", result)

    def test_leading_noise_cleanup_extracts_generic_noisy_intent_prefixes(self):
        criticism = asr_correction_service.normalize_asr_leading_noise("可能头来了讲的什么东西啊啊太烂了")
        scenic = asr_correction_service.normalize_asr_leading_noise("全体耶出讲解一下佛祖坛")
        natural = asr_correction_service.normalize_asr_leading_noise("我想请你讲解一下佛足坛")

        self.assertEqual("讲的什么东西啊啊太烂了", criticism)
        self.assertEqual("讲解一下佛祖坛", scenic)
        self.assertEqual("我想请你讲解一下佛足坛", natural)

    def test_correction_uses_leading_noise_cleanup_when_deepseek_key_is_missing(self):
        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "", "OPENAI_API_KEY": ""}, clear=False):
            result = asr_correction_service.correct_asr_text("客我想问九龙灌浴几点开始")

        self.assertEqual("我想问九龙灌浴几点开始", result["text"])
        self.assertEqual("客我想问九龙灌浴几点开始", result["original_text"])
        self.assertEqual("我想问九龙灌浴几点开始", result["corrected_text"])
        self.assertFalse(result["llm_corrected"])
        self.assertTrue(result["leading_noise_removed"])
        self.assertIn("未配置", result["correction_error"])

    def test_correction_prompt_focuses_on_leading_characters_and_keeps_criticism(self):
        captured = {}
        payload = {
            "corrected_text": "讲得太烂了，我都没听懂",
            "changed": False,
            "confidence": 0.88,
            "reason": "保留批评语气",
        }

        class FakeResponse:
            def read(self):
                return json.dumps(
                    {"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]},
                    ensure_ascii=False,
                ).encode("utf-8")

        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return FakeResponse()

        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-" + "x" * 32}, clear=False):
            with mock.patch.object(asr_correction_service, "urlopen", side_effect=fake_urlopen):
                asr_correction_service.correct_asr_text("讲得太烂了，我都没听懂")

        prompt_text = "\n".join(item["content"] for item in captured["body"]["messages"])
        self.assertIn("前 2 到 8 个字", prompt_text)
        self.assertIn("不要删除批评", prompt_text)
        self.assertIn("从整句中提取用户真实意图", prompt_text)

    def test_deepseek_correction_extracts_real_intent_from_noisy_criticism(self):
        payload = {
            "corrected_text": "讲的什么东西啊太烂了",
            "changed": True,
            "confidence": 0.93,
            "reason": "删除开头无意义误识别片段，保留批评语气",
        }

        class FakeResponse:
            def read(self):
                return json.dumps(
                    {"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]},
                    ensure_ascii=False,
                ).encode("utf-8")

        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-" + "x" * 32}, clear=False):
            with mock.patch.object(asr_correction_service, "urlopen", return_value=FakeResponse()):
                result = asr_correction_service.correct_asr_text("可能千万万讲的什么东西啊太烂了")

        self.assertEqual("讲的什么东西啊太烂了", result["text"])
        self.assertEqual("可能千万万讲的什么东西啊太烂了", result["original_text"])
        self.assertTrue(result["llm_corrected"])
        self.assertEqual("deepseek", result["correction_provider"])
        self.assertEqual("", result["correction_error"])

    def test_deepseek_unchanged_result_still_uses_generic_intent_cleanup(self):
        payload = {
            "corrected_text": "讲的什么东西啊啊太烂了",
            "changed": False,
            "confidence": 0.9,
            "reason": "保留原句",
        }

        class FakeResponse:
            def read(self):
                return json.dumps(
                    {"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]},
                    ensure_ascii=False,
                ).encode("utf-8")

        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-" + "x" * 32}, clear=False):
            with mock.patch.object(asr_correction_service, "urlopen", return_value=FakeResponse()):
                result = asr_correction_service.correct_asr_text("可能头来了讲的什么东西啊啊太烂了")

        self.assertEqual("讲的什么东西啊啊太烂了", result["text"])
        self.assertTrue(result["leading_noise_removed"])

    def test_deepseek_correction_fixes_noisy_scenic_request_without_sad_tone(self):
        payload = {
            "corrected_text": "请讲解一下佛足坛",
            "changed": True,
            "confidence": 0.91,
            "reason": "纠正开头误识别和景点专名",
        }

        class FakeResponse:
            def read(self):
                return json.dumps(
                    {"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]},
                    ensure_ascii=False,
                ).encode("utf-8")

        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-" + "x" * 32}, clear=False):
            with mock.patch.object(asr_correction_service, "urlopen", return_value=FakeResponse()):
                result = asr_correction_service.correct_asr_text("全体耶出讲解一下佛祖坛")

        self.assertEqual("请讲解一下佛足坛", result["text"])
        self.assertTrue(result["llm_corrected"])
        self.assertEqual("", result["correction_error"])

    def test_deepseek_correction_rejects_generated_answer_json(self):
        payload = {
            "corrected_text": "佛足坛位于灵山胜境，是展示佛足文化的重要景点，建议您从五明桥之后前往参观，我可以为您详细介绍它的历史背景和观赏重点。",
            "changed": True,
            "confidence": 0.8,
            "reason": "错误地生成了回答",
        }

        class FakeResponse:
            def read(self):
                return json.dumps(
                    {"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]},
                    ensure_ascii=False,
                ).encode("utf-8")

        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-" + "x" * 32}, clear=False):
            with mock.patch.object(asr_correction_service, "urlopen", return_value=FakeResponse()):
                result = asr_correction_service.correct_asr_text("全体耶出讲解一下佛祖坛")

        self.assertEqual("讲解一下佛祖坛", result["text"])
        self.assertFalse(result["llm_corrected"])
        self.assertIn("疑似生成回答", result["correction_error"])

    def test_deepseek_correction_updates_obvious_asr_error(self):
        payload = {
            "corrected_text": "请介绍一下九龙灌浴",
            "changed": True,
            "confidence": 0.92,
            "reason": "景点专名误识别",
        }

        class FakeResponse:
            def read(self):
                return json.dumps(
                    {"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]},
                    ensure_ascii=False,
                ).encode("utf-8")

        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-" + "x" * 32}, clear=False):
            with mock.patch.object(asr_correction_service, "urlopen", return_value=FakeResponse()):
                result = asr_correction_service.correct_asr_text("请介绍一下九龙观浴")

        self.assertEqual("请介绍一下九龙灌浴", result["text"])
        self.assertEqual("请介绍一下九龙观浴", result["original_text"])
        self.assertEqual("请介绍一下九龙灌浴", result["corrected_text"])
        self.assertTrue(result["llm_corrected"])
        self.assertEqual("deepseek", result["correction_provider"])
        self.assertGreater(result["correction_confidence"], 0.8)
        self.assertEqual("", result["correction_error"])

    def test_correction_falls_back_when_deepseek_returns_invalid_json(self):
        class FakeResponse:
            def read(self):
                return json.dumps(
                    {"choices": [{"message": {"content": "我来回答：九龙灌浴很精彩。"}}]},
                    ensure_ascii=False,
                ).encode("utf-8")

        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-" + "x" * 32}, clear=False):
            with mock.patch.object(asr_correction_service, "urlopen", return_value=FakeResponse()):
                result = asr_correction_service.correct_asr_text("九龙观浴几点开始")

        self.assertEqual("九龙观浴几点开始", result["text"])
        self.assertFalse(result["llm_corrected"])
        self.assertIn("JSON", result["correction_error"])

    def test_correction_is_skipped_without_deepseek_key(self):
        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "", "OPENAI_API_KEY": ""}, clear=False):
            result = asr_correction_service.correct_asr_text("九龙观浴几点开始")

        self.assertEqual("九龙观浴几点开始", result["text"])
        self.assertFalse(result["llm_corrected"])
        self.assertIn("未配置", result["correction_error"])


if __name__ == "__main__":
    unittest.main()
