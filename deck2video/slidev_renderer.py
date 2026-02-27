"""Render slide images using Slidev CLI."""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def check_slidev_cli() -> None:
    """Exit with helpful instructions if Slidev CLI is not available."""
    if shutil.which("slidev") is None and shutil.which("npx") is None:
        print(
            "Error: Neither `slidev` nor `npx` found on PATH.\n"
            "Install Slidev CLI with one of:\n"
            "  npm install -g @slidev/cli\n"
            "  # or use npx (requires Node.js / npm)\n",
            file=sys.stderr,
        )
        sys.exit(1)


def render_slidev_slides(
    input_md: str, temp_dir: Path, expected_count: int
) -> list[Path]:
    """Export a Slidev deck to PNG images.

    Returns a sorted list of image paths.
    """
    check_slidev_cli()

    output_stem = temp_dir / "slides"

    cmd: list[str]
    if shutil.which("slidev"):
        cmd = ["slidev"]
    else:
        cmd = ["npx", "@slidev/cli"]

    cmd += [
        "export",
        str(Path(input_md).resolve()),
        "--format", "png",
        "--output", str(output_stem),
    ]

    logger.debug("slidev command: %s", " ".join(cmd))
    print(f"  Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
    logger.debug("slidev stderr: %s", result.stderr)
    if result.returncode != 0:
        print("slidev stderr:", result.stderr, file=sys.stderr)
        raise RuntimeError(f"slidev export exited with code {result.returncode}")

    # Slidev export produces a slides/ subdirectory with 1.png, 2.png, …
    # Sort numerically so slide 10 comes after 9, not after 1.
    images = sorted(
        (temp_dir / "slides").glob("*.png"),
        key=lambda p: int(p.stem),
    )
    logger.debug("Rendered %d image(s): %s", len(images), images)

    if len(images) != expected_count:
        print(
            f"Error: parsed {expected_count} slides but slidev export produced "
            f"{len(images)} images.",
            file=sys.stderr,
        )
        print("  Images found:", file=sys.stderr)
        for img in images:
            print(f"    {img}", file=sys.stderr)
        sys.exit(1)

    return images
