# -*- coding: utf-8 -*-
import os
import shutil
import sys
from pathlib import Path


def _repo_root():
    return Path(__file__).resolve().parents[1]


def asset_root():
    value = os.getenv("AIDH_ASSET_ROOT", "").strip()
    if value:
        return str(Path(value))
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return str(Path(sys._MEIPASS))
    return str(_repo_root())


def runtime_root():
    value = os.getenv("AIDH_RUNTIME_ROOT", "").strip()
    if value:
        return str(Path(value))
    if getattr(sys, "frozen", False):
        return str(Path(sys.executable).resolve().parent)
    return asset_root()


def asset_path(*parts):
    return str(Path(asset_root()).joinpath(*parts))


def runtime_path(*parts):
    return str(Path(runtime_root()).joinpath(*parts))


def seed_runtime_tree(relative_path):
    source = Path(asset_path(relative_path))
    target = Path(runtime_path(relative_path))
    if source.resolve() == target.resolve() or not source.exists():
        return
    if source.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copy2(str(source), str(target))
        return
    target.mkdir(parents=True, exist_ok=True)
    for item in source.rglob("*"):
        rel = item.relative_to(source)
        destination = target / rel
        if item.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        elif not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(item), str(destination))


def ensure_runtime_dirs():
    for rel in ["backend", "knowledge", "logs", ".cache", "uploads", "uploads/voice", "uploads/voice_clones", "frontend/audio/tts"]:
        Path(runtime_path(rel)).mkdir(parents=True, exist_ok=True)
    for rel in ["knowledge", "uploads/voice_clones"]:
        seed_runtime_tree(rel)
