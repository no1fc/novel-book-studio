#!/usr/bin/env python3
"""Render a hand-written SVG drawing to a PNG of an exact pixel size.

Uses a locally installed Chromium-family browser in headless mode so that
gradients, masks, blur and noise filters and blend modes render as written.
Network access is blocked; the SVG may only reference local files. This turns
code-drawn art into a raster file for --cover-image or a visual plan. It does
not generate artwork and does not judge whether the drawing is good.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from PIL import Image

BROWSERS = ('google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser', 'chrome', 'msedge')
# A5 at 300dpi; cover and full-page art share the 148:210 page ratio.
SIZES = {'a5': (1748, 2480), 'a5-draft': (874, 1240), 'webtoon': (800, 1200), 'square': (1600, 1600)}


def render(svg, output, width, height, browser=None):
    svg, output = Path(svg).resolve(), Path(output).resolve()
    if not svg.is_file() or svg.suffix.lower() != '.svg':
        raise ValueError('--svg must be an existing .svg file')
    if output.suffix.lower() != '.png' or output == svg:
        raise ValueError('--output must be a .png path distinct from the SVG')
    if not (64 <= width <= 6000 and 64 <= height <= 6000):
        raise ValueError('size must be 64-6000 px per side')
    binary = browser or next((found for name in BROWSERS if (found := shutil.which(name))), None)
    if not binary:
        raise ValueError('no Chromium-family browser found; install one or pass --browser /path/to/chrome')
    output.parent.mkdir(parents=True, exist_ok=True)
    # Work beside the output: sandboxed browsers often cannot read system temp folders.
    with tempfile.TemporaryDirectory(dir=output.parent, prefix='.render-') as work:
        page, shot = Path(work) / 'page.html', Path(work) / 'shot.png'
        page.write_text('<!doctype html><meta charset="utf-8"><style>html,body{margin:0;overflow:hidden}'
                        f'img{{display:block;width:{width}px;height:{height}px}}</style>'
                        f'<img src="{svg.as_uri()}">', encoding='utf-8')
        result = subprocess.run(
            [binary, '--headless=new', '--no-sandbox', '--disable-gpu', '--hide-scrollbars',
             '--force-device-scale-factor=1', '--host-rules=MAP * ~NOTFOUND',
             f'--user-data-dir={Path(work) / "profile"}', f'--window-size={width},{height}',
             f'--screenshot={shot}', page.as_uri()],
            capture_output=True, text=True, timeout=120)
        if not shot.is_file():
            raise ValueError('browser did not produce an image: ' + result.stderr.strip()[-300:])
        with Image.open(shot) as image:
            if image.size != (width, height):
                raise ValueError(f'rendered {image.size}, expected {(width, height)}')
            if len(image.convert('RGB').resize((32, 32)).getcolors(1024)) < 2:
                raise ValueError('rendered image is a single flat color; check the SVG for errors')
        shot.replace(output)
    return {'output': str(output), 'width': width, 'height': height, 'browser': binary}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--svg', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path, help='PNG path; an existing file is replaced')
    parser.add_argument('--size', default='a5', help='a5 | a5-draft | webtoon | square | WIDTHxHEIGHT in px')
    parser.add_argument('--browser', help='Explicit Chromium-family executable')
    args = parser.parse_args()
    try:
        if args.size in SIZES:
            width, height = SIZES[args.size]
        else:
            width, height = (int(part) for part in args.size.lower().split('x'))
        result = render(args.svg, args.output, width, height, args.browser)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        parser.exit(2, f'error: {error}\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
