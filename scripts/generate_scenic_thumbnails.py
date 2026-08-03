# -*- coding: utf-8 -*-
"""从本地灵山全貌实拍中裁切核心景点缩略图。"""

from pathlib import Path

from PIL import Image, ImageEnhance


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "frontend" / "panorama" / "assets" / "overview" / "optimized"
OUTPUT_DIR = ROOT / "frontend" / "assets" / "scenics"
OUTPUT_SIZE = (760, 460)


SOURCES = {
    "overview1": SOURCE_DIR / "1_景区全貌-web.jpg",
    "overview2": SOURCE_DIR / "2_景区全貌-web.jpg",
    "overview3": SOURCE_DIR / "3_景区全貌-web.jpg",
}


# 坐标为 8192x4096 全景图上的中心点和裁切尺寸，优先选择画面中可辨认的真实景区区域。
CROPS = {
    "LS-001": ("overview3", 4140, 2800, 1540, 930),  # 灵山大照壁/入口轴线
    "LS-002": ("overview3", 1600, 2910, 1580, 940),  # 五明桥与香水海周边
    "LS-003": ("overview2", 1130, 3220, 1500, 910),  # 佛足坛/入口礼佛区
    "LS-004": ("overview3", 4120, 2800, 1300, 900),  # 五智门入口门楼
    "LS-005": ("overview2", 4100, 2860, 1450, 900),  # 菩提大道与中轴线
    "LS-006": ("overview1", 6130, 2460, 1500, 900),  # 九龙灌浴广场
    "LS-007": ("overview2", 4140, 3010, 1480, 900),  # 降魔浮雕/大佛前区
    "LS-008": ("overview3", 4320, 2740, 1280, 860),  # 阿育王柱与中轴广场
    "LS-009": ("overview2", 1290, 3230, 1520, 900),  # 天下第一掌区域
    "LS-010": ("overview2", 6990, 3230, 1500, 900),  # 百子戏弥勒区域
    "LS-011": ("overview2", 5010, 2140, 1640, 980),  # 灵山大佛
    "LS-012": ("overview1", 690, 2620, 1540, 940),   # 灵山梵宫
    "LS-013": ("overview1", 4080, 2750, 1500, 900),  # 五印坛城
    "LS-014": ("overview1", 2450, 2780, 1260, 850),  # 曼飞龙塔
    "LS-015": ("overview2", 6370, 3040, 1520, 900),  # 无尽意斋周边
    "LS-016": ("overview2", 4200, 2640, 1500, 900),  # 祥符禅寺/大佛前院
}


def clamp_crop_box(width, height, center_x, center_y, crop_w, crop_h):
    left = max(0, min(width - crop_w, int(center_x - crop_w / 2)))
    top = max(0, min(height - crop_h, int(center_y - crop_h / 2)))
    return left, top, left + crop_w, top + crop_h


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    opened = {name: Image.open(path).convert("RGB") for name, path in SOURCES.items()}
    try:
        for scenic_id, (source_name, x, y, crop_w, crop_h) in CROPS.items():
            image = opened[source_name]
            box = clamp_crop_box(image.width, image.height, x, y, crop_w, crop_h)
            thumb = image.crop(box).resize(OUTPUT_SIZE, Image.LANCZOS)
            thumb = ImageEnhance.Contrast(thumb).enhance(1.04)
            thumb = ImageEnhance.Sharpness(thumb).enhance(1.08)
            thumb.save(OUTPUT_DIR / f"{scenic_id}.jpg", quality=86, optimize=True)
    finally:
        for image in opened.values():
            image.close()


if __name__ == "__main__":
    main()
