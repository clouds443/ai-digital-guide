import base64
import hashlib
import json
import os
import random
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache"
EDGE_CANDIDATES = [
    Path(os.environ.get("EDGE_EXE", "")),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
]


class CdpWebSocket:
    def __init__(self, ws_url):
        self.url = ws_url
        self.sock = None
        self.next_id = 0
        self.events = []

    def connect(self):
        parsed = urllib.parse.urlparse(self.url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 80
        path = parsed.path
        if parsed.query:
            path += "?" + parsed.query
        self.sock = socket.create_connection((host, port), timeout=10)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            "GET {0} HTTP/1.1\r\n"
            "Host: {1}:{2}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Key: {3}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        ).format(path, host, port, key)
        self.sock.sendall(request.encode("ascii"))
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = self.sock.recv(4096)
            if not chunk:
                break
            response += chunk
        if b" 101 " not in response.split(b"\r\n", 1)[0]:
            raise RuntimeError("WebSocket handshake failed: " + response[:200].decode("latin1", "ignore"))
        accept = None
        for line in response.decode("latin1", "ignore").split("\r\n"):
            if line.lower().startswith("sec-websocket-accept:"):
                accept = line.split(":", 1)[1].strip()
                break
        expected = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()).decode("ascii")
        if accept != expected:
            raise RuntimeError("WebSocket accept mismatch")

    def close(self):
        try:
            if self.sock:
                self.sock.close()
        except Exception:
            pass

    def _send_frame(self, text):
        payload = text.encode("utf-8")
        header = bytearray([0x81])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))
        mask = os.urandom(4)
        header.extend(mask)
        masked = bytearray(payload)
        for index in range(len(masked)):
            masked[index] ^= mask[index % 4]
        self.sock.sendall(bytes(header) + bytes(masked))

    def _read_exact(self, length):
        chunks = []
        remaining = length
        while remaining:
            chunk = self.sock.recv(remaining)
            if not chunk:
                raise RuntimeError("WebSocket closed")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _read_frame(self):
        first = self._read_exact(2)
        opcode = first[0] & 0x0F
        masked = bool(first[1] & 0x80)
        length = first[1] & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._read_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._read_exact(8))[0]
        mask = self._read_exact(4) if masked else b""
        payload = bytearray(self._read_exact(length))
        if masked:
            for index in range(len(payload)):
                payload[index] ^= mask[index % 4]
        if opcode == 8:
            raise RuntimeError("WebSocket closed by peer")
        if opcode == 9:
            return self._read_frame()
        return payload.decode("utf-8", "replace")

    def call(self, method, params=None, timeout=15):
        self.next_id += 1
        message_id = self.next_id
        self._send_frame(json.dumps({"id": message_id, "method": method, "params": params or {}}))
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.sock.settimeout(max(0.1, deadline - time.time()))
            raw = self._read_frame()
            message = json.loads(raw)
            if message.get("id") == message_id:
                if "error" in message:
                    raise RuntimeError(json.dumps(message["error"], ensure_ascii=False))
                return message.get("result", {})
            self.events.append(message)
        raise TimeoutError(method)


def http_json(url, data=None, method=None):
    body = None
    headers = {}
    if data is not None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    request = urllib.request.Request(url, data=body, headers=headers, method=method or ("POST" if data is not None else "GET"))
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_http(url, timeout=15):
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            return http_json(url)
        except Exception as exc:
            last_error = exc
            time.sleep(0.3)
    raise RuntimeError("HTTP wait failed: {0}".format(last_error))


def find_edge():
    for candidate in EDGE_CANDIDATES:
        if candidate and str(candidate) and candidate.is_file():
            return candidate
    raise RuntimeError("Microsoft Edge executable not found")


def wait_eval(cdp, expression, timeout=20):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        result = cdp.call("Runtime.evaluate", {"expression": expression, "returnByValue": True, "awaitPromise": True}, timeout=5)
        value = result.get("result", {}).get("value")
        last = value
        if value:
            return value
        time.sleep(0.5)
    return last


def runtime_eval(cdp, expression, await_promise=True):
    result = cdp.call(
        "Runtime.evaluate",
        {"expression": expression, "returnByValue": True, "awaitPromise": await_promise},
        timeout=20,
    )
    if result.get("exceptionDetails"):
        return {"exception": result["exceptionDetails"]}
    return result.get("result", {}).get("value")


