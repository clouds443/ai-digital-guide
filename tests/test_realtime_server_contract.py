# -*- coding: utf-8 -*-
import asyncio
import importlib.util
import os
import sys
import unittest
from unittest import mock


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import realtime_server  # noqa: E402


def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class RealtimeServerContractTests(unittest.TestCase):
    def test_realtime_status_exposes_fast_asr_runtime_flags(self):
        status = realtime_server.realtime_status()
        asr = status["asr"]

        self.assertIn("warming", asr)
        self.assertIn("loaded", asr)
        self.assertIn("partial_interval_ms", asr)
        self.assertIn("final_fast_mode", asr)
        self.assertIn("speech_rms_threshold", asr)
        self.assertGreater(asr["speech_rms_threshold"], asr["silence_rms_threshold"])
        self.assertGreaterEqual(asr["partial_interval_ms"], 500)

    def test_realtime_volume_gate_requires_clear_voice_above_speech_threshold(self):
        with mock.patch.object(realtime_server, "realtime_silence_rms_threshold", return_value=0.01), mock.patch.object(
            realtime_server, "realtime_speech_rms_threshold", return_value=0.025
        ):
            quiet_noise = realtime_server.pcm16_stats((int(0.015 * 32767)).to_bytes(2, "little", signed=True) * 3200)
            clear_voice = realtime_server.pcm16_stats((int(0.04 * 32767)).to_bytes(2, "little", signed=True) * 3200)

        self.assertTrue(quiet_noise["is_above_silence"])
        self.assertFalse(quiet_noise["is_speech"])
        self.assertTrue(clear_voice["is_speech"])

    def test_partial_recognition_throttle_skips_when_recent_or_running(self):
        async def scenario():
            scheduler = realtime_server.PartialRecognitionScheduler(interval_ms=1000)
            calls = []

            async def recognize():
                calls.append("run")
                return "九龙灌浴"

            first = await scheduler.maybe_recognize(1000, recognize)
            second = await scheduler.maybe_recognize(1200, recognize)

            scheduler.running = True
            third = await scheduler.maybe_recognize(2500, recognize)

            return first, second, third, calls

        first, second, third, calls = run_async(scenario())

        self.assertEqual(first, "九龙灌浴")
        self.assertIsNone(second)
        self.assertIsNone(third)
        self.assertEqual(calls, ["run"])

    def test_partial_recognition_can_run_in_background_without_blocking_loop(self):
        async def scenario():
            scheduler = realtime_server.PartialRecognitionScheduler(interval_ms=1000)
            events = []

            async def recognize():
                events.append("started")
                await asyncio.sleep(0.02)
                events.append("finished")
                return "九龙灌浴"

            async def on_result(text):
                events.append(text)

            async def on_error(exc):
                events.append("error:" + str(exc))

            first = scheduler.schedule(1000, recognize, on_result, on_error)
            second = scheduler.schedule(1100, recognize, on_result, on_error)
            immediate_events = list(events)
            await asyncio.sleep(0.05)
            return first, second, immediate_events, events

        first, second, immediate_events, events = run_async(scenario())

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(immediate_events, [])
        self.assertEqual(events, ["started", "finished", "九龙灌浴"])

    def test_finalize_skips_punctuation_model_in_fast_mode(self):
        async def scenario():
            session = realtime_server.FunASRStreamingRecognizer()

            async def fake_feed(audio_bytes, is_final=False):
                return "九龙灌浴"

            with mock.patch.object(session, "feed", side_effect=fake_feed) as feed, mock.patch.object(
                realtime_server.FunASRStreamingRecognizer,
                "add_punctuation",
                side_effect=AssertionError("不应在快速模式加载标点模型"),
            ):
                result = await session.finalize(b"\0\0")
            return result, feed.call_args

        result, call_args = run_async(scenario())

        self.assertEqual(result, "九龙灌浴")
        self.assertTrue(call_args[1]["is_final"])

    def test_realtime_streaming_asr_passes_lingshan_hotwords_to_model(self):
        async def scenario():
            session = realtime_server.FunASRStreamingRecognizer()
            calls = []

            class FakeModel:
                def generate(self, **kwargs):
                    calls.append(kwargs)
                    return [{"text": "九龙观玉"}]

            async def fake_load_model():
                return FakeModel()

            with mock.patch.object(session, "load_model", side_effect=fake_load_model):
                text = await session.feed(b"\0\0", is_final=True)
            return text, calls

        text, calls = run_async(scenario())

        self.assertEqual(text, "九龙观玉")
        self.assertEqual(len(calls), 1)
        self.assertIn("hotword", calls[0])
        self.assertIn("九龙灌浴", calls[0]["hotword"])
        self.assertIn("阿育王柱", calls[0]["hotword"])

    def test_realtime_asr_clean_text_applies_lingshan_hotword_corrections(self):
        cases = {
            "来看看天下第一章在景区的什么位置": "来看看天下第一掌在景区的什么位置",
            "请介绍灵山饭宫和九龙观浴": "请介绍灵山梵宫和九龙灌浴",
            "五知门到无进意斋怎么走": "五智门到无尽意斋怎么走",
            "说一下介绍一下九龙观玉": "说一下介绍一下九龙灌浴",
            "要为介绍绍一阿玉王柱柱": "要我介绍一下阿育王柱",
            "百拜拜": "拜拜",
            "开开开喂喂喂听得见吗": "听得见吗",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(realtime_server.FunASRStreamingRecognizer.clean_text(raw), expected)

    def test_realtime_asr_final_can_use_deepseek_corrected_query(self):
        async def scenario():
            with mock.patch.object(
                realtime_server,
                "correct_asr_text",
                return_value={
                    "text": "九龙灌浴几点开始",
                    "original_text": "九龙观浴几点开始",
                    "corrected_text": "九龙灌浴几点开始",
                    "llm_corrected": True,
                    "correction_provider": "deepseek",
                    "correction_confidence": 0.9,
                    "correction_error": "",
                },
            ) as corrected:
                result = await realtime_server.correct_realtime_asr_query("九龙观浴几点开始", history=[{"role": "user", "content": "你好"}])
            return result, corrected.call_args

        result, call_args = run_async(scenario())

        self.assertEqual("九龙灌浴几点开始", result["text"])
        self.assertTrue(result["asr"]["llm_corrected"])
        self.assertTrue(call_args[1]["realtime"])

    def test_realtime_asr_correction_failure_is_marked_for_stop(self):
        async def scenario():
            with mock.patch.object(
                realtime_server,
                "correct_asr_text",
                return_value={
                    "text": "可能千万万讲的什么东西啊太烂了",
                    "original_text": "可能千万万讲的什么东西啊太烂了",
                    "corrected_text": "可能千万万讲的什么东西啊太烂了",
                    "pre_llm_text": "可能千万万讲的什么东西啊太烂了",
                    "leading_noise_removed": False,
                    "leading_noise_reason": "",
                    "llm_corrected": False,
                    "correction_provider": "deepseek",
                    "correction_confidence": 0.0,
                    "correction_error": "DeepSeek 超时",
                },
            ):
                return await realtime_server.correct_realtime_asr_query("可能千万万讲的什么东西啊太烂了", history=[])

        result = run_async(scenario())

        self.assertTrue(result["asr"]["correction_failed"])
        self.assertIn("DeepSeek 超时", result["asr"]["correction_error"])

    def test_realtime_finalize_turn_sends_corrected_asr_final_before_llm(self):
        from pathlib import Path

        source = Path(realtime_server.__file__).read_text(encoding="utf-8")

        self.assertIn("correct_realtime_asr_query(query, history)", source)
        self.assertIn('"asr": asr_correction', source)
        self.assertIn('stage": "asr_correction"', source)
        self.assertLess(source.index("correct_realtime_asr_query(query, history)"), source.index('{"type": "asr_final"'))

    def test_realtime_done_event_contains_answer_metadata_for_frontend(self):
        event = realtime_server.build_realtime_done_event(
            query="推荐一下九龙灌浴",
            answer="九龙灌浴很适合卡点观看，推荐提前到场。",
            started_at=1000.0,
            finished_at=1000.123,
            interrupted=False,
            reason="manual_stop",
        )

        self.assertEqual(event["type"], "done")
        self.assertEqual(event["emotion"], "happy")
        self.assertEqual(event["emotion_label"], "开心")
        self.assertEqual(event["latency_ms"], 123)
        self.assertGreater(len(event["sources"]), 0)
        self.assertEqual(event["query"], "推荐一下九龙灌浴")
        self.assertEqual(event["answer"], "九龙灌浴很适合卡点观看，推荐提前到场。")

    def test_realtime_done_event_prioritizes_sad_for_user_criticism(self):
        event = realtime_server.build_realtime_done_event(
            query="可能头来了讲的什么东西啊啊太烂了",
            answer="抱歉，刚才没有讲清楚。我重新为您讲解灵山大照壁。",
            started_at=1000.0,
            finished_at=1000.2,
            interrupted=False,
            reason="manual_stop",
        )

        self.assertEqual(event["emotion"], "sad")
        self.assertEqual(event["emotion_label"], "伤心反思")

    def test_realtime_tts_events_include_emotion_for_live2d_speaking_state(self):
        tts_start = realtime_server.build_realtime_tts_start_event(
            query="推荐一下九龙灌浴",
            answer_so_far="九龙灌浴很适合卡点观看，推荐提前到场。",
            sentence="推荐您提前到场，体验会更从容。",
        )
        audio_chunk = realtime_server.build_realtime_audio_chunk_event(
            sentence="推荐您提前到场，体验会更从容。",
            emotion=tts_start["emotion"],
            result={"audio_url": "/audio/demo.wav", "ok": True, "worker": "internal"},
        )

        self.assertEqual(tts_start["type"], "tts_start")
        self.assertEqual(tts_start["emotion"], "happy")
        self.assertEqual(tts_start["emotion_label"], "开心")
        self.assertEqual(audio_chunk["type"], "audio_chunk")
        self.assertEqual(audio_chunk["emotion"], "happy")
        self.assertNotIn("worker", audio_chunk["tts"])

    def test_realtime_tts_start_prioritizes_sad_for_user_criticism(self):
        tts_start = realtime_server.build_realtime_tts_start_event(
            query="讲的什么东西啊太烂了",
            answer_so_far="抱歉，刚才没有讲清楚。",
            sentence="我重新为您讲解。",
        )

        self.assertEqual(tts_start["emotion"], "sad")
        self.assertEqual(tts_start["emotion_label"], "伤心反思")


    def test_realtime_protocol_exposes_continuous_mode_and_barge_in_events(self):
        status = realtime_server.realtime_status()
        protocol = status["protocol"]

        self.assertIn("end_session", protocol["client_events"])
        self.assertIn("barge_in", protocol["client_events"])
        self.assertIn("turn_cancelled", protocol["server_events"])
        self.assertIn("listening", protocol["server_events"])
        self.assertTrue(protocol["continuous_mode"])
        self.assertTrue(protocol["barge_in_supported"])
        self.assertTrue(protocol["asr_correction_required"])
        self.assertTrue(protocol["asr_correction_uses_deepseek"])

    def test_realtime_done_event_marks_next_listening_when_session_continues(self):
        event = realtime_server.build_realtime_done_event(
            query="??????",
            answer="???????88??",
            started_at=1000.0,
            finished_at=1000.2,
            interrupted=False,
            reason="silence",
            continue_listening=True,
        )

        self.assertTrue(event["continue_listening"])
        self.assertEqual(event["next_state"], "listening")

    def test_realtime_server_defers_listening_until_client_finishes_audio(self):
        from pathlib import Path

        source = Path(realtime_server.__file__).read_text(encoding="utf-8")

        self.assertIn('continue_listening=True', source)
        self.assertIn('build_realtime_done_event(', source)
        self.assertNotIn('if continue_listening and not interrupted:\n                await send_listening()', source)

    def test_realtime_turn_cancelled_event_is_structured_for_barge_in(self):
        event = realtime_server.build_realtime_turn_cancelled_event("barge_in")

        self.assertEqual(event["type"], "turn_cancelled")
        self.assertEqual(event["reason"], "barge_in")
        self.assertTrue(event["continue_listening"])

    def test_realtime_barge_in_audio_frame_decodes_safely(self):
        import base64

        raw = b"\x01\x00\x02\x00"
        encoded = base64.b64encode(raw).decode("ascii")

        self.assertEqual(realtime_server.decode_realtime_audio_frame(encoded), raw)
        self.assertEqual(realtime_server.decode_realtime_audio_frame("bad!!!"), b"")

    def test_realtime_websocket_serializes_concurrent_send_events(self):
        from pathlib import Path

        source = Path(realtime_server.__file__).read_text(encoding="utf-8")

        self.assertIn("send_lock = asyncio.Lock()", source)
        self.assertIn("async with send_lock:", source)


if __name__ == "__main__":
    unittest.main()
