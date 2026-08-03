# -*- coding: utf-8 -*-
import asyncio
import importlib.util
import os
from pathlib import Path
import sys
import threading
import time
import types
import unittest


ROOT_DIR = Path(__file__).resolve().parents[1]
SERVER = ROOT_DIR / "backend" / "gsv_tts_lite_server.py"


def load_server():
    spec = importlib.util.spec_from_file_location("gsv_tts_lite_server_contract", SERVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_server_with_fake_fastapi():
    fake_fastapi = types.ModuleType("fastapi")

    class FakeFastAPI:
        def __init__(self, *args, **kwargs):
            pass

        def on_event(self, *args, **kwargs):
            return lambda fn: fn

        def get(self, *args, **kwargs):
            return lambda fn: fn

        def post(self, *args, **kwargs):
            return lambda fn: fn

    fake_fastapi.FastAPI = FakeFastAPI
    fake_pydantic = types.ModuleType("pydantic")

    class FakeBaseModel:
        def dict(self):
            return dict(getattr(self, "payload", {}))

    fake_pydantic.BaseModel = FakeBaseModel
    original_fastapi = sys.modules.get("fastapi")
    original_pydantic = sys.modules.get("pydantic")
    sys.modules["fastapi"] = fake_fastapi
    sys.modules["pydantic"] = fake_pydantic
    try:
        return load_server()
    finally:
        if original_fastapi is None:
            sys.modules.pop("fastapi", None)
        else:
            sys.modules["fastapi"] = original_fastapi
        if original_pydantic is None:
            sys.modules.pop("pydantic", None)
        else:
            sys.modules["pydantic"] = original_pydantic


class GsvTtsLiteServerContractTests(unittest.TestCase):
    def test_control_endpoint_identity_does_not_require_model_preload(self):
        original = os.environ.get("GSV_TTS_LITE_PRELOAD")
        os.environ["GSV_TTS_LITE_PRELOAD"] = "0"
        try:
            module = load_server()
        finally:
            if original is None:
                os.environ.pop("GSV_TTS_LITE_PRELOAD", None)
            else:
                os.environ["GSV_TTS_LITE_PRELOAD"] = original

        payload = module._control_payload()
        self.assertEqual(payload["provider"], "gsv_tts_lite")
        self.assertEqual(payload["engine"], "gsv_tts_lite")
        self.assertFalse(payload["loaded"])
        self.assertIn("preload", payload)
        self.assertEqual(payload["python_prefix"], sys.prefix)
        self.assertEqual(payload["python_executable"], sys.executable)
        self.assertIn("python_base_executable", payload)
        self.assertIn("gsv_tts_module", payload)
        self.assertIn("cuda_available", payload)
        self.assertIn("torch_version", payload)
        if importlib.util.find_spec("fastapi") and importlib.util.find_spec("pydantic"):
            self.assertIsNotNone(module.app)
            self.assertEqual(module.control.__name__, "control")

    def test_load_tts_disables_auto_bert_by_default_for_stable_cpu_synthesis(self):
        module = load_server()
        captured = {}

        fake_gsv_tts = types.ModuleType("gsv_tts")

        class FakeTTS:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        fake_gsv_tts.TTS = FakeTTS
        original = sys.modules.get("gsv_tts")
        original_auto = os.environ.get("GSV_TTS_LITE_AUTO_BERT")
        original_use = os.environ.get("GSV_TTS_LITE_USE_BERT")
        os.environ.pop("GSV_TTS_LITE_AUTO_BERT", None)
        os.environ.pop("GSV_TTS_LITE_USE_BERT", None)
        sys.modules["gsv_tts"] = fake_gsv_tts
        try:
            module._TTS = None
            module._load_tts()
        finally:
            module._TTS = None
            if original is None:
                sys.modules.pop("gsv_tts", None)
            else:
                sys.modules["gsv_tts"] = original
            if original_auto is None:
                os.environ.pop("GSV_TTS_LITE_AUTO_BERT", None)
            else:
                os.environ["GSV_TTS_LITE_AUTO_BERT"] = original_auto
            if original_use is None:
                os.environ.pop("GSV_TTS_LITE_USE_BERT", None)
            else:
                os.environ["GSV_TTS_LITE_USE_BERT"] = original_use

        self.assertFalse(captured["auto_bert"])
        self.assertFalse(captured["use_bert"])

    def test_load_tts_falls_back_to_cpu_when_cuda_requested_but_unavailable(self):
        module = load_server()
        captured = {}

        fake_gsv_tts = types.ModuleType("gsv_tts")

        class FakeTTS:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        fake_torch = types.ModuleType("torch")

        class FakeCuda:
            @staticmethod
            def is_available():
                return False

        fake_torch.cuda = FakeCuda()
        fake_gsv_tts.TTS = FakeTTS
        original_gsv = sys.modules.get("gsv_tts")
        original_torch = sys.modules.get("torch")
        original_device = os.environ.get("GSV_TTS_LITE_DEVICE")
        sys.modules["gsv_tts"] = fake_gsv_tts
        sys.modules["torch"] = fake_torch
        os.environ["GSV_TTS_LITE_DEVICE"] = "cuda"
        try:
            module._TTS = None
            module._load_tts()
            payload = module._control_payload()
        finally:
            module._TTS = None
            if original_gsv is None:
                sys.modules.pop("gsv_tts", None)
            else:
                sys.modules["gsv_tts"] = original_gsv
            if original_torch is None:
                sys.modules.pop("torch", None)
            else:
                sys.modules["torch"] = original_torch
            if original_device is None:
                os.environ.pop("GSV_TTS_LITE_DEVICE", None)
            else:
                os.environ["GSV_TTS_LITE_DEVICE"] = original_device

        self.assertEqual(captured["device"], "cpu")
        self.assertEqual(payload["device_requested"], "cuda")
        self.assertEqual(payload["effective_device"], "cpu")
        self.assertIn("CUDA", payload["device_warning"])

    def test_coerce_subtitles_merges_character_timestamps_into_phrase_segments(self):
        module = load_server()
        raw = []
        text = "现在我们来到灵山大照壁。先在这里停一下，听我把重点带起来。"
        cursor = 0.0
        for char in text:
            raw.append({"start_s": cursor, "end_s": cursor + 0.12, "text": char})
            cursor += 0.12

        subtitles = module._coerce_subtitles(raw, text, cursor)

        self.assertLess(len(subtitles), len(raw) // 3)
        self.assertGreaterEqual(len(subtitles), 2)
        self.assertEqual("".join(item["text"] for item in subtitles), text)
        self.assertTrue(any(item["text"].endswith("。") for item in subtitles))
        self.assertTrue(all(len(item["text"]) <= 28 for item in subtitles))

    def test_coerce_subtitles_splits_long_unpunctuated_text_into_readable_segments(self):
        module = load_server()
        text = "欢迎来到灵山胜境今天我们沿着中轴线慢慢参观感受山水和佛教文化"
        raw = [
            {"start_s": index * 0.1, "end_s": (index + 1) * 0.1, "text": char}
            for index, char in enumerate(text)
        ]

        subtitles = module._coerce_subtitles(raw, text, len(text) * 0.1)

        self.assertGreater(len(subtitles), 1)
        self.assertEqual("".join(item["text"] for item in subtitles), text)
        self.assertTrue(all(8 <= len(item["text"]) <= 28 for item in subtitles[:-1]))

    def test_coerce_subtitles_does_not_break_after_enumeration_punctuation(self):
        module = load_server()
        text = "沿五明桥、佛足坛、五智门一路向前，再到九龙灌浴。"
        raw = [
            {"start_s": index * 0.12, "end_s": (index + 1) * 0.12, "text": char}
            for index, char in enumerate(text)
        ]

        subtitles = module._coerce_subtitles(raw, text, len(text) * 0.12)

        self.assertEqual("".join(item["text"] for item in subtitles), text)
        self.assertTrue(all(not item["text"].endswith("、") for item in subtitles))

    def test_load_tts_is_thread_safe_for_first_parallel_narration_segments(self):
        module = load_server()
        calls = []

        fake_gsv_tts = types.ModuleType("gsv_tts")

        class FakeTTS:
            def __init__(self, **kwargs):
                calls.append(kwargs)
                time.sleep(0.05)

        fake_gsv_tts.TTS = FakeTTS
        original = sys.modules.get("gsv_tts")
        sys.modules["gsv_tts"] = fake_gsv_tts
        module._TTS = None
        try:
            threads = [threading.Thread(target=module._load_tts) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        finally:
            module._TTS = None
            if original is None:
                sys.modules.pop("gsv_tts", None)
            else:
                sys.modules["gsv_tts"] = original

        self.assertEqual(len(calls), 1)

    def test_tts_endpoint_runs_blocking_synthesis_off_event_loop(self):
        module = load_server_with_fake_fastapi()

        def slow_synthesis(payload):
            time.sleep(0.2)
            return {"ok": True, "audio_path": "fake.wav"}

        class FakeRequest:
            def dict(self):
                return {"text": "欢迎来到灵山。"}

        module.synthesize_with_gsv = slow_synthesis

        async def run_endpoint_and_probe_loop():
            started_at = time.perf_counter()
            task = asyncio.ensure_future(module.api_tts(FakeRequest()))
            await asyncio.sleep(0.02)
            elapsed = time.perf_counter() - started_at
            result = await task
            return elapsed, result

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            elapsed, result = loop.run_until_complete(run_endpoint_and_probe_loop())
        finally:
            asyncio.set_event_loop(None)
            loop.close()

        self.assertLess(elapsed, 0.12)
        self.assertTrue(result["ok"])

    def test_tts_endpoint_serializes_gsv_inference_requests(self):
        module = load_server_with_fake_fastapi()
        active = 0
        max_active = 0
        lock = threading.Lock()

        def slow_synthesis(payload):
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.08)
            with lock:
                active -= 1
            return {"ok": True, "audio_path": payload["text"] + ".wav"}

        class FakeRequest:
            def __init__(self, text):
                self.payload = {"text": text}

            def dict(self):
                return dict(self.payload)

        module.synthesize_with_gsv = slow_synthesis

        async def run_parallel_requests():
            results = await asyncio.gather(
                module.api_tts(FakeRequest("one")),
                module.api_tts(FakeRequest("two")),
            )
            return results

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            results = loop.run_until_complete(run_parallel_requests())
        finally:
            asyncio.set_event_loop(None)
            loop.close()

        self.assertEqual([item["ok"] for item in results], [True, True])
        self.assertEqual(max_active, 1)


if __name__ == "__main__":
    unittest.main()
