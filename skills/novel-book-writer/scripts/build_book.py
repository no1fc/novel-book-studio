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


def inline(text):
    escaped = html.escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", escaped)
    return escaped.replace("\n", "<br>")


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
p { margin: 0 0 2mm; text-indent: 1em; orphans: 3; widows: 3; }
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

    source = args.manuscript.resolve()
    output = args.output.resolve()
    manifest_path = output.with_suffix(".manifest.json")
    if output == source or manifest_path == source or output == manifest_path:
        raise ValueError("output PDF and manifest must be distinct from the input manuscript")
    if output.suffix.lower() != ".pdf":
        raise ValueError("--output must have a .pdf suffix")
    for value, label in [(args.title, "title"), (args.author, "author"), (args.font_family, "font family")]:
        if not value.strip():
            raise ValueError(f"{label} must not be empty")
    raw = source.read_bytes()
    preamble, chapters = parse_manuscript(raw.decode("utf-8-sig"))
    font_path = args.font_file.resolve() if args.font_file else None
    if font_path and not font_path.is_file():
        raise ValueError("--font-file must identify an existing local font file")
    if font_path and font_path in (output, manifest_path):
        raise ValueError("output must not overwrite the font file")

    def fetch_font_only(url, **_kwargs):
        if font_path and url == font_path.as_uri():
            return {"string": font_path.read_bytes()}
        raise ValueError("external resource fetching is disabled")

    family = "BookLocalFont" if font_path else args.font_family
    font_css = ("@font-face { font-family: BookLocalFont; src: url("
                + css_string(font_path.as_uri()) + "); }\n") if font_path else ""
    style = font_css + "html { font-family: " + css_string(family) + ", serif; }\n" + CSS
    title, author, subtitle = map(html.escape, (args.title, args.author, args.subtitle))
    subtitle_html = f'<p class="subtitle">{subtitle}</p>' if subtitle else ""
    front = (f'<section class="cover"><div class="ornament"></div><h1>{title}</h1>'
             f'{subtitle_html}<p class="author">{author}</p></section>'
             f'<section class="titlepage"><h1>{title}</h1>{subtitle_html}<div class="rule"></div>'
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
    body_class = "long-title" if len(args.title) > 80 else ""
    document = (f'<!doctype html><html lang="ko"><head><meta charset="utf-8">'
                f'<title>{title}</title><meta name="author" content="{author}">'
                f'<style>{style}</style></head><body class="{body_class}">{front}{toc}</nav>{body}</body></html>')
    rendered = HTML(string=document, url_fetcher=fetch_font_only).render(font_config=FontConfiguration())
    anchors = {key: index + 1 for index, page in enumerate(rendered.pages) for key in page.anchors}
    pdf = rendered.write_pdf()
    reader = PdfReader(BytesIO(pdf))
    chapter_pages = [{"title": chapter["title"], "pdf_page": anchors[f"chapter-{index + 1}"]}
                     for index, chapter in enumerate(chapters)]
    if len(reader.pages) != len(rendered.pages):
        raise ValueError("PDF page count differs from layout")
    manifest = {"source_sha256": hashlib.sha256(raw).hexdigest(),
                "page_count": len(reader.pages), "contents_pdf_page": anchors["contents"],
                "chapters": chapter_pages, "page_numbering": "physical PDF pages, starting at 1"}
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
    args = parser.parse_args()
    try:
        manifest = build(args)
    except (ValueError, OSError, ImportError) as error:
        parser.exit(2, f"error: {error}\n")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
