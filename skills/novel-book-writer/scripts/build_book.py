#!/usr/bin/env python3
"""Typeset a bounded UTF-8 novel manuscript as an A5 PDF and audit manifest.

Supported Markdown: one optional leading # title, ## sections, blank-line
paragraphs, *** scene breaks, and inline *emphasis* / **strong**. All ##
sections are included, in source order. Other Markdown is rejected explicitly.
"""
import argparse
import hashlib
import html
from io import BytesIO
import json
from pathlib import Path
import re
import sys
import tempfile


# Cover background/text, decorative accent, heading, body text, paper.
# These are starting palettes, not fixed rules about genres.
PALETTES = {
    "classic": ("#172028", "#f8f3e8", "#b9a374", "#655032", "#252a2f", "#ffffff"),
    "mystery": ("#172b35", "#edf4ef", "#c8a568", "#28505a", "#26353a", "#fafbf8"),
    "fantasy": ("#202d29", "#f6edd7", "#c4a15c", "#40543d", "#2f332b", "#fdfaf2"),
    "romance": ("#593849", "#fff4ed", "#e4b3a4", "#794455", "#382e32", "#fffaf7"),
    "horror": ("#211d25", "#f1e9e4", "#b76d70", "#743b47", "#30292e", "#faf7f4"),
    "sf": ("#142637", "#e7f5ff", "#76c8d6", "#245473", "#263440", "#f7fbfe"),
    "literary": ("#403d35", "#fff6e6", "#c4ae7b", "#61553d", "#35332e", "#fffdf7"),
}
COLOR_FIELDS = ("cover_background", "cover_text_color", "accent_color", "heading_color", "text_color", "paper_color")


def contrast(first, second):
    def luminance(color):
        channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in channels]
        return sum(c * weight for c, weight in zip(linear, (.2126, .7152, .0722)))
    light, dark = sorted((luminance(first), luminance(second)), reverse=True)
    return (light + .05) / (dark + .05)


def book_design(args):
    palette = dict(zip(COLOR_FIELDS, PALETTES[args.genre]))
    for field in COLOR_FIELDS:
        value = getattr(args, field) or palette[field]
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise ValueError(f"--{field.replace('_', '-')} must be a #RRGGBB color")
        palette[field] = value.lower()
    for ink, paper in (("cover_text_color", "cover_background"), ("text_color", "paper_color"), ("heading_color", "paper_color")):
        if contrast(palette[ink], palette[paper]) < 4.5:
            raise ValueError(f"insufficient contrast: {ink} / {paper}; choose a ratio of at least 4.5")
    return palette


def inline(text):
    escaped = html.escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", escaped)
    return escaped.replace("\n", "<br>")


def cover_title(args):
    if args.cover_title_lines is None:
        return html.escape(args.title), None
    lines = [line.strip() for line in args.cover_title_lines.split("|")]
    if not 1 <= len(lines) <= 4 or not all(lines):
        raise ValueError("--cover-title-lines needs 1 to 4 nonempty lines separated by |")
    if re.sub(r"\s+", "", "".join(lines)) != re.sub(r"\s+", "", args.title):
        raise ValueError("--cover-title-lines must match --title, ignoring whitespace")
    return "<br>".join(map(html.escape, lines)), lines


def cover_panel(palette):
    """Keep cover text readable even over the lightest/darkest possible image."""
    channels = [int(palette["cover_background"][i:i + 2], 16) for i in (1, 3, 5)]
    for opacity in range(90, 101):
        backgrounds = ["#" + "".join(f"{round(c * opacity / 100 + edge * (100 - opacity) / 100):02x}"
                                    for c in channels) for edge in (0, 255)]
        if all(contrast(palette["cover_text_color"], color) >= 4.5 for color in backgrounds):
            return f"rgba({','.join(map(str, channels))},{opacity / 100})"


