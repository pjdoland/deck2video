"""Tests for deck2video.marp_renderer — marp-cli wrapper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from deck2video.marp_renderer import check_marp_cli, render_slides


# ---------------------------------------------------------------------------
# check_marp_cli
# ---------------------------------------------------------------------------

class TestCheckMarpCli:
    def test_passes_when_marp_available(self):
        with patch("deck2video.marp_renderer.shutil.which", side_effect=lambda n: "/usr/bin/marp" if n == "marp" else None):
            check_marp_cli()  # should not raise

    def test_passes_when_npx_available(self):
        with patch("deck2video.marp_renderer.shutil.which", side_effect=lambda n: "/usr/bin/npx" if n == "npx" else None):
            check_marp_cli()  # should not raise

    def test_exits_when_neither_available(self):
        with patch("deck2video.marp_renderer.shutil.which", return_value=None):
            with pytest.raises(SystemExit):
                check_marp_cli()


# ---------------------------------------------------------------------------
# render_slides
# ---------------------------------------------------------------------------

class TestRenderSlides:
    def _setup_marp_output(self, tmp_path, count):
        """Create fake slide image files as marp-cli would."""
        for i in range(1, count + 1):
            (tmp_path / f"slides.{i:03d}").touch()

    def test_prefers_global_marp(self, tmp_path):
        self._setup_marp_output(tmp_path, 3)

        def which(name):
            if name == "marp":
                return "/usr/bin/marp"
            if name == "npx":
                return "/usr/bin/npx"
            return None

        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("deck2video.marp_renderer.shutil.which", side_effect=which):
            with patch("deck2video.marp_renderer.process.run", return_value=mock_result) as mock_run:
                render_slides("/tmp/deck.md", tmp_path, expected_count=3)
                cmd = mock_run.call_args[0][0]
                assert cmd[0] == "marp"

    def test_falls_back_to_npx(self, tmp_path):
        self._setup_marp_output(tmp_path, 2)

        def which(name):
            if name == "npx":
                return "/usr/bin/npx"
            return None

        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("deck2video.marp_renderer.shutil.which", side_effect=which):
            with patch("deck2video.marp_renderer.process.run", return_value=mock_result) as mock_run:
                render_slides("/tmp/deck.md", tmp_path, expected_count=2)
                cmd = mock_run.call_args[0][0]
                assert cmd[0] == "npx"
                assert cmd[1] == "--yes"
                assert cmd[2] == "@marp-team/marp-cli"

    def test_returns_sorted_paths(self, tmp_path):
        self._setup_marp_output(tmp_path, 3)
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("deck2video.marp_renderer.shutil.which", return_value="/usr/bin/marp"):
            with patch("deck2video.marp_renderer.process.run", return_value=mock_result):
                images = render_slides("/tmp/deck.md", tmp_path, expected_count=3)

        assert len(images) == 3
        assert all(isinstance(p, Path) for p in images)
        names = [p.name for p in images]
        assert names == ["slides.001", "slides.002", "slides.003"]

    def test_marp_failure_raises(self, tmp_path):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "marp error"

        with patch("deck2video.marp_renderer.shutil.which", return_value="/usr/bin/marp"):
            with patch("deck2video.marp_renderer.process.run", return_value=mock_result):
                with pytest.raises(RuntimeError, match="marp-cli exited"):
                    render_slides("/tmp/deck.md", tmp_path, expected_count=3)

    def test_count_mismatch_exits(self, tmp_path):
        # Create 2 files but expect 3
        self._setup_marp_output(tmp_path, 2)
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("deck2video.marp_renderer.shutil.which", return_value="/usr/bin/marp"):
            with patch("deck2video.marp_renderer.process.run", return_value=mock_result):
                with pytest.raises(SystemExit):
                    render_slides("/tmp/deck.md", tmp_path, expected_count=3)

    def test_command_includes_correct_flags(self, tmp_path):
        self._setup_marp_output(tmp_path, 1)
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("deck2video.marp_renderer.shutil.which", return_value="/usr/bin/marp"):
            with patch("deck2video.marp_renderer.process.run", return_value=mock_result) as mock_run:
                render_slides("/tmp/deck.md", tmp_path, expected_count=1)
                cmd = mock_run.call_args[0][0]
                assert "--images" in cmd
                assert "png" in cmd
                assert "--image-scale" in cmd
                assert "2" in cmd
                assert "--no-stdin" in cmd
