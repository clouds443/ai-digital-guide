# -*- coding: utf-8 -*-
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from docx import Document


ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT_DIR / "scripts" / "prepare_delivery_source.py"


def load_delivery_module():
    spec = importlib.util.spec_from_file_location("prepare_delivery_source", str(SCRIPT_PATH))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DeliveryContractTests(unittest.TestCase):
    def test_voice_clones_file_stays_a_json_list(self):
        voice_clones = json.loads((ROOT_DIR / "knowledge" / "voice_clones.json").read_text(encoding="utf-8"))

        self.assertIsInstance(voice_clones, list)
        for item in voice_clones:
            self.assertIn("id", item)
            self.assertIn("audio_path", item)

    def test_project_no_longer_contains_old_absolute_root_path(self):
        scanned_suffixes = {".py", ".js", ".html", ".json", ".bat", ".md", ".vbs"}
        old_root = "D:\\" + "AI" + "DigitalHuman"
        old_name = "AI" + "DigitalHuman"
        offenders = []
        for path in ROOT_DIR.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in scanned_suffixes:
                continue
            if any(part in {"__pycache__", ".git", ".venvs"} for part in path.parts):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if old_root in text or old_name in text:
                offenders.append(str(path.relative_to(ROOT_DIR)))

        self.assertEqual(offenders, [])

    def test_start_entrypoints_use_service_launcher_not_raw_backend_main(self):
        for filename in ["start_server.bat", "start_hidden.vbs", "start_light.bat", "start_full_services.bat"]:
            with self.subTest(filename=filename):
                text = (ROOT_DIR / filename).read_text(encoding="utf-8")
                self.assertIn("start_services.py", text)
                self.assertNotIn("backend\\main.py", text)

    def test_prepare_delivery_source_excludes_heavy_dirs_and_sanitizes_env(self):
        module = load_delivery_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            output = root / "交付源代码"
            for relative in [
                "backend",
                "frontend",
                "docs/submission",
                "scripts",
                "tests",
                "knowledge",
                "models",
                ".venvs",
                "third_party",
                "wheelhouse",
                ".git",
                ".cache",
                "build",
                "dist",
                "logs",
                "uploads",
            ]:
                (root / relative).mkdir(parents=True, exist_ok=True)
            (root / "backend" / "main.py").write_text("print('ok')\n", encoding="utf-8")
            (root / "backend" / ".env").write_text(
                "DEEPSEEK_API_KEY=sk-real-secret\n"
                "AMAP_JS_KEY=real-amap-key\n"
                "MYSQL_PASSWORD=real-password\n",
                encoding="utf-8",
            )
            (root / "models" / "model.pt").write_bytes(b"model")
            (root / "uploads" / "voice.wav").write_bytes(b"voice")
            (root / "README.md").write_text("readme\n", encoding="utf-8")

            result = module.prepare_delivery_source(root, output)
            delivered = {path.relative_to(result).as_posix() for path in result.rglob("*") if path.is_file()}
            env_text = (result / "backend" / ".env").read_text(encoding="utf-8")

            self.assertIn("backend/main.py", delivered)
            self.assertIn("README.md", delivered)
            self.assertFalse((result / "models").exists())
            self.assertFalse((result / ".venvs").exists())
            self.assertFalse((result / "third_party").exists())
            self.assertFalse((result / "uploads").exists())
            self.assertIn("DEEPSEEK_API_KEY=", env_text)
            self.assertIn("AMAP_JS_KEY=", env_text)
            self.assertIn("MYSQL_PASSWORD=", env_text)
            self.assertNotIn("sk-real-secret", env_text)
            self.assertNotIn("real-amap-key", env_text)
            self.assertNotIn("real-password", env_text)
            self.assertLess(module.directory_size(result), module.MAX_DELIVERY_BYTES)

    def test_prepare_delivery_source_script_defines_required_exclusions(self):
        module = load_delivery_module()

        excluded = set(module.EXCLUDED_ROOT_DIRS)
        for name in [".venvs", "models", "third_party", "wheelhouse", ".git", ".cache", "build", "dist", "logs", "uploads"]:
            self.assertIn(name, excluded)

    def test_prepare_delivery_source_refuses_to_delete_non_delivery_directory(self):
        module = load_delivery_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            unsafe_output = root / "backend"
            unsafe_output.mkdir(parents=True)
            (unsafe_output / "main.py").write_text("print('keep')\n", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "交付源代码"):
                module.prepare_delivery_source(root, unsafe_output)

            self.assertTrue((unsafe_output / "main.py").exists())

    def test_deployment_manual_documents_light_delivery_models_and_api_keys(self):
        markdown = (ROOT_DIR / "docs" / "submission" / "03_产品部署和使用手册.md").read_text(encoding="utf-8")
        doc = Document(str(ROOT_DIR / "docs" / "submission" / "03_产品部署和使用手册.docx"))
        docx_text = "\n".join(paragraph.text for paragraph in doc.paragraphs)
        combined = markdown + "\n" + docx_text

        for expected in [
            "交付源代码",
            "LingshanDigitalGuide.exe",
            "models\\SenseVoiceSmall",
            "models\\FunASR\\paraformer-zh-streaming",
            "models\\FunASR\\fsmn-vad",
            "models\\FunASR\\ct-punc",
            "third_party\\GPT-SoVITS\\GPT_SoVITS\\pretrained_models",
            "third_party\\GPT-SoVITS\\GPT_SoVITS\\text\\G2PWModel",
            "backend\\.env",
            "DEEPSEEK_API_KEY",
            "AMAP_JS_KEY",
            "AMAP_JS_SECURITY_CODE",
            "AMAP_WEB_SERVICE_KEY",
            "PADDLEOCR_API_TOKEN",
        ]:
            self.assertIn(expected, combined)

        self.assertNotIn("AMAP_JS_API_KEY", combined)
        self.assertNotIn("AMAP_SECURITY_JS_CODE", combined)


if __name__ == "__main__":
    unittest.main()