def parse_manuscript(text):
    preamble, chapters, paragraph = [], [], []
    blocks = preamble
    title_seen = False

    def flush():
        if paragraph:
            blocks.append("<p>" + inline("\n".join(paragraph)) + "</p>")
            paragraph.clear()

    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if any(ord(char) < 32 and char != "\t" for char in line):
            raise ValueError(f"line {number}: unsupported control character")
        if not stripped:
            flush()
        elif stripped.startswith("# "):
            if title_seen or chapters or preamble or paragraph:
                raise ValueError(f"line {number}: only one leading # manuscript title is supported")
            title_seen = True
        elif stripped.startswith("## "):
            flush()
            title = stripped[3:].strip()
            if not title:
                raise ValueError(f"line {number}: empty section title")
            blocks = []
            chapters.append({"title": title, "blocks": blocks})
        elif stripped == "***":
            flush()
            blocks.append('<p class="scene" aria-label="Scene break">* * *</p>')
        else:
            if (re.match(r"(?:#{1,6}(?:\s|$)|>|[-+*]\s|\d+[.)]\s|~~~|---+$|===+$)", stripped)
                    or "`" in line or "|" in line or "![" in line
                    or re.search(r"<[/!A-Za-z]|\[[^]]*\]\s*[(\[]|^\s*\[[^]]+\]:", line)):
                raise ValueError(f"line {number}: unsupported Markdown (use ## headings, paragraphs, *** and inline emphasis)")
            paragraph.append(line.strip())
    flush()
    if not chapters:
        raise ValueError("manuscript needs at least one ## section with prose")
    for chapter in chapters:
        if not any(block.startswith("<p>") for block in chapter["blocks"]):
            raise ValueError(f"section {chapter['title']!r} contains no prose")
    return preamble, chapters


def css_string(value):
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\a ").replace("\r", "\\d ").replace("<", "\\3c ") + '"'


CSS = """
@page { size: A5; margin: 18mm 15mm 20mm 20mm;
  @bottom-center { content: counter(page); font-size: 8pt; color: #79736a; }
}
@page:left { margin-left: 15mm; margin-right: 20mm; }
@page:right { margin-left: 20mm; margin-right: 15mm; }
@page cover { background: #172028; margin: 22mm 20mm;
  @bottom-center { content: none; }
}
html { font-size: 11pt; color: #252a2f; }
body { margin: 0; line-height: 1.75; overflow-wrap: anywhere; }
h1, h2 { font-weight: 500; line-height: 1.5; margin: 0; }
h1 { font-size: 25pt; bookmark-level: none; }
h2 { font-size: 18pt; margin-bottom: 10mm; bookmark-level: 1; }
p { margin: 0 0 1mm; text-indent: 1em; orphans: 3; widows: 3; }
strong { font-weight: bold; }
.cover { page: cover; break-after: page; color: #f8f3e8; text-align: center; padding-top: 18mm; }
.cover h1 { bookmark-level: 1; bookmark-label: "표지"; break-inside: auto; }
.ornament { width: 27mm; height: 27mm; border: 0.6pt solid #b9a374;
  border-radius: 50%; margin: 0 auto 14mm; break-after: avoid; }
.cover p { text-indent: 0; }
.subtitle { margin-top: 8mm; font-size: 12pt; color: #cab995; }
.author { margin-top: 13mm; font-size: 11pt; }
.titlepage { break-after: page; padding-top: 24mm; }
.titlepage .subtitle { color: #75623d; }
.long-title h1 { font-size: 18pt; break-inside: auto; }
.long-title .cover { padding-top: 8mm; }
.long-title .ornament { width: 20mm; height: 20mm; margin-bottom: 9mm; }
.long-title .titlepage { padding-top: 12mm; }
.rule { width: 22mm; border-top: 0.6pt solid #b9a374; margin: 12mm 0; }
.credits { margin-top: 12mm; color: #625d55; text-indent: 0; }
.preamble { break-after: page; }
.toc { break-after: page; }
.toc h2 { margin-bottom: 9mm; }
.toc a { display: block; position: relative; padding-right: 10mm; margin: 0 0 4mm;
  color: inherit; text-decoration: none; font-size: 10pt; line-height: 1.65; }
.toc a::after { content: target-counter(attr(href), page); position: absolute;
  right: 0; bottom: 0; color: #857049; font-size: 9pt; }
.chapter { break-before: page; }
.chapter h2 { padding-top: 9mm; }
.chapter h2 + p { text-indent: 0; }
.scene { text-align: center; text-indent: 0; color: #857049; margin: 6mm 0; }
"""


