# -*- coding: utf-8 -*-
import importlib.util
from pathlib import Path
import unittest
from unittest import mock


ROOT_DIR = Path(__file__).resolve().parents[1]
SERVICE_MANAGER = ROOT_DIR / "backend" / "service_manager.py"


def load_service_manager():
    spec = importlib.util.spec_from_file_location("service_manager_contract", SERVICE_MANAGER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ServiceManagerContractTests(unittest.TestCase):
    def test_find_pid_by_port_works_when_subprocess_lacks_text_keyword(self):
        module = load_service_manager()
        netstat_output = (
            "  TCP    0.0.0.0:8000           0.0.0.0:0              LISTENING       12345\r\n"
        ).encode("gbk")

        def old_python_check_output(command, **kwargs):
            if "text" in kwargs or "errors" in kwargs:
                raise TypeError("__init__() got an unexpected keyword argument 'text'")
            return netstat_output

        with mock.patch.object(module.os, "name", "nt"), mock.patch.object(module.subprocess, "check_output", side_effect=old_python_check_output):
            self.assertEqual(module.find_pid_by_port(8000), 12345)

    def test_windows_creationflags_tolerates_old_python_missing_detached_process(self):
        module = load_service_manager()

        class FakeSubprocess:
            CREATE_NEW_PROCESS_GROUP = 512

        self.assertEqual(module.windows_creationflags("nt", FakeSubprocess), 520)

    def test_popen_close_fds_is_disabled_for_windows_redirects(self):
        module = load_service_manager()

        self.assertFalse(module.popen_close_fds("nt"))
        self.assertTrue(module.popen_close_fds("posix"))

    def test_gpt_sovits_status_reports_missing_python_as_not_startable(self):
        module = load_service_manager()
        manager = module.ServiceManager()
        definition = manager.definitions["gpt_sovits"]

        with mock.patch.object(module, "find_pid_by_port", return_value=None), mock.patch.object(module.Path, "exists", return_value=False):
            status = manager.status("gpt_sovits")

        self.assertFalse(status["can_start"])
        self.assertIn("服务解释器不存在", status["error"])

    def test_realtime_status_reports_missing_runtime_dependencies_as_not_startable(self):
        module = load_service_manager()
        manager = module.ServiceManager()

        def fake_module_available(python_exe, module_name):
            return False

        with mock.patch.object(module, "find_pid_by_port", return_value=None), mock.patch.object(module, "python_has_module", side_effect=fake_module_available):
            status = manager.status("realtime")

        self.assertFalse(status["can_start"])
        self.assertIn("缺少依赖", status["error"])

    def test_python_module_check_uses_lightweight_find_spec(self):
        module = load_service_manager()
        seen = {}

        def fake_check_call(command, **kwargs):
            seen["command"] = command
            return 0

        with mock.patch.object(module.subprocess, "check_call", side_effect=fake_check_call):
            self.assertTrue(module.python_has_module("python", "funasr"))

        self.assertIn("find_spec", seen["command"][2])
        self.assertNotIn("import funasr", seen["command"][2])

    def test_service_commands_use_python_paths_from_backend_env(self):
        module = load_service_manager()

        env_values = {
            "REALTIME_PYTHON": str(ROOT_DIR / ".venvs" / "realtime" / "Scripts" / "python.exe"),
            "GSV_TTS_LITE_PYTHON": str(ROOT_DIR / ".venvs" / "gsv-tts-lite" / "Scripts" / "python.exe"),
            "GPT_SOVITS_PYTHON": str(ROOT_DIR / ".venvs" / "gpt-sovits" / "Scripts" / "python.exe"),
        }
        definitions = module.build_service_definitions(env_values)

        self.assertEqual(definitions["realtime"].command[0], env_values["REALTIME_PYTHON"])
        self.assertEqual(definitions["gpt_sovits"].command[0], env_values["GSV_TTS_LITE_PYTHON"])
        self.assertEqual(definitions["gpt_sovits"].cwd, module.BACKEND_DIR)
        self.assertIn("gsv_tts_lite_server.py", definitions["gpt_sovits"].command[1])

    def test_gpt_sovits_service_is_gsv_tts_lite_compatible_service(self):
        module = load_service_manager()
        definitions = module.build_service_definitions({})
        definition = definitions["gpt_sovits"]

        self.assertEqual(definition.id, "gpt_sovits")
        self.assertIn("GSV-TTS-Lite", definition.name)
        self.assertEqual(definition.port, 9880)
        self.assertIn("gsv_tts_lite_server.py", definition.command_line_hint)
        self.assertIn("GSV-TTS-Lite", module.service_setup_hint(definition))

    def test_gsv_service_env_requests_cuda_and_preload(self):
        module = load_service_manager()
        definitions = module.build_service_definitions({})
        definition = definitions["gpt_sovits"]

        self.assertEqual(definition.extra_env["GSV_TTS_LITE_DEVICE"], "cuda")
        self.assertEqual(definition.extra_env["GSV_TTS_LITE_PRELOAD"], "1")

    def test_ready_probe_requires_gsv_tts_lite_response_identity(self):
        module = load_service_manager()

        self.assertTrue(module.ready_response_matches_service({"provider": "gsv_tts_lite"}, "gpt_sovits"))
        self.assertTrue(module.ready_response_matches_service({"engine": "gsv_tts_lite"}, "gpt_sovits"))
        self.assertFalse(module.ready_response_matches_service(None, "gpt_sovits"))
        self.assertFalse(module.ready_response_matches_service({}, "gpt_sovits"))

    def test_gsv_service_status_disables_start_when_port_is_occupied_by_legacy_service(self):
        module = load_service_manager()
        manager = module.ServiceManager()

        with mock.patch.object(module, "find_pid_by_port", return_value=12345), mock.patch.object(
            module, "probe_url", return_value=(False, "9880 端口响应不是 GSV-TTS-Lite 包装服务")
        ), mock.patch.object(manager, "_pid_matches_service", return_value=False), mock.patch.object(
            module, "service_availability", return_value={"ok": True, "error": "", "hint": ""}
        ):
            status = manager.status("gpt_sovits")

        self.assertFalse(status["running"])
        self.assertFalse(status["can_start"])
        self.assertIn("端口响应不是 GSV-TTS-Lite", status["error"])

    def test_gsv_service_status_includes_runtime_device_details_from_ping(self):
        module = load_service_manager()
        manager = module.ServiceManager()
        ping_payload = {
            "ok": True,
            "provider": "gsv_tts_lite",
            "engine": "gsv_tts_lite",
            "effective_device": "cpu",
            "device_requested": "cuda",
            "device_warning": "CUDA requested but unavailable.",
            "torch_version": "2.12.1+cpu",
            "python_prefix": str(ROOT_DIR / ".venvs" / "gsv-tts-lite"),
        }

        with mock.patch.object(module, "find_pid_by_port", return_value=12345), mock.patch.object(
            module, "probe_url", return_value=(True, "")
        ), mock.patch.object(manager, "_pid_matches_service", return_value=True), mock.patch.object(
            module, "service_availability", return_value={"ok": True, "error": "", "hint": ""}
        ), mock.patch.object(module, "fetch_json", return_value=ping_payload):
            status = manager.status("gpt_sovits")

        self.assertEqual(status["runtime"]["engine"], "gsv_tts_lite")
        self.assertEqual(status["runtime"]["effective_device"], "cpu")
        self.assertEqual(status["runtime"]["device_requested"], "cuda")
        self.assertIn("CUDA", status["runtime"]["device_warning"])
        self.assertEqual(status["runtime"]["torch_version"], "2.12.1+cpu")

    def test_process_memory_uses_tasklist_without_powershell_on_windows(self):
        module = load_service_manager()
        seen = {}

        def fake_check_output(command, **kwargs):
            seen["command"] = command
            return "python.exe                 12345 Console                    1     48,120 K\r\n"

        with mock.patch.object(module.os, "name", "nt"), mock.patch.object(module.subprocess, "check_output", side_effect=fake_check_output):
            memory = module.process_memory_mb(12345)

        self.assertGreater(memory, 40)
        self.assertEqual(seen["command"][0], "tasklist")
        self.assertNotIn("powershell", " ".join(seen["command"]).lower())


if __name__ == "__main__":
    unittest.main()
