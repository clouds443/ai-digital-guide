# -*- coding: utf-8 -*-
import builtins
import json
import os
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from unittest.mock import Mock


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import knowledge_base as kb  # noqa: E402


class KnowledgeUploadContractTests(unittest.TestCase):
    def make_docx(self, path, text):
        xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body><w:p><w:r><w:t>{0}</w:t></w:r></w:p></w:body></w:document>"
        ).format(text)
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("word/document.xml", xml.encode("utf-8"))

    def test_pdf_always_uses_paddleocr_even_when_local_text_is_extractable(self):
        original_read_pdf = kb.read_pdf
        original_paddleocr_pdf_to_text = kb.paddleocr_pdf_to_text
        calls = {"ocr": 0}

        def fake_read_pdf(_filepath):
            return "灵山胜境历史文化资料。" * 4

        def fake_paddleocr_pdf_to_text(_filepath):
            calls["ocr"] += 1
            return "PaddleOCR 解析出的灵山胜境历史文化资料。" * 4, {
                "ocr_model": "PaddleOCR-VL-1.6",
                "page_count": 9,
            }

        try:
            kb.read_pdf = fake_read_pdf
            kb.paddleocr_pdf_to_text = fake_paddleocr_pdf_to_text
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(b"%PDF-1.4\n")
                tmp_path = tmp.name
            try:
                result = kb.extract_knowledge_file(tmp_path, "灵山胜境资料.pdf")
            finally:
                os.remove(tmp_path)
        finally:
            kb.read_pdf = original_read_pdf
            kb.paddleocr_pdf_to_text = original_paddleocr_pdf_to_text

        self.assertEqual(calls["ocr"], 1)
        self.assertEqual(result["extension"], "pdf")
        self.assertGreaterEqual(result["char_count"], kb.MIN_EXTRACTED_TEXT_CHARS)
        self.assertEqual(result["ocr_metadata"]["ocr_model"], "PaddleOCR-VL-1.6")
        self.assertEqual(result["ocr_metadata"]["page_count"], 9)

    def test_pdf_paddleocr_html_table_noise_is_cleaned_before_storage(self):
        dirty_text = (
            "### 4. 世界佛教文化的交流平台\n"
            "<table border=1 style=\"margin: auto; word-wrap: break-word;\">"
            "<tr><td style=\"text-align: center; word-wrap: break-word;\">项目</td>"
            "<td style=\"text-align: center; word-wrap: break-word;\">内容</td></tr>"
            "<tr><td>游览信息</td><td>灵山大佛高 88 米，景区门票和观光车可组合购买。</td></tr>"
            "</table>\n"
            "灵山胜境融合佛教文化、自然景观与人文体验。"
        )

        with patch.object(
            kb,
            "paddleocr_pdf_to_text",
            return_value=(dirty_text, {"ocr_model": "PaddleOCR-VL-1.6", "page_count": 2}),
        ):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(b"%PDF-1.4\n")
                tmp_path = tmp.name
            try:
                result = kb.extract_knowledge_file(tmp_path, "灵山资料.pdf")
            finally:
                os.remove(tmp_path)

        self.assertNotIn("<table", result["content"])
        self.assertNotIn("<td", result["content"])
        self.assertNotIn("style=", result["content"])
        self.assertNotIn("&quot;", result["content"])
        self.assertIn("灵山大佛高 88 米", result["content"])
        self.assertIn("景区门票和观光车", result["content"])

    def test_docx_upload_does_not_call_paddleocr_or_report_ocr_metadata(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
            tmp_path = tmp.name
        self.make_docx(tmp_path, "灵山胜境景点结构化数据集。灵山大佛高88米，是景区核心景点。" * 3)
        try:
            with patch.object(kb, "paddleocr_pdf_to_text", side_effect=AssertionError("docx must not use OCR")):
                result = kb.extract_knowledge_file(tmp_path, "灵山胜境 景点结构化数据集.docx")
        finally:
            os.remove(tmp_path)

        self.assertEqual(result["extension"], "docx")
        self.assertNotIn("ocr_metadata", result)
        self.assertIn("灵山大佛高88米", result["content"])

    def test_read_pdf_uses_external_parser_when_local_libraries_missing(self):
        with patch.object(kb, "_read_pdf_with_local_libraries", return_value=""):
            with patch.object(kb, "_read_pdf_with_external_python", return_value="外部解析出的灵山胜境 PDF 正文。" * 3) as external:
                text = kb.read_pdf("demo.pdf")

        external.assert_called_once_with("demo.pdf")
        self.assertGreaterEqual(len(text), kb.MIN_EXTRACTED_TEXT_CHARS)
        self.assertIn("外部解析", text)

    def test_paddleocr_uses_modern_worker_when_current_ssl_is_legacy(self):
        completed = Mock()
        completed.returncode = 0
        completed.stdout = (
            '{"ok": true, "text": "worker 解析出的灵山胜境 PDF 正文。worker 解析出的灵山胜境 PDF 正文。", '
            '"metadata": {"ocr_model": "PaddleOCR-VL-1.6", "page_count": 9}}'
        ).encode("utf-8")
        completed.stderr = b""

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(b"%PDF-1.4\n")
            tmp_path = tmp.name
        try:
            with patch.object(kb, "_should_use_paddleocr_worker", return_value=True), patch.object(
                kb,
                "_candidate_paddleocr_worker_pythons",
                return_value=[r"C:\modern-python\python.exe"],
            ), patch.object(kb.subprocess, "run", return_value=completed) as run:
                text, metadata = kb.PaddleOCRClient(token="secret-token").extract_pdf(tmp_path)
        finally:
            os.remove(tmp_path)

        self.assertIn("worker 解析", text)
        self.assertEqual(metadata["ocr_model"], "PaddleOCR-VL-1.6")
        self.assertEqual(metadata["page_count"], 9)
        self.assertEqual(run.call_count, 1)
        self.assertIn(b"secret-token", run.call_args[1]["input"])

    def test_write_json_file_uses_atomic_replace_when_existing_truncate_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, "admin_knowledge.json")
            original_open = builtins.open
            with original_open(target, "w", encoding="utf-8") as f:
                json.dump([{"title": "旧知识", "content": "旧内容"}], f, ensure_ascii=False)

            target_abs = os.path.abspath(target)

            def guarded_open(path, mode="r", *args, **kwargs):
                if os.path.abspath(str(path)) == target_abs and "w" in mode:
                    raise OSError(22, "Invalid argument", target)
                return original_open(path, mode, *args, **kwargs)

            with patch("builtins.open", side_effect=guarded_open):
                kb.write_json_file(target, [{"title": "新知识", "content": "灵山胜境正文"}])

            with original_open(target, "r", encoding="utf-8") as f:
                saved = json.load(f)
            self.assertEqual(saved[0]["title"], "新知识")

    def test_admin_knowledge_view_includes_base_and_uploaded_document_details(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            docs_dir = os.path.join(tmpdir, "docs")
            data_dir = os.path.join(tmpdir, "knowledge")
            os.makedirs(docs_dir)
            os.makedirs(data_dir)
            self.make_docx(os.path.join(docs_dir, "灵山胜境基础资料.docx"), "内置资料正文" * 20)

            admin_file = os.path.join(data_dir, "admin_knowledge.json")
            with open(admin_file, "w", encoding="utf-8") as f:
                json.dump(
                    [
                        {
                            "id": "kb-uploaded",
                            "title": "上传的灵山胜境资料",
                            "content": "管理员上传正文" * 30,
                            "type": "文史资料",
                            "created_at": "2026-06-21 10:49:16",
                            "metadata": {
                                "source": "paddleocr_upload",
                                "original_filename": "灵山资料.pdf",
                                "file_type": "pdf",
                                "char_count": 240,
                                "uploaded_at": "2026-06-21 10:49:16",
                                "ocr_model": "PaddleOCR-VL-1.6",
                                "page_count": 9,
                            },
                        }
                    ],
                    f,
                    ensure_ascii=False,
                )

            with patch.object(kb, "ADMIN_DOCS_FILE", admin_file):
                payload = kb.build_admin_knowledge_view(docs_dir)

        self.assertEqual(payload["summary"]["total_documents"], 2)
        self.assertEqual(payload["summary"]["uploaded_documents"], 1)
        self.assertEqual(payload["summary"]["base_documents"], 1)
        self.assertGreater(payload["summary"]["total_char_count"], 0)

        uploaded = next(doc for doc in payload["knowledge_documents"] if doc["id"] == "kb-uploaded")
        self.assertEqual(uploaded["title"], "上传的灵山胜境资料")
        self.assertEqual(uploaded["source_label"], "PaddleOCR 上传")
        self.assertEqual(uploaded["uploaded_at"], "2026-06-21 10:49:16")
        self.assertEqual(uploaded["ocr_model"], "PaddleOCR-VL-1.6")
        self.assertEqual(uploaded["page_count"], 9)
        self.assertTrue(uploaded["can_delete"])
        self.assertIn("管理员上传正文", uploaded["content_preview"])

        base_doc = next(doc for doc in payload["knowledge_documents"] if doc["source"] == "base_docx")
        self.assertEqual(base_doc["source_label"], "赛题资料包")
        self.assertFalse(base_doc["can_delete"])
        self.assertIn("内置资料正文", base_doc["content_preview"])
        self.assertIn("content", base_doc)

    def test_quality_report_flags_duplicate_ocr_fragments_and_missing_scenics(self):
        text = (
            "五印坛城的建造体现了汉传佛教、藏传佛教的文化交融。\n"
            "五印坛城的建造体现了汉传佛教、藏传佛教的文化交融。\n"
            "时段入园游客观赏、打卡。这里是进。\n"
            "灵山大佛高88米。"
        )

        report = kb.analyze_knowledge_quality(text, title="五印坛城残句资料")

        self.assertEqual(report["level"], "risk")
        self.assertGreaterEqual(report["duplicate_sentence_count"], 1)
        self.assertGreaterEqual(report["ocr_issue_count"], 1)
        self.assertIn("五印坛城", report["covered_scenics"])
        self.assertIn("灵山大佛", report["covered_scenics"])
        self.assertIn("核心景点覆盖不足", " ".join(report["suggestions"]))

    def test_quality_report_returns_extraction_issue_details_and_legacy_aliases(self):
        text = "灵山胜境正常介绍。时段入园游客观赏、打卡。这里是进。<table style=\"word-wrap: break-word;\"><tr><td>乱码</td></tr></table>"

        report = kb.analyze_knowledge_quality(text, title="抽取疑点资料")

        self.assertGreaterEqual(report["extraction_issue_count"], 1)
        self.assertIn("extraction_issues", report)
        self.assertTrue(any(item["text"] == "时段入园游客观赏、打卡" for item in report["extraction_issues"]))
        self.assertEqual(report["ocr_issue_count"], report["extraction_issue_count"])
        self.assertEqual(report["ocr_issues"], [item["text"] for item in report["extraction_issues"][:6]])

    def test_quality_report_does_not_mark_normal_docx_structure_as_extraction_issue(self):
        text = (
            "灵山胜境景点结构化数据集。表1：灵山胜境景点数据集。"
            "景区名称灵山，景点名称灵山大佛。核心功能包含文化内涵、详细介绍、游玩亮点。"
        )

        report = kb.analyze_knowledge_quality(text, title="灵山胜境 景点结构化数据集.docx")

        self.assertEqual(report["extraction_issue_count"], 0)
        self.assertEqual(report["ocr_issue_count"], 0)

    def test_quality_report_includes_duplicate_sentence_details(self):
        text = "灵山大佛是核心景点。灵山大佛是核心景点。九龙灌浴适合观看。"

        report = kb.analyze_knowledge_quality(text, title="重复句资料")

        self.assertGreaterEqual(report["duplicate_sentence_count"], 1)
        self.assertIn("duplicate_sentences", report)
        duplicate = next(
            item for item in report["duplicate_sentences"] if item["sentence"] == "灵山大佛是核心景点"
        )
        self.assertEqual(duplicate["count"], 2)
        self.assertEqual(duplicate["key"], "灵山大佛是核心景点")
        self.assertTrue(duplicate["is_duplicate"])

    def test_admin_document_view_recomputes_legacy_duplicate_details(self):
        doc = {
            "id": "legacy-quality",
            "title": "旧版质检报告",
            "content": "灵山大佛是核心景点。灵山大佛是核心景点。九龙灌浴适合观看。",
            "type": "文史资料",
            "created_at": "2026-07-19 10:00:00",
            "metadata": {
                "source": "manual",
                "char_count": 38,
                "quality_report": {
                    "level": "review",
                    "label": "需复核",
                    "duplicate_sentence_count": 1,
                    "suggestions": ["旧版报告只有重复数量。"],
                },
            },
        }

        view = kb._admin_document_view(doc)

        quality = view["quality_report"]
        self.assertIn("duplicate_sentences", quality)
        self.assertTrue(
            any(item["sentence"] == "灵山大佛是核心景点" and item["count"] == 2 for item in quality["duplicate_sentences"])
        )

    def test_legacy_dirty_content_is_cleaned_for_admin_view_and_rag_index(self):
        dirty_content = (
            "灵山胜境总览。<table border=1 style=\"margin:auto\">"
            "<tr><td style=\"word-wrap: break-word;\">项目</td><td>灵山大佛高88米</td></tr>"
            "</table>九龙灌浴每天演出。"
        )
        doc = {
            "id": "legacy-dirty",
            "title": "旧版 PDF 脏正文",
            "content": dirty_content,
            "type": "文史资料",
            "created_at": "2026-07-19 10:00:00",
            "metadata": {"source": "paddleocr_upload", "char_count": len(dirty_content)},
        }

        view = kb._admin_document_view(doc)

        self.assertNotIn("<table", view["content"])
        self.assertNotIn("style=", view["content"])
        self.assertIn("灵山大佛高88米", view["content"])

        with tempfile.TemporaryDirectory() as tmpdir:
            admin_file = os.path.join(tmpdir, "admin_knowledge.json")
            with open(admin_file, "w", encoding="utf-8") as f:
                json.dump([doc], f, ensure_ascii=False)
            with patch.object(kb, "ADMIN_DOCS_FILE", admin_file):
                base = kb.KnowledgeBase(docs_dir=os.path.join(tmpdir, "missing-docs"))
                base._load_admin_documents()

        indexed_content = "\n".join(chunk["content"] for chunk in base.chunks)
        self.assertNotIn("<td", indexed_content)
        self.assertNotIn("style=", indexed_content)
        self.assertIn("九龙灌浴每天演出", indexed_content)

    def test_admin_knowledge_view_compat_documents_are_cleaned(self):
        dirty_content = (
            "灵山梵宫介绍。&lt;table border=1 style=&quot;margin:auto; word-wrap: break-word;&quot;&gt;"
            "&lt;tr&gt;&lt;td style=&quot;text-align:center; word-wrap: break-word;&quot;&gt;项目&lt;/td&gt;"
            "&lt;td&gt;世界佛教论坛会场&lt;/td&gt;&lt;/tr&gt;&lt;/table&gt;"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            admin_file = os.path.join(tmpdir, "admin_knowledge.json")
            with open(admin_file, "w", encoding="utf-8") as f:
                json.dump(
                    [
                        {
                            "id": "legacy-compat-dirty",
                            "title": "旧版 PDF 兼容字段",
                            "content": dirty_content,
                            "type": "文史资料",
                            "created_at": "2026-07-19 10:00:00",
                            "metadata": {"source": "paddleocr_upload", "char_count": len(dirty_content)},
                        }
                    ],
                    f,
                    ensure_ascii=False,
                )

            with patch.object(kb, "ADMIN_DOCS_FILE", admin_file):
                payload = kb.build_admin_knowledge_view(docs_dir=os.path.join(tmpdir, "missing-docs"))

        compat_content = payload["documents"][0]["content"]
        self.assertNotIn("&lt;table", compat_content)
        self.assertNotIn("<table", compat_content)
        self.assertNotIn("style=", compat_content)
        self.assertNotIn("word-wrap", compat_content)
        self.assertIn("世界佛教论坛会场", compat_content)

    def test_admin_knowledge_view_includes_quality_summary_and_document_reports(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            docs_dir = os.path.join(tmpdir, "docs")
            data_dir = os.path.join(tmpdir, "knowledge")
            os.makedirs(docs_dir)
            os.makedirs(data_dir)
            self.make_docx(
                os.path.join(docs_dir, "灵山胜境基础资料.docx"),
                "灵山大照壁 五明桥 佛足坛 五智门 菩提大道 九龙灌浴 降魔浮雕 阿育王柱 天下第一掌 百子戏弥勒 灵山大佛 灵山梵宫 祥符禅寺 五印坛城 曼飞龙塔 无尽意斋。" * 3,
            )

            admin_file = os.path.join(data_dir, "admin_knowledge.json")
            with open(admin_file, "w", encoding="utf-8") as f:
                json.dump(
                    [
                        {
                            "id": "kb-risk",
                            "title": "残句资料",
                            "content": "五印坛城文化交融。五印坛城文化交融。时段入园游客观赏、打卡。是进。",
                            "type": "文史资料",
                            "created_at": "2026-07-11 10:00:00",
                            "metadata": {"source": "manual", "char_count": 40},
                        }
                    ],
                    f,
                    ensure_ascii=False,
                )

            with patch.object(kb, "ADMIN_DOCS_FILE", admin_file):
                payload = kb.build_admin_knowledge_view(docs_dir)

        self.assertIn("quality_summary", payload["summary"])
        self.assertGreaterEqual(payload["summary"]["quality_summary"]["risk"], 1)
        risky = next(doc for doc in payload["knowledge_documents"] if doc["id"] == "kb-risk")
        self.assertIn("quality_report", risky)
        self.assertEqual(risky["quality_report"]["level"], "risk")


if __name__ == "__main__":
    unittest.main()
