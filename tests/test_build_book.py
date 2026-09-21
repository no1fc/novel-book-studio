"""Run with: python -m unittest discover -s tests -v (PyMuPDF needed for QA)."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

import pymupdf as fitz
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/novel-book-writer/scripts/build_book.py"


def compact(text):
    return re.sub(r"\s+", "", text)


class BookTests(unittest.TestCase):
    def run_builder(self, source, output, title="바람의 도서관", *extra):
        self.assertTrue(SCRIPT.is_file(), "Portable PDF builder must exist")
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--manuscript", str(source),
             "--output", str(output), "--title", title, "--author", "테스트 작가",
             *extra], capture_output=True, text=True,
        )

    def test_complete_multilingual_book_with_overflowing_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "story.md"
            output = Path(directory) / "book.pdf"
            title = "긴 제목으로 읽는 바람과 바다의 도서관 A Library Beyond the Sea " * 3
            titles = [f"{i + 1}장. 한글과 English, café가 함께 있는 아주 긴 장 제목" for i in range(45)]
            titles[0] += " · 긴 제목은 줄을 바꿔도 전체가 보인다 A Long Journey" * 3
            titles.append("작가의 말")
            paragraphs = ["장 앞의 서문도 반드시 남아 있어야 한다."]
            pieces = ["# 원고 제목", paragraphs[0]]
            for index, heading in enumerate(titles):
                prose = f"문단{index:03d}. 작은 바람이 창문을 두드렸다. 모든 문장을 남긴다."
                dialogue = f'“대화{index:03d}. 돌아왔니?”'
                response = f'“응답{index:03d}. 여기에 있어.”'
                final = f"마지막{index:03d}. **강조**와 *기울임*도 읽을 수 있다."
                paragraphs.extend([prose, dialogue, response, final.replace("*", "")])
                pieces.extend(["## " + heading, prose, dialogue, response, "***", final])
                if index == 0:
                    for item in range(36):
                        continued = f"이어지는문단{item:03d}. " + "문장이 다음 쪽으로 흘러가도 온전히 남는다. " * 5
                        paragraphs.append(continued)
                        pieces.append(continued)
            manuscript = "\n\n".join(pieces) + "\n"
            source.write_text(manuscript, encoding="utf-8")
            result = self.run_builder(source, output, title, "--subtitle", "문장과 여백의 책")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(source.read_text(encoding="utf-8"), manuscript)
            manifest = json.loads(output.with_suffix(".manifest.json").read_text())
            self.assertEqual(manifest["source_sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
            reader = PdfReader(output)
            pdf = fitz.open(output)
            self.assertEqual(manifest["page_count"], len(reader.pages))
            self.assertEqual(reader.metadata.title, title)
            self.assertEqual(reader.metadata.author, "테스트 작가")
            text = compact("".join(page.get_text() for page in pdf))
            self.assertIn(compact("긴 제목으로 읽는"), compact(pdf[0].get_text()), "Cover title must begin on the cover")
            for paragraph in paragraphs:
                self.assertIn(compact(paragraph), text)
            self.assertEqual([item["title"] for item in manifest["chapters"]], titles)
            outlines = {item.title: reader.get_destination_page_number(item) + 1
                        for item in reader.outline if not isinstance(item, list)}
            toc_start = outlines["차례"]
            first_chapter = manifest["chapters"][0]["pdf_page"]
            self.assertGreater(first_chapter - toc_start, 1, "TOC must flow over multiple pages")
            toc_text = compact("".join(pdf[i].get_text() for i in range(toc_start - 1, first_chapter - 1)))
            link_targets = {link["page"] + 1
                            for i in range(toc_start - 1, first_chapter - 1)
                            for link in pdf[i].get_links()
                            if link["kind"] in (fitz.LINK_GOTO, fitz.LINK_NAMED) and link.get("page", -1) >= 0}
            for chapter in manifest["chapters"]:
                page = chapter["pdf_page"]
                self.assertEqual(outlines[chapter["title"]], page)
                self.assertIn(page, link_targets)
                self.assertIn(compact(chapter["title"]) + str(page), toc_text)
                self.assertIn(compact(chapter["title"]), compact(pdf[page - 1].get_text()))
            # All visible text stays inside the physical page; long titles must wrap.
            for page in pdf:
                self.assertAlmostEqual(page.rect.width, 419.53, delta=1)
                self.assertAlmostEqual(page.rect.height, 595.28, delta=1)
                for word in page.get_text("words"):
                    self.assertGreaterEqual(word[0], -1)
                    self.assertLessEqual(word[2], page.rect.width + 1)
                    self.assertGreaterEqual(word[1], -1)
                    self.assertLessEqual(word[3], page.rect.height + 1)

    def test_invalid_manuscripts_and_source_collision_fail_without_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "story.md"
            output = Path(directory) / "book.pdf"
            for invalid in ["", "just prose", "## Empty chapter", "## Title\n\n![alt](https://example.org/x.png)",
                            "## Title\n\n```python\nsecret\n```", "## Title\n\n<table>secret</table>",
                            "## Title\n\n| left | right |\n| --- | --- |", "### Lost heading\n\nwords"]:
                with self.subTest(invalid=invalid):
                    source.write_text(invalid, encoding="utf-8")
                    result = self.run_builder(source, output)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("error:", result.stderr.lower())
                    self.assertFalse(output.exists())
            manuscript = "## 하나\n\n보존할 문장.\n"
            source.write_text(manuscript, encoding="utf-8")
            result = self.run_builder(source, source)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(source.read_text(encoding="utf-8"), manuscript)
            result = self.run_builder(source, output, "title", "--font-file", str(Path(directory) / "missing.ttf"))
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
