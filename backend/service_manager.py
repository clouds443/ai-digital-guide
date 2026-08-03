# -*- coding: utf-8 -*-
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from runtime_paths import asset_path as package_asset_path, runtime_path as package_runtime_path

ROOT_DIR = Path(package_runtime_path())
ASSET_ROOT = Path(package_asset_path())
BACKEND_DIR = ASSET_ROOT / "backend"
LOGS_DIR = ROOT_DIR / "logs"
ENV_PATH = ROOT_DIR / "backend" / ".env"
ASSET_ENV_PATH = BACKEND_DIR / ".env"
PYTHON_EXE = Path(sys.executable)
DEFAULT_REALTIME_PYTHON = PYTHON_EXE
DEFAULT_GSV_TTS_LITE_PYTHON = ROOT_DIR / ".venvs" / "gsv-tts-lite" / "Scripts" / "python.exe"
DEFAULT_GPT_SOVITS_PYTHON = DEFAULT_GSV_TTS_LITE_PYTHON
GSV_TTS_LITE_SERVER = BACKEND_DIR / "gsv_tts_lite_server.py"


class ServiceDefinition:
    def __init__(
        self,
        id,
        name,
        port,
        url,
        ready_url,
        cwd,
        command,
        stdout_log,
        stderr_log,
        command_line_hint,
        extra_env,
    ):
        self.id = id
        self.name = name
        self.port = port
        self.url = url
        self.ready_url = ready_url
        self.cwd = cwd
        self.command = command
        self.stdout_log = stdout_log
        self.stderr_log = stderr_log
        self.command_line_hint = command_line_hint
        self.extra_env = extra_env


def parse_env_lines(lines):
    values = {}
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_backend_env(path=ENV_PATH):
    if not path.exists() and ASSET_ENV_PATH.exists():
        path = ASSET_ENV_PATH
    if not path.exists():
        return {}
    return parse_env_lines(path.read_text(encoding="utf-8").splitlines())


def runtime_path(env_values, key, default):
    value = str(env_values.get(key, "")).strip()
    return Path(value) if value else Path(default)


def build_service_definitions(env_values=None):
    env_values = dict(env_values or load_backend_env())
    realtime_python = runtime_path(env_values, "REALTIME_PYTHON", DEFAULT_REALTIME_PYTHON)
    gsv_tts_lite_python = runtime_path(
        env_values,
        "GSV_TTS_LITE_PYTHON",
        runtime_path(env_values, "GPT_SOVITS_PYTHON", DEFAULT_GSV_TTS_LITE_PYTHON),
    )
    return {
        "realtime": ServiceDefinition(
            id="realtime",
            name="实时语音服务",
            port=8010,
            url="http://127.0.0.1:8010/api/realtime/status",
            ready_url="http://127.0.0.1:8010/api/realtime/status",
            cwd=BACKEND_DIR,
            command=(str(realtime_python), str(BACKEND_DIR / "realtime_server.py")),
            stdout_log="realtime_stdout.log",
            stderr_log="realtime_stderr.log",
            command_line_hint=str(BACKEND_DIR / "realtime_server.py"),
            extra_env={
                "FUNASR_STREAMING_MODEL_DIR": str(ROOT_DIR / "models" / "FunASR" / "paraformer-zh-streaming"),
                "FUNASR_VAD_MODEL_DIR": str(ROOT_DIR / "models" / "FunASR" / "fsmn-vad"),
                "FUNASR_PUNC_MODEL_DIR": str(ROOT_DIR / "models" / "FunASR" / "ct-punc"),
                "FUNASR_DEVICE": "cuda:0",
                "REALTIME_SILENCE_END_MS": "600",
                "REALTIME_MIN_SPEECH_MS": "300",
                "REALTIME_MAX_LISTEN_MS": "15000",
            },
        ),
        "gpt_sovits": ServiceDefinition(
            id="gpt_sovits",
            name="GSV-TTS-Lite 克隆音色服务",
            port=9880,
            url="http://127.0.0.1:9880/control?command=ping",
            ready_url="http://127.0.0.1:9880/control?command=ping",
            cwd=BACKEND_DIR,
            command=(
                str(gsv_tts_lite_python),
                str(GSV_TTS_LITE_SERVER),
            ),
            stdout_log="gpt_sovits_stdout.log",
            stderr_log="gpt_sovits_stderr.log",
            command_line_hint=str(GSV_TTS_LITE_SERVER),
            extra_env={
                "TEMP": str(ROOT_DIR / ".cache" / "tmp"),
                "TMP": str(ROOT_DIR / ".cache" / "tmp"),
                "PYTHONUTF8": "1",
                "PYTHONIOENCODING": "utf-8",
                "GSV_TTS_LITE_PORT": "9880",
                "GSV_TTS_LITE_PRELOAD": "1",
                "GSV_TTS_LITE_DEVICE": "cuda",
            },
        ),
    }


