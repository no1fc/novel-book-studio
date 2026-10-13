#!/usr/bin/env python3
"""Map actual PDF pages to scene art; verify and insert without changing pagination."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile

import pymupdf

MM = 72 / 25.4


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def page_text(page, art_height):
    return page.get_text(clip=pymupdf.Rect(0, 0, page.rect.width,
                         page.rect.height - (20 + art_height) * MM)).strip()


def scene_digest(item):
    return sha256(json.dumps({key: item[key] for key in ('scene', 'characters', 'prompt')},
                             ensure_ascii=False, sort_keys=True).encode())


def write_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        tmp = Path(handle.name)
        try:
            handle.write(data)
            handle.close()
            tmp.replace(path)
        finally:
            tmp.unlink(missing_ok=True)


def load_base(pdf):
    manifest = json.loads(pdf.with_suffix('.manifest.json').read_text())
    if sha256(pdf.read_bytes()) != manifest['pdf_sha256']:
        raise ValueError('base PDF changed; rebuild and prepare the page map')
    if sha256(Path(manifest['source_path']).read_bytes()) != manifest['source_sha256']:
        raise ValueError('manuscript changed; rebuild before mapping images')
    if not 0 < manifest.get('page_art_height_mm', 0) <= 80:
        raise ValueError('build with --page-art-height-mm first')
    return manifest


def prepare(pdf, mapping, previous=None, character_references=()):
    pdf, mapping = Path(pdf).resolve(), Path(mapping).resolve()
    if mapping.exists():
        raise ValueError('page map already exists; use a new filename to preserve reviews')
    if mapping in (pdf, pdf.with_suffix('.manifest.json')):
        raise ValueError('page map must be distinct from the book')
    manifest = load_base(pdf)
    references = [{'path': str(Path(p).resolve()), 'sha256': sha256(Path(p).read_bytes())}
                  for p in character_references]
    reusable = {}
    if previous:
        previous = Path(previous).resolve()
        old = json.loads(previous.read_text())
        if old.get('character_references', []) == references:
            reusable = {p['text_sha256']: p for p in old['pages']}
    pages = []
    with pymupdf.open(pdf) as doc:
        for idx in range(manifest['body_start_pdf_page'] - 1, len(doc)):
            page = doc[idx]
            text = page_text(page, manifest['page_art_height_mm'])
            if not text:
                raise ValueError(f'empty body page {idx + 1}')
            left = 20 if (idx + 1) % 2 else 15
            rect = [left * MM, page.rect.height - (20 + manifest['page_art_height_mm']) * MM,
                    page.rect.width - (35 - left) * MM, page.rect.height - 20 * MM]
            pages.append({'id': f'body-{len(pages)+1:03}', 'pdf_page': idx + 1,
                          'text': text, 'text_sha256': sha256(text.encode()),
                          'rect_pt': rect,
                          'image': f'images/{mapping.stem}/body-{len(pages)+1:03}-{sha256(text.encode())[:12]}.png',
                          'scene': '', 'characters': [], 'prompt': '',
                          'review': {'status': 'pending', 'notes': ''}})
            previous_page = reusable.get(pages[-1]['text_sha256'])
            if previous_page:
                for key in ('scene', 'characters', 'prompt', 'review'):
                    pages[-1][key] = previous_page[key]
                pages[-1]['image'] = os.path.relpath((previous.parent / previous_page['image']).resolve(), mapping.parent)
                if old['source_sha256'] != manifest['source_sha256']:
                    pages[-1]['review'] = {**previous_page['review'], 'status': 'pending',
                                          'reason': 'manuscript changed; recheck surrounding context'}
    data = {'schema_version': 1, 'base_pdf_sha256': manifest['pdf_sha256'],
            'source_sha256': manifest['source_sha256'], 'character_references': references,
            'pages': pages}
    write_atomic(mapping, (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode())
    return data


def apply(pdf, mapping, output, overwrite=False):
    pdf, mapping, output = map(lambda p: Path(p).resolve(), (pdf, mapping, output))
    manifest = load_base(pdf)
    data = json.loads(mapping.read_text())
    for ref in data.get('character_references', []):
        if sha256(Path(ref['path']).read_bytes()) != ref['sha256']:
            raise ValueError('character reference changed; prepare a new map and review images')
    protected = {pdf, mapping, pdf.with_suffix('.manifest.json'), Path(manifest['source_path']).resolve()}
    if output in protected or output.suffix.lower() != '.pdf':
        raise ValueError('output must be a distinct .pdf')
    if data['base_pdf_sha256'] != manifest['pdf_sha256'] or data['source_sha256'] != manifest['source_sha256']:
        raise ValueError('stale page map: PDF or manuscript changed')
    expected = list(range(manifest['body_start_pdf_page'], manifest['page_count'] + 1))
    if [p['pdf_page'] for p in data['pages']] != expected:
        raise ValueError('page map must cover every body page exactly once in order')
    with pymupdf.open(pdf) as doc:
        original_text = [p.get_text() for p in doc]
        original_toc = doc.get_toc()
        images = []
        for item in data['pages']:
            page = doc[item['pdf_page'] - 1]
            current_text = page_text(page, manifest['page_art_height_mm'])
            digest = sha256(current_text.encode())
            if item['text_sha256'] != digest or item['text'].strip() != current_text:
                raise ValueError(f"stale page text: {item['id']}")
            asset = (mapping.parent / item['image']).resolve()
            if asset in protected or asset in (output, output.with_suffix('.manifest.json')):
                raise ValueError('image must be distinct from book files')
            image_bytes = asset.read_bytes()
            image_hash = sha256(image_bytes)
            review = item['review']
            if not item.get('scene', '').strip() or not item.get('prompt', '').strip():
                raise ValueError(f"missing scene or prompt: {item['id']}")
            if (review.get('status') != 'pass' or not review.get('notes', '').strip()
                    or review.get('text_sha256') != digest or review.get('image_sha256') != image_hash):
                raise ValueError(f"pending or stale image review: {item['id']}")
            if review.get('scene_sha256') != scene_digest(item):
                raise ValueError(f"stale scene review: {item['id']}")
            left = 20 if item['pdf_page'] % 2 else 15
            rect = pymupdf.Rect(left * MM, page.rect.height - (20 + manifest['page_art_height_mm']) * MM,
                                page.rect.width - (35 - left) * MM, page.rect.height - 20 * MM)
            if any(abs(a-b) > .01 for a,b in zip(rect, item['rect_pt'])):
                raise ValueError(f"changed image rectangle: {item['id']}")
            for block in page.get_text('blocks'):
                if pymupdf.Rect(block[:4]).intersects(rect):
                    raise ValueError(f"image overlaps text: {item['id']}")
            page.insert_image(rect, stream=image_bytes, keep_proportion=True)
            images.append({'id': item['id'], 'pdf_page': item['pdf_page'],
                           'text_sha256': digest, 'image_sha256': image_hash,
                           'review': review, 'image': str(asset)})
        result = doc.tobytes(garbage=4, deflate=True)
    with pymupdf.open(stream=result, filetype='pdf') as check:
        if len(check) != len(original_text) or check.get_toc() != original_toc:
            raise ValueError('page count or bookmarks changed during image insertion')
        for idx, page in enumerate(check):
            text = page.get_text()
            if text != original_text[idx]:
                raise ValueError('text changed during image insertion')
    final_manifest = {**manifest, 'base_pdf_sha256': manifest['pdf_sha256'],
                      'pdf_sha256': sha256(result), 'illustrations': images,
                      'page_art_complete': True}
    if output.with_suffix('.manifest.json') in protected:
        raise ValueError('output manifest would overwrite an input')
    if not overwrite and (output.exists() or output.with_suffix('.manifest.json').exists()):
        raise ValueError('output exists; use a new filename or explicitly --overwrite')
    write_atomic(output, result)
    write_atomic(output.with_suffix('.manifest.json'),
                 (json.dumps(final_manifest, ensure_ascii=False, indent=2) + '\n').encode())
    return final_manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'apply'))
    parser.add_argument('--pdf', required=True, type=Path)
    parser.add_argument('--map', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--previous', type=Path, help='Reuse matching page text/reviews from an earlier map')
    parser.add_argument('--character-reference', type=Path, action='append', default=[])
    parser.add_argument('--overwrite', action='store_true', help='Explicitly replace an existing final PDF/manifest')
    args = parser.parse_args()
    try:
        if args.action == 'prepare':
            result = prepare(args.pdf, args.map, args.previous, args.character_reference)
        else:
            if not args.output:
                parser.error('apply requires --output')
            result = apply(args.pdf, args.map, args.output, args.overwrite)
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(2, f'error: {exc}\n')
    print(json.dumps({'pages': len(result.get('pages', result.get('illustrations', [])))}, ensure_ascii=False))


if __name__ == '__main__':
    main()
