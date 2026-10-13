"""Observable PDF/layout regressions; run with the project .venv Python."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import pymupdf
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills/novel-book-writer/scripts'


class BookWorkflow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'manuscript.md'
        self.source.write_text('# 시험 소설\n\n## 첫 장\n\n' + '\n\n'.join(
            f'기록 {i}. 서윤은 창가에서 종이를 펼쳤다. 문밖의 발소리가 멈추었다. ' * 5
            for i in range(16)), encoding='utf-8')
        self.cover = self.root / 'cover.png'
        Image.new('RGB', (740, 1050), (40, 80, 90)).save(self.cover)
        self.pdf = self.root / 'book.pdf'

    def build(self, *extra):
        p = subprocess.run([sys.executable, str(SCRIPTS / 'build_book.py'),
            '--manuscript', str(self.source), '--output', str(self.pdf),
            '--title', '시험 소설', '--author', '창작', '--cover-image', str(self.cover),
            *extra], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(self.pdf.with_suffix('.manifest.json').read_text())

    def test_default_cover_preserves_art_behind_title(self):
        self.build()
        with pymupdf.open(self.pdf) as doc:
            pix = doc[0].get_pixmap()
            # Inside the former panel, away from any title/author glyph.
            self.assertEqual(pix.pixel(70, 80)[:3], (40, 80, 90))
            self.assertIn('시험', doc[0].get_text())

    def test_page_art_keeps_text_and_rejects_stale_map(self):
        manifest = self.build('--page-art-height-mm', '52')
        spec = importlib.util.spec_from_file_location('page_art', SCRIPTS / 'page_art.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        mapping = self.root / 'page-art.json'
        module.prepare(self.pdf, mapping)
        data = json.loads(mapping.read_text())
        self.assertGreater(len(data['pages']), 1)
        for item in data['pages']:
            self.assertTrue(item['text'].strip())
            item['scene'] = '서윤이 창가에서 종이를 펼친다.'
            item['prompt'] = 'Test fixture, no generated art.'
            asset = self.root / item['image']
            asset.parent.mkdir(parents=True, exist_ok=True)
            Image.new('RGB', (800, 360), (70, 100, 120)).save(asset)
            item['review'] = {'status': 'pass', 'notes': 'Test fixture only',
                              'text_sha256': item['text_sha256'],
                              'scene_sha256': module.scene_digest(item),
                              'image_sha256': module.sha256(asset.read_bytes())}
        mapping.write_text(json.dumps(data), encoding='utf-8')
        final = self.root / 'final.pdf'
        module.apply(self.pdf, mapping, final)
        with pymupdf.open(self.pdf) as before, pymupdf.open(final) as after:
            self.assertEqual(len(before), len(after))
            self.assertEqual(before.get_toc(), after.get_toc())
            for old, new in zip(before, after):
                self.assertEqual(old.get_text(), new.get_text())
            for item in data['pages']:
                self.assertEqual(len(after[item['pdf_page'] - 1].get_image_info()), 1)
        original = final.read_bytes()
        data['pages'][0]['text_sha256'] = 'stale'
        mapping.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'stale|changed'):
            module.apply(self.pdf, mapping, final)
        self.assertEqual(final.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
