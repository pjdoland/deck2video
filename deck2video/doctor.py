"""Preflight subcommand: verify external tooling, GPU, model cache, and disk.

``python -m deck2video doctor`` runs a sequence of independent checks and
prints one line per check. Exits 0 if every check passes; non-zero if any
check fails. The intent is to surface install / environment problems
*before* the user starts a long render.

Each check is a thin wrapper that returns a (status, message) tuple. They
must not raise — failures are reported as :data:`_FAIL` with the diagnostic.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import process

logger = logging.getLogger(__name__)


def _ascii_only_stdout() -> bool:
    """Return True if stdout can't encode unicode sigils (Windows cp1252, LANG=C)."""
    enc = (getattr(sys.stdout, "encoding", None) or "").lower()
    return "utf" not in enc


# Status sigils. Unicode by default; ASCII fallback on encoding-limited
# terminals so the output (which the user is reading *because* something
# is broken) doesn't itself crash with UnicodeEncodeError.
if _ascii_only_stdout():
    _OK = "OK  "
    _WARN = "WARN"
    _FAIL = "FAIL"
else:
    _OK = "✓"
    _WARN = "!"
    _FAIL = "✗"


def _install_hint(tool: str) -> str:
    """Platform-tailored install hint for a missing tool."""
    plat = sys.platform
    if tool == "ffmpeg":
        if plat == "darwin":
            return "install: brew install ffmpeg"
        if plat.startswith("linux"):
            return "install: apt install ffmpeg / dnf install ffmpeg"
        return "install: see https://ffmpeg.org/download.html"
    if tool == "node":
        if plat == "darwin":
            return "install: brew install node"
        if plat.startswith("linux"):
            return "install: apt install nodejs npm"
        return "install: see https://nodejs.org/"
    return ""


def _run_quick(cmd: list[str], *, timeout: float = 10.0) -> tuple[int, str]:
    """Run a quick command and return (returncode, combined-output)."""
    try:
        result = process.run(
            cmd, capture_output=True, text=True, timeout=timeout,
        )
    except FileNotFoundError:
        return (127, f"{cmd[0]}: command not found")
    except subprocess.TimeoutExpired:
        return (124, f"{cmd[0]}: timed out after {timeout}s")
    return (result.returncode, (result.stdout or "") + (result.stderr or ""))


def check_python() -> tuple[str, str]:
    """Confirm Python version is supported."""
    major, minor = sys.version_info[:2]
    version = f"{major}.{minor}.{sys.version_info.micro}"
    if (major, minor) >= (3, 11):
        return (_OK, f"Python {version}")
    return (_FAIL, f"Python {version} — 3.11+ required")


def check_ffmpeg() -> tuple[str, str]:
    """Verify ffmpeg is on PATH and runnable."""
    if shutil.which("ffmpeg") is None:
        hint = _install_hint("ffmpeg")
        return (_FAIL, f"ffmpeg not on PATH ({hint})")
    rc, out = _run_quick(["ffmpeg", "-version"])
    if rc != 0:
        first = out.splitlines()[0] if out else "no output"
        return (_FAIL, f"ffmpeg -version failed: {first}")
    first_line = out.splitlines()[0] if out else "ffmpeg ok"
    return (_OK, first_line)


def check_ffprobe() -> tuple[str, str]:
    """Verify ffprobe is on PATH and runnable."""
    if shutil.which("ffprobe") is None:
        return (_FAIL, "ffprobe not on PATH (usually ships with ffmpeg)")
    rc, _ = _run_quick(["ffprobe", "-version"])
    if rc != 0:
        return (_FAIL, "ffprobe -version failed")
    return (_OK, "ffprobe available")


def check_marp() -> tuple[str, str]:
    """marp-cli is reachable globally OR via npx."""
    if shutil.which("marp"):
        rc, out = _run_quick(["marp", "--version"])
        if rc == 0:
            return (_OK, f"marp-cli {out.strip().splitlines()[0]} (global)")
        return (_WARN, "marp on PATH but --version failed")
    if shutil.which("npx"):
        return (_WARN, "marp-cli not installed globally; will fall back to npx (slower first run)")
    return (_FAIL, f"Neither marp nor npx on PATH ({_install_hint('node')})")


def check_slidev() -> tuple[str, str]:
    """slidev CLI is reachable (only required for Slidev decks)."""
    if shutil.which("slidev"):
        return (_OK, "slidev (global)")
    if shutil.which("npx"):
        return (_WARN, "slidev not installed globally; will fall back to npx (Slidev decks only)")
    return (_WARN, "Neither slidev nor npx on PATH — Slidev rendering will be unavailable")


