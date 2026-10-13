#!/usr/bin/env python3
"""Compose reviewed scene panels into a scroll webtoon or comic PDF/CBZ.

This composes local art and searchable dialogue. It does not generate artwork,
adapt prose automatically, or certify character likeness.
"""
import argparse
from io import BytesIO
import html
import json
from pathlib import Path
import shutil
import tempfile
import zipfile

import pymupdf
from PIL import Image
from weasyprint import HTML
from weasyprint.urls import URLFetcher, URLFetcherResponse

from visual_assets import compact, digest, load_plan, local_path, rectangle

MM = 72 / 25.4


def overlaps(a, b):
    return (max(a[0], b[0]) < min(a[0] + a[2], b[0] + b[2]) - 1e-8
            and max(a[1], b[1]) < min(a[1] + a[3], b[1] + b[3]) - 1e-8)


def positive_int(value, label, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f'{label} must be an integer from {low} to {high}')
    return value


def compose(plan, base):
    mode, layout = plan['format'], plan['layout']
    shots = {s['id']: s for s in plan['shots']}
    resources = {local_path(base, s['image']).as_uri(): local_path(base, s['image']).read_bytes()
                 for s in plan['shots']}
    pages = []
    if mode == 'comic':
        if layout['reading_direction'] not in ('ltr', 'rtl'):
            raise ValueError('comic reading_direction must be ltr or rtl')
        for page in layout['pages']:
            panels = page['panels']
            if not panels:
                raise ValueError('comic page must contain panels')
            for idx, panel in enumerate(panels):
                rectangle(panel['rect'], 'comic panel')
                if any(overlaps(panel['rect'], other['rect']) for other in panels[:idx]):
                    raise ValueError('comic panels overlap')
            pages.append((148 * MM, 210 * MM, panels))
    elif mode == 'webtoon':
        width = positive_int(layout['width_px'], 'width_px', 320, 4096)
        positive_int(layout['max_slice_height_px'], 'max_slice_height_px', 320, 16000)
        positive_int(layout['gap_px'], 'gap_px', 0, 2000)
        for key in layout['sequence']:
            if key not in shots:
                raise ValueError(f'unknown panel: {key}')
            with Image.open(local_path(base, shots[key]['image'])) as picture:
                height = round(width * picture.height / picture.width)
            if height > layout['max_slice_height_px']:
                raise ValueError(f'{key}: panel exceeds slice height; recompose it instead of cutting a face/bubble')
            pages.append((width * .75, height * .75, [{'shot': key, 'rect': [0, 0, 1, 1]}]))
    else:
        raise ValueError('build_visual.py supports webtoon and comic; novels use build_book.py')
    used = [panel['shot'] for _, _, panels in pages for panel in panels]
    if len(used) != len(set(used)) or set(used) != set(shots):
        raise ValueError('layout must use every shot exactly once; use separate shot IDs for repeated beats')
    styles = ['''
@page { margin: 0; background: white; }
body { margin: 0; font-family: "Noto Sans CJK KR", sans-serif; }
.sheet { position: relative; break-after: page; overflow: hidden; }
.panel { position: absolute; overflow: hidden; }
.panel img { display: block; width: 100%; height: 100%; object-fit: cover; }
.bubble { position: absolute; box-sizing: border-box; padding: 1mm 1.5mm;
  border: .5pt solid #222; border-radius: 3mm; background: white; color: #111;
  line-height: 1.35; overflow-wrap: anywhere; font-size: 10pt; }
''']
    body, checks = [], []
    for idx, (width, height, panels) in enumerate(pages):
        styles.append(f'@page sheet{idx} {{ size: {width}pt {height}pt; }}')
        body.append(f'<section class="sheet" style="page:sheet{idx};width:{width}pt;height:{height}pt">')
        page_checks = []
        for panel in panels:
            x, y, w, h = panel['rect']
            shot = shots[panel['shot']]
            uri = local_path(base, shot['image']).as_uri()
            body.append(f'<div class="panel" style="left:{x*100}%;top:{y*100}%;width:{w*100}%;height:{h*100}%">'
                        f'<img src="{html.escape(uri, quote=True)}" alt="{html.escape(shot["scene"], quote=True)}">')
            occupied = []
            for bubble in shot.get('dialogue', []):
                bx, by, bw, bh = rectangle(bubble['rect'], 'dialogue')
                if any(overlaps(bubble['rect'], rect) for rect in occupied):
                    raise ValueError(f'{shot["id"]}: dialogue boxes overlap')
                occupied.append(bubble['rect'])
                size = positive_int(bubble.get('font_size_px', 16 if mode == 'comic' else 22), 'font_size_px', 8, 96)
                body.append(f'<div class="bubble" style="left:{bx*100}%;top:{by*100}%;width:{bw*100}%;height:{bh*100}%;'
                            f'font-size:{size}px">{html.escape(bubble["text"])}</div>')
                page_checks.append((bubble['text'], pymupdf.Rect((x + bx*w)*width, (y + by*h)*height,
                    (x + (bx+bw)*w)*width, (y + (by+bh)*h)*height)))
            body.append('</div>')
        body.append('</section>')
        checks.append(page_checks)

    class LocalAssets(URLFetcher):
        def fetch(self, url, headers=None):
            if url in resources:
                return URLFetcherResponse(url, resources[url])
            raise ValueError('external resource fetching is disabled')

    content = '<!doctype html><html lang="ko"><meta charset="utf-8"><style>' + ''.join(styles) + '</style><body>' + ''.join(body) + '</body></html>'
    raw = HTML(string=content, url_fetcher=LocalAssets(fail_on_errors=True)).write_pdf()
    with pymupdf.open(stream=raw, filetype='pdf') as doc:
        if len(doc) != len(pages):
            raise ValueError('panel composition overflowed a page')
        for page, bubbles in zip(doc, checks):
            for text, rect in bubbles:
                if compact(text) not in compact(page.get_text(clip=rect)):
                    raise ValueError('dialogue does not fit its bubble; enlarge/rewrite it before export')
    return raw, used


