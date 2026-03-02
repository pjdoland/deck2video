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

# Placeholder used to hide --- inside code fences during splitting.
_FENCE_PLACEHOLDER = "\x00DECK2VIDEO_SEP\x00"


def _mask_fenced_separators(raw: str) -> str:
    """Replace ``---`` lines inside fenced code blocks with a placeholder.

    This prevents code examples that contain YAML frontmatter (which starts
    and ends with ``---``) from being mis-counted as slide separators.
    """
    lines = raw.split("\n")
    result: list[str] = []
    in_fence = False
    fence_char = ""
    fence_len = 0

    for line in lines:
        if not in_fence:
            m = re.match(r"^(`{3,}|~{3,})", line)
            if m:
                in_fence = True
                fence_char = m.group(1)[0]
                fence_len = len(m.group(1))
            result.append(line)
        else:
            # A closing fence: same character, at least as many chars, nothing after
            m = re.match(r"^(" + re.escape(fence_char) + r"+)\s*$", line)
            if m and len(m.group(1)) >= fence_len:
                in_fence = False
                result.append(line)
            else:
                result.append(_FENCE_PLACEHOLDER if re.match(r"^---\s*$", line) else line)

    return "\n".join(result)


def parse_slidev(path: str) -> list[Slide]:
    """Parse a Slidev markdown file into a list of Slide objects.

    The file is split on ``---`` delimiters.  The first ``---`` block is
    treated as YAML front matter and is skipped.  Per-slide frontmatter
    (key: value lines at the start of each slide) is stripped from the body.
    HTML comments are extracted as speaker notes, except for video directives.
    """
    with open(path, encoding="utf-8") as f:
        raw = f.read()

    # Mask --- inside fenced code blocks so they aren't treated as slide separators.
    masked = _mask_fenced_separators(raw)

    # Split on Slidev slide separators.  A separator is either a bare "---" line
    # or a "---" followed by per-slide YAML frontmatter and a closing "---":
    #   \n---\n
    #   \n---\n<key: value lines>\n---\n
    # Both forms count as ONE slide boundary so frontmatter slides aren't
    # counted as extra slides.
    parts = re.split(
        r"\n---\s*\n(?:(?:[ \t]*[\w][\w-]*[ \t]*:.*\n)+---\s*\n)?", masked
    )

    # Restore any masked separators in the resulting parts.
    parts = [p.replace(_FENCE_PLACEHOLDER, "---") for p in parts]

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