def build(args):
    from pypdf import PdfReader
    from weasyprint import HTML
    from weasyprint.text.fonts import FontConfiguration
    from weasyprint.urls import URLFetcher, URLFetcherResponse

    source = args.manuscript.resolve()
    output = args.output.resolve()
    manifest_path = output.with_suffix(".manifest.json")
    if output == source or manifest_path == source or output == manifest_path:
        raise ValueError("output PDF and manifest must be distinct from the input manuscript")
    if output.suffix.lower() != ".pdf":
        raise ValueError("--output must have a .pdf suffix")
    palette = book_design(args)
    for value, label in [(args.title, "title"), (args.author, "author"), (args.font_family, "font family")]:
        if not value.strip():
            raise ValueError(f"{label} must not be empty")
    cover_heading, title_lines = cover_title(args)
    layout = args.cover_layout
    if layout == "auto":
        layout = "fullbleed" if args.cover_image else "typographic"
    if layout in ("fullbleed", "framed") and not args.cover_image:
        raise ValueError(f"--cover-layout {layout} requires --cover-image")
    if layout == "typographic" and args.cover_image:
        raise ValueError("--cover-layout typographic is image-free; remove --cover-image")
    if args.cover_title_position != "top" and layout != "fullbleed":
        raise ValueError("--cover-title-position bottom requires the fullbleed layout")
    raw = source.read_bytes()
    preamble, chapters = parse_manuscript(raw.decode("utf-8-sig"))
    font_path = args.font_file.resolve() if args.font_file else None
    if font_path and not font_path.is_file():
        raise ValueError("--font-file must identify an existing local font file")
    if font_path and font_path in (output, manifest_path):
        raise ValueError("output must not overwrite the font file")

    image_path = args.cover_image.resolve() if args.cover_image else None
    image_bytes = None
    if image_path:
        from PIL import Image
        if image_path in (source, output, manifest_path):
            raise ValueError("cover image must be distinct from manuscript and output files")
        image_bytes = image_path.read_bytes()
        try:
            with Image.open(BytesIO(image_bytes)) as picture:
                if picture.format not in ("PNG", "JPEG", "WEBP"):
                    raise ValueError("cover image must be PNG, JPEG or WebP")
                picture.verify()
        except (OSError, SyntaxError) as error:
            raise ValueError("invalid cover image") from error
    resources = {font_path.as_uri(): font_path.read_bytes()} if font_path else {}
    if image_path:
        resources[image_path.as_uri()] = image_bytes

    class LocalAssets(URLFetcher):
        def fetch(self, url, headers=None):
            if url in resources:
                return URLFetcherResponse(url, resources[url])
            raise ValueError("external resource fetching is disabled")

    family = "BookLocalFont" if font_path else args.font_family
    font_css = ("@font-face { font-family: BookLocalFont; src: url("
                + css_string(font_path.as_uri()) + "); }\n") if font_path else ""
    style = font_css + "html { font-family: " + css_string(family) + ", serif; }\n" + CSS
    style += """
@page { background: %(paper_color)s;
  @bottom-center { color: %(text_color)s; }
}
@page cover { background: %(cover_background)s; }
html, .credits { color: %(text_color)s; }
h1, h2, .titlepage .subtitle, .toc a::after, .scene { color: %(heading_color)s; }
.cover, .cover h1, .cover .subtitle { color: %(cover_text_color)s; }
.ornament, .rule { border-color: %(accent_color)s; }
.cover-art { display: block; width: 100%%; height: 85mm; object-fit: contain; }
.art-frame { box-sizing: border-box; width: 70mm; max-width: 100%%;
  border: 0.6pt solid %(accent_color)s; padding: 3mm; margin: 0 auto 10mm; }
.framed .cover { padding-top: 0; }
.framed .cover h1 { font-size: 25pt; }
.cover .subtitle { margin-top: 5mm; }
.cover .author { margin-top: 9mm; }
.typographic .cover { padding-top: 40mm; }
.typographic .cover h1 { font-size: 31pt; line-height: 1.4; }
.typographic .ornament { width: 24mm; height: 0; border: none; border-top: 0.7pt solid %(accent_color)s;
  border-radius: 0; margin-bottom: 14mm; }
.typographic .cover .author { margin-top: 19mm; }
.fullbleed .cover { box-sizing: border-box; min-height: 210mm; padding: 17mm 13mm;
  display: flex; flex-direction: column; justify-content: flex-start; }
.fullbleed.bottom .cover { justify-content: flex-end; }
.fullbleed .cover-copy { padding: 8mm 7mm; border-top: 0.7pt solid %(accent_color)s; }
.fullbleed .cover h1 { font-size: 32pt; line-height: 1.35; }
.fullbleed .cover .author { margin-top: 7mm; font-size: 10pt; }
.long-title .cover h1 { font-size: 18pt; }
.long-title .cover { padding-top: 8mm; }
.long-title .cover-art { height: 43mm; }
.long-title .art-frame { margin-bottom: 5mm; }
.long-title.framed .cover h1 { font-size: 16pt; }
.long-title.fullbleed .cover h1 { font-size: 22pt; }
""" % palette
    if layout == "fullbleed":
        style += ("@page cover { margin: 0; background-image: url(" + css_string(image_path.as_uri())
                  + "); background-size: cover; background-position: center; }\n"
                  + ".fullbleed .cover-copy { background: " + cover_panel(palette) + "; }\n")
    title, author, subtitle = map(html.escape, (args.title, args.author, args.subtitle))
    subtitle_html = f'<p class="subtitle">{subtitle}</p>' if subtitle else ""
    artwork = (f'<div class="art-frame"><img class="cover-art" src="{html.escape(image_path.as_uri(), quote=True)}" '
               f'alt="{html.escape(args.cover_image_alt, quote=True)}"></div>') if layout == "framed" else (
                   '<div class="ornament"></div>' if layout == "typographic" else "")
    front = (f'<section class="cover">{artwork}<div class="cover-copy"><h1>{cover_heading}</h1>'
             f'{subtitle_html}<p class="author">{author}</p></div></section>'
             f'<section class="titlepage" id="titlepage"><h1>{title}</h1>{subtitle_html}<div class="rule"></div>'
             f'<p class="credits">{author}<br>A5 · PDF 독서본</p></section>')
    if preamble:
        front += '<section class="preamble">' + "".join(preamble) + "</section>"
    toc = '<nav class="toc"><h2 id="contents">차례</h2>'
    body = ""
    for index, chapter in enumerate(chapters):
        key = f"chapter-{index + 1}"
        label = html.escape(chapter["title"])
        toc += f'<a href="#{key}">{label}</a>'
        body += (f'<section class="chapter"><h2 id="{key}">{label}</h2>'
                 + "".join(chapter["blocks"]) + "</section>")
    body_class = "long-title" if len(args.title) > (32 if image_path else 80) else ""
    body_class += f" {layout} {args.cover_title_position}"
    document = (f'<!doctype html><html lang="ko"><head><meta charset="utf-8">'
                f'<title>{title}</title><meta name="author" content="{author}">'
                f'<style>{style}</style></head><body class="{body_class}">{front}{toc}</nav>{body}</body></html>')
    rendered = HTML(string=document, url_fetcher=LocalAssets(fail_on_errors=True)).render(font_config=FontConfiguration())
    anchors = {key: index + 1 for index, page in enumerate(rendered.pages) for key in page.anchors}
    if anchors["titlepage"] != 2:
        raise ValueError("cover exceeds one page; shorten the title, subtitle or author label")
    pdf = rendered.write_pdf()
    reader = PdfReader(BytesIO(pdf))
    chapter_pages = [{"title": chapter["title"], "pdf_page": anchors[f"chapter-{index + 1}"]}
                     for index, chapter in enumerate(chapters)]
    if len(reader.pages) != len(rendered.pages):
        raise ValueError("PDF page count differs from layout")
    manifest = {"source_sha256": hashlib.sha256(raw).hexdigest(),
                "page_count": len(reader.pages), "contents_pdf_page": anchors["contents"],
                "chapters": chapter_pages, "page_numbering": "physical PDF pages, starting at 1",
                "design": {"genre": args.genre, "palette": palette,
                           "cover_layout": layout, "cover_title_position": args.cover_title_position,
                           "cover_title_lines": title_lines,
                           "cover_image_sha256": hashlib.sha256(image_bytes).hexdigest() if image_bytes else None}}
    output.parent.mkdir(parents=True, exist_ok=True)
    # Write complete temporary files first; invalid manuscripts never touch outputs.
    for destination, data in [(output, pdf), (manifest_path, (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))]:
        with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as handle:
            temporary = Path(handle.name)
            try:
                handle.write(data)
                handle.close()
                temporary.replace(destination)
            finally:
                temporary.unlink(missing_ok=True)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manuscript", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--title", required=True)
    parser.add_argument("--author", required=True)
    parser.add_argument("--subtitle", default="")
    parser.add_argument("--font-family", default="Noto Serif CJK KR")
    parser.add_argument("--font-file", type=Path)
    parser.add_argument("--genre", choices=PALETTES, default="classic", help="Starting color palette; individual colors can be overridden")
    for field in COLOR_FIELDS:
        parser.add_argument("--" + field.replace("_", "-"), help="Override using #RRGGBB")
    parser.add_argument("--cover-image", type=Path, help="Local PNG, JPEG or WebP illustration (optional)")
    parser.add_argument("--cover-image-alt", default="표지 삽화")
    parser.add_argument("--cover-layout", choices=("auto", "fullbleed", "framed", "typographic"), default="auto",
                        help="auto uses fullbleed with an image, otherwise typographic")
    parser.add_argument("--cover-title-position", choices=("top", "bottom"), default="top",
                        help="Title panel position on a fullbleed cover")
    parser.add_argument("--cover-title-lines", help="Optional 1-4 title lines separated by |; must match --title")
    args = parser.parse_args()
    try:
        manifest = build(args)
    except (ValueError, OSError, ImportError) as error:
        parser.exit(2, f"error: {error}\n")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
