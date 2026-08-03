# -*- coding: utf-8 -*-
from pathlib import Path
import unittest


ROOT_DIR = Path(__file__).resolve().parents[1]
INSTALL_SCRIPT = ROOT_DIR / "scripts" / "install_gsv_tts_lite_env.ps1"


class GsvInstallScriptContractTests(unittest.TestCase):
    def test_cuda_install_prefers_local_wheelhouse_before_network_index(self):
        text = INSTALL_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("$Wheelhouse", text)
        self.assertIn("Find-LocalTorchWheel", text)
        self.assertIn("torch-*+cu126-cp*-win_amd64.whl", text)
        self.assertIn("torchaudio-*+cu126-cp*-win_amd64.whl", text)
        self.assertIn("$torchWheel.FullName", text)
        self.assertIn("$audioWheel.FullName", text)
        self.assertIn("download.pytorch.org/whl/cu126", text)


if __name__ == "__main__":
    unittest.main()
