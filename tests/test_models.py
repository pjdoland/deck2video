"""Tests for deck2video.models — Step dataclass, click splitting, and expansion."""

from __future__ import annotations

import pytest

from deck2video.models import (
    CLICK_RE,
    Slide,
    Step,
    expand_slides_to_steps,
    split_notes_on_clicks,
)


# ---------------------------------------------------------------------------
# split_notes_on_clicks
# ---------------------------------------------------------------------------

class TestSplitNotesOnClicks:
    def test_no_markers_returns_single_element(self):
        result = split_notes_on_clicks("Hello world.")
        assert result == ["Hello world."]

    def test_none_returns_none_list(self):
        result = split_notes_on_clicks(None)
        assert result == [None]

    def test_one_marker_splits_into_two(self):
        result = split_notes_on_clicks("First part.\n[click]\nSecond part.")
        assert result == ["First part.", "Second part."]

    def test_multiple_markers(self):
        result = split_notes_on_clicks("A.\n[click]\nB.\n[click]\nC.")
        assert result == ["A.", "B.", "C."]

    def test_whitespace_only_fragment_becomes_none(self):
        result = split_notes_on_clicks("[click]\nSome text.")
        assert result == [None, "Some text."]

    def test_trailing_click_produces_none(self):
        result = split_notes_on_clicks("Some text.\n[click]")
        assert result == ["Some text.", None]

    def test_case_insensitive(self):
        result = split_notes_on_clicks("A.\n[CLICK]\nB.")
        assert result == ["A.", "B."]

    def test_mixed_case(self):
        result = split_notes_on_clicks("A.\n[Click]\nB.")
        assert result == ["A.", "B."]

    def test_surrounding_whitespace_stripped(self):
        result = split_notes_on_clicks("  Hello.  \n[click]\n  World.  ")
        assert result == ["Hello.", "World."]

    def test_empty_string_returns_none_list(self):
        result = split_notes_on_clicks("")
        assert result == [None]

    def test_click_with_spaces_on_line(self):
        result = split_notes_on_clicks("A.\n  [click]  \nB.")
        assert result == ["A.", "B."]


# ---------------------------------------------------------------------------
# Step dataclass
# ---------------------------------------------------------------------------

class TestStepDataclass:
    def test_field_access(self):
        step = Step(index=3, slide_index=2, click=1, notes="Hello.")
        assert step.index == 3
        assert step.slide_index == 2
        assert step.click == 1
        assert step.notes == "Hello."
        assert step.video is None

    def test_video_default_is_none(self):
        step = Step(index=1, slide_index=1, click=0, notes=None)
        assert step.video is None

    def test_video_can_be_set(self):
        step = Step(index=1, slide_index=1, click=0, notes=None, video="demo.mov")
        assert step.video == "demo.mov"


# ---------------------------------------------------------------------------
# expand_slides_to_steps
# ---------------------------------------------------------------------------

class TestExpandSlidesToSteps:
    def test_slide_without_clicks_becomes_one_step(self):
        slides = [Slide(index=1, body="# Slide", notes="Hello.")]
        steps = expand_slides_to_steps(slides)
        assert len(steps) == 1
        assert steps[0].index == 1
        assert steps[0].slide_index == 1
        assert steps[0].click == 0
        assert steps[0].notes == "Hello."

    def test_slide_with_one_click_becomes_two_steps(self):
        slides = [Slide(index=1, body="# Slide", notes="First.\n[click]\nSecond.")]
        steps = expand_slides_to_steps(slides)
        assert len(steps) == 2
        assert steps[0].click == 0
        assert steps[0].notes == "First."
        assert steps[1].click == 1
        assert steps[1].notes == "Second."

    def test_slide_with_no_notes_becomes_one_silent_step(self):
        slides = [Slide(index=1, body="# Slide", notes=None)]
        steps = expand_slides_to_steps(slides)
        assert len(steps) == 1
        assert steps[0].notes is None

    def test_video_slide_produces_one_step(self):
        slides = [Slide(index=1, body="# Slide", notes="Some notes.", video="demo.mov")]
        steps = expand_slides_to_steps(slides)
        assert len(steps) == 1
        assert steps[0].video == "demo.mov"
        assert steps[0].notes == "Some notes."

    def test_video_slide_click_markers_stripped(self):
        slides = [Slide(index=1, body="# Slide", notes="A.\n[click]\nB.", video="demo.mov")]
        steps = expand_slides_to_steps(slides)
        assert len(steps) == 1
        assert "[click]" not in (steps[0].notes or "")

    def test_video_slide_with_only_click_notes_becomes_none(self):
        slides = [Slide(index=1, body="# Slide", notes="[click]", video="demo.mov")]
        steps = expand_slides_to_steps(slides)
        assert len(steps) == 1
        assert steps[0].notes is None

    def test_sequential_indexing_across_slides(self):
        slides = [
            Slide(index=1, body="A", notes="A.\n[click]\nB."),  # 2 steps
            Slide(index=2, body="B", notes="C."),               # 1 step
            Slide(index=3, body="C", notes="D.\n[click]\nE."),  # 2 steps
        ]
        steps = expand_slides_to_steps(slides)
        assert len(steps) == 5
        assert [s.index for s in steps] == [1, 2, 3, 4, 5]

    def test_slide_index_preserved_across_steps(self):
        slides = [
            Slide(index=1, body="A", notes="A.\n[click]\nB."),
            Slide(index=2, body="B", notes="C."),
        ]
        steps = expand_slides_to_steps(slides)
        assert steps[0].slide_index == 1
        assert steps[1].slide_index == 1
        assert steps[2].slide_index == 2

    def test_mixed_video_and_click_slides(self):
        slides = [
            Slide(index=1, body="A", notes="A.\n[click]\nB."),     # 2 steps
            Slide(index=2, body="B", notes="C.", video="v.mov"),    # 1 step (video)
            Slide(index=3, body="C", notes="D."),                   # 1 step
        ]
        steps = expand_slides_to_steps(slides)
        assert len(steps) == 4
        # steps[0] = slide 1 click 0, steps[1] = slide 1 click 1
        # steps[2] = slide 2 (video), steps[3] = slide 3
        assert steps[2].video == "v.mov"
        assert steps[3].video is None

    def test_empty_slides_list(self):
        assert expand_slides_to_steps([]) == []

    def test_no_clicks_returns_same_count_as_slides(self):
        slides = [
            Slide(index=1, body="A", notes="A."),
            Slide(index=2, body="B", notes="B."),
            Slide(index=3, body="C", notes=None),
        ]
        steps = expand_slides_to_steps(slides)
        assert len(steps) == len(slides)
