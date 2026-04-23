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


def _parse_image_stem(stem: str) -> tuple[int, int]:
    """Parse a slide image stem into a (slide, click) sort key.

    Handles both naming conventions produced by different Slidev versions:

    Old (pre-v52): ``'3'`` → ``(3, 0)``, ``'3-1'`` → ``(3, 1)``
    New (v52+):    ``'003-01'`` → ``(3, 1)``, ``'003-02'`` → ``(3, 2)``

    Both sort correctly: initial state always has the lowest click key for a
    given slide number, and subsequent click states are ordered numerically.
    """
    if "-" in stem:
        slide_part, click_part = stem.split("-", 1)
        return (int(slide_part), int(click_part))
    return (int(stem), 0)


def render_slidev_slides(
    input_md: str, temp_dir: Path, expected_count: int, with_clicks: bool = False
) -> list[Path]:
    """Export a Slidev deck to PNG images.

    Returns a sorted list of image paths. When *with_clicks* is True the
    ``--with-clicks`` flag is appended to the export command so that Slidev
    produces one image per click step (e.g. ``2.png``, ``2-1.png``, …).
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

    if with_clicks:
        cmd.append("--with-clicks")

    logger.debug("slidev command: %s", " ".join(cmd))
    print(f"  Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
    logger.debug("slidev stderr: %s", result.stderr)
    if result.returncode != 0:
        print("slidev stderr:", result.stderr, file=sys.stderr)
        raise RuntimeError(f"slidev export exited with code {result.returncode}")

    # Slidev export produces a slides/ subdirectory with 1.png, 2.png, …
    # When --with-clicks is used, click steps appear as 2-1.png, 2-2.png, etc.
    # Sort numerically so slide 10 comes after 9, and click steps are ordered.
    images = sorted(
        (temp_dir / "slides").glob("*.png"),
        key=lambda p: _parse_image_stem(p.stem),
    )
    logger.debug("Rendered %d image(s): %s", len(images), images)

    if len(images) != expected_count:
        print(
            f"Error: expected {expected_count} step(s) but slidev export produced "
            f"{len(images)} image(s).",
            file=sys.stderr,
        )
        if with_clicks:
            print(
                "  Hint: verify that the number of [click] markers in your speaker notes "
                "matches the v-click directives in each slide.",
                file=sys.stderr,
            )
        print("  Images found:", file=sys.stderr)
        for img in images:
            print(f"    {img}", file=sys.stderr)
        sys.exit(1)

    return images
