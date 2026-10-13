"""Regression cases found by independently exercising the page-art workflow."""
import base64
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import pymupdf


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/novel-book-writer/scripts"
SPEC = importlib.util.spec_from_file_location("page_art_regressions", SCRIPTS / "page_art.py")
PAGE_ART = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PAGE_ART)
# Fixed binary test fixture, restored locally; no image-generation service is used.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class PageArtRegressions(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="page-art-regressions-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def build(self, name, sections, *, preamble="", art=True, success=True):
        source = self.root / f"{name}.md"
        source.write_text("# Test\n\n" + preamble + "".join(
            f"## {heading}\n\n{prose}\n\n" for heading, prose in sections
        ), encoding="utf-8")
        pdf = self.root / f"{name}.pdf"
        command = [sys.executable, "-B", str(SCRIPTS / "build_book.py"),
                   "--manuscript", str(source), "--output", str(pdf),
                   "--title", "Test", "--author", "Regression fixture"]
        if art:
            command += ["--page-art-height-mm", "52"]
        result = subprocess.run(command, capture_output=True, text=True)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertFalse(pdf.exists())
            self.assertFalse(pdf.with_suffix(".manifest.json").exists())
        return pdf

    def save_map(self, mapping, data):
        mapping.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def approve_fixture(self, mapping, item):
        """Simulate recorded review data; this does not claim a visual review."""
        asset = mapping.parent / item["image"]
        asset.parent.mkdir(parents=True, exist_ok=True)
        asset.write_bytes(PNG)
        item.update(scene="Fixture scene", characters=["Mina"], prompt="Fixture prompt")
        item["review"] = {
            "status": "pass", "notes": "Automated fixture only, not a visual review",
            "text_sha256": item["text_sha256"],
            "image_sha256": PAGE_ART.sha256(PNG),
            "scene_sha256": PAGE_ART.scene_digest(item),
        }

    def approved_map(self, pdf, name="old-map"):
        mapping = self.root / "assets" / f"{name}.json"
        data = PAGE_ART.prepare(pdf, mapping)
        for item in data["pages"]:
            self.approve_fixture(mapping, item)
        self.save_map(mapping, data)
        return mapping, data

    def test_moved_page_does_not_share_new_image_path(self):
        old_pdf = self.build("old", [("Alpha", "Original Alpha."), ("Beta", "Original Beta.")])
        old_map, old_data = self.approved_map(old_pdf)
        old_image = (old_map.parent / old_data["pages"][0]["image"]).resolve()
        new_pdf = self.build("new", [("Gamma", "New Gamma."), ("Alpha", "Original Alpha.")])
        new_map = old_map.with_name("new-map.json")
        new_data = PAGE_ART.prepare(new_pdf, new_map, previous=old_map)
        images = [(new_map.parent / item["image"]).resolve() for item in new_data["pages"]]
        self.assertEqual(len(images), 2)
        self.assertEqual(len(set(images)), 2)
        self.assertEqual(images[1], old_image)
        self.assertFalse(images[0].exists())
        self.assertEqual(old_image.read_bytes(), PNG)

    def test_previous_context_change_requires_review_of_unchanged_page(self):
        old_pdf = self.build("context-old", [("Setup", "Mina wore a red coat."),
                                             ("Entrance", "She entered the room.")])
        old_map, old_data = self.approved_map(old_pdf)
        item = old_data["pages"][1]
        item.update(scene="Mina enters wearing the red coat from the previous page.",
                    prompt="Mina enters in a red coat.")
        item["review"]["scene_sha256"] = PAGE_ART.scene_digest(item)
        self.save_map(old_map, old_data)
        new_pdf = self.build("context-new", [("Setup", "Mina wore a blue coat."),
                                             ("Entrance", "She entered the room.")])
        new_map = old_map.with_name("context-new-map.json")
        new_data = PAGE_ART.prepare(new_pdf, new_map, previous=old_map)
        reused = new_data["pages"][1]
        self.assertEqual(reused["text_sha256"], old_data["pages"][1]["text_sha256"])
        self.assertEqual(reused["image"], old_data["pages"][1]["image"])
        self.assertEqual(reused["review"]["status"], "pending")
        self.approve_fixture(new_map, new_data["pages"][0])
        self.save_map(new_map, new_data)
        output = self.root / "context-final.pdf"
        with self.assertRaisesRegex(ValueError, "pending|stale"):
            PAGE_ART.apply(new_pdf, new_map, output)
        self.assertFalse(output.exists())

    def test_unchanged_manuscript_can_reuse_existing_review(self):
        pdf = self.build("unchanged", [("Start", "Mina entered the room.")])
        old_map, old_data = self.approved_map(pdf)
        new_map = old_map.with_name("same-source-map.json")
        data = PAGE_ART.prepare(pdf, new_map, previous=old_map)
        self.assertEqual(data["pages"][0]["review"], old_data["pages"][0]["review"])
        result = PAGE_ART.apply(pdf, new_map, self.root / "unchanged-final.pdf")
        self.assertTrue(result["page_art_complete"])

    def test_changed_scene_characters_or_prompt_invalidates_review(self):
        pdf = self.build("scene", [("Start", "Mina entered the room.")])
        mapping, original = self.approved_map(pdf)
        for key, replacement in (("scene", "Mina leaves the house."),
                                 ("characters", ["Jin"]),
                                 ("prompt", "Draw an entirely different scene.")):
            with self.subTest(field=key):
                data = deepcopy(original)
                data["pages"][0][key] = replacement
                changed_map = mapping.with_name(f"changed-{key}.json")
                self.save_map(changed_map, data)
                output = self.root / f"changed-{key}.pdf"
                with self.assertRaisesRegex(ValueError, "stale scene review"):
                    PAGE_ART.apply(pdf, changed_map, output)
                self.assertFalse(output.exists())

    def test_existing_pdf_or_manifest_is_preserved_by_default(self):
        pdf = self.build("preserve", [("Start", "Mina entered the room.")])
        mapping, _ = self.approved_map(pdf)
        sentinel = b"Existing original must be preserved"
        for suffix in (".pdf", ".manifest.json"):
            with self.subTest(existing=suffix):
                output = self.root / ("existing-pdf.pdf" if suffix == ".pdf" else "existing-manifest.pdf")
                existing = output if suffix == ".pdf" else output.with_suffix(suffix)
                other = output.with_suffix(".manifest.json") if suffix == ".pdf" else output
                existing.write_bytes(sentinel)
                with self.assertRaisesRegex(ValueError, "output exists"):
                    PAGE_ART.apply(pdf, mapping, output)
                self.assertEqual(existing.read_bytes(), sentinel)
                self.assertFalse(other.exists())

    def test_explicit_overwrite_replaces_final_files_and_preserves_source_pdf(self):
        pdf = self.build("overwrite", [("Start", "Mina entered the room.")])
        source_bytes = pdf.read_bytes()
        mapping, _ = self.approved_map(pdf)
        output = self.root / "final.pdf"
        output.write_bytes(b"old final")
        output.with_suffix(".manifest.json").write_text("old manifest")
        result = PAGE_ART.apply(pdf, mapping, output, overwrite=True)
        self.assertTrue(result["page_art_complete"])
        self.assertEqual(pdf.read_bytes(), source_bytes)
        self.assertEqual(json.loads(output.with_suffix(".manifest.json").read_text()), result)
        with pymupdf.open(pdf) as before, pymupdf.open(output) as after:
            self.assertEqual(len(before), len(after))
            self.assertEqual(before.get_toc(), after.get_toc())
            self.assertEqual([p.get_text() for p in before], [p.get_text() for p in after])

    def test_page_art_rejects_unmapped_preamble_prose(self):
        self.build("preamble-art", [("Start", "She searched for the letter.")],
                   preamble="Before the first chapter she lost the letter.\n\n", success=False)

    def test_regular_book_still_accepts_preamble_prose(self):
        pdf = self.build("preamble-regular", [("Start", "She searched for the letter.")],
                         preamble="Before the first chapter she lost the letter.\n\n", art=False)
        with pymupdf.open(pdf) as doc:
            self.assertIn("Before the first chapter", "".join(page.get_text() for page in doc))


if __name__ == "__main__":
    unittest.main()
