"""Tests for deck2video.slidev_renderer — Slidev CLI rendering."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from deck2video.slidev_renderer import check_slidev_cli, render_slidev_slides


class TestCheckSlidevCli:
    def test_exits_when_nothing_available(self):
        with patch("shutil.which", return_value=None):
            with pytest.raises(SystemExit):
                check_slidev_cli()

    def test_passes_when_slidev_available(self):
        with patch("shutil.which", side_effect=lambda x: "/usr/bin/slidev" if x == "slidev" else None):
            check_slidev_cli()  # should not raise

    def test_passes_when_npx_available(self):
        with patch("shutil.which", side_effect=lambda x: "/usr/bin/npx" if x == "npx" else None):
            check_slidev_cli()  # should not raise


class TestRenderSlidevSlides:
    def _setup_pngs(self, temp_dir, count):
        """Create fake slide PNG files in the slides/ subdirectory (Slidev v52+ format)."""
        slides_dir = temp_dir / "slides"
        slides_dir.mkdir(exist_ok=True)
        paths = []
        for i in range(1, count + 1):
            p = slides_dir / f"{i}.png"
            p.touch()
            paths.append(p)
        return paths

    def test_uses_slidev_binary_when_available(self, tmp_path):
        self._setup_pngs(tmp_path, 2)

        with patch("shutil.which", side_effect=lambda x: "/usr/bin/slidev" if x == "slidev" else None):
            with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")) as mock_run:
                result = render_slidev_slides("deck.md", tmp_path, expected_count=2)

        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "slidev"
        assert "export" in cmd
        assert len(result) == 2

    def test_falls_back_to_npx(self, tmp_path):
        self._setup_pngs(tmp_path, 1)

        def which_mock(x):
            if x == "slidev":
                return None
            if x == "npx":
                return "/usr/bin/npx"
            return None

        with patch("shutil.which", side_effect=which_mock):
            with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")):
                with patch("deck2video.slidev_renderer.check_slidev_cli"):
                    result = render_slidev_slides("deck.md", tmp_path, expected_count=1)

        assert len(result) == 1

    def test_raises_on_nonzero_exit(self, tmp_path):
        with patch("shutil.which", return_value="/usr/bin/slidev"):
            with patch("subprocess.run", return_value=MagicMock(returncode=1, stdout="", stderr="error")):
                with pytest.raises(RuntimeError, match="exited with code 1"):
                    render_slidev_slides("deck.md", tmp_path, expected_count=1)

    def test_count_mismatch_exits(self, tmp_path):
        # Create 1 PNG but expect 3
        self._setup_pngs(tmp_path, 1)

        with patch("shutil.which", return_value="/usr/bin/slidev"):
            with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")):
                with pytest.raises(SystemExit):
                    render_slidev_slides("deck.md", tmp_path, expected_count=3)

    def test_output_sorted(self, tmp_path):
        # Create PNGs out of order
        slides_dir = tmp_path / "slides"
        slides_dir.mkdir()
        (slides_dir / "3.png").touch()
        (slides_dir / "1.png").touch()
        (slides_dir / "2.png").touch()

        with patch("shutil.which", return_value="/usr/bin/slidev"):
            with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")):
                result = render_slidev_slides("deck.md", tmp_path, expected_count=3)

        assert result[0].name == "1.png"
        assert result[1].name == "2.png"
        assert result[2].name == "3.png"
