# -*- coding: utf-8 -*-
import os
import sys
import unittest
from unittest import mock
from pathlib import Path
import builtins


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import tts_service  # noqa: E402


class TtsServiceContractTests(unittest.TestCase):
    def test_prepare_tts_text_removes_stage_direction_and_speaks_times_naturally(self):
        text = "（微微欠身，语气温和而庄重）感谢您，10:00、11:30、13:30、15:00开始，9:00-17:00开放。"

        result = tts_service.prepare_tts_text(text)

        self.assertNotIn("微微欠身", result)
        self.assertNotIn("语气温和", result)
        self.assertNotIn("（", result)
        self.assertIn("十点", result)
        self.assertIn("十一点半", result)
        self.assertIn("十三点半", result)
        self.assertIn("十五点", result)
        self.assertIn("九点到十七点", result)

    def test_prepare_tts_text_normalizes_ranges_and_durations(self):
        text = "入口到五智门约 25 分钟，演出停留 15-20 分钟，2小时内可以看核心景点。"

        result = tts_service.prepare_tts_text(text)

        self.assertIn("二十五分钟", result)
        self.assertIn("十五到二十分钟", result)
        self.assertIn("两小时", result)

    def test_prepare_tts_text_normalizes_three_digit_cultural_numbers(self):
        text = "通往大佛的216级台阶，暗合108烦恼与108愿望的对应关系。"

        result = tts_service.prepare_tts_text(text)

        self.assertIn("二百一十六级台阶", result)
        self.assertIn("一百零八烦恼", result)
        self.assertIn("一百零八愿望", result)
        self.assertNotIn("216", result)
        self.assertNotIn("108", result)

    def test_prepare_tts_text_speaks_decimal_measurements_with_point(self):
        text = "祥符禅钟重12.8吨，钟声浑厚悠远。"

        result = tts_service.prepare_tts_text(text)

        self.assertIn("十二点八吨", result)
        self.assertNotIn("十二.八", result)

    def test_prepare_tts_text_closes_clause_ending_segments_for_tts(self):
        text = "这里被誉为佛教艺术的卢浮宫，"

        result = tts_service.prepare_tts_text(text)

        self.assertEqual(result, "这里被誉为佛教艺术的卢浮宫。")

    def test_prepare_tts_text_guides_tibetan_context_zang_pronunciation(self):
        text = "汉藏文化交流、藏传佛教、藏式建筑和藏香体验都值得了解，但收藏展品不要触摸。"

        result = tts_service.prepare_tts_text(text)

        self.assertIn("汉臧文化交流", result)
        self.assertIn("臧传佛教", result)
        self.assertIn("臧式建筑", result)
        self.assertIn("臧香体验", result)
        self.assertIn("收藏展品", result)

    def test_prepare_tts_text_guides_tongxing_pronunciation_for_travel_companions(self):
        text = "如果同行有老人和孩子，可以短暂停留；也很适合给同行的人留一张照片。"

        result = tts_service.prepare_tts_text(text)

        self.assertIn("同游有老人和孩子", result)
        self.assertIn("给同游的人留一张照片", result)
        self.assertNotIn("同行有老人", result)
        self.assertNotIn("同行的人", result)

    def test_prepare_tts_text_guides_qiaochang_as_length(self):
        text = "五明桥的价值不在桥长，而在空间转换。"

        result = tts_service.prepare_tts_text(text)

        self.assertIn("五明桥的价值不在桥的常度", result)
        self.assertNotIn("桥长", result)

    def test_prepare_tts_text_guides_quanchang_as_total_length(self):
        text = "灵山大照壁全长39.8米，最高处7米。成长故事可以另行介绍。"

        result = tts_service.prepare_tts_text(text)

        self.assertIn("灵山大照壁总常度三十九点八米", result)
        self.assertIn("成常故事", result)
        self.assertNotIn("全长39.8米", result)
        self.assertNotIn("长", result)

    def test_prepare_tts_text_guides_qiaoshenchang_as_bridge_body_length(self):
        text = "每座桥身长9米，桥面宽3米。"

        result = tts_service.prepare_tts_text(text)

        self.assertIn("每座桥身常度九米", result)
        self.assertNotIn("桥身长九米", result)
        self.assertNotIn("长", result)

    def test_prepare_tts_text_defaults_every_chang_to_chang_pronunciation(self):
        text = "长廊全长39.8米，长者介绍这里的成长故事。"

        result = tts_service.prepare_tts_text(text)

        self.assertIn("常廊总常度三十九点八米", result)
        self.assertIn("常者介绍这里的成常故事", result)
        self.assertNotIn("长", result)

    def test_synthesize_speech_sends_clean_text_to_edge(self):
        config = {"voice_provider": "edge"}
        edge_result = {
            "ok": True,
            "provider": "edge",
            "audio_url": "/audio/tts/clean.mp3",
        }

        with mock.patch.object(tts_service, "synthesize_edge", return_value=edge_result) as synthesize_edge:
            result = tts_service.synthesize_speech("（微微一笑）10:00开始。", config)

        self.assertTrue(result["ok"])
        clean_text = synthesize_edge.call_args[0][0]
        self.assertNotIn("微微一笑", clean_text)
        self.assertIn("十点", clean_text)

    def test_gsv_payload_uses_clean_text_for_clone_voice(self):
        clone = {
            "audio_path": "D:/AIhumannew/uploads/voice-clones/demo.wav",
            "prompt_text": "您好，我是灵山胜境导游。",
        }

        payload = tts_service._build_gsv_tts_lite_payload("（微微欠身）11:30开始。", clone)

        self.assertNotIn("微微欠身", payload["text"])
        self.assertIn("十一点半", payload["text"])

    def test_gsv_payload_clamps_prompt_text_to_trimmed_reference_audio(self):
        long_prompt = (
            "菩提大道不用急着赶路。"
            "这段树影和步道会把人慢慢带向核心广场，也让“菩提”的意味落到脚步里。"
            "菩提大道是一段很适合慢行的空间，两侧景观会把游客一步步引向核心区域。"
        )
        clone = {
            "audio_path": "D:/AIhumannew/uploads/voice-clones/demo.wav",
            "prompt_text": long_prompt,
            "reference_duration_seconds": 9.8,
            "trimmed": True,
        }

        payload = tts_service._build_gsv_tts_lite_payload("现在讲解降魔浮雕。", clone)

        self.assertLess(len(payload["prompt_text"]), len(long_prompt))
        self.assertIn("菩提大道不用急着赶路", payload["prompt_text"])
        self.assertIn("脚步里。", payload["prompt_text"])
        self.assertNotIn("菩提大道是一段很适合慢行的空间", payload["prompt_text"])

    def test_narration_first_segment_prefers_edge_fast_path(self):
        config = {
            "voice_provider": "gpt_sovits",
            "purpose": "narration_first",
            "voice_preset": "custom",
        }
        edge_result = {
            "ok": True,
            "provider": "edge",
            "audio_url": "/audio/tts/fast.mp3",
            "synthesis_seconds": 0.8,
        }

        with mock.patch.object(tts_service.importlib.util, "find_spec", return_value=object()), mock.patch.object(
            tts_service, "synthesize_edge", return_value=edge_result
        ) as synthesize_edge, mock.patch.object(tts_service, "synthesize_gpt_sovits") as synthesize_gpt:
            result = tts_service.synthesize_speech("欢迎来到九龙灌浴。", config)

        self.assertEqual(result["provider"], "gpt_sovits")
        self.assertEqual(result["fallback_provider"], "edge")
        self.assertTrue(result["fast_first"])
        self.assertEqual(result["audio_url"], "/audio/tts/fast.mp3")
        synthesize_edge.assert_called_once()
        synthesize_gpt.assert_not_called()

    def test_narration_first_segment_uses_clone_voice_when_clone_is_selected(self):
        config = {
            "voice_provider": "gpt_sovits",
            "purpose": "narration_first",
            "voice_clone_id": "clone-demo",
        }
        gpt_result = {
            "ok": True,
            "provider": "gpt_sovits",
            "audio_url": "/audio/tts/clone.wav",
            "voice_clone_id": "clone-demo",
            "synthesis_seconds": 4.2,
        }

        with mock.patch.object(tts_service, "synthesize_edge") as synthesize_edge, mock.patch.object(
            tts_service, "synthesize_gpt_sovits", return_value=gpt_result
        ) as synthesize_gpt:
            result = tts_service.synthesize_speech("欢迎来到灵山大佛。", config)

        self.assertEqual(result["provider"], "gpt_sovits")
        self.assertEqual(result["voice_clone_id"], "clone-demo")
        self.assertNotIn("fallback_provider", result)
        synthesize_gpt.assert_called_once()
        synthesize_edge.assert_not_called()

    def test_clone_voice_failure_does_not_fallback_to_edge(self):
        config = {
            "voice_provider": "gpt_sovits",
            "voice_clone_id": "clone-demo",
        }

        with mock.patch.object(
            tts_service,
            "get_voice_clone",
            return_value={
                "id": "clone-demo",
                "name": "演示克隆音色",
                "audio_exists": True,
                "audio_path": "D:/AIhumannew/uploads/voice-clones/demo.wav",
                "prompt_text": "您好，我是灵山胜境导游。",
            },
        ), mock.patch.object(tts_service, "gpt_sovits_status", return_value={"ok": False, "error": "api down"}), mock.patch.object(
            tts_service, "synthesize_edge"
        ) as synthesize_edge:
            result = tts_service.synthesize_speech("欢迎来到灵山大佛。", config)

        self.assertFalse(result["ok"])
        self.assertEqual(result["provider"], "gpt_sovits")
        self.assertEqual(result["fallback_provider"], "")
        self.assertIn("克隆音色", result["error"])
        synthesize_edge.assert_not_called()

    def test_gpt_sovits_provider_calls_gsv_tts_lite_adapter(self):
        config = {
            "voice_provider": "gpt_sovits",
            "voice_clone_id": "clone-demo",
        }
        clone = {
            "id": "clone-demo",
            "name": "演示克隆音色",
            "audio_exists": True,
            "audio_path": "D:/AIhumannew/uploads/voice-clones/demo.wav",
            "prompt_text": "您好，我是灵山胜境导游。",
        }
        gsv_result = {
            "ok": True,
            "audio_path": str(Path(ROOT_DIR) / "frontend" / "audio" / "tts" / "gsv-demo.wav"),
            "audio_url": "/audio/tts/gsv-demo.wav",
            "subtitles": [{"start_s": 0.0, "end_s": 1.2, "text": "欢迎来到灵山胜境。"}],
            "synthesis_seconds": 1.25,
            "bytes": 2048,
        }

        with mock.patch.object(tts_service, "get_voice_clone", return_value=clone), mock.patch.object(
            tts_service, "gsv_tts_lite_status", return_value={"ok": True}
        ), mock.patch.object(tts_service, "_post_gsv_tts_lite_tts", return_value=gsv_result) as post_gsv:
            result = tts_service.synthesize_speech("欢迎来到灵山胜境。", config)

        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "gpt_sovits")
        self.assertEqual(result["engine"], "gsv_tts_lite")
        self.assertEqual(result["voice_clone_id"], "clone-demo")
        self.assertEqual(result["subtitles"][0]["text"], "欢迎来到灵山胜境。")
        payload = post_gsv.call_args[0][0]
        self.assertEqual(payload["ref_audio_path"], clone["audio_path"])
        self.assertEqual(payload["prompt_text"], clone["prompt_text"])

    def test_gpt_sovits_uses_gsv_audio_url_when_returned_audio_path_disappears(self):
        config = {
            "voice_provider": "gpt_sovits",
            "voice_clone_id": "clone-demo",
        }
        clone = {
            "id": "clone-demo",
            "name": "演示克隆音色",
            "audio_exists": True,
            "audio_path": "D:/AIhumannew/uploads/voice-clones/demo.wav",
            "prompt_text": "您好，我是灵山胜境导游。",
        }
        gsv_result = {
            "ok": True,
            "audio_path": str(Path(ROOT_DIR) / "frontend" / "audio" / "tts" / "gsv-missing.wav"),
            "audio_url": "/audio/tts/gsv-missing.wav",
            "subtitles": [{"start_s": 0.0, "end_s": 1.2, "text": "欢迎来到灵山胜境。"}],
            "synthesis_seconds": 1.25,
        }
        real_isfile = os.path.isfile
        real_open = builtins.open

        def fake_isfile(path):
            if str(path) == gsv_result["audio_path"]:
                return True
            return real_isfile(path)

        def fake_open(path, *args, **kwargs):
            if str(path) == gsv_result["audio_path"]:
                raise FileNotFoundError(2, "系统找不到指定的文件。", str(path))
            return real_open(path, *args, **kwargs)

        with mock.patch.object(tts_service, "get_voice_clone", return_value=clone), mock.patch.object(
            tts_service, "gsv_tts_lite_status", return_value={"ok": True}
        ), mock.patch.object(tts_service, "_post_gsv_tts_lite_tts", return_value=gsv_result), mock.patch.object(
            tts_service, "synthesize_edge"
        ) as synthesize_edge, mock.patch.object(tts_service.os.path, "isfile", side_effect=fake_isfile), mock.patch(
            "builtins.open", side_effect=fake_open
        ):
            result = tts_service.synthesize_speech("欢迎来到灵山胜境。", config)

        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "gpt_sovits")
        self.assertEqual(result["engine"], "gsv_tts_lite")
        self.assertEqual(result["audio_url"], "/audio/tts/gsv-missing.wav")
        self.assertEqual(result["bytes"], 0)
        synthesize_edge.assert_not_called()

    def test_gsv_tts_lite_failure_for_clone_voice_does_not_fallback_to_edge(self):
        config = {
            "voice_provider": "gpt_sovits",
            "voice_clone_id": "clone-demo",
        }

        with mock.patch.object(
            tts_service,
            "get_voice_clone",
            return_value={
                "id": "clone-demo",
                "name": "演示克隆音色",
                "audio_exists": True,
                "audio_path": "D:/AIhumannew/uploads/voice-clones/demo.wav",
                "prompt_text": "您好，我是灵山胜境导游。",
            },
        ), mock.patch.object(tts_service, "gsv_tts_lite_status", return_value={"ok": True}), mock.patch.object(
            tts_service, "_post_gsv_tts_lite_tts", side_effect=RuntimeError("adapter timeout")
        ), mock.patch.object(tts_service, "synthesize_edge") as synthesize_edge:
            result = tts_service.synthesize_speech("欢迎来到灵山大佛。", config)

        self.assertFalse(result["ok"])
        self.assertEqual(result["provider"], "gpt_sovits")
        self.assertEqual(result["engine"], "gsv_tts_lite")
        self.assertEqual(result["fallback_provider"], "")
        self.assertIn("GSV-TTS-Lite", result["error"])
        synthesize_edge.assert_not_called()

    def test_tts_status_reports_external_edge_runtime_as_fallback_available(self):
        fake_python = Path(ROOT_DIR) / ".venvs" / "realtime" / "Scripts" / "python.exe"

        with mock.patch.object(tts_service.importlib.util, "find_spec", return_value=None), mock.patch.object(
            tts_service, "external_edge_python", return_value=str(fake_python)
        ), mock.patch.object(tts_service, "gpt_sovits_status", return_value={"ok": True}):
            status = tts_service.tts_status({"voice_provider": "gpt_sovits"})

        self.assertFalse(status["edge_tts_installed"])
        self.assertTrue(status["edge_tts_external"])
        self.assertTrue(status["fallback_available"])
        self.assertIn(str(fake_python), status["edge"]["external_python"])

    def test_tts_status_reports_gsv_tts_lite_and_gpt_sovits_compatibility_blocks(self):
        gsv_status = {
            "ok": True,
            "provider": "gsv_tts_lite",
            "api_url": "http://127.0.0.1:9880",
            "engine": "gsv_tts_lite",
        }

        with mock.patch.object(tts_service.importlib.util, "find_spec", return_value=object()), mock.patch.object(
            tts_service, "gsv_tts_lite_status", return_value=gsv_status
        ):
            status = tts_service.tts_status({"voice_provider": "gpt_sovits"})

        self.assertTrue(status["ok"])
        self.assertEqual(status["provider"], "gpt_sovits")
        self.assertEqual(status["engine"], "gsv_tts_lite")
        self.assertEqual(status["gsv_tts_lite"]["provider"], "gsv_tts_lite")
        self.assertEqual(status["gpt_sovits"]["engine"], "gsv_tts_lite")
        self.assertIn("兼容", status["gpt_sovits"]["hint"])

    def test_gsv_tts_lite_status_rejects_legacy_null_ping_response(self):
        with mock.patch.object(tts_service, "_http_json", return_value=None):
            status = tts_service.gsv_tts_lite_status()

        self.assertFalse(status["ok"])
        self.assertFalse(status["api_reachable"])
        self.assertIn("GSV-TTS-Lite", status["error"])


if __name__ == "__main__":
    unittest.main()