SERVICE_DEFINITIONS = build_service_definitions()


def clean_env(extra=None):
    env = {}
    for key, value in os.environ.items():
        normalized = "PATH" if key.lower() == "path" else key
        if normalized not in env:
            env[normalized] = value
    if extra:
        for key, value in extra.items():
            normalized = "PATH" if key.lower() == "path" else key
            env[normalized] = value
    env["PATH"] = str(ASSET_ROOT / "bin") + os.pathsep + str(ROOT_DIR / "bin") + os.pathsep + env.get("PATH", "")
    return env


def parse_start_profile(argv):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--profile", choices=["light", "full"], default="light")
    parser.add_argument("--no-gpt-sovits", action="store_true")
    parser.add_argument("--no-realtime", action="store_true")
    args, _ = parser.parse_known_args(argv)
    result = {
        "flask": True,
        "realtime": args.profile == "full",
        "gpt_sovits": args.profile == "full",
    }
    if args.no_realtime:
        result["realtime"] = False
    if args.no_gpt_sovits:
        result["gpt_sovits"] = False
    return result


class ServiceManager:
    def __init__(self, definitions=None):
        self.definitions = definitions or SERVICE_DEFINITIONS

    def _definition(self, service_id):
        if service_id not in self.definitions:
            raise ValueError("Unsupported service: {0}".format(service_id))
        return self.definitions[service_id]

    def status_all(self):
        return {"services": [self.status(service_id) for service_id in ["flask", *self.definitions.keys()]]}

    def status(self, service_id):
        if service_id == "flask":
            return self._flask_status()
        definition = self._definition(service_id)
        pid = find_pid_by_port(definition.port)
        ready, error = (False, "")
        if pid:
            ready, error = probe_url(definition.ready_url, timeout=3)
        runtime = runtime_details(definition, ready) if pid else {}
        availability = service_availability(definition)
        running = bool(pid and (self._ready_proves_service(definition, ready) or self._pid_matches_service(pid, definition)))
        port_blocked = bool(pid and not running)
        effective_error = "端口 {0} 已被其他服务占用。{1}".format(definition.port, error) if port_blocked else (availability["error"] or error)
        return {
            "id": definition.id,
            "name": definition.name,
            "running": running,
            "pid": pid if running else None,
            "port": definition.port,
            "memory_mb": process_memory_mb(pid) if running else 0,
            "ready": ready,
            "runtime": runtime,
            "url": definition.url,
            "error": "" if ready else effective_error,
            "stdout_tail": read_log_tail(definition.stdout_log),
            "stderr_tail": read_log_tail(definition.stderr_log),
            "can_start": bool(availability["ok"] and not port_blocked),
            "can_stop": True,
            "hint": availability["hint"] or ("请先停止占用端口的旧服务，再启动 GSV-TTS-Lite。" if port_blocked else ""),
        }

    def start_service(self, service_id):
        definition = self._definition(service_id)
        current = self.status(service_id)
        if current["running"]:
            return current
        if not current.get("can_start", True):
            raise RuntimeError(current.get("error") or "服务当前不可启动，请先补齐运行环境。")
        validate_service_paths(definition)
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        for key in ("TEMP", "TMP"):
            if key in definition.extra_env:
                Path(definition.extra_env[key]).mkdir(parents=True, exist_ok=True)
        stdout = open(LOGS_DIR / definition.stdout_log, "ab", buffering=0)
        stderr = open(LOGS_DIR / definition.stderr_log, "ab", buffering=0)
        creationflags = windows_creationflags()
        subprocess.Popen(
            list(definition.command),
            cwd=str(definition.cwd),
            stdout=stdout,
            stderr=stderr,
            stdin=subprocess.DEVNULL,
            env=clean_env(definition.extra_env),
            creationflags=creationflags,
            close_fds=popen_close_fds(),
        )
        for _ in range(30):
            time.sleep(1)
            status = self.status(service_id)
            if status["running"] and status["ready"]:
                return status
        return self.status(service_id)

    def stop_service(self, service_id):
        definition = self._definition(service_id)
        status = self.status(service_id)
        pid = status.get("pid")
        if not pid:
            return status
        if not (self._pid_matches_service(pid, definition) or self._ready_proves_service(definition, status.get("ready"))):
            raise RuntimeError("Refusing to stop PID {0}: command line does not match {1}".format(pid, definition.id))
        stop_pid(pid)
        time.sleep(1)
        return self.status(service_id)

    def _flask_status(self):
        pid = find_pid_by_port(8000)
        ready, error = probe_url("http://127.0.0.1:8000/", timeout=3) if pid else (False, "not listening")
        return {
            "id": "flask",
            "name": "主后端",
            "running": bool(pid),
            "pid": pid,
            "port": 8000,
            "memory_mb": process_memory_mb(pid) if pid else 0,
            "ready": ready,
            "url": "http://127.0.0.1:8000/",
            "error": "" if ready else error,
            "stdout_tail": read_log_tail("flask_stdout.log"),
            "stderr_tail": "",
            "can_start": False,
            "can_stop": False,
        }

    def _pid_matches_service(self, pid, definition):
        command = process_command_line(pid)
        return bool(command and definition.command_line_hint.lower() in command.lower())

    def _ready_proves_service(self, definition, ready):
        return bool(ready and definition.ready_url)


