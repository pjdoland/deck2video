"""Tests for marp2video.__main__ — CLI argument parsing and orchestration."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from marp2video.models import Slide


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_pipeline(**overrides):
    """Return a dict of patches for all pipeline steps with sensible defaults."""
    defaults = {
        "marp2video.__main__.check_ffmpeg": MagicMock(),
        "marp2video.__main__.detect_format": MagicMock(return_value="marp"),
        "marp2video.__main__.parse_marp": MagicMock(return_value=[
            Slide(index=1, body="body", notes="Hello.", video=None),
            Slide(index=2, body="body", notes=None, video=None),
        ]),
        "marp2video.__main__.parse_slidev": MagicMock(return_value=[
            Slide(index=1, body="body", notes="Hello.", video=None),
            Slide(index=2, body="body", notes=None, video=None),
        ]),
        "marp2video.__main__.render_slides": MagicMock(return_value=[
            Path("/tmp/slides.001"), Path("/tmp/slides.002"),
        ]),
        "marp2video.__main__.render_slidev_slides": MagicMock(return_value=[
            Path("/tmp/slides.001.png"), Path("/tmp/slides.002.png"),
        ]),
        "marp2video.__main__.generate_audio_for_slides": MagicMock(return_value=[
            Path("/tmp/audio_001.wav"), Path("/tmp/audio_002.wav"),
        ]),
        "marp2video.__main__.assemble_video": MagicMock(),
    }
    defaults.update(overrides)
    return defaults


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

class TestArgParsing:
    def test_input_required(self):
        with pytest.raises(SystemExit):
            from marp2video.__main__ import main
            with patch("sys.argv", ["marp2video"]):
                main()

    def test_missing_input_file_exits(self, tmp_path):
        from marp2video.__main__ import main
        with patch("sys.argv", ["marp2video", str(tmp_path / "nonexistent.md")]):
            with pytest.raises(SystemExit):
                main()

    def test_default_output_derives_from_input(self, tmp_path):
        md = tmp_path / "talk.md"
        md.write_text("---\nmarp: true\n---\n\n# Slide\n")

        patches = _patch_pipeline()
        with patch("sys.argv", ["marp2video", str(md)]):
            for target, mock in patches.items():
                with patch(target, mock):
                    pass

            # We need all patches active at once
            import contextlib
            with contextlib.ExitStack() as stack:
                mocks = {}
                for target, mock_obj in patches.items():
                    mocks[target] = stack.enter_context(patch(target, mock_obj))

                from marp2video.__main__ import main
                main()

                # assemble_video should be called with output = talk.mp4
                assemble_call = mocks["marp2video.__main__.assemble_video"]
                call_args = assemble_call.call_args
                output_arg = call_args[0][2]  # third positional arg
                assert output_arg == md.with_suffix(".mp4")


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------

class TestPipelineOrchestration:
    def _run_main(self, argv, patches):
        import contextlib
        from marp2video.__main__ import main

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

        mocks = self._run_main(["marp2video", str(md)], patches)

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

        with patch("marp2video.__main__.load_pronunciations", return_value={"kubectl": "cube control"}) as mock_load:
            patches = _patch_pipeline()
            patches["marp2video.__main__.load_pronunciations"] = mock_load
            mocks = self._run_main(
                ["marp2video", str(md), "--pronunciations", str(pron)],
                patches,
            )
            mock_load.assert_called_once()

    def test_missing_pronunciations_file_exits(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text("---\nmarp: true\n---\n\n# Slide\n")

        with patch("sys.argv", ["marp2video", str(md), "--pronunciations", "/no/such/file.json"]):
            from marp2video.__main__ import main
            with patch("marp2video.__main__.check_ffmpeg"):
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
            "marp2video.__main__.parse_marp": MagicMock(return_value=slides),
            "marp2video.__main__.render_slides": MagicMock(return_value=[Path("/tmp/slides.001")]),
            "marp2video.__main__.generate_audio_for_slides": MagicMock(return_value=[Path("/tmp/audio_001.wav")]),
            "marp2video.__main__.get_video_fps": MagicMock(return_value=30.0),
        })

        import contextlib
        from marp2video.__main__ import main

        with patch("sys.argv", ["marp2video", str(md)]):
            with contextlib.ExitStack() as stack:
                mocks = {}
                for target, mock_obj in patches.items():
                    mocks[target] = stack.enter_context(patch(target, mock_obj))
                main()

                # assemble_video should receive the resolved video path
                assemble_call = mocks["marp2video.__main__.assemble_video"]
                call_kwargs = assemble_call.call_args[1]
                videos = call_kwargs["videos"]
                assert videos[0] == video_file.resolve()

    def test_missing_video_file_exits(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text("---\nmarp: true\n---\n\n# Slide\n")

        slides = [Slide(index=1, body="body", notes=None, video="missing.mov")]
        patches = _patch_pipeline(**{
            "marp2video.__main__.parse_marp": MagicMock(return_value=slides),
        })

        import contextlib
        from marp2video.__main__ import main

        with patch("sys.argv", ["marp2video", str(md)]):
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
            "marp2video.__main__.parse_marp": MagicMock(return_value=slides),
        })

        import contextlib
        from marp2video.__main__ import main

        with patch("sys.argv", ["marp2video", str(md)]):
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
        from marp2video.__main__ import main

        with patch("sys.argv", ["marp2video", str(md), "--fps", "60"]):
            with contextlib.ExitStack() as stack:
                mocks = {}
                for target, mock_obj in patches.items():
                    mocks[target] = stack.enter_context(patch(target, mock_obj))
                main()

                assemble_call = mocks["marp2video.__main__.assemble_video"]
                assert assemble_call.call_args[1]["fps"] == 60

    def test_default_fps_is_24(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text("---\nmarp: true\n---\n\n# Slide\n")

        patches = _patch_pipeline()

        import contextlib
        from marp2video.__main__ import main

        with patch("sys.argv", ["marp2video", str(md)]):
            with contextlib.ExitStack() as stack:
                mocks = {}
                for target, mock_obj in patches.items():
                    mocks[target] = stack.enter_context(patch(target, mock_obj))
                main()

                assemble_call = mocks["marp2video.__main__.assemble_video"]
                assert assemble_call.call_args[1]["fps"] == 24


# ---------------------------------------------------------------------------
# Audio padding
# ---------------------------------------------------------------------------

class TestAudioPadding:
    def _run_main(self, argv, patches):
        import contextlib
        from marp2video.__main__ import main

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

        mocks = self._run_main(["marp2video", str(md)], _patch_pipeline())
        assemble_call = mocks["marp2video.__main__.assemble_video"]
        assert assemble_call.call_args[1]["audio_padding_ms"] == 0

    def test_padding_passed_to_assembler(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text("---\nmarp: true\n---\n\n# Slide\n")

        mocks = self._run_main(
            ["marp2video", str(md), "--audio-padding", "400"],
            _patch_pipeline(),
        )
        assemble_call = mocks["marp2video.__main__.assemble_video"]
        assert assemble_call.call_args[1]["audio_padding_ms"] == 400


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
        from marp2video.__main__ import main

        with patch("sys.argv", ["marp2video", str(md), "--temp-dir", str(custom_temp)]):
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
        from marp2video.__main__ import main

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
        mocks = self._run_main(["marp2video", str(md)], patches)
        mocks["marp2video.__main__.detect_format"].assert_called_once()

    def test_explicit_marp_skips_detect(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text("---\nmarp: true\n---\n\n# Slide\n")

        patches = _patch_pipeline()
        mocks = self._run_main(["marp2video", str(md), "--format", "marp"], patches)
        mocks["marp2video.__main__.detect_format"].assert_not_called()

    def test_explicit_slidev_skips_detect(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text("---\ntransition: fade\n---\n\n# Slide\n")

        patches = _patch_pipeline()
        mocks = self._run_main(["marp2video", str(md), "--format", "slidev"], patches)
        mocks["marp2video.__main__.detect_format"].assert_not_called()

    def test_marp_format_uses_marp_pipeline(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text("---\nmarp: true\n---\n\n# Slide\n")

        patches = _patch_pipeline()
        mocks = self._run_main(["marp2video", str(md), "--format", "marp"], patches)
        mocks["marp2video.__main__.parse_marp"].assert_called_once()
        mocks["marp2video.__main__.render_slides"].assert_called_once()
        mocks["marp2video.__main__.parse_slidev"].assert_not_called()
        mocks["marp2video.__main__.render_slidev_slides"].assert_not_called()

    def test_slidev_format_uses_slidev_pipeline(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text("---\ntransition: fade\n---\n\n# Slide\n")

        patches = _patch_pipeline()
        mocks = self._run_main(["marp2video", str(md), "--format", "slidev"], patches)
        mocks["marp2video.__main__.parse_slidev"].assert_called_once()
        mocks["marp2video.__main__.render_slidev_slides"].assert_called_once()
        mocks["marp2video.__main__.parse_marp"].assert_not_called()
        mocks["marp2video.__main__.render_slides"].assert_not_called()

    def test_auto_detected_slidev_uses_slidev_pipeline(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text("---\ntransition: fade\n---\n\n# Slide\n")

        patches = _patch_pipeline(**{
            "marp2video.__main__.detect_format": MagicMock(return_value="slidev"),
        })
        mocks = self._run_main(["marp2video", str(md)], patches)
        mocks["marp2video.__main__.parse_slidev"].assert_called_once()
        mocks["marp2video.__main__.render_slidev_slides"].assert_called_once()


# ---------------------------------------------------------------------------
# Pipeline failure and --keep-temp
# ---------------------------------------------------------------------------

class TestPipelineFailure:
    def test_pipeline_failure_preserves_temp_and_reraises(self, tmp_path):
        md = tmp_path / "deck.md"
        md.write_text("---\nmarp: true\n---\n\n# Slide\n")

        patches = _patch_pipeline(**{
            "marp2video.__main__.assemble_video": MagicMock(
                side_effect=RuntimeError("ffmpeg exploded")
            ),
        })

        import contextlib
        from marp2video.__main__ import main

        with patch("sys.argv", ["marp2video", str(md)]):
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
        from marp2video.__main__ import main

        with patch("sys.argv", ["marp2video", str(md), "--keep-temp",
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
        from marp2video.__main__ import main

        with patch("sys.argv", ["marp2video", str(md), "--keep-temp",
                                 "--temp-dir", str(build_dir)]):
            with contextlib.ExitStack() as stack:
                for target, mock_obj in patches.items():
                    stack.enter_context(patch(target, mock_obj))
                main()

        captured = capsys.readouterr()
        assert "Temp files kept at:" in captured.out
