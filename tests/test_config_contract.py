# -*- coding: utf-8 -*-
import os
import sys
import unittest


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from knowledge_base import CONFIG_FILE, get_digital_human_config, read_json_file, update_digital_human_config, write_json_file  # noqa: E402


class ConfigContractTests(unittest.TestCase):
    def test_default_config_exposes_multi_avatar_options_and_emotion_defaults(self):
        original = read_json_file(CONFIG_FILE, {})
        try:
            write_json_file(CONFIG_FILE, {})
            config = get_digital_human_config()

            self.assertIn("model_options", config)
            self.assertGreaterEqual(len(config["model_options"]), 3)
            self.assertIn("emotion_enabled", config)
            self.assertEqual(config["emotion_enabled"], "true")
            self.assertIn("avatar_preset_id", config)
            self.assertIn("avatar_presets", config)
            self.assertGreaterEqual(len(config["avatar_presets"]), 2)
            labels = [preset["label"] for preset in config["avatar_presets"]]
            self.assertIn("配置一：温婉新中式导游", labels)
            self.assertIn("配置二：亲和活力讲解员", labels)
            required = {
                "id",
                "label",
                "summary",
                "name",
                "model",
                "appearance",
                "costume",
                "emotion_enabled",
                "style",
                "opening",
                "voice_provider",
                "voice_preset",
                "voice_description",
                "voice_clone_id",
                "edge_voice",
                "voice_rate",
                "voice_pitch",
                "voice_volume",
            }
            for preset in config["avatar_presets"]:
                self.assertTrue(required.issubset(set(preset.keys())))
        finally:
            write_json_file(CONFIG_FILE, original)

    def test_update_config_accepts_appearance_voice_and_emotion_fields(self):
        original = get_digital_human_config()
        try:
            config = update_digital_human_config(
                {
                    "appearance": "温婉新中式导游",
                    "costume": "青绿色新中式导游服",
                    "emotion_enabled": "false",
                    "voice_provider": "edge",
                }
            )

            self.assertEqual(config["appearance"], "温婉新中式导游")
            self.assertEqual(config["costume"], "青绿色新中式导游服")
            self.assertEqual(config["emotion_enabled"], "false")
            self.assertEqual(config["voice_provider"], "edge")
        finally:
            update_digital_human_config(original)

    def test_update_config_accepts_avatar_preset_id_and_keeps_compatible_fields(self):
        original = get_digital_human_config()
        try:
            config = update_digital_human_config(
                {
                    "avatar_preset_id": "preset_2",
                    "name": "灵小境",
                    "appearance": "亲和活力讲解员",
                    "voice_provider": "edge",
                    "edge_voice": "zh-CN-XiaoyiNeural",
                }
            )

            self.assertEqual(config["avatar_preset_id"], "preset_2")
            self.assertEqual(config["appearance"], "亲和活力讲解员")
            self.assertEqual(config["voice_provider"], "edge")
            self.assertEqual(config["edge_voice"], "zh-CN-XiaoyiNeural")
            self.assertIn("avatar_presets", config)
            self.assertGreaterEqual(len(config["avatar_presets"]), 2)
        finally:
            update_digital_human_config(original)

    def test_update_config_persists_modified_avatar_preset_catalog(self):
        original = get_digital_human_config()
        try:
            presets = [dict(preset) for preset in original["avatar_presets"]]
            for preset in presets:
                if preset["id"] == "preset_2":
                    preset.update(
                        {
                            "label": "配置二：比赛讲解员",
                            "summary": "语速稳、信息密度高，适合比赛演示。",
                            "appearance": "比赛讲解数字人",
                            "costume": "深蓝礼仪导览服",
                            "voice_provider": "edge",
                            "edge_voice": "zh-CN-YunxiNeural",
                        }
                    )

            config = update_digital_human_config(
                {
                    "avatar_preset_id": "preset_2",
                    "avatar_presets": presets,
                    "name": "灵小境",
                    "model": "Hiyori",
                    "appearance": "比赛讲解数字人",
                    "costume": "深蓝礼仪导览服",
                    "style": "稳重、清晰、适合比赛讲解",
                    "voice_provider": "edge",
                    "edge_voice": "zh-CN-YunxiNeural",
                }
            )
            refreshed = get_digital_human_config()
            persisted = next(preset for preset in refreshed["avatar_presets"] if preset["id"] == "preset_2")

            self.assertEqual(config["avatar_preset_id"], "preset_2")
            self.assertEqual(persisted["label"], "配置二：比赛讲解员")
            self.assertEqual(persisted["summary"], "语速稳、信息密度高，适合比赛演示。")
            self.assertEqual(persisted["appearance"], "比赛讲解数字人")
            self.assertEqual(persisted["costume"], "深蓝礼仪导览服")
            self.assertEqual(persisted["edge_voice"], "zh-CN-YunxiNeural")
        finally:
            update_digital_human_config(original)

    def test_update_config_persists_new_custom_avatar_preset(self):
        original = get_digital_human_config()
        try:
            custom = dict(original["avatar_presets"][0])
            custom.update(
                {
                    "id": "custom_competition",
                    "label": "配置三：自定义配置",
                    "summary": "从当前配置复制，用于新增数字人方案。",
                    "appearance": "自定义比赛形象",
                    "costume": "魔法斗篷休闲套装",
                    "voice_provider": "gpt_sovits",
                    "voice_preset": "family_friendly",
                }
            )
            presets = [dict(preset) for preset in original["avatar_presets"]] + [custom]

            config = update_digital_human_config(
                {
                    "avatar_preset_id": "custom_competition",
                    "avatar_presets": presets,
                    "name": custom["name"],
                    "model": custom["model"],
                    "appearance": custom["appearance"],
                    "costume": custom["costume"],
                    "style": custom["style"],
                    "voice_provider": custom["voice_provider"],
                    "voice_preset": custom["voice_preset"],
                }
            )

            self.assertEqual(config["avatar_preset_id"], "custom_competition")
            ids = [preset["id"] for preset in config["avatar_presets"]]
            self.assertIn("custom_competition", ids)
            persisted = next(preset for preset in config["avatar_presets"] if preset["id"] == "custom_competition")
            self.assertEqual(persisted["label"], "配置三：自定义配置")
            self.assertEqual(persisted["costume"], "魔法斗篷休闲套装")
        finally:
            update_digital_human_config(original)

    def test_legacy_custom_avatar_id_without_catalog_is_preserved_for_editing(self):
        original = read_json_file(CONFIG_FILE, {})
        try:
            write_json_file(
                CONFIG_FILE,
                {
                    "avatar_preset_id": "custom_legacy_saved",
                    "name": "灵小境",
                    "model": "Mao",
                    "appearance": "保存后的比赛形象",
                    "costume": "银白新中式演示服",
                    "emotion_enabled": "true",
                    "style": "稳重、清晰、适合比赛答辩",
                    "opening": "欢迎来到灵山胜境。",
                    "voice_provider": "edge",
                    "voice_preset": "family_friendly",
                    "voice_description": "比赛讲解音色",
                    "voice_clone_id": "",
                    "edge_voice": "zh-CN-XiaoyiNeural",
                    "voice_rate": "+6%",
                    "voice_pitch": "+2Hz",
                    "voice_volume": "+0%",
                },
            )

            config = get_digital_human_config()
            preset = next((item for item in config["avatar_presets"] if item["id"] == "custom_legacy_saved"), None)

            self.assertEqual(config["avatar_preset_id"], "custom_legacy_saved")
            self.assertIsNotNone(preset)
            self.assertEqual(preset["appearance"], "保存后的比赛形象")
            self.assertEqual(preset["costume"], "银白新中式演示服")
            self.assertEqual(preset["edge_voice"], "zh-CN-XiaoyiNeural")
            self.assertNotIn("model_options", preset)
            self.assertNotIn("voice", preset)
        finally:
            write_json_file(CONFIG_FILE, original)

    def test_update_config_without_avatar_presets_keeps_selected_custom_preset(self):
        original = read_json_file(CONFIG_FILE, {})
        try:
            write_json_file(
                CONFIG_FILE,
                {
                    "avatar_preset_id": "custom_unsent_catalog",
                    "name": "灵小境",
                    "model": "Hiyori",
                    "appearance": "待保存自定义形象",
                    "costume": "浅蓝白色轻运动导览服",
                    "emotion_enabled": "true",
                    "style": "亲切、轻快、短句清晰",
                    "opening": "您好，我是灵小境。",
                    "voice_provider": "edge",
                    "voice_preset": "family_friendly",
                    "voice_description": "亲和女声",
                    "voice_clone_id": "",
                    "edge_voice": "zh-CN-XiaoyiNeural",
                    "voice_rate": "+6%",
                    "voice_pitch": "+2Hz",
                    "voice_volume": "+0%",
                },
            )

            config = update_digital_human_config(
                {
                    "avatar_preset_id": "custom_unsent_catalog",
                    "name": "灵小境",
                    "model": "Mao",
                    "appearance": "保存后的自定义形象",
                    "costume": "青白渐变导览服",
                    "style": "稳重、清晰、适合比赛答辩",
                    "voice_provider": "edge",
                    "edge_voice": "zh-CN-XiaoxiaoNeural",
                }
            )
            refreshed = get_digital_human_config()
            raw_saved = read_json_file(CONFIG_FILE, {})
            preset = next((item for item in refreshed["avatar_presets"] if item["id"] == "custom_unsent_catalog"), None)
            raw_preset_ids = [item.get("id") for item in raw_saved.get("avatar_presets", [])]

            self.assertEqual(config["avatar_preset_id"], "custom_unsent_catalog")
            self.assertIn("custom_unsent_catalog", raw_preset_ids)
            self.assertIsNotNone(preset)
            self.assertEqual(config["model"], "Mao")
            self.assertEqual(config["appearance"], "保存后的自定义形象")
            self.assertEqual(preset["model"], "Mao")
            self.assertEqual(preset["appearance"], "保存后的自定义形象")
            self.assertEqual(preset["costume"], "青白渐变导览服")
            self.assertEqual(preset["edge_voice"], "zh-CN-XiaoxiaoNeural")
        finally:
            write_json_file(CONFIG_FILE, original)

    def test_update_config_persists_deleted_avatar_preset_from_catalog(self):
        original = read_json_file(CONFIG_FILE, {})
        try:
            initial = get_digital_human_config()
            kept_presets = [dict(preset) for preset in initial["avatar_presets"] if preset["id"] != "preset_2"]
            selected = dict(kept_presets[0])

            config = update_digital_human_config(
                {
                    "avatar_preset_id": selected["id"],
                    "avatar_presets": kept_presets,
                    "name": selected["name"],
                    "model": selected["model"],
                    "appearance": selected["appearance"],
                    "costume": selected["costume"],
                    "style": selected["style"],
                    "voice_provider": selected["voice_provider"],
                    "voice_preset": selected["voice_preset"],
                    "edge_voice": selected["edge_voice"],
                }
            )
            refreshed = get_digital_human_config()
            raw_saved = read_json_file(CONFIG_FILE, {})
            refreshed_ids = [preset["id"] for preset in refreshed["avatar_presets"]]
            raw_ids = [preset.get("id") for preset in raw_saved.get("avatar_presets", [])]

            self.assertEqual(config["avatar_preset_id"], selected["id"])
            self.assertNotIn("preset_2", refreshed_ids)
            self.assertNotIn("preset_2", raw_ids)
        finally:
            write_json_file(CONFIG_FILE, original)


if __name__ == "__main__":
    unittest.main()
