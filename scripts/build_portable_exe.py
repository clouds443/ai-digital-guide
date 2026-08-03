# -*- coding: utf-8 -*-
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
ENTRYPOINT = ROOT / "backend" / "packaged_entry.py"
HOOKS_DIR = ROOT / "packaging_hooks"
APP_NAME = "LingshanDigitalGuide"
MAX_UPLOAD_BYTES = 1024 * 1024 * 1024
STAGING_ROOT = ROOT / "build" / "packaging_staging"
HEAVY_ROOTS = [
    ".venvs",
    "models",
    "third_party",
    "wheelhouse",
    ".git",
    ".cache",
    "build",
    "dist",
    "logs",
    "uploads",
]
SENSITIVE_FILE_NAMES = {".env"}
IGNORED_COPY_DIRS = {"__pycache__"}
IGNORED_COPY_SUFFIXES = {".pyc", ".pyo"}
DATA_ROOTS = [
    ("backend", "backend"),
    ("frontend", "frontend"),
    ("knowledge", "knowledge"),
    ("20260323113204906", "20260323113204906"),
    ("bin", "bin"),
    ("scripts", "scripts"),
    (os.path.join("tests", "fixtures"), os.path.join("tests", "fixtures")),
]


def excluded_roots():
    return list(HEAVY_ROOTS)


def collect_data_entries(root=ROOT):
    root = Path(root)
    entries = []
    for source, target in DATA_ROOTS:
        source_path = root / source
        if source_path.exists():
            entries.append((str(source_path), target))
    return entries


def _add_data_arg(source, target):
    return "{0}{1}{2}".format(source, os.pathsep, target)


def _copy_ignore(_directory, names):
    ignored = set()
    for name in names:
        if name in SENSITIVE_FILE_NAMES or name in IGNORED_COPY_DIRS:
            ignored.add(name)
            continue
        suffix = Path(name).suffix.lower()
        if suffix in IGNORED_COPY_SUFFIXES:
            ignored.add(name)
    return ignored


def _safe_remove_tree(path, root):
    path = Path(path).resolve()
    root = Path(root).resolve()
    if path == root or root not in path.parents:
        raise RuntimeError("拒绝删除非项目子目录：{0}".format(path))
    if path.exists():
        shutil.rmtree(str(path))


def create_packaging_staging(root=ROOT, staging_root=STAGING_ROOT):
    root = Path(root)
    staging_root = Path(staging_root)
    _safe_remove_tree(staging_root, root)
    staging_root.mkdir(parents=True, exist_ok=True)
    for source, target in DATA_ROOTS:
        source_path = root / source
        target_path = staging_root / target
        if not source_path.exists():
            continue
        if source_path.is_dir():
            shutil.copytree(str(source_path), str(target_path), ignore=_copy_ignore)
        else:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(source_path), str(target_path))
    return staging_root


def build_pyinstaller_args(root=ROOT, staging_root=None):
    root = Path(root)
    data_root = Path(staging_root) if staging_root else root
    args = [
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        APP_NAME,
        "--distpath",
        str(root / "dist"),
        "--workpath",
        str(root / "build" / "pyinstaller"),
        "--specpath",
        str(root / "build"),
        "--additional-hooks-dir",
        str(root / "packaging_hooks"),
    ]
    for source, target in collect_data_entries(data_root):
        args.extend(["--add-data", _add_data_arg(source, target)])
    for name in excluded_roots():
        # 这个标记给测试和构建日志使用，后面会在调用 PyInstaller 前过滤掉。
        args.append("--exclude-heavy={0}".format(name))
    args.extend([
        "--hidden-import",
        "pymysql",
        "--hidden-import",
        "docx",
        "--hidden-import",
        "edge_tts",
        str(data_root / "backend" / "packaged_entry.py"),
    ])
    return args


def _pyinstaller_args_for_subprocess(root=ROOT, staging_root=None):
    return [arg for arg in build_pyinstaller_args(root, staging_root=staging_root) if not arg.startswith("--exclude-heavy=")]


def file_size(path):
    path = Path(path)
    return path.stat().st_size if path.exists() else 0


def ensure_pyinstaller_available():
    if shutil.which("pyinstaller"):
        return [shutil.which("pyinstaller")]
    try:
        import PyInstaller  # noqa: F401
        return [sys.executable, "-m", "PyInstaller"]
    except Exception:
        raise RuntimeError("未安装 PyInstaller。请先运行：python -m pip install pyinstaller")


def build(root=ROOT):
    staging_root = create_packaging_staging(root, Path(root) / "build" / "packaging_staging")
    command = ensure_pyinstaller_available() + _pyinstaller_args_for_subprocess(root, staging_root=staging_root)
    env = os.environ.copy()
    env.setdefault("PYINSTALLER_CONFIG_DIR", str(Path(root) / ".cache" / "pyinstaller"))
    Path(env["PYINSTALLER_CONFIG_DIR"]).mkdir(parents=True, exist_ok=True)
    print("Running:", " ".join(command))
    subprocess.check_call(command, cwd=str(root), env=env)
    exe = Path(root) / "dist" / (APP_NAME + ".exe")
    size = file_size(exe)
    if size > MAX_UPLOAD_BYTES:
        raise RuntimeError("EXE 超过 1GB：{0:.2f} MB".format(size / 1024 / 1024))
    print("EXE:", exe)
    print("Size: {0:.2f} MB".format(size / 1024 / 1024))
    return exe


def main(argv=None):
    parser = argparse.ArgumentParser(description="构建小于 1GB 的灵山 AI 数字人轻量 EXE。")
    parser.add_argument("--print-args", action="store_true", help="只打印 PyInstaller 参数，不执行构建。")
    args = parser.parse_args(argv)
    if args.print_args:
        print("\n".join(build_pyinstaller_args(ROOT)))
        return 0
    build(ROOT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
