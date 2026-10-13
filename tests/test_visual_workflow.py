"""Rendered output and dependency checks, using explicitly synthetic QA art."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile

import pymupdf
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills/novel-book-writer/scripts'
sys.path.insert(0, str(SCRIPTS))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compact(text):
    return re.sub(r'\s+', '', text)


class VisualWorkflow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'manuscript.md'
        self.excerpt = '소년은 부러진 다리 앞에서 멈췄다. 청년은 그를 등 뒤로 물리고 도끼를 들었다.'
        self.source.write_text('# 시험\n\n## 첫 장\n\n' + self.excerpt + '\n\n[[art:bridge]]\n\n'
                               '도끼를 내려놓자 숲은 다시 고요해졌다.\n\n## 귀환\n\n그들은 마을로 돌아왔다.\n')
        Image.new('RGB', (1000, 1419), '#264e6e').save(self.root / 'reference.png')
        Image.new('RGB', (1000, 1419), '#456d39').save(self.root / 'scene.png')
        self.plan = self.root / 'production.json'
        self.data = {'schema_version': 1, 'format': 'illustrated-novel',
            'source': {'path': 'manuscript.md', 'sha256': digest(self.source)},
            'style': 'Synthetic QA fixtures, not generated character art.',
            'characters': [{'id': 'hero', 'name': '청년',
                'invariants': {'hair': 'black', 'eyes': 'brown'},
                'outfits': {'village': 'linen shirt'},
                'reference': {'path': 'reference.png', 'sha256': digest(self.root / 'reference.png')}}],
            'shots': [{'id': 'bridge', 'excerpt': self.excerpt, 'scene': '숲의 부러진 다리',
                'characters': [{'id': 'hero', 'outfit': 'village', 'state': '오른손에 도끼, 부상 없음'}],
                'prompt': 'Synthetic fixture used only to exercise page layout.',
                'image': 'scene.png', 'dialogue': [], 'review': {'status': 'pending', 'notes': ''}}]}
        self.save()

    def save(self):
        self.plan.write_text(json.dumps(self.data, ensure_ascii=False, indent=2))

    def run_cli(self, script, *args):
        return subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)], capture_output=True, text=True)

    def review(self):
        result = self.run_cli('visual_assets.py', 'record-review', '--plan', self.plan,
                              '--shot', 'bridge', '--notes', 'Synthetic QA art inspected for test geometry only.')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.data = json.loads(self.plan.read_text())

    def build(self, *extra):
        return self.run_cli('build_book.py', '--manuscript', self.source, '--output', self.root / 'book.pdf',
                            '--title', '시험 소설', '--author', '조판 검사', '--visual-plan', self.plan, *extra)

    def test_full_page_recto_preserves_prose_and_live_contents(self):
        self.review()
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads((self.root / 'book.manifest.json').read_text())
        self.assertTrue(manifest['visual_complete'])
        art = manifest['illustrations'][0]
        self.assertEqual(art['pdf_page'] % 2, 1)
        with pymupdf.open(self.root / 'book.pdf') as pdf:
            page = pdf[art['pdf_page'] - 1]
            self.assertFalse(page.get_text().strip(), 'Art page must have no prose or folio')
            self.assertIn(compact(self.excerpt), compact(pdf[art['pdf_page'] - 2].get_text()))
            bounds = pymupdf.Rect(page.get_image_info()[0]['bbox'])
            self.assertLessEqual(bounds.x0, 1)
            self.assertLessEqual(bounds.y0, 1)
            self.assertGreaterEqual(bounds.x1, page.rect.width - 1)
            self.assertGreaterEqual(bounds.y1, page.rect.height - 1)
            text = compact(''.join(p.get_text() for p in pdf))
            for prose in (self.excerpt, '도끼를 내려놓자 숲은 다시 고요해졌다.', '그들은 마을로 돌아왔다.'):
                self.assertIn(compact(prose), text)
            toc = pdf[manifest['contents_pdf_page'] - 1]
            targets = {link.get('page', -1) + 1 for link in toc.get_links()}
            for chapter in manifest['chapters']:
                self.assertIn(chapter['pdf_page'], targets)
                self.assertIn(compact(chapter['title']) + str(chapter['pdf_page']), compact(toc.get_text()))
                self.assertIn(compact(chapter['title']), compact(pdf[chapter['pdf_page'] - 1].get_text()))

    def test_pending_draft_is_not_final_and_bad_facing_page_fails(self):
        result = self.build()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / 'book.pdf').exists())
        result = self.build('--allow-pending-art')
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads((self.root / 'book.manifest.json').read_text())
        self.assertFalse(manifest['visual_complete'])
        self.review()
        # Move the anchor beyond another chapter: the preceding text no longer matches.
        text = self.source.read_text().replace('[[art:bridge]]\n\n', '') + '\n[[art:bridge]]\n'
        self.source.write_text(text)
        self.data['source']['sha256'] = digest(self.source)
        self.save()
        self.review()
        before = (self.root / 'book.pdf').read_bytes()
        result = self.build()
        self.assertNotEqual(result.returncode, 0)
        self.assertRegex(result.stderr, 'facing|left')
        self.assertEqual((self.root / 'book.pdf').read_bytes(), before)

    def test_changes_to_any_visual_dependency_invalidate_review(self):
        self.review()
        original = json.loads(self.plan.read_text())
        for field in ('style', 'scene', 'outfit', 'image', 'reference', 'source'):
            with self.subTest(field=field):
                self.data = json.loads(json.dumps(original))
                if field == 'style': self.data['style'] += ' changed'
                if field == 'scene': self.data['shots'][0]['scene'] += ' at night'
                if field == 'outfit': self.data['characters'][0]['outfits']['village'] = 'armor'
                if field == 'image': self.data['shots'][0]['image'] = 'reference.png'
                if field == 'reference': self.data['characters'][0]['reference']['sha256'] = '0' * 64
                if field == 'source': self.data['source']['sha256'] = '0' * 64
                self.save()
                result = self.run_cli('visual_assets.py', 'validate', '--plan', self.plan)
                self.assertNotEqual(result.returncode, 0, field)

    def test_one_finished_shot_can_be_reviewed_before_other_images_exist(self):
        self.data['shots'].append(dict(self.data['shots'][0], id='later', image='not-generated.png'))
        self.save()
        self.review()
        self.assertEqual(self.data['shots'][0]['review']['status'], 'pass')
        self.assertEqual(self.data['shots'][1]['review']['status'], 'pending')
        result = self.run_cli('visual_assets.py', 'validate', '--plan', self.plan)
        self.assertNotEqual(result.returncode, 0, 'Partial production is still not final')

    def test_shared_bible_invalidates_all_derivative_reviews(self):
        bible = self.root / 'character-bible.json'
        bible.write_text(json.dumps({'schema_version': 1, 'style': self.data.pop('style'),
                                    'characters': self.data.pop('characters')}))
        self.data['bible'] = {'path': bible.name, 'sha256': digest(bible)}
        self.save()
        self.review()
        self.assertNotIn('characters', json.loads(self.plan.read_text()), 'Keep one source of character truth')
        bible.write_text(bible.read_text().replace('black', 'silver'))
        result = self.run_cli('visual_assets.py', 'validate', '--plan', self.plan)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('bible', result.stderr)

    def test_project_initialization_is_resumable_and_preserves_existing_work(self):
        project = self.root / 'trilogy'
        result = self.run_cli('story_project.py', 'init', '--project', project, '--title', '천마의 마을', '--parts', '3')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((project / 'character-bible.json').is_file())
        self.assertEqual(len(list((project / 'volumes').glob('*/production.json'))), 3)
        progress = (project / 'progress.md').read_bytes()
        result = self.run_cli('story_project.py', 'init', '--project', project, '--title', '덮어쓰기')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((project / 'progress.md').read_bytes(), progress)
        result = self.run_cli('story_project.py', 'status', '--project', project)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('pending', result.stdout)

    def test_output_manifest_cannot_overwrite_shared_bible(self):
        bible = self.root / 'book.manifest.json'
        bible.write_text(json.dumps({'schema_version': 1, 'style': self.data.pop('style'),
                                    'characters': self.data.pop('characters')}))
        self.data['bible'] = {'path': bible.name, 'sha256': digest(bible)}
        self.save()
        self.review()
        original = bible.read_bytes()
        result = self.build()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(bible.read_bytes(), original)
        self.assertFalse((self.root / 'book.pdf').exists())

    def test_webtoon_slicing_preserves_all_panel_spacing(self):
        self.data['format'] = 'webtoon'
        template = self.data['shots'][0]
        self.data['shots'] = [dict(template, id=f'panel-{i}') for i in range(3)]
        self.data['layout'] = {'sequence': [s['id'] for s in self.data['shots']],
                              'width_px': 800, 'max_slice_height_px': 2400, 'gap_px': 80}
        self.save()
        for shot in self.data['shots']:
            result = self.run_cli('visual_assets.py', 'record-review', '--plan', self.plan,
                                 '--shot', shot['id'], '--notes', 'Synthetic geometry fixture only.')
            self.assertEqual(result.returncode, 0, result.stderr)
        output = self.root / 'strips'
        result = self.run_cli('build_visual.py', '--plan', self.plan, '--output', output)
        self.assertEqual(result.returncode, 0, result.stderr)
        heights = []
        for path in sorted(output.glob('*.png')):
            with Image.open(path) as picture:
                self.assertEqual(picture.width, 800)
                self.assertLessEqual(picture.height, 2400)
                heights.append(picture.height)
        self.assertGreater(len(heights), 1)
        self.assertEqual(sum(heights), round(800 * 1419 / 1000) * 3 + 80 * 2)

    def test_comic_and_webtoon_are_real_outputs_with_dialogue(self):
        self.data['format'] = 'comic'
        self.data['shots'][0]['dialogue'] = [{'speaker': 'hero', 'text': '내 뒤에 있어.', 'rect': [.08, .05, .7, .15]}]
        self.data['layout'] = {'reading_direction': 'ltr', 'pages': [{'panels': [{'shot': 'bridge', 'rect': [.08, .08, .84, .84]}]}]}
        self.save()
        self.review()
        output = self.root / 'comic'
        result = self.run_cli('build_visual.py', '--plan', self.plan, '--output', output)
        self.assertEqual(result.returncode, 0, result.stderr)
        with pymupdf.open(output / 'comic.pdf') as pdf:
            self.assertEqual(len(pdf), 1)
            self.assertIn('내뒤에있어.', compact(pdf[0].get_text()))
        with zipfile.ZipFile(output / 'comic.cbz') as archive:
            self.assertEqual(archive.namelist(), ['001.png'])
        self.data['format'] = 'webtoon'
        self.data['layout'] = {'sequence': ['bridge'], 'width_px': 800, 'max_slice_height_px': 2000, 'gap_px': 64}
        self.save()
        self.review()
        output = self.root / 'webtoon'
        result = self.run_cli('build_visual.py', '--plan', self.plan, '--output', output)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('내 뒤에 있어.', (output / 'index.html').read_text())
        with Image.open(output / '001.png') as strip:
            self.assertEqual(strip.width, 800)
            self.assertLessEqual(strip.height, 2000)

    def test_rejects_overlapping_panels_before_output(self):
        self.data['format'] = 'comic'
        self.data['layout'] = {'reading_direction': 'ltr', 'pages': [{'panels': [
            {'shot': 'bridge', 'rect': [.1, .1, .8, .8]}, {'shot': 'bridge', 'rect': [.2, .2, .6, .6]}]}]}
        self.save()
        self.review()
        result = self.run_cli('build_visual.py', '--plan', self.plan, '--output', self.root / 'bad')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / 'bad').exists())


if __name__ == '__main__':
    unittest.main()
