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

class CoverDesignTests(unittest.TestCase):
    run_builder = BookTests.run_builder

    def test_cover_layouts_title_placement_and_manual_lines(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output, art = root/'story.md', root/'book.pdf', root/'art.png'
            source.write_text('## 첫 장\n\n온전한 본문.\n', encoding='utf-8')
            Image.new('RGB', (296, 420), '#426970').save(art)
            title_positions = {}
            for layout, position in [('auto', 'top'), ('fullbleed', 'bottom'), ('framed', 'top'), ('typographic', 'top')]:
                with self.subTest(layout=layout, position=position):
                    extra = ['--cover-layout', layout, '--cover-title-position', position,
                             '--cover-title-lines', '해안의|우편함']
                    if layout != 'typographic':
                        extra += ['--cover-image', str(art)]
                    result = self.run_builder(source, output, '해안의 우편함', *extra)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    manifest = json.loads(output.with_suffix('.manifest.json').read_text())
                    expected = 'fullbleed' if layout == 'auto' else layout
                    self.assertEqual(manifest['design']['cover_layout'], expected)
                    self.assertEqual(manifest['design']['cover_title_position'], position)
                    self.assertEqual(manifest['design']['cover_title_lines'], ['해안의', '우편함'])
                    with fitz.open(output) as pdf:
                        cover = pdf[0]
                        self.assertIn('해안의\n우편함', cover.get_text())
                        self.assertIn('테스트작가', compact(cover.get_text()))
                        title_positions[layout] = cover.search_for('해안의')[0].y0
                        if expected == 'fullbleed':
                            bounds = fitz.Rect(cover.get_image_info()[0]['bbox'])
                            self.assertLessEqual(bounds.x0, 1)
                            self.assertLessEqual(bounds.y0, 1)
                            self.assertGreaterEqual(bounds.x1, cover.rect.width - 1)
                            self.assertGreaterEqual(bounds.y1, cover.rect.height - 1)
                        elif expected == 'framed':
                            bounds = fitz.Rect(cover.get_image_info()[0]['bbox'])
                            self.assertGreater(bounds.x0, 10)
                            self.assertGreater(bounds.y0, 10)
                            self.assertLess(bounds.x1, cover.rect.width - 10)
                        else:
                            self.assertFalse(cover.get_images())
                        for word in cover.get_text('words'):
                            self.assertGreaterEqual(word[0], 0)
                            self.assertLessEqual(word[2], cover.rect.width)
                            self.assertGreaterEqual(word[1], 0)
                            self.assertLessEqual(word[3], cover.rect.height)
            self.assertGreater(title_positions['fullbleed'], title_positions['auto'] + 150)

    def test_invalid_cover_options_preserve_existing_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root/'story.md', root/'book.pdf'
            source.write_text('## 첫 장\n\n온전한 본문.\n', encoding='utf-8')
            output.write_bytes(b'existing output')
            for options in [('--cover-title-lines', '다른|제목'), ('--cover-title-lines', '해안의||우편함'),
                            ('--cover-title-lines', '해|안|의|우편|함'),
                            ('--cover-layout', 'fullbleed'), ('--cover-layout', 'framed')]:
                with self.subTest(options=options):
                    result = self.run_builder(source, output, '해안의 우편함', *options)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('error:', result.stderr.lower())
                    self.assertEqual(output.read_bytes(), b'existing output')

    def test_genre_palette_and_real_cover_image(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output, art = root / 'story.md', root / 'book.pdf', root / 'cover.png'
            source.write_text('## 첫 장\n\n그녀는 우편함을 열었다.\n', encoding='utf-8')
            Image.new('RGB', (180, 260), '#426970').save(art)
            result = self.run_builder(source, output, '해안의 우편함', '--genre', 'mystery', '--cover-image', str(art))
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads(output.with_suffix('.manifest.json').read_text())
            self.assertEqual(manifest['design']['genre'], 'mystery')
            self.assertEqual(manifest['design']['cover_image_sha256'], hashlib.sha256(art.read_bytes()).hexdigest())
            pdf = fitz.open(output)
            self.assertTrue(pdf[0].get_image_info(), 'Real illustration must be rendered on cover, including background patterns')
            self.assertIn('해안의우편함', compact(pdf[0].get_text()))
            self.assertTrue(any(span['color'] == int('edf4ef',16)
                                for b in pdf[0].get_text('dict')['blocks'] if 'lines' in b
                                for l in b['lines'] for span in l['spans']))
            self.assertIn('그녀는우편함을열었다.', compact(''.join(p.get_text() for p in pdf)))
            long_title = ('바닷가에서 사라진 편지를 찾아가는 사람들의 이야기 ' * 3)[:70]
            long_result = self.run_builder(source, output, long_title, '--genre', 'mystery',
                                           '--cover-image', str(art), '--subtitle', '늦게 도착한 마음의 기록')
            self.assertEqual(long_result.returncode, 0, long_result.stderr)
            with fitz.open(output) as long_pdf:
                self.assertIn(compact(long_title), compact(long_pdf[0].get_text()))
                self.assertIn('테스트작가', compact(long_pdf[0].get_text()))
            original = output.read_bytes()
            for extra in [('--text-color', '#ffffff'), ('--cover-text-color', '#172b35'),
                          ('--accent-color', 'red; color:white'), ('--cover-image', str(root/'missing.png'))]:
                bad = self.run_builder(source, output, '제목', '--genre', 'mystery', *extra)
                self.assertNotEqual(bad.returncode, 0, bad.stdout)
                self.assertEqual(output.read_bytes(), original)

    def test_custom_colors_are_applied_to_text_and_page(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory)/'story.md', Path(directory)/'book.pdf'
            source.write_text('## 봄날\n\n다시 만난 두 사람.\n', encoding='utf-8')
            result = self.run_builder(source, output, '편지', '--genre', 'romance',
                                      '--text-color', '#382830', '--paper-color', '#fffaf5',
                                      '--heading-color', '#663344')
            self.assertEqual(result.returncode, 0, result.stderr)
            pdf = fitz.open(output)
            spans = [s for p in pdf for b in p.get_text('dict')['blocks'] if 'lines' in b
                     for l in b['lines'] for s in l['spans']]
            self.assertTrue(any(s['color'] == int('382830',16) for s in spans))
            self.assertTrue(any(s['color'] == int('663344',16) for s in spans))
            color = pdf[-1].get_pixmap().pixel(2,2)
            self.assertTrue(all(abs(a-b)<=1 for a,b in zip(color,(255,250,245))),color)


if __name__ == "__main__":
    unittest.main()
