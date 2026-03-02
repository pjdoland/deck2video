"""Tests for deck2video.slidev_parser — Slidev markdown parsing."""

from __future__ import annotations

import pytest

from deck2video.slidev_parser import parse_slidev


class TestBasicParsing:
    def test_single_slide(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text("---\ntitle: Test\n---\n\n# Hello World\n")
        slides = parse_slidev(str(md))
        assert len(slides) == 1
        assert slides[0].index == 1
        assert "# Hello World" in slides[0].body

    def test_multiple_slides(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text(
            "---\ntitle: Test\n---\n\n# Slide 1\n\n---\n\n# Slide 2\n\n---\n\n# Slide 3\n"
        )
        slides = parse_slidev(str(md))
        assert len(slides) == 3
        assert slides[0].index == 1
        assert slides[1].index == 2
        assert slides[2].index == 3

    def test_no_separators_raises(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text("# Just some markdown\n")
        with pytest.raises(ValueError, match="No slide separators"):
            parse_slidev(str(md))


class TestSpeakerNotes:
    def test_notes_extracted_from_comment(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text("---\ntitle: Test\n---\n\n# Slide\n\n<!-- This is a note -->\n")
        slides = parse_slidev(str(md))
        assert slides[0].notes == "This is a note"

    def test_multiline_notes(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text(
            "---\ntitle: Test\n---\n\n# Slide\n\n"
            "<!-- First line.\nSecond line. -->\n"
        )
        slides = parse_slidev(str(md))
        assert "First line." in slides[0].notes
        assert "Second line." in slides[0].notes

    def test_slide_without_notes(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text("---\ntitle: Test\n---\n\n# No notes here\n")
        slides = parse_slidev(str(md))
        assert slides[0].notes is None

    def test_empty_comment_produces_empty_string(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text("---\ntitle: Test\n---\n\n# Slide\n\n<!--  -->\n")
        slides = parse_slidev(str(md))
        assert slides[0].notes == ""

    def test_multiple_comments_joined(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text(
            "---\ntitle: Test\n---\n\n# Slide\n\n"
            "<!-- First note -->\n<!-- Second note -->\n"
        )
        slides = parse_slidev(str(md))
        assert slides[0].notes == "First note\nSecond note"


class TestVideoDirective:
    def test_video_directive_extracted(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text("---\ntitle: Test\n---\n\n# Slide\n\n<!-- video: demo.mov -->\n")
        slides = parse_slidev(str(md))
        assert slides[0].video == "demo.mov"
        assert slides[0].notes is None

    def test_video_and_notes(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text(
            "---\ntitle: Test\n---\n\n# Slide\n\n"
            "<!-- video: demo.mov -->\n<!-- Speaker notes here -->\n"
        )
        slides = parse_slidev(str(md))
        assert slides[0].video == "demo.mov"
        assert slides[0].notes == "Speaker notes here"


class TestPerSlideFrontmatter:
    def test_frontmatter_stripped_from_body(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text(
            "---\ntitle: Test\n---\n\n"
            "layout: center\nclass: text-center\n\n# Centered Slide\n"
        )
        slides = parse_slidev(str(md))
        assert "layout:" not in slides[0].body
        assert "class:" not in slides[0].body
        assert "# Centered Slide" in slides[0].body


class TestCodeFenceSeparators:
    def test_dash_inside_code_fence_not_a_separator(self, tmp_path):
        """--- inside a fenced code block must not be treated as a slide separator."""
        md = tmp_path / "deck.md"
        md.write_text(
            "---\ntitle: Test\n---\n\n"
            "# Slide 1\n\n"
            "```yaml\n---\ntheme: my-theme\n---\n```\n\n"
            "---\n\n"
            "# Slide 2\n"
        )
        slides = parse_slidev(str(md))
        assert len(slides) == 2
        assert "```yaml" in slides[0].body
        assert "---" in slides[0].body  # restored in body
        assert "# Slide 2" in slides[1].body

    def test_dash_inside_tilde_fence_not_a_separator(self, tmp_path):
        """--- inside a ~~~ fenced block must not be treated as a slide separator."""
        md = tmp_path / "deck.md"
        md.write_text(
            "---\ntitle: Test\n---\n\n"
            "# Slide 1\n\n"
            "~~~yaml\n---\nkey: value\n---\n~~~\n\n"
            "---\n\n"
            "# Slide 2\n"
        )
        slides = parse_slidev(str(md))
        assert len(slides) == 2


class TestNoMarpDirectiveFiltering:
    def test_marp_style_comments_kept_as_notes(self, tmp_path):
        """Slidev parser should NOT filter Marp-style directives as the Marp parser does."""
        md = tmp_path / "deck.md"
        md.write_text(
            "---\ntitle: Test\n---\n\n# Slide\n\n<!-- _class: lead -->\n"
        )
        slides = parse_slidev(str(md))
        # In Slidev mode, this comment is treated as a note, not filtered
        assert slides[0].notes == "_class: lead"
