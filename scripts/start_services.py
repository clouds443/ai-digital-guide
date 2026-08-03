import os
import subprocess
import sys
import time
import urllib.request
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from service_manager import parse_start_profile  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
LOGS = ROOT / "logs"
ENV_PATH = BACKEND / ".env"
PYTHON = Path(sys.executable)
ANACONDA_PYTHON = Path(r"D:\Anaconda\python.exe")
DEFAULT_REALTIME_PYTHON = PYTHON
DEFAULT_GSV_TTS_LITE_PYTHON = ROOT / ".venvs" / "gsv-tts-lite" / "Scripts" / "python.exe"
DEFAULT_GPT_SOVITS_PYTHON = DEFAULT_GSV_TTS_LITE_PYTHON
GSV_TTS_LITE_SERVER = BACKEND / "gsv_tts_lite_server.py"


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
    if not path.exists():
        return {}
    return parse_env_lines(path.read_text(encoding="utf-8").splitlines())


def runtime_path(env_values, key, default):
    value = str(env_values.get(key, "")).strip()
    return Path(value) if value else Path(default)


def python_has_module(python_exe, module_name):
    python_exe = Path(python_exe)
    if not python_exe.exists():
        return False
    try:
        result = subprocess.run(
            [str(python_exe), "-c", "import {0}".format(module_name)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=8,
        )
    except Exception:
        return False
    return result.returncode == 0


def select_python_for_module(module_name, candidates=None, has_module=python_has_module):
    candidates = list(candidates or [Path(os.getenv("FLASK_PYTHON", "")), PYTHON, ANACONDA_PYTHON])
    seen = set()
    for candidate in candidates:
        if not candidate:
            continue
        candidate = Path(candidate)
        key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        if has_module(candidate, module_name):
            return candidate
    return PYTHON


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
    return env


def service_env(extra=None):
    base = {
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
    }
    if extra:
        base.update(extra)
    return base


def gsv_tts_lite_env():
    tmp_dir = ROOT / ".cache" / "tmp"
    return {
        "TEMP": str(tmp_dir),
        "TMP": str(tmp_dir),
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "Path": str(ROOT / "bin") + os.pathsep + os.environ.get("Path", ""),
        "GSV_TTS_LITE_PORT": "9880",
        "GSV_TTS_LITE_PRELOAD": "1",
        "GSV_TTS_LITE_DEVICE": "cuda",
    }


def windows_creationflags(os_name=os.name, subprocess_module=subprocess, breakaway=False):
    if os_name != "nt":
        return 0
    new_group = int(getattr(subprocess_module, "CREATE_NEW_PROCESS_GROUP", 0x00000200))
    detached = int(getattr(subprocess_module, "DETACHED_PROCESS", 0x00000008))
    flags = new_group | detached
    if breakaway:
        flags |= int(getattr(subprocess_module, "CREATE_BREAKAWAY_FROM_JOB", 0x01000000))
    return flags


def popen_close_fds(os_name=os.name):
    return os_name != "nt"


def start_service(name, script, stdout_name, stderr_name, extra_env=None, python_exe=None):
    LOGS.mkdir(parents=True, exist_ok=True)
    stdout = open(LOGS / stdout_name, "ab", buffering=0)
    stderr = open(LOGS / stderr_name, "ab", buffering=0)
    creationflags = windows_creationflags(breakaway=os.getenv("START_SERVICES_BREAKAWAY", "") == "1")
    python_exe = Path(python_exe or PYTHON)
    process = subprocess.Popen(
        [str(python_exe), str(BACKEND / script)],
        cwd=str(BACKEND),
        stdout=stdout,
        stderr=stderr,
        stdin=subprocess.DEVNULL,
        env=clean_env(extra_env),
        creationflags=creationflags,
        close_fds=popen_close_fds(),
    )
    print(f"{name}: pid={process.pid}")
    return process


def start_gpt_sovits():
    env_values = load_backend_env()
    gsv_python = runtime_path(
        env_values,
        "GSV_TTS_LITE_PYTHON",
        runtime_path(env_values, "GPT_SOVITS_PYTHON", DEFAULT_GSV_TTS_LITE_PYTHON),
    )
    if not gsv_python.exists() or not GSV_TTS_LITE_SERVER.exists():
        print("GSV-TTS-Lite: skipped, environment or wrapper script is missing")
        return None
    LOGS.mkdir(parents=True, exist_ok=True)
    tmp_dir = ROOT / ".cache" / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    stdout = open(LOGS / "gpt_sovits_stdout.log", "ab", buffering=0)
    stderr = open(LOGS / "gpt_sovits_stderr.log", "ab", buffering=0)
    creationflags = windows_creationflags(breakaway=os.getenv("START_SERVICES_BREAKAWAY", "") == "1")
    env = clean_env(gsv_tts_lite_env())
    process = subprocess.Popen(
        [
            str(gsv_python),
            str(GSV_TTS_LITE_SERVER),
        ],
        cwd=str(BACKEND),
        stdout=stdout,
        stderr=stderr,
        stdin=subprocess.DEVNULL,
        env=env,
        creationflags=creationflags,
        close_fds=popen_close_fds(),
    )
    print(f"GSV-TTS-Lite 9880: pid={process.pid}")
    return process


def wait_url(url, seconds=35):
    deadline = time.time() + seconds
    last_error = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                return response.status, ""
        except Exception as exc:
            last_error = str(exc)
            time.sleep(1)
    return None, last_error


def check_flask_contract(base_url):
    def get_json(path, timeout=8):
        with urllib.request.urlopen(base_url.rstrip("/") + path, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    payload = json.dumps(
        {
            "query": "我带孩子玩四小时，请推荐路线",
            "interest": "亲子家庭",
            "history": [],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        base_url.rstrip("/") + "/api/chat",
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return False, str(exc)

    required = {"answer", "emotion", "route_suggestion", "sources", "latency_ms"}
    missing = sorted(required.difference(data))
    if missing:
        return False, "missing chat metadata: " + ", ".join(missing)
    route_id = (data.get("route_suggestion") or {}).get("id")
    if route_id != "route_family":
        return False, "unexpected route_suggestion id: {0}".format(route_id)
    try:
        map_config = get_json("/api/map/config")
        route_map = get_json("/api/map/route/route_history")
    except Exception as exc:
        return False, "map contract failed: /api/map/config or /api/map/route/route_history unavailable ({0})".format(exc)
    if "ok" not in map_config or "center" not in map_config:
        return False, "map contract failed: /api/map/config missing ok/center"
    if not route_map.get("points") or not route_map.get("polyline"):
        return False, "map contract failed: /api/map/route/route_history missing points/polyline"
    return True, "chat and map contract ok, latency_ms={0}".format(data.get("latency_ms"))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    profile = parse_start_profile(argv)
    print("Starting Lingshan AI Digital Human services...")
    print("Profile: {0}".format("full" if profile["realtime"] and profile["gpt_sovits"] else "light/custom"))
    if profile["gpt_sovits"]:
        start_gpt_sovits()
    else:
        print("GSV-TTS-Lite 9880: skipped by low-memory profile")
    flask_python = select_python_for_module("flask")
    flask_env = service_env({"LOCAL_RAG_ONLY": "0" if profile["gpt_sovits"] and profile["realtime"] else "1"})
    start_service("Flask 8000", "main.py", "flask_stdout.log", "flask_stderr.log", extra_env=flask_env, python_exe=flask_python)
    if profile["realtime"]:
        realtime_python = runtime_path(load_backend_env(), "REALTIME_PYTHON", DEFAULT_REALTIME_PYTHON)
        start_service(
            "Realtime 8010",
            "realtime_server.py",
            "realtime_stdout.log",
            "realtime_stderr.log",
            {
                "FUNASR_STREAMING_MODEL_DIR": str(ROOT / "models" / "FunASR" / "paraformer-zh-streaming"),
                "FUNASR_VAD_MODEL_DIR": str(ROOT / "models" / "FunASR" / "fsmn-vad"),
                "FUNASR_PUNC_MODEL_DIR": str(ROOT / "models" / "FunASR" / "ct-punc"),
                "FUNASR_DEVICE": "cuda:0",
                "REALTIME_SILENCE_END_MS": "600",
                "REALTIME_MIN_SPEECH_MS": "300",
                "REALTIME_MAX_LISTEN_MS": "15000",
            },
            python_exe=realtime_python,
        )
    else:
        print("Realtime 8010: skipped by low-memory profile")

    checks = [("Flask", "http://127.0.0.1:8000/")]
    if profile["gpt_sovits"]:
        checks.insert(0, ("GSV-TTS-Lite", "http://127.0.0.1:9880/control?command=ping"))
    if profile["realtime"]:
        checks.append(("Realtime", "http://127.0.0.1:8010/api/realtime/status"))
    ok = True
    for name, url in checks:
        status, error = wait_url(url)
        if status:
            print(f"{name}: http {status} {url}")
        else:
            ok = False
            print(f"{name}: failed {url} ({error})")
    if ok:
        contract_ok, contract_message = check_flask_contract("http://127.0.0.1:8000")
        if contract_ok:
            print("Flask contract: {0}".format(contract_message))
        else:
            ok = False
            print("Flask contract failed: {0}".format(contract_message))
            print("If port 8000 is occupied by an old process, stop that process and rerun this script.")
    if not profile["gpt_sovits"] or not profile["realtime"]:
        print("Low-memory mode: start optional services from Admin > 服务管理 when needed.")
    print("TTS: GSV-TTS-Lite API expected at http://127.0.0.1:9880 when enabled; gpt_sovits remains a compatibility provider value")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