def check_gpu() -> tuple[str, str]:
    """Detect a usable accelerator. Informational — CPU is fine, just slower."""
    try:
        import torch
    except Exception as exc:
        return (_WARN, f"torch not importable: {exc}")
    if torch.cuda.is_available():
        try:
            name = torch.cuda.get_device_name(0)
            return (_OK, f"CUDA available ({name})")
        except Exception:
            return (_OK, "CUDA available")
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return (_OK, "Apple MPS available")
    return (_WARN, "No GPU detected — TTS will run on CPU (much slower)")


def check_disk(min_free_gb: float = 5.0) -> tuple[str, str]:
    """Verify the temp partition has enough free space for a render."""
    target = Path(tempfile.gettempdir())
    try:
        free_gb = shutil.disk_usage(target).free / (1024 ** 3)
    except OSError as exc:
        return (_FAIL, f"disk_usage({target}) failed: {exc}")
    if free_gb < min_free_gb:
        ge = ">=" if _ascii_only_stdout() else "≥"
        return (_FAIL, f"only {free_gb:.1f} GB free in {target} (need {ge} {min_free_gb} GB)")
    return (_OK, f"{free_gb:.1f} GB free in {target}")


def _hf_cache_root() -> Path:
    """Return the HuggingFace cache root, honoring both env vars."""
    # HUGGINGFACE_HUB_CACHE wins over HF_HOME per HuggingFace's own resolution.
    explicit = os.environ.get("HUGGINGFACE_HUB_CACHE")
    if explicit:
        return Path(explicit)
    return Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"


def check_chatterbox_cache() -> tuple[str, str]:
    """Detect a HuggingFace cache containing a Chatterbox checkpoint.

    Informational only — first-run users haven't loaded a model yet so a
    WARN here is expected. Tightened glob targets the canonical HF
    snapshot path so we don't false-positive on unrelated repos containing
    "chatterbox" in their name, and short-circuits on the first hit so
    we don't walk gigabytes of unrelated cache files.
    """
    cache_root = _hf_cache_root()
    # Real path is e.g. hub/models--ResembleAI--chatterbox/snapshots/<sha>/...
    # Some users may have HF_HOME pointing at the parent (no `hub`), so
    # check both. glob() on a non-existent path is a graceful no-op.
    for root in (cache_root, cache_root.parent):
        if not root.exists():
            continue
        match = next(root.glob("models--*chatterbox*"), None)
        if match is not None:
            return (_OK, f"chatterbox snapshot present ({match.name})")
    return (_WARN, f"No chatterbox snapshot in {cache_root} — model will download on first run")


# Order matters: hard requirements first, then soft / informational.
# Each check returns (sigil, message). Result is the worst sigil seen.
CHECKS = [
    ("python", check_python),
    ("ffmpeg", check_ffmpeg),
    ("ffprobe", check_ffprobe),
    ("marp-cli", check_marp),
    ("slidev", check_slidev),
    ("gpu", check_gpu),
    ("disk", check_disk),
    ("chatterbox cache", check_chatterbox_cache),
]


def run_doctor() -> int:
    """Run all preflight checks. Return shell exit code."""
    try:
        from . import __version__ as version
    except ImportError:
        version = "(version unknown)"

    print(f"deck2video doctor {version} — preflight checks\n")

    # Width up to the longest check name so messages line up regardless
    # of how many checks we add.
    name_width = max(len(name) for name, _ in CHECKS)

    overall_ok = True
    overall_warn = False
    for name, check in CHECKS:
        try:
            sigil, msg = check()
        except Exception as exc:
            sigil, msg = _FAIL, f"check raised: {exc!r}"
            logger.exception("doctor check %s raised", name)
        print(f"  {sigil}  {name:<{name_width}}  {msg}")
        if sigil == _FAIL:
            overall_ok = False
        elif sigil == _WARN:
            overall_warn = True

    print()
    if not overall_ok:
        warn = "FAIL" if _ascii_only_stdout() else "✗"
        print(f"Some required checks failed. Fix the items marked {warn} before rendering.",
              file=sys.stderr)
        return 1
    if overall_warn:
        warn = "WARN" if _ascii_only_stdout() else "!"
        print(f"All required checks passed. Items marked {warn} are warnings — review them if you hit issues.")
    else:
        print("All checks passed.")
    return 0
