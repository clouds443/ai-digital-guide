import importlib.util
import json
import os
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
START_SERVICES = ROOT / "scripts" / "start_services.py"


def load_start_services():
    spec = importlib.util.spec_from_file_location("start_services", START_SERVICES)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class StartServicesTests(unittest.TestCase):
    def test_select_python_for_module_prefers_candidate_with_required_module(self):
        module = load_start_services()
        missing = ROOT / ".cache" / "missing-python.exe"
        available = ROOT / ".cache" / "available-python.exe"

        def fake_has_module(python_exe, module_name):
            return Path(python_exe) == available and module_name == "flask"

        selected = module.select_python_for_module(
            "flask",
            candidates=[missing, available],
            has_module=fake_has_module,
        )

        self.assertEqual(selected, available)

    def test_light_profile_disables_remote_llm_for_fast_demo_response(self):
        module = load_start_services()

        env = module.service_env({"LOCAL_RAG_ONLY": "1"})

        self.assertEqual(env["LOCAL_RAG_ONLY"], "1")

    def test_clean_env_keeps_uppercase_path_for_anaconda(self):
        module = load_start_services()
        original_env = dict(os.environ)
        try:
            os.environ.clear()
            os.environ.update({"Path": r"C:\lower", "PATH": r"C:\upper", "OTHER": "1"})

            env = module.clean_env()
        finally:
            os.environ.clear()
            os.environ.update(original_env)

        self.assertIn("PATH", env)
        self.assertNotIn("Path", env)
        self.assertTrue(env["PATH"])

    def test_check_flask_contract_requires_current_chat_metadata(self):
        module = load_start_services()

        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps({"answer": "旧接口"}).encode("utf-8")

        with mock.patch.object(module.urllib.request, "urlopen", return_value=Response()):
            ok, message = module.check_flask_contract("http://127.0.0.1:8000")

        self.assertFalse(ok)
        self.assertIn("route_suggestion", message)

    def test_check_flask_contract_requires_map_routes_after_amap_integration(self):
        module = load_start_services()

        class Response:
            status = 200

            def __init__(self, payload):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")

        responses = [
            Response({
                "answer": "ok",
                "emotion": "neutral",
                "route_suggestion": {"id": "route_family"},
                "sources": [],
                "latency_ms": 1,
            }),
            Exception("HTTP Error 404: Not Found"),
        ]

        def fake_urlopen(*args, **kwargs):
            item = responses.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        with mock.patch.object(module.urllib.request, "urlopen", side_effect=fake_urlopen):
            ok, message = module.check_flask_contract("http://127.0.0.1:8000")

        self.assertFalse(ok)
        self.assertIn("/api/map/config", message)

    def test_windows_creationflags_tolerates_missing_detached_process_constant(self):
        module = load_start_services()

        class FakeSubprocess:
            CREATE_NEW_PROCESS_GROUP = 512

        flags = module.windows_creationflags("nt", FakeSubprocess)

        self.assertEqual(flags, 520)

    def test_windows_creationflags_can_request_breakaway_when_environment_allows_it(self):
        module = load_start_services()

        class FakeSubprocess:
            CREATE_NEW_PROCESS_GROUP = 512

        flags = module.windows_creationflags("nt", FakeSubprocess, breakaway=True)

        self.assertEqual(flags, 16777736)

    def test_popen_close_fds_is_disabled_for_redirected_windows_streams(self):
        module = load_start_services()

        self.assertFalse(module.popen_close_fds("nt"))
        self.assertTrue(module.popen_close_fds("posix"))

    def test_runtime_python_paths_can_be_loaded_from_backend_env(self):
        module = load_start_services()
        lines = [
            "REALTIME_PYTHON=D:\\AIhumannew\\.venvs\\realtime\\Scripts\\python.exe",
            "GPT_SOVITS_PYTHON=D:\\AIhumannew\\.venvs\\gpt-sovits\\Scripts\\python.exe",
        ]

        env = module.parse_env_lines(lines)

        self.assertEqual(env["REALTIME_PYTHON"], r"D:\AIhumannew\.venvs\realtime\Scripts\python.exe")
        self.assertEqual(env["GPT_SOVITS_PYTHON"], r"D:\AIhumannew\.venvs\gpt-sovits\Scripts\python.exe")

    def test_full_profile_gsv_env_requests_cuda_and_preload(self):
        module = load_start_services()

        env = module.gsv_tts_lite_env()

        self.assertEqual(env["GSV_TTS_LITE_DEVICE"], "cuda")
        self.assertEqual(env["GSV_TTS_LITE_PRELOAD"], "1")


if __name__ == "__main__":
    unittest.main()
