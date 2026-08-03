import base64
import json
import os
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from edge_map_probe import (  # noqa: E402
    CACHE,
    CdpWebSocket,
    find_edge,
    runtime_eval,
    wait_eval,
    wait_http,
)

import subprocess  # noqa: E402


ROUTE_FOCUS_VIEWS = {
    "route_history": [
        {"name": "central_zoomed", "zoom": 17.55, "center": [120.10005, 31.42550], "pitch": 55, "rotation": 0},
        {"name": "north_zoomed", "zoom": 17.35, "center": [120.10045, 31.42710], "pitch": 55, "rotation": 0},
    ],
    "route_nature": [
        {"name": "jiulong_buddha_zoomed", "zoom": 17.20, "center": [120.09870, 31.42710], "pitch": 55, "rotation": 0},
        {"name": "garden_jingshe_zoomed", "zoom": 17.20, "center": [120.09935, 31.42530], "pitch": 55, "rotation": 0},
    ],
    "route_family": [
        {"name": "jiulong_baizi_zoomed", "zoom": 17.55, "center": [120.09910, 31.42590], "pitch": 55, "rotation": 0},
        {"name": "fangong_wuyin_zoomed", "zoom": 17.35, "center": [120.10145, 31.42670], "pitch": 55, "rotation": 0},
    ],
}


def capture_screenshot(cdp, path):
    screenshot = cdp.call("Page.captureScreenshot", {"format": "png", "fromSurface": True}, timeout=20)
    path.write_bytes(base64.b64decode(screenshot["data"]))
    return str(path)


def apply_map_view(cdp, view):
    expression = """(() => {
      if (typeof state === 'undefined' || !state.map) return false;
      const view = %s;
      if (state.map.setPitch) state.map.setPitch(view.pitch || 55);
      if (state.map.setRotation) state.map.setRotation(view.rotation || 0);
      if (state.map.setZoomAndCenter) {
        state.map.setZoomAndCenter(view.zoom, view.center);
      } else {
        if (state.map.setZoom) state.map.setZoom(view.zoom);
        if (state.map.setCenter) state.map.setCenter(view.center);
      }
      return true;
    })()""" % json.dumps(view, ensure_ascii=False)
    return runtime_eval(cdp, expression)


