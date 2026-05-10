"""Tests for deck2video.doctor — the preflight subcommand."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from deck2video import doctor
from deck2video.doctor import (
    _FAIL,
    _OK,
    _WARN,
    check_chatterbox_cache,
    check_disk,
    check_ffmpeg,
    check_ffprobe,
    check_gpu,
    check_marp,
    check_python,
    check_slidev,
    run_doctor,
)


# ---------------------------------------------------------------------------
# Individual checks — failure paths
# ---------------------------------------------------------------------------

class TestCheckFfmpeg:
    def test_passes_when_ffmpeg_present(self):
        with patch("deck2video.doctor.shutil.which", return_value="/usr/bin/ffmpeg"), \
             patch("deck2video.doctor._run_quick", return_value=(0, "ffmpeg version 6.1\n")):
            sigil, msg = check_ffmpeg()
        assert sigil == _OK
        assert "ffmpeg" in msg

    def test_fails_when_ffmpeg_missing(self):
        with patch("deck2video.doctor.shutil.which", return_value=None):
            sigil, msg = check_ffmpeg()
        assert sigil == _FAIL
        assert "PATH" in msg

    def test_fails_when_ffmpeg_version_errors(self):
        with patch("deck2video.doctor.shutil.which", return_value="/usr/bin/ffmpeg"), \
             patch("deck2video.doctor._run_quick", return_value=(1, "boom")):
            sigil, _ = check_ffmpeg()
        assert sigil == _FAIL


class TestCheckFfprobe:
    def test_passes(self):
        with patch("deck2video.doctor.shutil.which", return_value="/usr/bin/ffprobe"), \
             patch("deck2video.doctor._run_quick", return_value=(0, "ok")):
            assert check_ffprobe()[0] == _OK

    def test_fails_when_missing(self):
        with patch("deck2video.doctor.shutil.which", return_value=None):
            assert check_ffprobe()[0] == _FAIL


class TestCheckMarp:
    def test_global_marp_is_ok(self):
        def which(name):
            return "/usr/local/bin/marp" if name == "marp" else None
        with patch("deck2video.doctor.shutil.which", side_effect=which), \
             patch("deck2video.doctor._run_quick", return_value=(0, "marp 4.0.0\n")):
            sigil, msg = check_marp()
        assert sigil == _OK
        assert "global" in msg

    def test_npx_fallback_is_warn(self):
        def which(name):
            return "/usr/local/bin/npx" if name == "npx" else None
        with patch("deck2video.doctor.shutil.which", side_effect=which):
            sigil, msg = check_marp()
        assert sigil == _WARN
        assert "npx" in msg

    def test_no_marp_no_npx_is_fail(self):
        with patch("deck2video.doctor.shutil.which", return_value=None):
            sigil, _ = check_marp()
        assert sigil == _FAIL


class TestCheckSlidev:
    def test_global_slidev_is_ok(self):
        with patch("deck2video.doctor.shutil.which",
                   side_effect=lambda n: "/usr/local/bin/slidev" if n == "slidev" else None):
            assert check_slidev()[0] == _OK

    def test_npx_only_is_warn(self):
        with patch("deck2video.doctor.shutil.which",
                   side_effect=lambda n: "/usr/local/bin/npx" if n == "npx" else None):
            assert check_slidev()[0] == _WARN

    def test_neither_is_warn_not_fail(self):
        # Slidev is optional — missing is a warn, not a fail.
        with patch("deck2video.doctor.shutil.which", return_value=None):
            assert check_slidev()[0] == _WARN


class TestCheckPython:
    def test_python_311_is_ok(self):
        # sys.version_info is a named tuple; a regular tuple works for
        # numeric subscripting (sys.version_info[:2]) and .micro access.
        from collections import namedtuple
        VI = namedtuple("VI", "major minor micro releaselevel serial")
        with patch("deck2video.doctor.sys.version_info", VI(3, 11, 5, "final", 0)):
            assert check_python()[0] == _OK

    def test_python_310_is_fail(self):
        from collections import namedtuple
        VI = namedtuple("VI", "major minor micro releaselevel serial")
        with patch("deck2video.doctor.sys.version_info", VI(3, 10, 0, "final", 0)):
            sigil, msg = check_python()
        assert sigil == _FAIL
        assert "3.11" in msg


class TestCheckDisk:
    def test_enough_disk(self, tmp_path):
        usage = MagicMock()
        usage.free = 50 * 1024 ** 3
        with patch("deck2video.doctor.shutil.disk_usage", return_value=usage):
            assert check_disk(min_free_gb=5.0)[0] == _OK

    def test_low_disk_fails(self, tmp_path):
        usage = MagicMock()
        usage.free = int(0.5 * 1024 ** 3)
        with patch("deck2video.doctor.shutil.disk_usage", return_value=usage):
            sigil, msg = check_disk(min_free_gb=5.0)
        assert sigil == _FAIL
        assert "0.5 GB" in msg


class TestCheckGpu:
    def test_no_torch_is_warn(self):
        with patch.dict("sys.modules", {"torch": None}):
            sigil, _ = check_gpu()
        assert sigil == _WARN

    def test_cuda_is_ok(self):
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.get_device_name.return_value = "NVIDIA H100"
        mock_torch.backends.mps.is_available.return_value = False
        with patch.dict("sys.modules", {"torch": mock_torch}):
            sigil, msg = check_gpu()
        assert sigil == _OK
        assert "H100" in msg

    def test_cpu_only_is_warn(self):
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False
        mock_torch.backends.mps.is_available.return_value = False
        with patch.dict("sys.modules", {"torch": mock_torch}):
            sigil, _ = check_gpu()
        assert sigil == _WARN


class TestCheckChatterboxCache:
    def test_missing_cache_dir_is_warn(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HF_HOME", str(tmp_path / "no-such-dir"))
        assert check_chatterbox_cache()[0] == _WARN

    def test_no_chatterbox_in_cache_is_warn(self, tmp_path, monkeypatch):
        (tmp_path / "some-other-model").mkdir()
        monkeypatch.setenv("HF_HOME", str(tmp_path))
        assert check_chatterbox_cache()[0] == _WARN

    def test_chatterbox_present_is_ok_canonical_layout(self, tmp_path, monkeypatch):
        """HF cache layout is HF_HOME/hub/models--Org--Repo/..."""
        hub = tmp_path / "hub"
        hub.mkdir()
        (hub / "models--ResembleAI--chatterbox").mkdir()
        monkeypatch.setenv("HF_HOME", str(tmp_path))
        monkeypatch.delenv("HUGGINGFACE_HUB_CACHE", raising=False)
        assert check_chatterbox_cache()[0] == _OK

    def test_chatterbox_present_is_ok_flat_layout(self, tmp_path, monkeypatch):
        """Some users point HF_HOME directly at the snapshots dir; tolerate that."""
        (tmp_path / "models--ResembleAI--chatterbox").mkdir()
        monkeypatch.setenv("HF_HOME", str(tmp_path))
        monkeypatch.delenv("HUGGINGFACE_HUB_CACHE", raising=False)
        assert check_chatterbox_cache()[0] == _OK

    def test_huggingface_hub_cache_overrides_hf_home(self, tmp_path, monkeypatch):
        """HUGGINGFACE_HUB_CACHE wins over HF_HOME (matches HF's own resolution)."""
        explicit = tmp_path / "explicit"
        explicit.mkdir()
        (explicit / "models--ResembleAI--chatterbox").mkdir()
        # HF_HOME points somewhere wrong but HUGGINGFACE_HUB_CACHE wins.
        monkeypatch.setenv("HF_HOME", str(tmp_path / "wrong"))
        monkeypatch.setenv("HUGGINGFACE_HUB_CACHE", str(explicit))
        assert check_chatterbox_cache()[0] == _OK


# ---------------------------------------------------------------------------
# run_doctor — overall exit code
# ---------------------------------------------------------------------------

class TestRunDoctor:
    def test_all_pass_returns_zero(self, capsys):
        ok = (_OK, "fine")
        with patch("deck2video.doctor.CHECKS", [
            ("python", lambda: ok),
            ("ffmpeg", lambda: ok),
        ]):
            rc = run_doctor()
        assert rc == 0
        captured = capsys.readouterr()
        assert "All checks passed" in captured.out

    def test_any_fail_returns_one(self, capsys):
        with patch("deck2video.doctor.CHECKS", [
            ("python", lambda: (_OK, "fine")),
            ("ffmpeg", lambda: (_FAIL, "missing")),
        ]):
            rc = run_doctor()
        assert rc == 1
        captured = capsys.readouterr()
        assert "Some required checks failed" in captured.err

    def test_warnings_only_returns_zero(self, capsys):
        with patch("deck2video.doctor.CHECKS", [
            ("python", lambda: (_OK, "fine")),
            ("gpu", lambda: (_WARN, "cpu only")),
        ]):
            rc = run_doctor()
        assert rc == 0
        captured = capsys.readouterr()
        assert "warnings" in captured.out.lower()

    def test_check_that_raises_is_treated_as_fail(self, capsys):
        def boom():
            raise RuntimeError("kaboom")
        with patch("deck2video.doctor.CHECKS", [("explosive", boom)]):
            rc = run_doctor()
        assert rc == 1


# ---------------------------------------------------------------------------
# main() routing — `deck2video doctor` is detected before argparse
# ---------------------------------------------------------------------------

class TestDoctorRouting:
    def test_doctor_arg_runs_doctor_not_main_pipeline(self):
        """`python -m deck2video doctor` must short-circuit to run_doctor."""
        from deck2video.__main__ import main
        with patch("deck2video.doctor.run_doctor", return_value=0) as mock_doc:
            with patch("sys.argv", ["deck2video", "doctor"]):
                with pytest.raises(SystemExit) as excinfo:
                    main()
        assert excinfo.value.code == 0
        mock_doc.assert_called_once()
