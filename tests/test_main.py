"""Tests for deck2video.__main__ — CLI argument parsing and orchestration."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from deck2video.__main__ import _build_padding_list, _discover_temp_files, _parse_slide_list, _resolve_videos_and_fps
from deck2video.models import Slide, Step


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_pipeline(**overrides):
    """Return a dict of patches for all pipeline steps with sensible defaults."""
    defaults = {
        "deck2video.__main__.check_ffmpeg": MagicMock(),
        "deck2video.__main__.detect_format": MagicMock(return_value="marp"),
        "deck2video.__main__.parse_marp": MagicMock(return_value=[
            Slide(index=1, body="body", notes="Hello.", video=None),
            Slide(index=2, body="body", notes=None, video=None),
        ]),
        "deck2video.__main__.parse_slidev": MagicMock(return_value=[
            Slide(index=1, body="body", notes="Hello.", video=None),
            Slide(index=2, body="body", notes=None, video=None),
        ]),
        "deck2video.__main__.render_slides": MagicMock(return_value=[
            Path("/tmp/slides.001"), Path("/tmp/slides.002"),
        ]),
        "deck2video.__main__.render_slidev_slides": MagicMock(return_value=[
            Path("/tmp/slides.001.png"), Path("/tmp/slides.002.png"),
        ]),
        "deck2video.__main__.generate_audio_for_slides": MagicMock(return_value=[
            Path("/tmp/audio_001.wav"), Path("/tmp/audio_002.wav"),
        ]),
        "deck2video.__main__.assemble_video": MagicMock(),
        "deck2video.__main__.get_video_fps": MagicMock(return_value=30.0),
    }
    defaults.update(overrides)
    return defaults


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

class TestArgParsing:
    def test_input_required(self):
        with pytest.raises(SystemExit):
            from deck2video.__main__ import main
            with patch("sys.argv", ["deck2video"]):
                main()

    def test_missing_input_file_exits(self, tmp_path):
        from deck2video.__main__ import main
        with patch("sys.argv", ["deck2video", str(tmp_path / "nonexistent.md")]):
            with pytest.raises(SystemExit):
                main()

    def test_default_output_derives_from_input(self, tmp_path):
        md = tmp_path / "talk.md"
        md.write_text("---\nmarp: true\n---\n\n# Slide\n")

        patches = _patch_pipeline()
        with patch("sys.argv", ["deck2video", str(md)]):
            for target, mock in patches.items():
                with patch(target, mock):
                    pass

            # We need all patches active at once
            import contextlib
            with contextlib.ExitStack() as stack:
                mocks = {}
                for target, mock_obj in patches.items():
                    mocks[target] = stack.enter_context(patch(target, mock_obj))

                from deck2video.__main__ import main
                main()

                # assemble_video should be called with output = talk.mp4
                assemble_call = mocks["deck2video.__main__.assemble_video"]
                call_args = assemble_call.call_args
                output_arg = call_args[0][2]  # third positional arg
                assert output_arg == md.with_suffix(".mp4")


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------

class TestPipelineOrchestration:
    def _run_main(self, argv, patches):
        import contextlib
        from deck2video.__main__ import main

        with patch("sys.argv", argv):
            with contextlib.ExitStack() as stack:
                mocks = {}
                for target, mock_obj in patches.items():
                    mocks[target] = stack.enter_context(patch(target, mock_obj))
                main()
                return mocks

    def test_all_stages_called_in_order(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text("---\nmarp: true\n---\n\n# Slide\n")
        call_order = []

        patches = _patch_pipeline()
        for key in patches:
            original = patches[key]

            def make_side_effect(name, orig):
                def side_effect(*a, **kw):
                    call_order.append(name.split(".")[-1])
                    return orig.return_value
                return side_effect

            patches[key] = MagicMock(side_effect=make_side_effect(key, original))
            patches[key].return_value = original.return_value

        mocks = self._run_main(["deck2video", str(md)], patches)

        assert "check_ffmpeg" in call_order
        assert "parse_marp" in call_order
        assert "render_slides" in call_order
        assert "generate_audio_for_slides" in call_order
        assert "assemble_video" in call_order

        # Verify ordering
        assert call_order.index("parse_marp") < call_order.index("render_slides")
        assert call_order.index("render_slides") < call_order.index("generate_audio_for_slides")
        assert call_order.index("generate_audio_for_slides") < call_order.index("assemble_video")

    def test_pronunciations_loaded_and_passed(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text("---\nmarp: true\n---\n\n# Slide\n<!-- Hello. -->\n")
        pron = tmp_path / "pron.json"
        pron.write_text(json.dumps({"kubectl": "cube control"}))

        with patch("deck2video.__main__.load_pronunciations", return_value={"kubectl": "cube control"}) as mock_load, \
             patch("deck2video.__main__.compile_pronunciations", return_value=[]) as mock_compile:
            patches = _patch_pipeline()
            patches["deck2video.__main__.load_pronunciations"] = mock_load
            patches["deck2video.__main__.compile_pronunciations"] = mock_compile
            mocks = self._run_main(
                ["deck2video", str(md), "--pronunciations", str(pron)],
                patches,
            )
            mock_load.assert_called_once()

    def test_missing_pronunciations_file_exits(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text("---\nmarp: true\n---\n\n# Slide\n")

        with patch("sys.argv", ["deck2video", str(md), "--pronunciations", "/no/such/file.json"]):
            from deck2video.__main__ import main
            with patch("deck2video.__main__.check_ffmpeg"):
                with pytest.raises(SystemExit):
                    main()


# ---------------------------------------------------------------------------
# Video path resolution
# ---------------------------------------------------------------------------

class TestVideoPathResolution:
    def test_video_resolved_relative_to_input(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text("---\nmarp: true\n---\n\n# Slide\n<!-- video: assets/demo.mov -->\n")

        # Create the video file
        assets = tmp_path / "assets"
        assets.mkdir()
        video_file = assets / "demo.mov"
        video_file.touch()

        slides = [Slide(index=1, body="body", notes=None, video="assets/demo.mov")]
        patches = _patch_pipeline(**{
            "deck2video.__main__.parse_marp": MagicMock(return_value=slides),
            "deck2video.__main__.render_slides": MagicMock(return_value=[Path("/tmp/slides.001")]),
            "deck2video.__main__.generate_audio_for_slides": MagicMock(return_value=[Path("/tmp/audio_001.wav")]),
            "deck2video.__main__.get_video_fps": MagicMock(return_value=30.0),
        })

        import contextlib
        from deck2video.__main__ import main

        with patch("sys.argv", ["deck2video", str(md)]):
            with contextlib.ExitStack() as stack:
                mocks = {}
                for target, mock_obj in patches.items():
                    mocks[target] = stack.enter_context(patch(target, mock_obj))
                main()

                # assemble_video should receive the resolved video path
                assemble_call = mocks["deck2video.__main__.assemble_video"]
                call_kwargs = assemble_call.call_args[1]
                videos = call_kwargs["videos"]
                assert videos[0] == video_file.resolve()

    def test_missing_video_file_exits(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text("---\nmarp: true\n---\n\n# Slide\n")

        slides = [Slide(index=1, body="body", notes=None, video="missing.mov")]
        patches = _patch_pipeline(**{
            "deck2video.__main__.parse_marp": MagicMock(return_value=slides),
        })

        import contextlib
        from deck2video.__main__ import main

        with patch("sys.argv", ["deck2video", str(md)]):
            with contextlib.ExitStack() as stack:
                for target, mock_obj in patches.items():
                    stack.enter_context(patch(target, mock_obj))
                with pytest.raises(SystemExit):
                    main()

    def test_video_path_traversal_exits(self, tmp_path):
        """Video paths that escape the input directory should be rejected."""
        md = tmp_path / "deck.md"
        md.write_text("---\nmarp: true\n---\n\n# Slide\n")

        slides = [Slide(index=1, body="body", notes=None, video="../../etc/passwd")]
        patches = _patch_pipeline(**{
            "deck2video.__main__.parse_marp": MagicMock(return_value=slides),
        })

        import contextlib
        from deck2video.__main__ import main

        with patch("sys.argv", ["deck2video", str(md)]):
            with contextlib.ExitStack() as stack:
                for target, mock_obj in patches.items():
                    stack.enter_context(patch(target, mock_obj))
                with pytest.raises(SystemExit):
                    main()


# ---------------------------------------------------------------------------
# FPS auto-detection
# ---------------------------------------------------------------------------

class TestFpsAutoDetection:
    def test_explicit_fps_used(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text("---\nmarp: true\n---\n\n# Slide\n")

        patches = _patch_pipeline()

        import contextlib
        from deck2video.__main__ import main

        with patch("sys.argv", ["deck2video", str(md), "--fps", "60"]):
            with contextlib.ExitStack() as stack:
                mocks = {}
                for target, mock_obj in patches.items():
                    mocks[target] = stack.enter_context(patch(target, mock_obj))
                main()

                assemble_call = mocks["deck2video.__main__.assemble_video"]
                assert assemble_call.call_args[1]["fps"] == 60

    def test_default_fps_is_24(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text("---\nmarp: true\n---\n\n# Slide\n")

        patches = _patch_pipeline()

        import contextlib
        from deck2video.__main__ import main

        with patch("sys.argv", ["deck2video", str(md)]):
            with contextlib.ExitStack() as stack:
                mocks = {}
                for target, mock_obj in patches.items():
                    mocks[target] = stack.enter_context(patch(target, mock_obj))
                main()

                assemble_call = mocks["deck2video.__main__.assemble_video"]
                assert assemble_call.call_args[1]["fps"] == 24


# ---------------------------------------------------------------------------
# Audio padding
# ---------------------------------------------------------------------------

class TestBuildPaddingList:
    """Unit tests for _build_padding_list."""

    def _slide(self, index):
        return Slide(index=index, body="", notes=None)

    def _step(self, index, slide_index, click):
        return Step(index=index, slide_index=slide_index, click=click, notes=None)

    def test_all_slides_use_audio_padding(self):
        slides = [self._slide(1), self._slide(2), self._slide(3)]
        result = _build_padding_list(slides, audio_padding_ms=500, with_clicks_padding_ms=0)
        assert result == [500, 500, 500]

    def test_click_steps_use_with_clicks_padding(self):
        steps = [
            self._step(1, 1, 0),   # slide boundary
            self._step(2, 1, 1),   # click step
            self._step(3, 2, 0),   # slide boundary
            self._step(4, 2, 1),   # click step
        ]
        result = _build_padding_list(steps, audio_padding_ms=500, with_clicks_padding_ms=100)
        assert result == [500, 100, 500, 100]

    def test_no_clicks_same_as_scalar(self):
        steps = [self._step(1, 1, 0), self._step(2, 2, 0)]
        result = _build_padding_list(steps, audio_padding_ms=300, with_clicks_padding_ms=50)
        assert result == [300, 300]

    def test_with_clicks_padding_zero_by_default_effect(self):
        steps = [self._step(1, 1, 0), self._step(2, 1, 1), self._step(3, 2, 0)]
        result = _build_padding_list(steps, audio_padding_ms=400, with_clicks_padding_ms=0)
        assert result == [400, 0, 400]

    def test_marp_slides_no_click_attribute(self):
        slides = [self._slide(1), self._slide(2)]
        result = _build_padding_list(slides, audio_padding_ms=200, with_clicks_padding_ms=999)
        # Slide objects have no click attribute → always audio_padding_ms
        assert result == [200, 200]


class TestAudioPadding:
    def _run_main(self, argv, patches):
        import contextlib
        from deck2video.__main__ import main

        with patch("sys.argv", argv):
            with contextlib.ExitStack() as stack:
                mocks = {}
                for target, mock_obj in patches.items():
                    mocks[target] = stack.enter_context(patch(target, mock_obj))
                main()
                return mocks

    def test_default_padding_is_zero(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text("---\nmarp: true\n---\n\n# Slide\n")

        mocks = self._run_main(["deck2video", str(md)], _patch_pipeline())
        assemble_call = mocks["deck2video.__main__.assemble_video"]
        # Marp: 2 slides, both click=0, default padding 0 → [0, 0]
        assert assemble_call.call_args[1]["audio_padding_ms"] == [0, 0]

    def test_padding_passed_to_assembler(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text("---\nmarp: true\n---\n\n# Slide\n")

        mocks = self._run_main(
            ["deck2video", str(md), "--audio-padding", "400"],
            _patch_pipeline(),
        )
        assemble_call = mocks["deck2video.__main__.assemble_video"]
        # Marp: 2 slides → [400, 400]
        assert assemble_call.call_args[1]["audio_padding_ms"] == [400, 400]

    def test_with_clicks_padding_applies_to_click_steps(self, tmp_path):
        """Click steps use --with-clicks-audio-padding; slide boundaries use --audio-padding."""
        md = tmp_path / "deck.md"
        md.write_text("---\ntransition: fade\n---\n\n# Slide\n")

        slides = [
            Slide(index=1, body="# Slide 1", notes="A.\n[click]\nB.", video=None),
            Slide(index=2, body="# Slide 2", notes="C.", video=None),
        ]
        patches = _patch_pipeline(**{
            "deck2video.__main__.detect_format": MagicMock(return_value="slidev"),
            "deck2video.__main__.parse_slidev": MagicMock(return_value=slides),
            "deck2video.__main__.render_slidev_slides": MagicMock(return_value=[
                Path("/tmp/1.png"), Path("/tmp/1-1.png"), Path("/tmp/2.png"),
            ]),
            "deck2video.__main__.generate_audio_for_slides": MagicMock(return_value=[
                Path("/tmp/audio_001.wav"),
                Path("/tmp/audio_002.wav"),
                Path("/tmp/audio_003.wav"),
            ]),
        })
        mocks = self._run_main(
            ["deck2video", str(md), "--format", "slidev",
             "--audio-padding", "500", "--with-clicks-audio-padding", "100"],
            patches,
        )
        assemble_call = mocks["deck2video.__main__.assemble_video"]
        # steps: slide1/click0=500, slide1/click1=100, slide2/click0=500
        assert assemble_call.call_args[1]["audio_padding_ms"] == [500, 100, 500]


# ---------------------------------------------------------------------------
# Temp directory handling
# ---------------------------------------------------------------------------

class TestTempDirectory:
    def test_user_temp_dir_created(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text("---\nmarp: true\n---\n\n# Slide\n")
        custom_temp = tmp_path / "my_temp"

        patches = _patch_pipeline()

        import contextlib
        from deck2video.__main__ import main

        with patch("sys.argv", ["deck2video", str(md), "--temp-dir", str(custom_temp)]):
            with contextlib.ExitStack() as stack:
                for target, mock_obj in patches.items():
                    stack.enter_context(patch(target, mock_obj))
                main()

        assert custom_temp.exists()


# ---------------------------------------------------------------------------
# Format detection and routing
# ---------------------------------------------------------------------------

class TestFormatRouting:
    def _run_main(self, argv, patches):
        import contextlib
        from deck2video.__main__ import main

        with patch("sys.argv", argv):
            with contextlib.ExitStack() as stack:
                mocks = {}
                for target, mock_obj in patches.items():
                    mocks[target] = stack.enter_context(patch(target, mock_obj))
                main()
                return mocks

    def test_auto_format_calls_detect(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text("---\nmarp: true\n---\n\n# Slide\n")

        patches = _patch_pipeline()
        mocks = self._run_main(["deck2video", str(md)], patches)
        mocks["deck2video.__main__.detect_format"].assert_called_once()

    def test_explicit_marp_skips_detect(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text("---\nmarp: true\n---\n\n# Slide\n")

        patches = _patch_pipeline()
        mocks = self._run_main(["deck2video", str(md), "--format", "marp"], patches)
        mocks["deck2video.__main__.detect_format"].assert_not_called()

    def test_explicit_slidev_skips_detect(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text("---\ntransition: fade\n---\n\n# Slide\n")

        patches = _patch_pipeline()
        mocks = self._run_main(["deck2video", str(md), "--format", "slidev"], patches)
        mocks["deck2video.__main__.detect_format"].assert_not_called()

    def test_marp_format_uses_marp_pipeline(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text("---\nmarp: true\n---\n\n# Slide\n")

        patches = _patch_pipeline()
        mocks = self._run_main(["deck2video", str(md), "--format", "marp"], patches)
        mocks["deck2video.__main__.parse_marp"].assert_called_once()
        mocks["deck2video.__main__.render_slides"].assert_called_once()
        mocks["deck2video.__main__.parse_slidev"].assert_not_called()
        mocks["deck2video.__main__.render_slidev_slides"].assert_not_called()

    def test_slidev_format_uses_slidev_pipeline(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text("---\ntransition: fade\n---\n\n# Slide\n")

        patches = _patch_pipeline()
        mocks = self._run_main(["deck2video", str(md), "--format", "slidev"], patches)
        mocks["deck2video.__main__.parse_slidev"].assert_called_once()
        mocks["deck2video.__main__.render_slidev_slides"].assert_called_once()
        mocks["deck2video.__main__.parse_marp"].assert_not_called()
        mocks["deck2video.__main__.render_slides"].assert_not_called()

    def test_auto_detected_slidev_uses_slidev_pipeline(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text("---\ntransition: fade\n---\n\n# Slide\n")

        patches = _patch_pipeline(**{
            "deck2video.__main__.detect_format": MagicMock(return_value="slidev"),
        })
        mocks = self._run_main(["deck2video", str(md)], patches)
        mocks["deck2video.__main__.parse_slidev"].assert_called_once()
        mocks["deck2video.__main__.render_slidev_slides"].assert_called_once()

    def test_slidev_with_clicks_expands_steps(self, tmp_path):
        """Slidev slides with [click] markers expand into steps; renderer gets step count."""
        from deck2video.models import Slide

        md = tmp_path / "deck.md"
        md.write_text("---\ntransition: fade\n---\n\n# Slide\n")

        # Two slides, first has 1 click (→ 2 steps), second has none (→ 1 step) = 3 total
        slides_with_clicks = [
            Slide(index=1, body="body", notes="First.\n[click]\nSecond.", video=None),
            Slide(index=2, body="body", notes="Third.", video=None),
        ]
        patches = _patch_pipeline(**{
            "deck2video.__main__.parse_slidev": MagicMock(return_value=slides_with_clicks),
            "deck2video.__main__.render_slidev_slides": MagicMock(return_value=[
                Path("/tmp/1.png"), Path("/tmp/2.png"), Path("/tmp/2-1.png"),
            ]),
            "deck2video.__main__.generate_audio_for_slides": MagicMock(return_value=[
                Path("/tmp/audio_001.wav"), Path("/tmp/audio_002.wav"), Path("/tmp/audio_003.wav"),
            ]),
        })
        mocks = self._run_main(["deck2video", str(md), "--format", "slidev"], patches)

        # Renderer should be called with expected_count=3 and with_clicks=True
        render_call = mocks["deck2video.__main__.render_slidev_slides"]
        render_kwargs = render_call.call_args[1]
        assert render_kwargs["expected_count"] == 3
        assert render_kwargs["with_clicks"] is True

        # TTS should receive 3 steps
        gen_call = mocks["deck2video.__main__.generate_audio_for_slides"]
        steps_arg = gen_call.call_args[0][0]
        assert len(steps_arg) == 3

    def test_slidev_without_clicks_no_with_clicks_flag(self, tmp_path):
        """Slidev slides without [click] markers should not pass with_clicks=True."""
        from deck2video.models import Slide

        md = tmp_path / "deck.md"
        md.write_text("---\ntransition: fade\n---\n\n# Slide\n")

        slides_no_clicks = [
            Slide(index=1, body="body", notes="Hello.", video=None),
            Slide(index=2, body="body", notes=None, video=None),
        ]
        patches = _patch_pipeline(**{
            "deck2video.__main__.parse_slidev": MagicMock(return_value=slides_no_clicks),
        })
        mocks = self._run_main(["deck2video", str(md), "--format", "slidev"], patches)

        render_call = mocks["deck2video.__main__.render_slidev_slides"]
        render_kwargs = render_call.call_args[1]
        assert render_kwargs.get("with_clicks") is False


# ---------------------------------------------------------------------------
# Pipeline failure and --keep-temp
# ---------------------------------------------------------------------------

class TestPipelineFailure:
    def test_pipeline_failure_preserves_temp_and_reraises(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text("---\nmarp: true\n---\n\n# Slide\n")

        patches = _patch_pipeline(**{
            "deck2video.__main__.assemble_video": MagicMock(
                side_effect=RuntimeError("ffmpeg exploded")
            ),
        })

        import contextlib
        from deck2video.__main__ import main

        with patch("sys.argv", ["deck2video", str(md)]):
            with contextlib.ExitStack() as stack:
                for target, mock_obj in patches.items():
                    stack.enter_context(patch(target, mock_obj))
                with pytest.raises(RuntimeError, match="ffmpeg exploded"):
                    main()

    def test_keep_temp_preserves_files(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text("---\nmarp: true\n---\n\n# Slide\n")

        patches = _patch_pipeline()

        import contextlib
        from deck2video.__main__ import main

        with patch("sys.argv", ["deck2video", str(md), "--keep-temp",
                                 "--temp-dir", str(tmp_path / "build")]):
            with contextlib.ExitStack() as stack:
                for target, mock_obj in patches.items():
                    stack.enter_context(patch(target, mock_obj))
                main()

        # Temp dir should still exist
        assert (tmp_path / "build").exists()

    def test_keep_temp_prints_message(self, tmp_path, capsys):
        md = tmp_path / "deck.md"
        md.write_text("---\nmarp: true\n---\n\n# Slide\n")
        build_dir = tmp_path / "kept"

        patches = _patch_pipeline()

        import contextlib
        from deck2video.__main__ import main

        with patch("sys.argv", ["deck2video", str(md), "--keep-temp",
                                 "--temp-dir", str(build_dir)]):
            with contextlib.ExitStack() as stack:
                for target, mock_obj in patches.items():
                    stack.enter_context(patch(target, mock_obj))
                main()

        captured = capsys.readouterr()
        assert "Temp files kept at:" in captured.out


# ---------------------------------------------------------------------------
# _discover_temp_files helper
# ---------------------------------------------------------------------------

class TestDiscoverTempFiles:
    def test_finds_slidev_images_and_audio(self, tmp_path):
        for i in range(1, 4):
            (tmp_path / f"slides.{i:03d}.png").touch()
            (tmp_path / f"audio_{i:03d}.wav").touch()

        images, audio = _discover_temp_files(tmp_path)
        assert len(images) == 3
        assert len(audio) == 3
        assert all(p.suffix == ".png" for p in images)

    def test_finds_marp_images_and_audio(self, tmp_path):
        for i in range(1, 3):
            (tmp_path / f"slides.{i:03d}").touch()
            (tmp_path / f"audio_{i:03d}.wav").touch()

        images, audio = _discover_temp_files(tmp_path)
        assert len(images) == 2
        assert len(audio) == 2

    def test_prefers_slidev_over_marp(self, tmp_path):
        """If both .png and extensionless exist, picks .png (Slidev)."""
        for i in range(1, 3):
            (tmp_path / f"slides.{i:03d}.png").touch()
            (tmp_path / f"slides.{i:03d}").touch()
            (tmp_path / f"audio_{i:03d}.wav").touch()

        images, _ = _discover_temp_files(tmp_path)
        assert all(p.suffix == ".png" for p in images)

    def test_no_images_exits(self, tmp_path):
        (tmp_path / "audio_001.wav").touch()
        with pytest.raises(SystemExit):
            _discover_temp_files(tmp_path)

    def test_no_audio_exits(self, tmp_path):
        (tmp_path / "slides.001.png").touch()
        with pytest.raises(SystemExit):
            _discover_temp_files(tmp_path)

    def test_count_mismatch_exits(self, tmp_path):
        (tmp_path / "slides.001.png").touch()
        (tmp_path / "slides.002.png").touch()
        (tmp_path / "audio_001.wav").touch()
        with pytest.raises(SystemExit):
            _discover_temp_files(tmp_path)

    def test_finds_click_step_images_in_slides_subdir(self, tmp_path):
        """Click-step images like 2-1.png in slides/ subdir should be discovered."""
        slides_dir = tmp_path / "slides"
        slides_dir.mkdir()
        for name in ["1.png", "2.png", "2-1.png"]:
            (slides_dir / name).touch()
        for i in range(1, 4):
            (tmp_path / f"audio_{i:03d}.wav").touch()

        images, audio = _discover_temp_files(tmp_path)
        assert len(images) == 3
        names = [p.name for p in images]
        assert names == ["1.png", "2.png", "2-1.png"]

    def test_click_step_images_sorted_correctly(self, tmp_path):
        """Click steps must interleave between slides, not sort lexicographically."""
        slides_dir = tmp_path / "slides"
        slides_dir.mkdir()
        # Out-of-order creation to test sort
        for name in ["3.png", "2-2.png", "1.png", "2.png", "2-1.png"]:
            (slides_dir / name).touch()
        for i in range(1, 6):
            (tmp_path / f"audio_{i:03d}.wav").touch()

        images, _ = _discover_temp_files(tmp_path)
        names = [p.name for p in images]
        assert names == ["1.png", "2.png", "2-1.png", "2-2.png", "3.png"]


# ---------------------------------------------------------------------------
# _parse_slide_list helper
# ---------------------------------------------------------------------------

class TestParseSlideList:
    def test_single_slide(self):
        assert _parse_slide_list("3") == [3]

    def test_multiple_slides(self):
        assert _parse_slide_list("2,3,7") == [2, 3, 7]

    def test_deduplicates_and_sorts(self):
        assert _parse_slide_list("7,2,2,3") == [2, 3, 7]

    def test_invalid_input_exits(self):
        with pytest.raises(SystemExit):
            _parse_slide_list("a,b,c")

    def test_zero_index_exits(self):
        with pytest.raises(SystemExit):
            _parse_slide_list("0,1,2")


# ---------------------------------------------------------------------------
# --reassemble mode
# ---------------------------------------------------------------------------

class TestReassembleMode:
    def _run_main(self, argv, patches):
        import contextlib
        from deck2video.__main__ import main

        with patch("sys.argv", argv):
            with contextlib.ExitStack() as stack:
                mocks = {}
                for target, mock_obj in patches.items():
                    mocks[target] = stack.enter_context(patch(target, mock_obj))
                main()
                return mocks

    def test_reassemble_requires_temp_dir(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text("---\nmarp: true\n---\n\n# Slide\n")

        from deck2video.__main__ import main
        with patch("sys.argv", ["deck2video", str(md), "--reassemble"]):
            with patch("deck2video.__main__.check_ffmpeg"):
                with pytest.raises(SystemExit):
                    main()

    def test_reassemble_skips_render_tts(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text("---\nmarp: true\n---\n\n# Slide\n")
        temp = tmp_path / "build"
        temp.mkdir()
        for i in range(1, 3):
            (temp / f"slides.{i:03d}.png").touch()
            (temp / f"audio_{i:03d}.wav").touch()

        patches = _patch_pipeline()
        mocks = self._run_main(
            ["deck2video", str(md), "--reassemble", "--temp-dir", str(temp)],
            patches,
        )

        # Parse IS called (to resolve video paths and detect FPS)
        mocks["deck2video.__main__.parse_marp"].assert_called_once()

        # Render and TTS should NOT be called
        mocks["deck2video.__main__.render_slides"].assert_not_called()
        mocks["deck2video.__main__.render_slidev_slides"].assert_not_called()
        mocks["deck2video.__main__.generate_audio_for_slides"].assert_not_called()

        # Assemble SHOULD be called
        mocks["deck2video.__main__.assemble_video"].assert_called_once()

    def test_reassemble_passes_discovered_files(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text("---\nmarp: true\n---\n\n# Slide 1\n\n---\n\n# Slide 2\n")
        temp = tmp_path / "build"
        temp.mkdir()
        for i in range(1, 3):
            (temp / f"slides.{i:03d}.png").touch()
            (temp / f"audio_{i:03d}.wav").touch()

        patches = _patch_pipeline()
        mocks = self._run_main(
            ["deck2video", str(md), "--reassemble", "--temp-dir", str(temp)],
            patches,
        )

        call_args = mocks["deck2video.__main__.assemble_video"].call_args
        images_arg = call_args[0][0]
        audio_arg = call_args[0][1]
        assert len(images_arg) == 2
        assert len(audio_arg) == 2

    def test_reassemble_passes_videos_and_detects_fps(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text("---\nmarp: true\n---\n\n# Slide\n")
        temp = tmp_path / "build"
        temp.mkdir()
        for i in range(1, 3):
            (temp / f"slides.{i:03d}.png").touch()
            (temp / f"audio_{i:03d}.wav").touch()

        # Create a video file
        assets = tmp_path / "assets"
        assets.mkdir()
        video_file = assets / "demo.mov"
        video_file.touch()

        slides = [
            Slide(index=1, body="body", notes="Hello", video="assets/demo.mov"),
            Slide(index=2, body="body", notes=None, video=None),
        ]
        patches = _patch_pipeline(**{
            "deck2video.__main__.parse_marp": MagicMock(return_value=slides),
            "deck2video.__main__.get_video_fps": MagicMock(return_value=60.0),
        })

        mocks = self._run_main(
            ["deck2video", str(md), "--reassemble", "--temp-dir", str(temp)],
            patches,
        )

        assemble_call = mocks["deck2video.__main__.assemble_video"]
        call_kwargs = assemble_call.call_args[1]
        assert call_kwargs["videos"][0] == video_file.resolve()
        assert call_kwargs["videos"][1] is None
        assert call_kwargs["fps"] == 60

    def test_reassemble_requires_input_file(self, tmp_path):
        temp = tmp_path / "build"
        temp.mkdir()
        for i in range(1, 3):
            (temp / f"slides.{i:03d}.png").touch()
            (temp / f"audio_{i:03d}.wav").touch()

        from deck2video.__main__ import main
        with patch("sys.argv", ["deck2video", str(tmp_path / "missing.md"),
                                 "--reassemble", "--temp-dir", str(temp)]):
            with patch("deck2video.__main__.check_ffmpeg"):
                with pytest.raises(SystemExit):
                    main()


# ---------------------------------------------------------------------------
# --redo-slides mode
# ---------------------------------------------------------------------------

class TestRedoSlidesMode:
    def _run_main(self, argv, patches):
        import contextlib
        from deck2video.__main__ import main

        with patch("sys.argv", argv):
            with contextlib.ExitStack() as stack:
                mocks = {}
                for target, mock_obj in patches.items():
                    mocks[target] = stack.enter_context(patch(target, mock_obj))
                main()
                return mocks

    def test_redo_slides_requires_temp_dir(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text("---\nmarp: true\n---\n\n# Slide\n")

        from deck2video.__main__ import main
        with patch("sys.argv", ["deck2video", str(md), "--redo-slides", "1"]):
            with patch("deck2video.__main__.check_ffmpeg"):
                with pytest.raises(SystemExit):
                    main()

    def test_redo_slides_requires_input_file(self, tmp_path):
        temp = tmp_path / "build"
        temp.mkdir()
        for i in range(1, 3):
            (temp / f"slides.{i:03d}.png").touch()
            (temp / f"audio_{i:03d}.wav").touch()

        from deck2video.__main__ import main
        with patch("sys.argv", ["deck2video", str(tmp_path / "missing.md"),
                                 "--redo-slides", "1", "--temp-dir", str(temp)]):
            with patch("deck2video.__main__.check_ffmpeg"):
                with pytest.raises(SystemExit):
                    main()

    def test_redo_slides_regenerates_selected_and_assembles(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text("---\nmarp: true\n---\n\n# Slide 1\n<!-- Hello -->\n\n---\n\n# Slide 2\n<!-- World -->\n")
        temp = tmp_path / "build"
        temp.mkdir()
        for i in range(1, 3):
            (temp / f"slides.{i:03d}.png").touch()
            (temp / f"audio_{i:03d}.wav").touch()

        slides = [
            Slide(index=1, body="# Slide 1", notes="Hello", video=None),
            Slide(index=2, body="# Slide 2", notes="World", video=None),
        ]
        patches = _patch_pipeline(**{
            "deck2video.__main__.parse_marp": MagicMock(return_value=slides),
        })

        mocks = self._run_main(
            ["deck2video", str(md), "--redo-slides", "2",
             "--temp-dir", str(temp), "--voice", "voice.wav"],
            patches,
        )

        # TTS should be called with only slide 2
        gen_call = mocks["deck2video.__main__.generate_audio_for_slides"]
        gen_call.assert_called_once()
        slides_arg = gen_call.call_args[0][0]
        assert len(slides_arg) == 1
        assert slides_arg[0].index == 2

        # Render should NOT be called
        mocks["deck2video.__main__.render_slides"].assert_not_called()

        # Assemble should be called
        mocks["deck2video.__main__.assemble_video"].assert_called_once()

    def test_redo_slides_passes_videos_and_detects_fps(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text("---\nmarp: true\n---\n\n# Slide 1\n<!-- Hello -->\n\n---\n\n# Slide 2\n<!-- World -->\n")
        temp = tmp_path / "build"
        temp.mkdir()
        for i in range(1, 3):
            (temp / f"slides.{i:03d}.png").touch()
            (temp / f"audio_{i:03d}.wav").touch()

        # Create a video file
        assets = tmp_path / "assets"
        assets.mkdir()
        video_file = assets / "demo.mov"
        video_file.touch()

        slides = [
            Slide(index=1, body="# Slide 1", notes="Hello", video="assets/demo.mov"),
            Slide(index=2, body="# Slide 2", notes="World", video=None),
        ]
        patches = _patch_pipeline(**{
            "deck2video.__main__.parse_marp": MagicMock(return_value=slides),
            "deck2video.__main__.get_video_fps": MagicMock(return_value=30.0),
        })

        mocks = self._run_main(
            ["deck2video", str(md), "--redo-slides", "2",
             "--temp-dir", str(temp), "--voice", "voice.wav"],
            patches,
        )

        assemble_call = mocks["deck2video.__main__.assemble_video"]
        call_kwargs = assemble_call.call_args[1]
        assert call_kwargs["videos"][0] == video_file.resolve()
        assert call_kwargs["videos"][1] is None
        assert call_kwargs["fps"] == 30

    def test_redo_slides_invalid_index_exits(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text("---\nmarp: true\n---\n\n# Slide 1\n")
        temp = tmp_path / "build"
        temp.mkdir()
        (temp / "slides.001.png").touch()
        (temp / "audio_001.wav").touch()

        slides = [Slide(index=1, body="# Slide 1", notes="Hello", video=None)]
        patches = _patch_pipeline(**{
            "deck2video.__main__.parse_marp": MagicMock(return_value=slides),
        })

        import contextlib
        from deck2video.__main__ import main

        with patch("sys.argv", ["deck2video", str(md), "--redo-slides", "5",
                                 "--temp-dir", str(temp)]):
            with contextlib.ExitStack() as stack:
                for target, mock_obj in patches.items():
                    stack.enter_context(patch(target, mock_obj))
                with pytest.raises(SystemExit):
                    main()

    def test_reassemble_and_redo_slides_mutually_exclusive(self, tmp_path):
        """argparse should reject both flags together."""
        md = tmp_path / "deck.md"
        md.write_text("---\nmarp: true\n---\n\n# Slide\n")

        from deck2video.__main__ import main
        with patch("sys.argv", ["deck2video", str(md), "--reassemble",
                                 "--redo-slides", "1", "--temp-dir", str(tmp_path)]):
            with pytest.raises(SystemExit):
                main()

    def test_redo_slides_slidev_with_clicks_regenerates_all_steps_for_slide(self, tmp_path):
        """--redo-slides on a Slidev deck regenerates all steps for the specified slide."""
        md = tmp_path / "deck.md"
        md.write_text("---\ntransition: fade\n---\n\n# Slide 1\n\n---\n\n# Slide 2\n")
        temp = tmp_path / "build"
        temp.mkdir()
        # 4 steps total: slide 1 → 2 steps, slide 2 → 2 steps
        for i in range(1, 5):
            (temp / f"audio_{i:03d}.wav").touch()
        slides_subdir = temp / "slides"
        slides_subdir.mkdir()
        for name in ["1.png", "1-1.png", "2.png", "2-1.png"]:
            (slides_subdir / name).touch()

        slides = [
            Slide(index=1, body="# Slide 1", notes="A.\n[click]\nB.", video=None),
            Slide(index=2, body="# Slide 2", notes="C.\n[click]\nD.", video=None),
        ]
        patches = _patch_pipeline(**{
            "deck2video.__main__.detect_format": MagicMock(return_value="slidev"),
            "deck2video.__main__.parse_slidev": MagicMock(return_value=slides),
            "deck2video.__main__.generate_audio_for_slides": MagicMock(return_value=[
                Path(str(temp / "audio_001.wav")),
                Path(str(temp / "audio_002.wav")),
            ]),
        })

        mocks = self._run_main(
            ["deck2video", str(md), "--redo-slides", "1",
             "--temp-dir", str(temp), "--format", "slidev"],
            patches,
        )

        gen_call = mocks["deck2video.__main__.generate_audio_for_slides"]
        gen_call.assert_called_once()
        steps_arg = gen_call.call_args[0][0]
        # Should regenerate both steps for slide 1 (slide_index==1)
        assert len(steps_arg) == 2
        assert all(s.slide_index == 1 for s in steps_arg)
