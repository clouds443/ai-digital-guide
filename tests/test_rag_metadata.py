# -*- coding: utf-8 -*-
import os
import re
import sys
import unittest
from unittest.mock import patch


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from knowledge_base import SCENIC_NAMES, get_knowledge_base, init_knowledge_base  # noqa: E402
from rag_service import RAGService, classify_emotion, classify_turn_emotion, prepare_narration_voice_segments, split_narration_segments  # noqa: E402


class RagMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_knowledge_base()

    def test_classify_emotion_maps_tourist_intent_to_live2d_state(self):
        cases = {
            "太感谢你了，讲得真好": "thanks",
            "九龙灌浴居然会莲花开合吗": "surprised",
            "这个门票价格我有点疑惑": "confused",
            "推荐一条亲子路线": "happy",
            "讲的什么东西啊，完全没讲清楚": "sad",
            "讲得不好，请重新讲一遍": "sad",
            "我能听懂讲的太烂了我都没听懂": "sad",
            "讲得太烂了，重新讲": "sad",
            "我没听懂五智门是什么意思": "confused",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(classify_emotion(text), expected)

    def test_turn_emotion_prioritizes_user_criticism_over_answer_wording(self):
        cases = {
            "可能千万万讲的什么东西啊太烂了": "sad",
            "讲得不好，重新讲一下佛足坛": "sad",
            "全体耶出讲解一下佛祖坛": "neutral",
            "我没听懂五智门是什么意思": "confused",
        }
        answer = "您好，我来为您讲解佛足坛。"
        for query, expected in cases.items():
            with self.subTest(query=query):
                self.assertEqual(classify_turn_emotion(query, answer), expected)

    def test_chat_detail_returns_answer_metadata_sources_and_latency(self):
        service = RAGService(api_key="")
        result = service.chat_detail("灵山大佛有什么特色？", history=[], interest="历史文化")

        self.assertIn("灵山", result["answer"])
        self.assertIn(result["emotion"], {"neutral", "happy", "thanks", "surprised", "confused", "sad"})
        self.assertIsInstance(result["sources"], list)
        self.assertGreater(len(result["sources"]), 0)
        self.assertIn("latency_ms", result)
        self.assertGreaterEqual(result["latency_ms"], 0)

    def test_route_question_includes_route_suggestion(self):
        service = RAGService(api_key="")
        result = service.chat_detail("我带孩子玩四小时，请推荐路线", history=[], interest="亲子家庭")

        self.assertTrue(result["route_suggestion"])
        self.assertEqual(result["route_suggestion"]["id"], "route_family")
        self.assertIn("亲子", result["answer"])

    def test_short_time_route_question_is_not_misclassified_as_show_time(self):
        service = RAGService(api_key="sk-" + "x" * 32)

        with patch.object(service, "_llm_chat", return_value="九龙灌浴演出时间是 10:00。") as llm_chat:
            result = service.chat_detail("给出一条游玩路线，我只有2个小时，希望用最短的时间去游览最多的场景", history=[], interest="")

        llm_chat.assert_not_called()
        self.assertIn("2小时", result["answer"])
        self.assertIn("路线", result["answer"])
        self.assertIn("灵山大照壁", result["answer"])
        self.assertIn("灵山大佛", result["answer"])
        self.assertNotIn("常见场次为 10:00、11:30、13:30、15:00", result["answer"])
        self.assertEqual(result["route_suggestion"]["id"], "route_fast_2h")
        self.assertEqual(result["route_suggestion"]["duration"], "约2小时")

    def test_best_visit_season_uses_direct_fact_answer_before_llm(self):
        service = RAGService(api_key="sk-" + "x" * 32)

        with patch.object(service, "_llm_chat", return_value="临时展厅与禅意茶室适合静坐。") as llm_chat:
            result = service.chat_detail("什么季节来灵山胜境参观最好？", history=[], interest="")

        llm_chat.assert_not_called()
        self.assertIn("春秋", result["answer"])
        self.assertIn("3-5月", result["answer"])
        self.assertIn("9-11月", result["answer"])
        self.assertNotIn("临时展厅", result["answer"])
        self.assertNotIn("禅意茶室", result["answer"])

    def test_force_llm_bypasses_direct_fact_answer_for_evaluation(self):
        service = RAGService(api_key="sk-" + "x" * 32)

        with patch.object(service, "_llm_chat", return_value="DeepSeek 回答：春秋季节更适合游览灵山胜境。") as llm_chat:
            result = service.chat_detail("什么季节来灵山胜境参观最好？", history=[], interest="", force_llm=True)

        llm_chat.assert_called_once()
        self.assertEqual("deepseek", result["answer_provider"])
        self.assertIn("DeepSeek 回答", result["answer"])

    def test_evaluation_rag_adds_local_evidence_without_leaking_expected_keywords(self):
        service = RAGService(api_key="sk-" + "x" * 32)
        captured = {}
        fake_sources = [
            {
                "id": "kb-001",
                "source": "unit-doc",
                "title": "灵山大佛资料",
                "content": "灵山大佛佛像高88米，是灵山胜境的核心地标。",
                "excerpt": "灵山大佛佛像高88米",
                "score": 8.8,
            }
        ]

        def fake_llm(query, context, history, interest, timeout_seconds=None, evaluation_rag=False):
            captured["context"] = context
            return "灵山大佛高88米，是灵山胜境的核心地标。"

        with patch.object(service.kb, "search", return_value=fake_sources) as search:
            with patch.object(
                service,
                "_direct_fact_answer",
                return_value={"answer": "候选事实：灵山大佛高88米。", "source_query": "灵山大佛有多高？"},
            ):
                with patch.object(service, "_llm_chat", side_effect=fake_llm):
                    result = service.chat_detail(
                        "灵山大佛有多高？",
                        history=[],
                        interest="",
                        force_llm=True,
                        evaluation_rag=True,
                    )

        self.assertEqual("deepseek", result["answer_provider"])
        self.assertGreaterEqual(search.call_args[1].get("n_results", 0), 12)
        self.assertIn("本地候选事实", captured["context"])
        self.assertIn("灵山大佛高88米", captured["context"])
        self.assertIn("unit-doc", captured["context"])
        self.assertNotIn("must_include", captured["context"])
        self.assertNotIn("应包含", captured["context"])

    def test_force_llm_retries_empty_deepseek_answer_for_evaluation(self):
        service = RAGService(api_key="sk-" + "x" * 32)

        with patch.dict(os.environ, {"EVALUATION_LLM_RETRIES": "1", "EVALUATION_LLM_TIMEOUT_SECONDS": "30"}, clear=False):
            with patch.object(service, "_llm_chat", side_effect=["", "DeepSeek 重试成功：历史文化路线约6小时。"]) as llm_chat:
                result = service.chat_detail("历史文化爱好者怎么游灵山？", history=[], interest="", force_llm=True)

        self.assertEqual(2, llm_chat.call_count)
        self.assertEqual("deepseek", result["answer_provider"])
        self.assertIn("重试成功", result["answer"])

    def test_small_talk_uses_short_direct_answer_without_route_suggestion(self):
        service = RAGService(api_key="sk-" + "x" * 32)

        with patch.object(service, "_llm_chat", return_value="我给您推荐历史文化深度游。") as llm_chat:
            result = service.chat_detail("你好", history=[], interest="历史文化")

        llm_chat.assert_not_called()
        self.assertLessEqual(len(result["answer"]), 90)
        self.assertIn("灵小境", result["answer"])
        self.assertIsNone(result["route_suggestion"])
        self.assertNotIn("历史文化深度游", result["answer"])

    def test_compliment_and_affection_use_short_direct_answers_without_stage_directions(self):
        service = RAGService(api_key="sk-" + "x" * 32)

        cases = ["你好可爱", "我爱你"]
        for query in cases:
            with self.subTest(query=query), patch.object(service, "_llm_chat", return_value="（微微欠身）谢谢。") as llm_chat:
                result = service.chat_detail(query, history=[], interest="历史文化")

            llm_chat.assert_not_called()
            self.assertLessEqual(len(result["answer"]), 120)
            self.assertNotIn("（", result["answer"])
            self.assertNotIn("微微", result["answer"])
            self.assertIsNone(result["route_suggestion"])

    def test_noisy_asr_goodbye_and_mic_check_do_not_route_to_scenic_answers(self):
        service = RAGService(api_key="sk-" + "x" * 32)

        cases = [
            ("百拜拜", ["再见", "下次"], ["百子戏弥勒", "雕塑"]),
            ("开开开喂喂喂听得见吗", ["听得见", "继续问"], ["开放时间", "拈花湾"]),
        ]
        for query, expected_words, forbidden_words in cases:
            with self.subTest(query=query), patch.object(service, "_llm_chat", return_value="错误的景点回答") as llm_chat:
                result = service.chat_detail(query, history=[], interest="历史文化")

            llm_chat.assert_not_called()
            for word in expected_words:
                self.assertIn(word, result["answer"])
            for word in forbidden_words:
                self.assertNotIn(word, result["answer"])
            self.assertIsNone(result["route_suggestion"])

    def test_noisy_asr_scenic_name_variants_route_to_correct_spot(self):
        service = RAGService(api_key="sk-" + "x" * 32)

        cases = [
            ("说一下介绍一下九龙观玉", "九龙灌浴", "灵山梵宫"),
            ("要为介绍绍一阿玉王柱柱", "阿育王柱", "百子戏弥勒"),
        ]
        for query, expected, forbidden in cases:
            with self.subTest(query=query), patch.object(service, "_llm_chat", return_value="错误的景点回答") as llm_chat:
                result = service.chat_detail(query, history=[], interest="")

            llm_chat.assert_not_called()
            self.assertIn(expected, result["answer"])
            self.assertNotIn(forbidden, result["answer"])

    def test_tianxia_first_palm_from_dazhaobi_uses_direct_answer_before_llm(self):
        service = RAGService(api_key="sk-" + "x" * 32)

        with patch.object(service, "_llm_chat", return_value="九龙灌浴常见场次为 10:00、11:30。") as llm_chat:
            result = service.chat_detail("天下第一掌怎么样？从灵山大照壁到那里需要多长时间？", history=[], interest="历史文化")

        llm_chat.assert_not_called()
        self.assertIn("天下第一掌", result["answer"])
        self.assertIn("灵山大照壁", result["answer"])
        self.assertTrue("5到8分钟" in result["answer"] or "5-8分钟" in result["answer"])
        self.assertNotIn("九龙灌浴常见场次", result["answer"])
        self.assertNotIn("10:00、11:30", result["answer"])

    def test_show_time_question_uses_direct_fact_answer_before_llm(self):
        service = RAGService(api_key="sk-" + "x" * 32)

        with patch.object(service, "_llm_chat", return_value="这条路线建议先去梵宫。") as llm_chat:
            result = service.chat_detail("九龙灌浴几点演出？", history=[], interest="历史文化")

        llm_chat.assert_not_called()
        self.assertIn("10:00", result["answer"])
        self.assertIn("11:30", result["answer"])
        self.assertIn("提前", result["answer"])
        self.assertNotIn("梵宫", result["answer"])

    def test_jixiangsong_show_time_uses_fangong_answer_not_jiulong_template(self):
        service = RAGService(api_key="sk-" + "x" * 32)

        with patch.object(service, "_llm_chat", return_value="九龙灌浴常见场次为 10:00、11:30、13:30、15:00。") as llm_chat:
            result = service.chat_detail("《吉祥颂》每天什么时间演出？", history=[], interest="")

        llm_chat.assert_not_called()
        self.assertIn("吉祥颂", result["answer"])
        self.assertIn("10:35", result["answer"])
        self.assertIn("14:00", result["answer"])
        self.assertIn("16:00", result["answer"])
        self.assertIn("20分钟", result["answer"])
        self.assertNotIn("13:30", result["answer"])
        self.assertNotIn("莲花开合", result["answer"])

    def test_generic_show_time_mentions_both_main_performances(self):
        service = RAGService(api_key="sk-" + "x" * 32)

        with patch.object(service, "_llm_chat", return_value="只推荐先去灵山大佛。") as llm_chat:
            result = service.chat_detail("景区有哪些主要演出时间？", history=[], interest="")

        llm_chat.assert_not_called()
        self.assertIn("九龙灌浴", result["answer"])
        self.assertIn("10:00", result["answer"])
        self.assertIn("吉祥颂", result["answer"])
        self.assertIn("10:35", result["answer"])
        self.assertIn("以景区公告为准", result["answer"])

    def test_high_confidence_lingshan_fact_answers_do_not_fall_back_to_unrelated_excerpts(self):
        service = RAGService(api_key="sk-" + "x" * 32)

        with patch.object(service, "_llm_chat", return_value="我给您提炼一下：无关片段。") as llm_chat:
            result = service.chat_detail("登云道216级台阶有什么含义？", history=[], interest="")

        llm_chat.assert_not_called()
        self.assertIn("216", result["answer"])
        self.assertIn("108烦恼", result["answer"])
        self.assertIn("108愿望", result["answer"])
        self.assertNotIn("我给您提炼一下", result["answer"])

    def test_split_narration_segments_keeps_opening_short_for_fast_tts(self):
        text = (
            "现在我们来到灵山大照壁。先在这里停一下，别急着往前走；"
            "这处景观像一段开场白，把灵山胜境的礼佛氛围慢慢带出来。"
            "后面的讲解继续介绍文化故事、观看重点和游览提醒。"
        )

        segments = split_narration_segments(text)

        self.assertLessEqual(len(segments[0]), 32)
        self.assertIn("灵山大照壁", segments[0])
        self.assertEqual("".join(segments), text)

    def test_split_narration_segments_prefers_complete_opening_sentence(self):
        text = (
            "现在我们来到灵山梵宫。这里被誉为佛教艺术的卢浮宫，"
            "内部汇集东阳木雕、敦煌壁画、扬州漆器、景泰蓝须弥灯等多种传统工艺。"
            "您可以先抬头看穹顶天象图，再留意两侧墙面的装饰细节。"
        )

        segments = split_narration_segments(text)

        self.assertEqual(segments[0], "现在我们来到灵山梵宫。")
        self.assertEqual("".join(segments), text)

    def test_split_narration_segments_avoids_fixed_width_breaks_after_dunhao(self):
        text = (
            "如果您对历史文化感兴趣，建议从灵山大照壁进入，沿五明桥、佛足坛、"
            "五智门、菩提大道一路向前，再到九龙灌浴、天下第一掌、灵山大佛和梵宫，"
            "这样走下来文化线索最完整。"
        )

        segments = split_narration_segments(text)

        self.assertEqual("".join(segments), text)
        self.assertTrue(all(not segment.endswith("、") for segment in segments))

    def test_split_narration_segments_avoids_weak_clause_endings(self):
        text = (
            "您可以先看正面的题字和青石浮雕，它像给整条中轴线定下第一声调。"
            "大照壁常被游客当作第一张照片的背景，其实它更像入园后的第一道提示："
            "从这里开始，视线会被引向中轴线，也会被带入更庄重的游览节奏。"
        )

        segments = split_narration_segments(text)

        self.assertEqual("".join(segments), text)
        self.assertTrue(all(not segment.endswith(("，", ",", "、", "：", ":")) for segment in segments))

    def test_prepare_narration_voice_segments_closes_weak_clause_endings(self):
        segments = ["从这里开始，视线会被引向中轴线，", "五明桥、", "继续向前。"]

        result = prepare_narration_voice_segments(segments)

        self.assertEqual(result, ["从这里开始，视线会被引向中轴线。", "五明桥。", "继续向前。"])

    def test_scenic_narration_voice_segments_do_not_end_with_weak_punctuation(self):
        service = RAGService(api_key="")

        data = service.scenic_narration("LS-001")

        self.assertTrue(data["segments"])
        self.assertTrue(all(not segment.endswith(("，", ",", "、", "：", ":")) for segment in data["segments"]))

    def test_scenic_narration_voice_segments_keep_predicate_complements_together(self):
        service = RAGService(api_key="")

        data = service.scenic_narration("LS-001")

        joined = "\n".join(data["segments"])
        self.assertNotIn("观看重点。\n是把", joined)
        self.assertFalse(any(segment.startswith(("是把", "是将", "是让", "是为了")) for segment in data["segments"][1:]))
        self.assertTrue(all(len(segment) <= 110 for segment in data["segments"][1:]))

    def test_scenic_narration_deduplicates_and_filters_broken_source_sentences(self):
        service = RAGService(api_key="")

        for scenic_id, name in SCENIC_NAMES:
            with self.subTest(scenic_id=scenic_id, name=name):
                data = service.scenic_narration(scenic_id)
                sentences = [
                    sentence.strip()
                    for sentence in re.findall(r"[^。！？!?；;]+[。！？!?；;]?", data["answer"])
                    if len(sentence.strip()) >= 12
                ]
                seen = set()
                duplicates = []
                for sentence in sentences:
                    normalized = re.sub(r"\s+", "", sentence.strip("。！？!?；;，, "))
                    if normalized in seen:
                        duplicates.append(sentence)
                    seen.add(normalized)

                self.assertEqual([], duplicates)
                self.assertNotRegex(data["answer"], r"门楣处雕刻。|故居为[。！？!?；;]|(?<!意斋)无尽\s*(?:[。！？!?；;]|\n|$)")
                self.assertNotIn("。。", data["answer"])
                self.assertTrue(all(segment.endswith(("。", "！", "？")) for segment in data["display_segments"]))
                self.assertFalse(any(segment.endswith(("为。", "包括。", "雕刻。", "采用。")) for segment in data["display_segments"]))

    def test_wuming_bridge_narration_filters_near_duplicate_and_broken_source_sentences(self):
        service = RAGService(api_key="")

        data = service.scenic_narration("LS-002")
        answer = data["answer"]

        self.assertNotIn("是进。", answer)
        self.assertNotIn("时段入园游客观赏、打卡", answer)
        self.assertLessEqual(answer.count("大照壁北侧，横跨香水海，连接景区入口区域与核心朝圣区域"), 1)
        self.assertLessEqual(answer.count("进入核心景区的必经之路"), 1)

    def test_scenic_narration_filters_containment_style_repeated_facts(self):
        service = RAGService(api_key="")

        for scenic_id, name in SCENIC_NAMES:
            with self.subTest(scenic_id=scenic_id, name=name):
                data = service.scenic_narration(scenic_id)
                fingerprints = []
                for sentence in re.findall(r"[^。！？!?；;]+[。！？!?；;]?", data["answer"]):
                    fingerprint = re.sub(r"\s+", "", sentence.strip("。！？!?；;，, "))
                    fingerprint = fingerprint.replace(name, "")
                    fingerprint = re.sub(r"[，,。！？!?；;、：:\s“”\"'（）()《》\-—]", "", fingerprint)
                    if len(fingerprint) >= 18:
                        fingerprints.append(fingerprint)

                repeated_pairs = []
                for index, current in enumerate(fingerprints):
                    for previous in fingerprints[:index]:
                        if current in previous or previous in current:
                            repeated_pairs.append((previous, current))

                self.assertEqual([], repeated_pairs)

    def test_local_fact_accuracy_suite_reaches_ninety_percent(self):
        service = RAGService(api_key="")
        cases = [
            ("灵山胜境门票多少钱？", ["210", "105"]),
            ("九龙灌浴几点演出？", ["10:00", "11:30"]),
            ("灵山胜境怎么去？", ["无锡", "88"]),
            ("景区里哪里吃素斋？", ["灵山斋", "灵山精舍"]),
            ("亲子家庭路线怎么走？", ["亲子", "九龙灌浴"]),
            ("历史文化路线推荐一下", ["历史文化深度游", "灵山大佛"]),
            ("自然风光路线有什么？", ["自然风光轻松游", "太湖"]),
            ("灵山大佛有什么特色？", ["灵山", "大佛"]),
            ("灵山梵宫值得看吗？", ["梵宫", "佛教"]),
            ("五印坛城是什么？", ["五印坛城"]),
            ("天下第一掌适合拍照吗？", ["天下第一掌"]),
            ("百子戏弥勒介绍一下", ["百子戏弥勒"]),
            ("菩提大道有什么讲解重点？", ["菩提大道"]),
            ("五智门介绍一下", ["五智门"]),
            ("阿育王柱有什么文化含义？", ["阿育王柱"]),
            ("佛足坛是什么景点？", ["佛足坛"]),
            ("五明桥在哪里？", ["五明桥"]),
            ("灵山大照壁介绍一下", ["灵山大照壁"]),
            ("祥符禅寺有什么特色？", ["祥符禅寺"]),
            ("曼飞龙塔介绍一下", ["曼飞龙塔"]),
            ("无尽意斋是做什么的？", ["无尽意斋"]),
            ("降魔浮雕有什么故事？", ["降魔浮雕"]),
            ("老人小孩适合什么路线？", ["亲子", "老人"]),
            ("我想轻松拍照怎么玩？", ["自然", "拍照"]),
            ("我想看佛教建筑怎么安排？", ["历史", "文化"]),
            ("演出需要提前到吗？", ["提前", "分钟"]),
            ("节假日停车要注意什么？", ["节假日", "停车"]),
            ("学生票有优惠吗？", ["学生", "优惠"]),
            ("午饭安排在哪里比较好？", ["午餐", "梵宫"]),
            ("能先给我一个导游开场吗？", ["灵山胜境", "导游"]),
        ]

        hits = 0
        for query, expected_words in cases:
            answer = service.chat(query, [], "")
            if all(word in answer for word in expected_words):
                hits += 1

        self.assertGreaterEqual(hits / len(cases), 0.9)


if __name__ == "__main__":
    unittest.main()
