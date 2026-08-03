# -*- coding: utf-8 -*-
import os
import sys
import threading
import webbrowser
from pathlib import Path


def _is_frozen():
    return bool(getattr(sys, "frozen", False))


def _asset_root():
    if _is_frozen() and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[1]


def _runtime_root():
    if _is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _prepare_paths():
    os.environ.setdefault("AIDH_ASSET_ROOT", str(_asset_root()))
    os.environ.setdefault("AIDH_RUNTIME_ROOT", str(_runtime_root()))
    backend_dir = Path(os.environ["AIDH_ASSET_ROOT"]) / "backend"
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))


def _maybe_open_browser(host, port):
    default_value = "1" if _is_frozen() else "0"
    enabled = os.getenv("AIDH_OPEN_BROWSER", default_value).strip().lower()
    if enabled in {"0", "false", "no", "off"}:
        return
    url = "http://{0}:{1}/".format("127.0.0.1" if host in {"0.0.0.0", "::"} else host, port)
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()


def main():
    _prepare_paths()
    from runtime_paths import ensure_runtime_dirs

    ensure_runtime_dirs()
    from main import app

    host = os.getenv("AIDH_HOST", "127.0.0.1")
    port = int(os.getenv("PORT") or os.getenv("AIDH_PORT") or "8000")
    _maybe_open_browser(host, port)
    app.run(host=host, port=port, threaded=True)


if __name__ == "__main__":
    main()
