"""Subprocess execution with signal-aware child cleanup.

Wraps :class:`subprocess.Popen` so that:

* Each child runs in its own process group (POSIX) so we can ``killpg``
  the whole tree on signal/timeout. Without this, killing the parent
  Python process leaves grandchildren — npx → marp-cli → Chromium — alive.
* On SIGINT / SIGTERM the registered process groups are signalled, then
  reaped, before the parent exits with the conventional 128+signum code.

POSIX-first: on Windows we set ``CREATE_NEW_PROCESS_GROUP`` and fall back
to :meth:`Popen.terminate`. ``terminate`` only kills the direct child, so
on Windows grandchildren spawned by ``npx`` may still survive — see B28
follow-up.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import threading
from typing import Any

logger = logging.getLogger(__name__)

# Lock guarding the active-process registry. Individual ``set`` mutations
# are GIL-atomic in CPython, but iterating a set while another thread
# mutates it raises ``RuntimeError: Set changed size during iteration``
# — possible because torch lazy-loads on a worker thread for some
# accelerators. The lock makes the snapshot taken in ``_signal_handler``
# correct under concurrency.
_lock = threading.Lock()
_active_processes: set[subprocess.Popen] = set()


def _kill_proc_group(proc: subprocess.Popen, sig: int = signal.SIGTERM) -> None:
    """Send ``sig`` to ``proc``'s process group on POSIX, terminate on Windows.

    Swallows :class:`ProcessLookupError` and :class:`PermissionError` —
    the child may have already exited (PID reuse race) or transitioned to
    a uid we can't signal.
    """
    if os.name == "posix":
        try:
            # PID-reuse mitigation: if the child has already exited, its
            # pid may belong to another process group. Skip in that case.
            if proc.poll() is not None:
                return
            os.killpg(os.getpgid(proc.pid), sig)
        except (ProcessLookupError, PermissionError):
            pass
    else:
        try:
            proc.terminate()
        except (ProcessLookupError, OSError):
            pass


def _signal_handler(signum: int, frame: Any) -> None:
    """Reap active children, then exit with the conventional 128+signum status."""
    logger.warning("Received signal %d — terminating %d active subprocess(es)",
                   signum, len(_active_processes))
    print(
        f"\nInterrupted (signal {signum}). Cleaning up child processes…",
        file=sys.stderr,
    )

    # Restore default disposition first so a second Ctrl-C while we're
    # cleaning up exits immediately instead of re-entering this handler.
    signal.signal(signum, signal.SIG_DFL)

    with _lock:
        snapshot = list(_active_processes)

    # Send SIGTERM, give children a moment, then SIGKILL the holdouts.
    for proc in snapshot:
        _kill_proc_group(proc, signal.SIGTERM)
    for proc in snapshot:
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            _kill_proc_group(proc, signal.SIGKILL)
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass

    # Use the conventional shell exit status: 128 + signum.
    sys.exit(128 + signum)


def install_signal_cleanup() -> None:
    """Register SIGINT (and SIGTERM on POSIX) cleanup handlers.

    Idempotent — safe to call repeatedly. Windows omits SIGTERM because
    its default disposition there is unreliable.
    """
    signal.signal(signal.SIGINT, _signal_handler)
    if os.name == "posix":
        signal.signal(signal.SIGTERM, _signal_handler)


def run(cmd: list[str], *, timeout: float | None = None, **kwargs) -> subprocess.CompletedProcess:
    """Drop-in replacement for ``subprocess.run`` that:

    * Starts the child in its own process group so we can reap descendants.
    * Tracks the child in :data:`_active_processes` for signal-driven cleanup.
    * On :class:`subprocess.TimeoutExpired`, signals the entire process group
      (not just the direct child) before re-raising.

    Returns a :class:`subprocess.CompletedProcess` with the same fields as
    the standard library version. Most callers only inspect ``returncode``,
    ``stdout``, and ``stderr``.
    """
    if os.name == "posix":
        kwargs.setdefault("start_new_session", True)
    elif os.name == "nt":
        kwargs["creationflags"] = (
            kwargs.get("creationflags", 0) | subprocess.CREATE_NEW_PROCESS_GROUP
        )

    # Re-implement subprocess.run's capture/input plumbing here so we can
    # intercept the timeout cleanup at the process-group level.
    capture_output = kwargs.pop("capture_output", False)
    if capture_output:
        kwargs.setdefault("stdout", subprocess.PIPE)
        kwargs.setdefault("stderr", subprocess.PIPE)
    input_data = kwargs.pop("input", None)
    if input_data is not None:
        kwargs.setdefault("stdin", subprocess.PIPE)

    proc = subprocess.Popen(cmd, **kwargs)
    with _lock:
        _active_processes.add(proc)
    try:
        try:
            stdout, stderr = proc.communicate(input=input_data, timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_proc_group(proc, signal.SIGTERM)
            try:
                # Bound the second communicate so a child holding the pipe
                # FD open (Chromium grandchild on Windows is the classic
                # case) doesn't hang us indefinitely.
                stdout, stderr = proc.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                _kill_proc_group(proc, signal.SIGKILL)
                try:
                    stdout, stderr = proc.communicate(timeout=1)
                except subprocess.TimeoutExpired:
                    stdout, stderr = b"", b""
            raise subprocess.TimeoutExpired(cmd, timeout, output=stdout, stderr=stderr)
        return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
    finally:
        with _lock:
            _active_processes.discard(proc)
