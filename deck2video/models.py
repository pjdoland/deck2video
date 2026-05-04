"""Shared data models and parsing constants."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Slide:
    index: int
    body: str
    notes: str | None
    video: str | None = None


# Matches HTML comments, including multi-line ones.
COMMENT_RE = re.compile(r"<!--(.*?)-->", re.DOTALL)

# Video directive: <!-- video: path/to/file.mov -->
VIDEO_RE = re.compile(r"^\s*video:\s*(.+?)\s*$", re.IGNORECASE)

# Click marker: [click] on its own line (case-insensitive)
CLICK_RE = re.compile(r"^\s*\[click\]\s*$", re.MULTILINE | re.IGNORECASE)


def split_notes_on_clicks(notes: str | None) -> list[str | None]:
    """Split notes text on [click] markers.

    Returns a list where each element is either a text fragment or None
    (for empty/whitespace-only fragments). None input returns [None].
    Notes without [click] return a single-element list.
    """
    if notes is None:
        return [None]
    fragments = CLICK_RE.split(notes)
    result = []
    for f in fragments:
        stripped = f.strip()
        result.append(stripped if stripped else None)
    return result


@dataclass
class Step:
    index: int          # sequential 1-based position in flat list (for file naming)
    slide_index: int    # original 1-based slide number
    click: int          # 0 = initial state, 1 = after click 1, etc.
    notes: str | None
    video: str | None = None


def expand_slides_to_steps(slides: list[Slide]) -> list[Step]:
    """Expand a list of slides into a flat list of Steps.

    Each [click] marker in a slide's notes creates an additional step.
    Video slides produce exactly one step (no click expansion).
    """
    steps: list[Step] = []
    step_index = 1
    for slide in slides:
        if slide.video is not None:
            # Video slides: one step only, strip [click] markers from notes
            notes = slide.notes
            if notes is not None:
                notes = CLICK_RE.sub("", notes).strip() or None
            steps.append(Step(
                index=step_index,
                slide_index=slide.index,
                click=0,
                notes=notes,
                video=slide.video,
            ))
            step_index += 1
        else:
            fragments = split_notes_on_clicks(slide.notes)
            for click, fragment in enumerate(fragments):
                steps.append(Step(
                    index=step_index,
                    slide_index=slide.index,
                    click=click,
                    notes=fragment,
                ))
                step_index += 1
    return steps