def main():
    base_url = os.environ.get("PROBE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    route_id = os.environ.get("PROBE_ROUTE_ID", "route_history")
    port = int(os.environ.get("EDGE_CDP_PORT", "9720"))
    CACHE.mkdir(parents=True, exist_ok=True)
    edge = find_edge()
    profile = CACHE / "edge-standalone-map-profile-{0}-{1}".format(port, int(time.time() * 1000))
    profile.mkdir(parents=True, exist_ok=True)
    url = base_url + "/map.html?route=" + route_id
    edge_args = [
        str(edge),
        "--window-size={0}".format(os.environ.get("EDGE_WINDOW_SIZE", "1440,960")),
        "--remote-debugging-port={0}".format(port),
        "--user-data-dir={0}".format(profile),
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        "--disable-background-networking",
        "--disable-sync",
        "--disable-popup-blocking",
        "--remote-allow-origins=*",
    ]
    if os.environ.get("EDGE_HEADLESS", "1") not in {"0", "false", "False"}:
        edge_args.extend(["--headless=new", "--disable-gpu"])
    edge_args.append(url)
    process = subprocess.Popen(
        edge_args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    cdp = None
    try:
        version = wait_http("http://127.0.0.1:{0}/json/version".format(port), timeout=20)
        pages = wait_http("http://127.0.0.1:{0}/json/list".format(port), timeout=10)
        page = next((item for item in pages if item.get("url", "").startswith(base_url + "/map.html")), pages[0])
        cdp = CdpWebSocket(page["webSocketDebuggerUrl"])
        cdp.connect()
        for method in ["Runtime.enable", "Page.enable", "Network.enable", "Log.enable"]:
            try:
                cdp.call(method, timeout=5)
            except Exception:
                pass
        wait_eval(cdp, "document.readyState === 'complete' && !!document.querySelector('#standaloneAmap')", timeout=25)
        time.sleep(float(os.environ.get("EDGE_MAP_WAIT_SECONDS", "12")))
        view_expr = os.environ.get("EDGE_MAP_VIEW_EXPR", "").strip()
        if view_expr:
            runtime_eval(cdp, view_expr)
            time.sleep(float(os.environ.get("EDGE_MAP_POST_VIEW_WAIT_SECONDS", "2")))
        state = runtime_eval(
            cdp,
            """(() => {
              const map = document.querySelector('#standaloneAmap');
              const fallback = document.querySelector('#mapFallback');
              const status = document.querySelector('#mapStatus');
              const select = document.querySelector('#routeSelect');
              const rect = map ? map.getBoundingClientRect() : null;
              const resources = performance.getEntriesByType('resource')
                .map(item => item.name)
                .filter(name => /amap|autonavi|webapi/.test(name))
                .slice(0, 40);
              return {
                url: location.href,
                title: document.title,
                routeValue: select ? select.value : '',
                statusText: status ? status.textContent : '',
                mapRect: rect ? {x: rect.x, y: rect.y, width: rect.width, height: rect.height} : null,
                fallbackDisplay: fallback ? getComputedStyle(fallback).display : '',
                fallbackText: fallback ? fallback.textContent.trim() : '',
                amapLoaded: !!window.AMap,
                canvasCount: map ? map.querySelectorAll('canvas').length : 0,
                imageCount: map ? map.querySelectorAll('img').length : 0,
                markerCount: map ? map.querySelectorAll('.amap-marker, .amap-marker-label').length : 0,
                routeMarkerCount: map ? map.querySelectorAll('.route-marker').length : 0,
                routeMarkers: map ? Array.from(map.querySelectorAll('.route-marker')).map((item) => {
                  const marker = item.closest('.amap-marker');
                  const name = item.querySelector('.route-marker-name');
                  const itemRect = item.getBoundingClientRect();
                  const markerRect = marker ? marker.getBoundingClientRect() : null;
                  const nameRect = name ? name.getBoundingClientRect() : null;
                  const itemStyle = getComputedStyle(item);
                  const markerStyle = marker ? getComputedStyle(marker) : null;
                  const nameStyle = name ? getComputedStyle(name) : null;
                  return {
                    text: name ? name.textContent.trim() : '',
                    itemWidth: Math.round(itemRect.width),
                    itemLeft: Math.round(itemRect.left),
                    itemRight: Math.round(itemRect.right),
                    markerWidth: markerRect ? Math.round(markerRect.width) : 0,
                    nameWidth: nameRect ? Math.round(nameRect.width) : 0,
                    itemOverflow: itemStyle.overflow,
                    markerOverflow: markerStyle ? markerStyle.overflow : '',
                    nameOverflow: nameStyle ? nameStyle.overflow : '',
                    clipped: rect ? itemRect.left < rect.left || itemRect.right > rect.right : false
                  };
                }) : [],
                controlBarCount: map ? map.querySelectorAll('.amap-controlbar, .amap-controlbar-outer').length : 0,
                controlBarText: map ? Array.from(map.querySelectorAll('.amap-controlbar, .amap-controlbar-outer')).map(item => item.textContent.trim()).join(' ') : '',
                routePathSource: typeof state !== 'undefined' ? state.routePathSource : '',
                polylinePointCount: (() => {
                  try {
                    return typeof state !== 'undefined' && state.polyline && state.polyline.getPath ? state.polyline.getPath().length : 0;
                  } catch (error) {
                    return 0;
                  }
                })(),
                controlledWaypoints: (() => {
                  const expectedByRoute = {
                    route_history: [
                      [120.100820, 31.423802],
                      [120.099922, 31.424501],
                      [120.099549, 31.424970],
                      [120.098468, 31.427413],
                      [120.096493, 31.430161],
                      [120.100100, 31.426181],
                      [120.102491, 31.427799],
                      [120.102600, 31.426597],
                      [120.103073, 31.424501]
                    ],
                    route_nature: [
                      [120.100820, 31.423802],
                      [120.099922, 31.424501],
                      [120.096493, 31.430161],
                      [120.098077, 31.424293],
                      [120.098824, 31.424674],
                      [120.100751, 31.426306]
                    ],
                    route_family: [
                      [120.099922, 31.424501],
                      [120.099527, 31.426181],
                      [120.098468, 31.427413],
                      [120.100100, 31.426181],
                      [120.102491, 31.427799],
                      [120.102600, 31.426597],
                      [120.103073, 31.424501]
                    ]
                  };
                  const expected = expectedByRoute[select ? select.value : 'route_history'] || expectedByRoute.route_history;
                  try {
                    const path = typeof state !== 'undefined' && state.polyline && state.polyline.getPath ? state.polyline.getPath().map((point) => {
                      const lng = typeof point.getLng === 'function' ? point.getLng() : (point.lng !== undefined ? point.lng : point[0]);
                      const lat = typeof point.getLat === 'function' ? point.getLat() : (point.lat !== undefined ? point.lat : point[1]);
                      return [Number(lng), Number(lat)];
                    }) : [];
                    return expected.map(([lng, lat]) => path.some((point) => Math.abs(point[0] - lng) < 0.00001 && Math.abs(point[1] - lat) < 0.00001));
                  } catch (error) {
                    return expected.map(() => false);
                  }
                })(),
                mapPitch: window.AMap && typeof state !== 'undefined' && state.map && state.map.getPitch ? state.map.getPitch() : null,
                mapRotation: window.AMap && typeof state !== 'undefined' && state.map && state.map.getRotation ? state.map.getRotation() : null,
                resources
              };
            })()""",
        )
        walking_probe = {}
        if os.environ.get("EDGE_EXTRACT_WALKING", "0") in {"1", "true", "True"}:
            walking_probe = runtime_eval(
                cdp,
                """(async () => {
                  if (typeof state === 'undefined' || !state.AMap || !state.routeMap || !state.routeMap.points) {
                    return {ok: false, error: 'map state not ready'};
                  }
                  const walking = new state.AMap.Walking({autoFitView: false, hideMarkers: true});
                  const points = state.routeMap.points;
                  const toLngLat = (point) => [Number(point.lng), Number(point.lat)];
                  const normalizePath = (path) => (path || []).map((item) => {
                    const lng = typeof item.getLng === 'function' ? item.getLng() : (item.lng !== undefined ? item.lng : item[0]);
                    const lat = typeof item.getLat === 'function' ? item.getLat() : (item.lat !== undefined ? item.lat : item[1]);
                    return [Number(lng.toFixed(6)), Number(lat.toFixed(6))];
                  });
                  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
                  const searchOnce = (start, end) => new Promise((resolve) => {
                    walking.search(toLngLat(start), toLngLat(end), (status, result) => resolve({status, result}));
                  });
                  const searchSegment = async (start, end) => {
                    let last = null;
                    for (let attempt = 1; attempt <= 3; attempt += 1) {
                      last = await searchOnce(start, end);
                      const {status, result} = last;
                      if (status === 'complete' && result && result.routes && result.routes[0]) {
                        const route = result.routes[0];
                        const steps = route.steps || [];
                        const path = [];
                        steps.forEach((step) => normalizePath(step.path).forEach((item) => path.push(item)));
                        return {
                          from: start.name,
                          to: end.name,
                          ok: true,
                          attempt,
                          distance: route.distance,
                          stepCount: steps.length,
                          pathCount: path.length,
                          sample: path.filter((_, index) => index === 0 || index === path.length - 1 || index % Math.max(1, Math.floor(path.length / 10)) === 0).slice(0, 16),
                          path
                        };
                      }
                      await sleep(900);
                    }
                    return {from: start.name, to: end.name, ok: false, status: last && last.status, info: last && last.result && last.result.info};
                  };
                  const segments = [];
                  for (let index = 0; index < points.length - 1; index += 1) {
                    segments.push(await searchSegment(points[index], points[index + 1]));
                  }
                  return {ok: true, segments};
                })()""",
                await_promise=True,
            )
        logs = []
        for event in cdp.events:
            method = event.get("method", "")
            params = event.get("params", {})
            if method in {"Runtime.consoleAPICalled", "Log.entryAdded", "Network.loadingFailed"}:
                logs.append({"method": method, "params": params})
        screenshot_path = CACHE / "edge-standalone-map-screenshot.png"
        safe_route_id = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in route_id)
        full_screenshot_path = CACHE / "edge-standalone-map-{0}-full.png".format(safe_route_id)
        screenshot_error = ""
        screenshots = {}
        try:
            screenshots["full"] = capture_screenshot(cdp, full_screenshot_path)
            if screenshot_path != full_screenshot_path:
                screenshot_path.write_bytes(full_screenshot_path.read_bytes())
            for view in ROUTE_FOCUS_VIEWS.get(route_id, ROUTE_FOCUS_VIEWS["route_history"]):
                apply_map_view(cdp, view)
                time.sleep(float(os.environ.get("EDGE_MAP_ZOOM_WAIT_SECONDS", "2.5")))
                view_name = view["name"]
                screenshots[view_name] = capture_screenshot(
                    cdp,
                    CACHE / "edge-standalone-map-{0}-{1}.png".format(safe_route_id, view_name),
                )
        except Exception as exc:
            screenshot_error = str(exc)
        output = {
            "edge": str(edge),
            "edge_version": version.get("Browser"),
            "screenshot": str(screenshot_path) if not screenshot_error else "",
            "screenshots": screenshots,
            "screenshot_error": screenshot_error,
            "state": state,
            "walking_probe": walking_probe,
            "logs": logs[-80:],
        }
        output_path = CACHE / "edge-standalone-map-state.json"
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