def validate_service_paths(definition):
    executable = Path(definition.command[0])
    if not executable.exists():
        raise FileNotFoundError("服务解释器不存在：{0}".format(executable))
    if definition.id == "gpt_sovits" and not GSV_TTS_LITE_SERVER.exists():
        raise FileNotFoundError("GSV-TTS-Lite 包装服务脚本不存在：{0}".format(GSV_TTS_LITE_SERVER))
    if definition.id == "realtime" and not (BACKEND_DIR / "realtime_server.py").exists():
        raise FileNotFoundError("实时服务脚本不存在：{0}".format(BACKEND_DIR / "realtime_server.py"))


def service_availability(definition):
    try:
        validate_service_paths(definition)
    except Exception as exc:
        return {"ok": False, "error": str(exc), "hint": service_setup_hint(definition)}
    missing = missing_python_modules(definition)
    if missing:
        return {
            "ok": False,
            "error": "缺少依赖：{0}".format("、".join(missing)),
            "hint": service_setup_hint(definition),
        }
    return {"ok": True, "error": "", "hint": ""}


def service_setup_hint(definition):
    if definition.id == "gpt_sovits":
        return "请先运行 scripts\\install_gsv_tts_lite_env.ps1，安装 .venvs\\gsv-tts-lite 后再启动 GSV-TTS-Lite。旧服务 id gpt_sovits 仅用于兼容。"
    if definition.id == "realtime":
        return "请在实时语音 Python 环境中安装 fastapi、uvicorn、funasr、modelscope，或先使用普通录音模式。"
    return ""


def missing_python_modules(definition):
    if definition.id == "realtime":
        required = ["fastapi", "uvicorn", "funasr"]
    elif definition.id == "gpt_sovits":
        required = ["fastapi", "uvicorn", "gsv_tts"]
    else:
        required = []
    return [name for name in required if not python_has_module(definition.command[0], name)]


