# -*- coding: utf-8 -*-
import importlib.util
import os
import tempfile
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
SCRIPT_PATH = ROOT_DIR / "scripts" / "build_portable_exe.py"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def load_build_module():
    spec = importlib.util.spec_from_file_location("build_portable_exe", str(SCRIPT_PATH))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PackagingContractTests(unittest.TestCase):
    def test_packaging_manifest_excludes_heavy_local_model_and_env_directories(self):
        module = load_build_module()

        excluded = {Path(item).as_posix() for item in module.excluded_roots()}
        data_entries = module.collect_data_entries(ROOT_DIR)
        data_sources = {Path(source).relative_to(ROOT_DIR).parts[0] for source, _target in data_entries}

        for name in [".venvs", "models", "third_party", "wheelhouse", ".git", ".cache"]:
            self.assertIn(name, excluded)
            self.assertNotIn(name, data_sources)

    def test_packaging_manifest_includes_lightweight_runtime_assets(self):
        module = load_build_module()

        data_entries = module.collect_data_entries(ROOT_DIR)
        targets = {target.replace("\\", "/") for _source, target in data_entries}

        self.assertIn("frontend", targets)
        self.assertIn("backend", targets)
        self.assertIn("knowledge", targets)
        self.assertIn("20260323113204906", targets)
        self.assertIn("bin", targets)
        self.assertIn("scripts", targets)
        self.assertIn("tests/fixtures", targets)
        self.assertNotIn("uploads/voice_clones", targets)

    def test_packaging_staging_excludes_env_models_and_uploaded_audio(self):
        module = load_build_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            staging = root / "build" / "packaging_staging"
            for relative in [
                "backend",
                "frontend",
                "knowledge",
                "bin",
                "scripts",
                "tests/fixtures",
                "20260323113204906",
                "uploads/voice_clones",
                "models",
                ".venvs",
                "third_party",
                "wheelhouse",
            ]:
                (root / relative).mkdir(parents=True, exist_ok=True)
            (root / "backend" / "packaged_entry.py").write_text("print('entry')\n", encoding="utf-8")
            (root / "backend" / "main.py").write_text("print('main')\n", encoding="utf-8")
            (root / "backend" / ".env").write_text("DEEPSEEK_API_KEY=sk-real-secret\n", encoding="utf-8")
            (root / "uploads" / "voice_clones" / "sample.wav").write_bytes(b"voice")
            (root / "models" / "model.pt").write_bytes(b"model")

            result = module.create_packaging_staging(root, staging)
            staged_files = {path.relative_to(result).as_posix() for path in result.rglob("*") if path.is_file()}

            self.assertIn("backend/main.py", staged_files)
            self.assertIn("frontend", {path.relative_to(result).as_posix() for path in result.iterdir()})
            self.assertNotIn("backend/.env", staged_files)
            self.assertNotIn("uploads/voice_clones/sample.wav", staged_files)
            self.assertFalse((result / "models").exists())
            self.assertFalse((result / ".venvs").exists())

    def test_packaged_entry_exists_and_initializes_runtime_roots(self):
        entrypoint = BACKEND_DIR / "packaged_entry.py"

        self.assertTrue(entrypoint.exists())
        text = entrypoint.read_text(encoding="utf-8")
        self.assertIn("AIDH_ASSET_ROOT", text)
        self.assertIn("AIDH_RUNTIME_ROOT", text)
        self.assertIn("ensure_runtime_dirs", text)
        self.assertIn("app.run", text)

    def test_runtime_dirs_create_external_backend_env_parent_for_packaged_exe(self):
        text = (BACKEND_DIR / "runtime_paths.py").read_text(encoding="utf-8")

        self.assertIn('"backend"', text)

    def test_backend_uses_runtime_audio_route_for_packaged_tts_outputs(self):
        text = (BACKEND_DIR / "main.py").read_text(encoding="utf-8")

        self.assertIn('/audio/tts/<path:filename>', text)
        self.assertIn("runtime_path", text)
        self.assertIn("send_from_directory(runtime_path", text)

    def test_runtime_paths_separate_readonly_assets_from_writable_data_root(self):
        with mock.patch.dict(
            os.environ,
            {
                "AIDH_ASSET_ROOT": r"C:\packed\assets",
                "AIDH_RUNTIME_ROOT": r"C:\Users\demo\LingshanRuntime",
            },
            clear=False,
        ):
            import runtime_paths

            self.assertEqual(Path(runtime_paths.asset_root()), Path(r"C:\packed\assets"))
            self.assertEqual(Path(runtime_paths.runtime_root()), Path(r"C:\Users\demo\LingshanRuntime"))
            self.assertEqual(Path(runtime_paths.asset_path("frontend")), Path(r"C:\packed\assets\frontend"))
            self.assertEqual(Path(runtime_paths.runtime_path("knowledge")), Path(r"C:\Users\demo\LingshanRuntime\knowledge"))

    def test_writable_services_use_runtime_paths_in_packaged_mode(self):
        expectations = {
            "knowledge_base.py": ["runtime_path", "asset_path"],
            "tts_service.py": ["TTS_AUDIO_DIR = runtime_path", "asset_path"],
            "voice_clone_service.py": ["VOICE_CLONE_DIR = runtime_path", "resolve_packaged_clone_path"],
            "evaluation_service.py": ["CACHE_DIR = runtime_path", "EVALUATOR_PATH = asset_path"],
        }

        for filename, needles in expectations.items():
            with self.subTest(filename=filename):
                text = (BACKEND_DIR / filename).read_text(encoding="utf-8")
                for needle in needles:
                    self.assertIn(needle, text)

    def test_pyinstaller_args_use_onefile_and_do_not_bundle_heavy_trees(self):
        module = load_build_module()

        args = module.build_pyinstaller_args(ROOT_DIR)
        joined = " ".join(args)

        self.assertIn("--onefile", args)
        self.assertIn("--name", args)
        self.assertIn("LingshanDigitalGuide", args)
        for name in [".venvs", "models", "third_party", "wheelhouse", ".git", ".cache"]:
            self.assertIn("--exclude-heavy={0}".format(name), joined)

    def test_pyinstaller_build_uses_staging_entrypoint_when_provided(self):
        module = load_build_module()
        staging = ROOT_DIR / "build" / "packaging_staging"

        args = module.build_pyinstaller_args(ROOT_DIR, staging_root=staging)
        joined = " ".join(args)

        self.assertIn(str(staging / "backend" / "packaged_entry.py"), args)
        self.assertIn(str(staging / "backend"), joined)
        self.assertNotIn(str(ROOT_DIR / "backend" / ".env"), joined)


if __name__ == "__main__":
    unittest.main()
