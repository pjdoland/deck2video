"""Slidev markdown parser — splits slides and extracts speaker notes."""

from __future__ import annotations

import logging
import re

from .models import COMMENT_RE, VIDEO_RE, Slide

logger = logging.getLogger(__name__)

# Slidev per-slide frontmatter: a YAML block at the very start of a slide
# (between --- lines, but we've already split on --- so it appears at the
# top of the slide text as key: value lines before any markdown content).
_SLIDE_FRONTMATTER_RE = re.compile(
    r"\A(\s*\w[\w-]*\s*:.*\n)*", re.MULTILINE
)


def parse_slidev(path: str) -> list[Slide]:
    """Parse a Slidev markdown file into a list of Slide objects.

    The file is split on ``---`` delimiters.  The first ``---`` block is
    treated as YAML front matter and is skipped.  Per-slide frontmatter
    (key: value lines at the start of each slide) is stripped from the body.
    HTML comments are extracted as speaker notes, except for video directives.
    """
    with open(path, encoding="utf-8") as f:
        raw = f.read()

    # Split on Slidev slide separators.  A separator is either a bare "---" line
    # or a "---" followed by per-slide YAML frontmatter and a closing "---":
    #   \n---\n
    #   \n---\n<key: value lines>\n---\n
    # Both forms count as ONE slide boundary so frontmatter slides aren't
    # counted as extra slides.
    parts = re.split(
        r"\n---\s*\n(?:(?:[ \t]*[\w][\w-]*[ \t]*:.*\n)+---\s*\n)?", raw
    )

    # The first part is the YAML front-matter block — skip it.
    if len(parts) < 2:
        raise ValueError(
            "No slide separators (---) found. Is this a valid Slidev deck?"
        )

    slide_parts = parts[1:]
    slides: list[Slide] = []
    logger.debug("Parsing %s: found %d slide block(s)", path, len(slide_parts))

    for i, part in enumerate(slide_parts):
        notes_fragments: list[str] = []
        video_path: str | None = None

        def _collect(m: re.Match) -> str:
            nonlocal video_path
            content = m.group(1).strip()
            # Extract video directive
            video_match = VIDEO_RE.match(content)
            if video_match:
                video_path = video_match.group(1)
                return ""
            notes_fragments.append(content)
            return ""

        # Remove HTML comments (collecting notes and video directives)
        body = COMMENT_RE.sub(_collect, part)

        # Strip per-slide frontmatter from the body
        body = _SLIDE_FRONTMATTER_RE.sub("", body).strip()

        notes = "\n".join(notes_fragments) if notes_fragments else None

        slides.append(Slide(index=i + 1, body=body, notes=notes, video=video_path))
        notes_len = len(notes) if notes else 0
        logger.debug("  Slide %d: notes=%d chars, video=%s", i + 1, notes_len, video_path)

    return slides