def python_has_module(python_exe, module_name):
    try:
        code = "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec({0!r}) else 1)".format(module_name)
        subprocess.check_call(
            [str(python_exe), "-c", code],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:
        return False


def find_pid_by_port(port):
    if os.name == "nt":
        command = ["netstat", "-ano", "-p", "tcp"]
        output = check_output_text(command)
        for line in output.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[1].endswith(":{0}".format(port)) and parts[3].upper() == "LISTENING":
                try:
                    return int(parts[4])
                except ValueError:
                    return None
    return None


def process_command_line(pid):
    try:
        command = [
            "powershell",
            "-NoProfile",
            "-Command",
            "(Get-CimInstance Win32_Process -Filter \"ProcessId={0}\").CommandLine".format(int(pid)),
        ]
        return check_output_text(command, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


def process_memory_mb(pid):
    try:
        if os.name == "nt":
            command = ["tasklist", "/fi", "PID eq {0}".format(int(pid))]
            output = check_output_text(command)
            match = re.search(r"([\d,]+)\s+K", output)
            if not match:
                return 0
            kb = int(match.group(1).replace(",", ""))
            return round(kb / 1024, 1)
        command = [
            "powershell",
            "-NoProfile",
            "-Command",
            "(Get-Process -Id {0}).WorkingSet64".format(int(pid)),
        ]
        raw = check_output_text(command, stderr=subprocess.DEVNULL).strip()
        return round(int(raw) / 1024 / 1024, 1)
    except Exception:
        return 0


def check_output_text(command, **kwargs):
    try:
        output = subprocess.check_output(command, universal_newlines=True, stderr=kwargs.get("stderr"))
    except TypeError:
        output = subprocess.check_output(command, stderr=kwargs.get("stderr"))
    if isinstance(output, bytes):
        return output.decode("utf-8", "ignore")
    return str(output)


def windows_creationflags(os_name=os.name, subprocess_module=subprocess):
    if os_name != "nt":
        return 0
    new_group = int(getattr(subprocess_module, "CREATE_NEW_PROCESS_GROUP", 0x00000200))
    detached = int(getattr(subprocess_module, "DETACHED_PROCESS", 0x00000008))
    return new_group | detached


def popen_close_fds(os_name=os.name):
    return os_name != "nt"


def stop_pid(pid):
    if os.name == "nt":
        subprocess.check_call(["taskkill", "/PID", str(int(pid)), "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        os.kill(int(pid), 15)


def probe_url(url, timeout=3):
    try:
        payload = fetch_json(url, timeout=timeout)
        if not ready_response_matches_service(payload, "gpt_sovits") and "9880" in str(url):
            return False, "9880 端口响应不是 GSV-TTS-Lite 包装服务，请停止旧服务后重新启动。"
        return True, ""
    except Exception as exc:
        return False, str(exc)


def fetch_json(url, timeout=3):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        raw = response.read()
    try:
        return json.loads(raw.decode("utf-8", "ignore")) if raw else {}
    except Exception:
        return {}


def runtime_details(definition, ready):
    if definition.id != "gpt_sovits" or not ready:
        return {}
    try:
        payload = fetch_json(definition.ready_url, timeout=3)
    except Exception:
        return {}
    return {
        "engine": payload.get("engine") or payload.get("provider") or "",
        "effective_device": payload.get("effective_device") or "",
        "device_requested": payload.get("device_requested") or "",
        "device_warning": payload.get("device_warning") or "",
        "torch_version": payload.get("torch_version") or "",
        "cuda_available": bool(payload.get("cuda_available")),
        "cuda_device": payload.get("cuda_device") or "",
        "python_prefix": payload.get("python_prefix") or "",
    }


def ready_response_matches_service(payload, service_id):
    if service_id != "gpt_sovits":
        return True
    if not isinstance(payload, dict):
        return False
    return payload.get("provider") == "gsv_tts_lite" or payload.get("engine") == "gsv_tts_lite"


def read_log_tail(log_name, max_chars=1200):
    path = LOGS_DIR / log_name
    if not path.exists():
        return ""
    try:
        data = path.read_text(encoding="utf-8", errors="ignore")
        return data[-max_chars:]
    except Exception:
        return ""