def main():
    base_url = os.environ.get("PROBE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    port = int(os.environ.get("EDGE_CDP_PORT", "9460")) + random.randint(0, 200)
    CACHE.mkdir(parents=True, exist_ok=True)
    profile = Path(tempfile.mkdtemp(prefix="edge-map-profile-", dir=str(CACHE)))
    edge = find_edge()
    process = subprocess.Popen(
        [
            str(edge),
            "--headless=new",
            "--window-size=1280,900",
            "--remote-debugging-port={0}".format(port),
            "--user-data-dir={0}".format(profile),
            "--no-first-run",
            "--disable-extensions",
            "about:blank",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    cdp = None
    try:
        version = wait_http("http://127.0.0.1:{0}/json/version".format(port), timeout=20)
        pages = wait_http("http://127.0.0.1:{0}/json/list".format(port), timeout=10)
        page = next((item for item in pages if item.get("url") == "about:blank"), pages[0])
        login = http_json(
            base_url + "/api/auth/login",
            {"username": "user", "password": "user123456", "role": "user"},
        )
        cdp = CdpWebSocket(page["webSocketDebuggerUrl"])
        cdp.connect()
        for method in ["Runtime.enable", "Page.enable", "Network.enable", "Log.enable"]:
            try:
                cdp.call(method, timeout=5)
            except Exception:
                pass
        cdp.call("Page.navigate", {"url": base_url + "/"}, timeout=5)
        wait_eval(cdp, "document.readyState === 'complete'", timeout=20)
        user_json = json.dumps(json.dumps(login["user"], ensure_ascii=False), ensure_ascii=False)
        token_json = json.dumps(login["token"], ensure_ascii=False)
        runtime_eval(
            cdp,
            "localStorage.setItem('authToken', {0}); localStorage.setItem('authUser', {1}); true".format(token_json, user_json),
        )
        cdp.call("Page.navigate", {"url": base_url + "/"}, timeout=5)
        wait_eval(cdp, "document.readyState === 'complete' && !!document.querySelector('#lingshanMapPanel')", timeout=25)
        time.sleep(float(os.environ.get("EDGE_MAP_WAIT_SECONDS", "12")))
        state = runtime_eval(
            cdp,
            """(() => {
              const map = document.querySelector('#lingshanAmap');
              const panel = document.querySelector('#lingshanMapPanel');
              const fallback = document.querySelector('#mapFallback');
              const status = document.querySelector('#mapStatusText');
              const info = document.querySelector('#mapInfoText');
              const mapOpenBtn = document.querySelector('#mapOpenBtn');
              const rect = map ? map.getBoundingClientRect() : null;
              const resources = performance.getEntriesByType('resource')
                .map(item => item.name)
                .filter(name => /amap|autonavi|webapi/.test(name))
                .slice(0, 40);
              return {
                url: location.href,
                title: document.title,
                loginHidden: document.querySelector('#loginView')?.classList.contains('hidden'),
                appHidden: document.querySelector('#appView')?.classList.contains('hidden'),
                statusText: status ? status.textContent : '',
                infoText: info ? info.textContent : '',
                mapOpenButtonText: mapOpenBtn ? mapOpenBtn.textContent.trim() : '',
                standaloneMapUrl: typeof buildStandaloneMapUrl === 'function' ? buildStandaloneMapUrl() : '',
                mapRect: rect ? {x: rect.x, y: rect.y, width: rect.width, height: rect.height} : null,
                panelClass: panel ? panel.className : '',
                fallbackDisplay: fallback ? getComputedStyle(fallback).display : '',
                fallbackText: fallback ? fallback.textContent.trim() : '',
                amapLoaded: !!window.AMap,
                canvasCount: map ? map.querySelectorAll('canvas').length : 0,
                imageCount: map ? map.querySelectorAll('img').length : 0,
                markerCount: map ? map.querySelectorAll('.amap-marker, .amap-marker-label').length : 0,
                childTags: map ? Array.from(map.children).map(node => node.tagName + '#' + (node.id || '') + '.' + node.className).slice(0, 20) : [],
                resources
              };
            })()""",
        )
        logs = []
        for event in cdp.events:
            method = event.get("method", "")
            params = event.get("params", {})
            if method in {"Runtime.consoleAPICalled", "Log.entryAdded", "Network.loadingFailed"}:
                logs.append({"method": method, "params": params})
        screenshot = cdp.call("Page.captureScreenshot", {"format": "png", "fromSurface": True}, timeout=20)
        screenshot_path = CACHE / "edge-map-screenshot.png"
        screenshot_path.write_bytes(base64.b64decode(screenshot["data"]))
        output = {
            "edge": str(edge),
            "edge_version": version.get("Browser"),
            "profile": str(profile),
            "screenshot": str(screenshot_path),
            "state": state,
            "logs": logs[-80:],
        }
        output_path = CACHE / "edge-map-state.json"
        output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    finally:
        if cdp:
            cdp.close()
        try:
            process.terminate()
            process.wait(timeout=5)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
