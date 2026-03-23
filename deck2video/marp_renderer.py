"""Render slide images using marp-cli."""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def check_marp_cli() -> None:
    """Exit with helpful instructions if marp-cli is not available."""
    if shutil.which("npx") is None and shutil.which("marp") is None:
        print(
            "Error: Neither `npx` nor `marp` found on PATH.\n"
            "Install marp-cli with one of:\n"
            "  npm install -g @marp-team/marp-cli\n"
            "  # or use npx (requires Node.js / npm)\n",
            file=sys.stderr,
        )
        sys.exit(1)


def render_slides(input_md: str, temp_dir: Path, expected_count: int) -> list[Path]:
    """Render the Marp deck to 1920x1080 PNG images.

    Returns a sorted list of image paths.
    """
    check_marp_cli()

    output_stem = temp_dir / "slides"

    cmd: list[str]
    if shutil.which("marp"):
        cmd = ["marp"]
    else:
        # --yes auto-accepts the "Need to install @marp-team/marp-cli" prompt
        # so the pipeline never hangs waiting for hidden interactive input.
        cmd = ["npx", "--yes", "@marp-team/marp-cli"]

    cmd += [
        str(Path(input_md).resolve()),
        "--images", "png",
        "--image-scale", "2",
        "--no-stdin",
        "--output", str(output_stem),
    ]

    logger.debug("marp-cli command: %s", " ".join(cmd))
    print(f"  Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
    logger.debug("marp-cli stderr: %s", result.stderr)
    if result.returncode != 0:
        print("marp-cli stderr:", result.stderr, file=sys.stderr)
        raise RuntimeError(f"marp-cli exited with code {result.returncode}")

    # marp-cli produces slides.001, slides.002, … (no extension)
    images = sorted(temp_dir.glob("slides.[0-9][0-9][0-9]"))
    logger.debug("Rendered %d image(s): %s", len(images), images)

    if len(images) != expected_count:
        print(
            f"Error: parsed {expected_count} slides but marp-cli produced "
            f"{len(images)} images.",
            file=sys.stderr,
        )
        print("  Images found:", file=sys.stderr)
        for img in images:
            print(f"    {img}", file=sys.stderr)
        sys.exit(1)

    return list(images)