def build(plan_path, output):
    plan_path, output = Path(plan_path).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError('output directory exists; choose a new version to preserve published assets')
    plan = load_plan(plan_path)
    raw, used = compose(plan, plan_path.parent)
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.visual-', dir=output.parent))
    try:
        with pymupdf.open(stream=raw, filetype='pdf') as doc:
            if plan['format'] == 'comic':
                from pypdf import PdfWriter
                from pypdf.generic import DictionaryObject, NameObject
                writer = PdfWriter(clone_from=BytesIO(raw))
                rtl = plan['layout']['reading_direction'] == 'rtl'
                writer._root_object[NameObject('/ViewerPreferences')] = DictionaryObject({
                    NameObject('/Direction'): NameObject('/R2L' if rtl else '/L2R')})
                writer.write(staging / 'comic.pdf')
                with zipfile.ZipFile(staging / 'comic.cbz', 'w', zipfile.ZIP_DEFLATED) as archive:
                    for idx, page in enumerate(doc):
                        name = f'{idx+1:03}.png'
                        page.get_pixmap(dpi=150).save(staging / name)
                        archive.write(staging / name, name)
            else:
                layout = plan['layout']
                width, limit, gap = layout['width_px'], layout['max_slice_height_px'], layout['gap_px']
                strips, pending, total = [], [], 0

                def flush():
                    if not pending:
                        return
                    canvas = Image.new('RGB', (width, total), 'white')
                    y = 0
                    for panel, band_height in pending:
                        if panel is not None:
                            canvas.paste(panel, (0, y))
                        y += band_height
                    name = f'{len(strips)+1:03}.png'
                    canvas.save(staging / name)
                    strips.append(name)

                for idx, page in enumerate(doc):
                    pix = page.get_pixmap(matrix=pymupdf.Matrix(4/3, 4/3), alpha=False)
                    panel = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
                    if panel.width != width or panel.height > limit:
                        raise ValueError('rendered panel exceeds configured dimensions')
                    # Whitespace may cross a slice boundary; artwork must remain intact.
                    remaining_gap = gap if idx else 0
                    while remaining_gap:
                        band = min(remaining_gap, limit - total)
                        pending.append((None, band))
                        total += band
                        remaining_gap -= band
                        if total == limit:
                            flush()
                            pending, total = [], 0
                    if total + panel.height > limit:
                        flush()
                        pending, total = [], 0
                    pending.append((panel, panel.height))
                    total += panel.height
                flush()
                dialogue = ''.join('<p>' + html.escape(b['text']) + '</p>' for s in plan['shots'] for b in s.get('dialogue', []))
                (staging / 'index.html').write_text('<!doctype html><html lang="ko"><meta charset="utf-8">'
                    '<meta name="viewport" content="width=device-width,initial-scale=1"><title>웹툰</title>'
                    f'<style>body{{margin:0;background:#eee}}main{{max-width:{width}px;margin:auto;background:white}}'
                    'img{display:block;width:100%;height:auto}details{padding:1rem}</style><main>'
                    + ''.join(f'<img src="{s}" alt="웹툰 {i+1}번째 구간">' for i, s in enumerate(strips))
                    + '<details><summary>대사 읽기</summary>' + dialogue + '</details></main></html>', encoding='utf-8')
        files = {p.name: digest(p.read_bytes()) for p in sorted(staging.iterdir()) if p.is_file()}
        manifest = {'format': plan['format'], 'source_sha256': plan['source']['sha256'],
                    'plan_sha256': digest(plan_path.read_bytes()), 'shots': used,
                    'files': files, 'review_scope': 'Recorded asset reviews plus mechanical layout checks; final visual inspection still required'}
        (staging / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
        staging.rename(output)
        return manifest
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path, help='New directory; existing directories are never replaced')
    args = parser.parse_args()
    try:
        manifest = build(args.plan, args.output)
    except (ValueError, OSError, KeyError, TypeError, ImportError) as error:
        parser.exit(2, f'error: {error}\n')
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
