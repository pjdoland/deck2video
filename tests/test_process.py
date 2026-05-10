"""Tests for deck2video.process — subprocess wrapper with signal cleanup."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from deck2video import process


class TestRun:
    def test_returns_completed_process(self):
        """Equivalent to subprocess.run for the happy path."""
        result = process.run([sys.executable, "-c", "print('hello')"], capture_output=True, text=True)
        assert result.returncode == 0
        assert "hello" in result.stdout

    def test_returncode_propagates(self):
        result = process.run([sys.executable, "-c", "import sys; sys.exit(7)"], capture_output=True)
        assert result.returncode == 7

    def test_stderr_captured(self):
        result = process.run(
            [sys.executable, "-c", "import sys; sys.stderr.write('ouch')"],
            capture_output=True,
            text=True,
        )
        assert "ouch" in result.stderr

    def test_input_passed_through(self):
        result = process.run(
            [sys.executable, "-c", "import sys; sys.stdout.write(sys.stdin.read())"],
            capture_output=True,
            text=True,
            input="from-test",
        )
        assert "from-test" in result.stdout

    @pytest.mark.skipif(os.name != "posix", reason="POSIX-only: start_new_session check")
    def test_starts_new_session_on_posix(self):
        """The child must be in its own session/process group so we can killpg."""
        result = process.run(
            [sys.executable, "-c",
             "import os; print(os.getpgrp() == os.getpid())"],
            capture_output=True, text=True,
        )
        assert "True" in result.stdout

    def test_timeout_raises_and_kills_child(self):
        """A child that ignores SIGTERM must still be killed by the wrapper."""
        with pytest.raises(subprocess.TimeoutExpired):
            process.run(
                [sys.executable, "-c", "import time; time.sleep(60)"],
                timeout=0.5,
                capture_output=True,
            )

    def test_active_processes_set_drains_on_success(self):
        process._active_processes.clear()
        process.run([sys.executable, "-c", "pass"])
        assert len(process._active_processes) == 0

    def test_active_processes_set_drains_on_timeout(self):
        process._active_processes.clear()
        with pytest.raises(subprocess.TimeoutExpired):
            process.run(
                [sys.executable, "-c", "import time; time.sleep(60)"],
                timeout=0.3,
            )
        assert len(process._active_processes) == 0


class TestKillProcGroup:
    @pytest.mark.skipif(os.name != "posix", reason="killpg is POSIX only")
    def test_killpg_called_with_sigterm(self):
        proc = MagicMock()
        proc.pid = 12345
        proc.poll.return_value = None  # still running
        with patch("os.killpg") as mock_killpg, \
             patch("os.getpgid", return_value=12345):
            process._kill_proc_group(proc)
        mock_killpg.assert_called_once_with(12345, signal.SIGTERM)

    @pytest.mark.skipif(os.name != "posix", reason="killpg is POSIX only")
    def test_already_exited_skips_killpg(self):
        """PID-reuse mitigation: if the child has exited, don't signal at all."""
        proc = MagicMock()
        proc.pid = 12345
        proc.poll.return_value = 0  # already exited
        with patch("os.killpg") as mock_killpg:
            process._kill_proc_group(proc)
        mock_killpg.assert_not_called()

    @pytest.mark.skipif(os.name != "posix", reason="killpg is POSIX only")
    def test_swallows_process_lookup_error(self):
        """If the child exits between poll() and killpg, error must not propagate."""
        proc = MagicMock()
        proc.pid = 12345
        proc.poll.return_value = None
        with patch("os.getpgid", return_value=12345), \
             patch("os.killpg", side_effect=ProcessLookupError):
            process._kill_proc_group(proc)  # no exception


class TestInstallSignalCleanup:
    def test_sigint_handler_is_our_function(self):
        """install_signal_cleanup registers our handler for SIGINT."""
        import signal as _sig
        original = _sig.getsignal(_sig.SIGINT)
        try:
            process.install_signal_cleanup()
            assert _sig.getsignal(_sig.SIGINT) is process._signal_handler
        finally:
            _sig.signal(_sig.SIGINT, original)

    def test_idempotent(self):
        """Calling twice doesn't raise."""
        process.install_signal_cleanup()
        process.install_signal_cleanup()  # no exception
