# -*- coding: utf-8 -*-
import argparse
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "交付源代码"
MAX_DELIVERY_BYTES = 1024 * 1024 * 1024
EXCLUDED_ROOT_DIRS = {
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
    "交付源代码",
}
EXCLUDED_DIR_NAMES = {"__pycache__", ".pytest_cache"}
EXCLUDED_FILE_NAMES = {".env"}
EXCLUDED_FILE_SUFFIXES = {".pyc", ".pyo", ".log"}
ENV_TEMPLATE = """# 灵山胜境 AI 数字人导游系统配置模板
# 源码运行时复制或直接修改本文件；EXE 运行时放在 LingshanDigitalGuide.exe 同目录的 backend\\.env。

DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat

AMAP_JS_KEY=
AMAP_JS_SECURITY_CODE=
AMAP_WEB_SERVICE_KEY=

PADDLEOCR_API_TOKEN=

MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=
MYSQL_DATABASE=aidigitalhuman
AUTH_DEMO_FALLBACK=1

OPEN_SOURCE_TTS_PROVIDER=edge
REALTIME_TTS_PROVIDER=edge
GSV_TTS_LITE_API_URL=http://127.0.0.1:9880
GPT_SOVITS_API_URL=http://127.0.0.1:9880
GPT_SOVITS_TEXT_LANG=zh
GPT_SOVITS_PROMPT_LANG=zh
GPT_SOVITS_TIMEOUT_SECONDS=120
GSV_TTS_LITE_DEVICE=cpu

REALTIME_PYTHON=
GSV_TTS_LITE_PYTHON=
GPT_SOVITS_PYTHON=
SENSEVOICE_MODEL_DIR=
"""


def directory_size(path):
    total = 0
    for item in Path(path).rglob("*"):
        if item.is_file():
            total += item.stat().st_size
    return total


def _safe_remove_output(output, root):
    output = Path(output).resolve()
    root = Path(root).resolve()
    if output.name != "交付源代码":
        raise RuntimeError("输出目录必须命名为交付源代码：{0}".format(output))
    if output == root or root not in output.parents:
        raise RuntimeError("拒绝清理非项目子目录：{0}".format(output))
    if output.exists():
        shutil.rmtree(str(output))


def _should_skip_dir(path, root, output):
    path = Path(path)
    if path.resolve() == Path(output).resolve():
        return True
    if path.parent.resolve() == Path(root).resolve() and path.name in EXCLUDED_ROOT_DIRS:
        return True
    return path.name in EXCLUDED_DIR_NAMES


def _should_skip_file(path):
    path = Path(path)
    if path.name in EXCLUDED_FILE_NAMES:
        return True
    return path.suffix.lower() in EXCLUDED_FILE_SUFFIXES


def _copy_tree_filtered(source, target, root, output):
    source = Path(source)
    target = Path(target)
    if _should_skip_dir(source, root, output):
        return
    target.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        destination = target / item.name
        if item.is_dir():
            _copy_tree_filtered(item, destination, root, output)
        elif item.is_file() and not _should_skip_file(item):
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(item), str(destination))


def _write_env_template(output):
    backend_dir = Path(output) / "backend"
    backend_dir.mkdir(parents=True, exist_ok=True)
    env_path = backend_dir / ".env"
    example_path = backend_dir / ".env.example"
    for path in [env_path, example_path]:
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(ENV_TEMPLATE)


def prepare_delivery_source(root=ROOT, output=DEFAULT_OUTPUT):
    root = Path(root)
    output = Path(output)
    _safe_remove_output(output, root)
    output.mkdir(parents=True, exist_ok=True)
    for item in root.iterdir():
        destination = output / item.name
        if item.is_dir():
            _copy_tree_filtered(item, destination, root, output)
        elif item.is_file() and not _should_skip_file(item):
            shutil.copy2(str(item), str(destination))
    _write_env_template(output)
    size = directory_size(output)
    if size > MAX_DELIVERY_BYTES:
        raise RuntimeError("交付源代码超过 1GB：{0:.2f} MB".format(size / 1024 / 1024))
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description="生成不含模型和敏感 Key 的交付源代码目录。")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="输出目录，默认 D:\\AIhumannew\\交付源代码")
    args = parser.parse_args(argv)
    output = prepare_delivery_source(ROOT, Path(args.output))
    print("交付源代码：{0}".format(output))
    print("Size: {0:.2f} MB".format(directory_size(output) / 1024 / 1024))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
