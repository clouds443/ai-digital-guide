# -*- coding: utf-8 -*-
import os
import sys
import unittest


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import main  # noqa: E402


class PanoramaContractTests(unittest.TestCase):
    def setUp(self):
        self.client = main.app.test_client()

    def test_panorama_scenics_returns_core_spot_statuses(self):
        response = self.client.get("/api/panorama/scenics")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(16, len(data["scenics"]))
        first = data["scenics"][0]
        self.assertIn("scenic_id", first)
        self.assertIn("name", first)
        self.assertIn("available", first)
        self.assertIn("cover_url", first)
        self.assertIn("panorama_url", first)
        self.assertIn("external_url", first)

    def test_panorama_detail_returns_wuming_bridge_config_and_hotspots(self):
        response = self.client.get("/api/panorama/scenic/LS-002")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual("LS-002", data["scenic_id"])
        self.assertEqual("五明桥", data["name"])
        self.assertIn("available", data)
        self.assertIn("hotspots", data)
        self.assertTrue(data["external_url"].startswith("https://street.456ss.com/"))
        self.assertTrue(any(item["target_scenic_id"] for item in data["hotspots"]))

    def test_panorama_unknown_scenic_returns_unavailable_payload(self):
        response = self.client.get("/api/panorama/scenic/UNKNOWN")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertFalse(data["available"])
        self.assertEqual("UNKNOWN", data["scenic_id"])
        self.assertIn("暂无实景素材", data["message"])
        self.assertTrue(data["external_url"].startswith("https://street.456ss.com/"))

    def test_panorama_overview_returns_uploaded_scenic_overview_images(self):
        response = self.client.get("/api/panorama/overview")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual("overview", data["scenic_id"])
        self.assertEqual("灵山胜境全景地图", data["name"])
        self.assertTrue(data["available"])
        self.assertGreaterEqual(len(data["panoramas"]), 3)
        self.assertTrue(data["panorama_url"].startswith("/panorama/assets/overview/"))
        self.assertTrue(any("景区全貌" in item["name"] for item in data["panoramas"]))
        self.assertTrue(all(item["url"].startswith("/panorama/assets/overview/") for item in data["panoramas"]))

    def test_panorama_overview_uses_web_optimized_images_for_viewer(self):
        response = self.client.get("/api/panorama/overview")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("/optimized/", data["panorama_url"])
        for item in data["panoramas"]:
            with self.subTest(item=item["name"]):
                self.assertIn("/optimized/", item["url"])
                self.assertIn("source_url", item)
                self.assertLessEqual(item["width"], 8192)
                self.assertLessEqual(item["height"], 4096)
                self.assertLess(item["size_bytes"], item["source_size_bytes"])


if __name__ == "__main__":
    unittest.main()
