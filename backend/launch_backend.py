# -*- coding: utf-8 -*-
import os
import subprocess
import sys


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")
PYTHON_EXE = os.path.join(
    os.path.expanduser("~"),
    ".cache",
    "codex-runtimes",
    "codex-primary-runtime",
    "dependencies",
    "python",
    "python.exe",
)
if not os.path.exists(PYTHON_EXE):
    PYTHON_EXE = sys.executable


def main():
    env = {}
    for key, value in os.environ.items():
        if key.lower() == "path":
            env["PATH"] = value
        else:
            env[key] = value
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")

    stdout_path = os.path.join(ROOT_DIR, "server_current_stdout.log")
    stderr_path = os.path.join(ROOT_DIR, "server_current_stderr.log")
    with open(stdout_path, "ab", buffering=0) as stdout, open(stderr_path, "ab", buffering=0) as stderr:
        subprocess.Popen(
            [PYTHON_EXE, os.path.join(BACKEND_DIR, "main.py")],
            cwd=BACKEND_DIR,
            stdout=stdout,
            stderr=stderr,
            env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )


if __name__ == "__main__":
    main()
