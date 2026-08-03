# -*- coding: utf-8 -*-
import os

from map_service import SCENIC_MAP_POINTS
from runtime_paths import asset_path

try:
    from PIL import Image
except Exception:  # pragma: no cover - Pillow is optional outside the demo package.
    Image = None


ROOT_DIR = asset_path()
PANORAMA_ASSET_ROOT = asset_path("frontend", "panorama", "assets")
DEFAULT_EXTERNAL_URL = "https://street.456ss.com/jiejing/c-73.html"
OVERVIEW_DIR = os.path.join(PANORAMA_ASSET_ROOT, "overview")
OVERVIEW_OPTIMIZED_DIR = os.path.join(OVERVIEW_DIR, "optimized")
OVERVIEW_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


PANORAMA_CONFIG = {
    "LS-001": {
        "cover": "/panorama/assets/LS-001/cover.svg",
        "panorama": "/panorama/assets/LS-001/panorama.svg",
        "hotspots": [{"label": "前往五明桥", "target_scenic_id": "LS-002"}],
    },
    "LS-002": {
        "cover": "/panorama/assets/LS-002/cover.svg",
        "panorama": "/panorama/assets/LS-002/panorama.svg",
        "hotspots": [
            {"label": "返回灵山大照壁", "target_scenic_id": "LS-001"},
            {"label": "前往佛足坛", "target_scenic_id": "LS-003"},
        ],
    },
    "LS-006": {
        "cover": "/panorama/assets/LS-006/cover.svg",
        "panorama": "/panorama/assets/LS-006/panorama.svg",
        "hotspots": [{"label": "前往天下第一掌", "target_scenic_id": "LS-009"}],
    },
    "LS-011": {
        "cover": "/panorama/assets/LS-011/cover.svg",
        "panorama": "/panorama/assets/LS-011/panorama.svg",
        "hotspots": [{"label": "前往灵山梵宫", "target_scenic_id": "LS-012"}],
    },
    "LS-012": {
        "cover": "/panorama/assets/LS-012/cover.svg",
        "panorama": "/panorama/assets/LS-012/panorama.svg",
        "hotspots": [{"label": "前往五印坛城", "target_scenic_id": "LS-014"}],
    },
}


def _asset_exists(url):
    if not url or not url.startswith("/panorama/assets/"):
        return False
    relative = url.lstrip("/").replace("/", os.sep)
    return os.path.exists(asset_path("frontend", relative))


def _asset_url(relative_path):
    return "/panorama/assets/" + relative_path.replace(os.sep, "/")


def _overview_asset_url(path):
    return _asset_url(os.path.relpath(path, PANORAMA_ASSET_ROOT))


def _image_size(path):
    if Image is None or not os.path.exists(path):
        return 0, 0
    try:
        with Image.open(path) as image:
            return int(image.width), int(image.height)
    except Exception:
        return 0, 0


def _optimized_overview_path(source_path):
    name, _ = os.path.splitext(os.path.basename(source_path))
    optimized = os.path.join(OVERVIEW_OPTIMIZED_DIR, "{0}-web.jpg".format(name))
    return optimized if os.path.exists(optimized) else source_path


def _overview_files():
    if not os.path.isdir(OVERVIEW_DIR):
        return []
    files = []
    for filename in sorted(os.listdir(OVERVIEW_DIR)):
        path = os.path.join(OVERVIEW_DIR, filename)
        if not os.path.isfile(path):
            continue
        name, ext = os.path.splitext(filename)
        if ext.lower() not in OVERVIEW_EXTENSIONS:
            continue
        optimized_path = _optimized_overview_path(path)
        width, height = _image_size(optimized_path)
        files.append({
            "id": name,
            "name": name,
            "url": _overview_asset_url(optimized_path),
            "source_url": _overview_asset_url(path),
            "size_bytes": os.path.getsize(optimized_path),
            "source_size_bytes": os.path.getsize(path),
            "width": width,
            "height": height,
        })
    return files


def _scenic_lookup():
    return {item["id"]: item for item in SCENIC_MAP_POINTS if item.get("id", "").startswith("LS-") and item["id"][:3] == "LS-"}


def _normalize_hotspots(hotspots):
    result = []
    for hotspot in hotspots or []:
        target = str(hotspot.get("target_scenic_id") or "").strip()
        if not target:
            continue
        result.append({
            "label": hotspot.get("label") or "前往下一处实景",
            "target_scenic_id": target,
            "yaw": float(hotspot.get("yaw", 0)),
            "pitch": float(hotspot.get("pitch", 0)),
        })
    return result


def panorama_detail(scenic_id):
    scenic_id = str(scenic_id or "").strip()
    scenic = _scenic_lookup().get(scenic_id)
    config = PANORAMA_CONFIG.get(scenic_id, {})
    cover_url = config.get("cover", "")
    panorama_url = config.get("panorama", "")
    has_panorama = _asset_exists(panorama_url)
    has_cover = _asset_exists(cover_url)
    name = scenic.get("name") if scenic else scenic_id
    return {
        "scenic_id": scenic_id,
        "name": name or "未知景点",
        "available": bool(has_panorama),
        "cover_url": cover_url if has_cover else "",
        "panorama_url": panorama_url if has_panorama else "",
        "external_url": config.get("external_url") or DEFAULT_EXTERNAL_URL,
        "hotspots": _normalize_hotspots(config.get("hotspots")),
        "message": "" if has_panorama else "暂无实景素材，可先打开无锡街景参考。",
    }


def panorama_overview():
    panoramas = _overview_files()
    first = panoramas[0] if panoramas else {}
    return {
        "scenic_id": "overview",
        "name": "灵山胜境全景地图",
        "available": bool(panoramas),
        "cover_url": first.get("url", ""),
        "panorama_url": first.get("url", ""),
        "external_url": DEFAULT_EXTERNAL_URL,
        "hotspots": [],
        "panoramas": panoramas,
        "message": "" if panoramas else "暂无景区全貌全景素材。",
    }


def list_panorama_scenics():
    result = []
    for point in SCENIC_MAP_POINTS:
        scenic_id = point.get("id", "")
        if not scenic_id.startswith("LS-") or len(scenic_id) != 6:
            continue
        detail = panorama_detail(scenic_id)
        result.append({
            "scenic_id": detail["scenic_id"],
            "name": detail["name"],
            "available": detail["available"],
            "cover_url": detail["cover_url"],
            "panorama_url": detail["panorama_url"],
            "external_url": detail["external_url"],
        })
    return result
