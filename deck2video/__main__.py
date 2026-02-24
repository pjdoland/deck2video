"""deck2video — Convert a Marp or Slidev markdown presentation into a narrated MP4 video."""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
import tempfile
import time
from pathlib import Path

from .assembler import assemble_video
from .detect import detect_format
from .marp_parser import parse_marp
from .marp_renderer import render_slides
from .slidev_parser import parse_slidev
from .slidev_renderer import render_slidev_slides
from .tts import generate_audio_for_slides, load_pronunciations
from .utils import check_ffmpeg, get_video_fps

logger = logging.getLogger(__name__)


def _discover_temp_files(temp_dir: Path) -> tuple[list[Path], list[Path]]:
    """Find existing slide images and audio files in a temp directory.

    Returns (images, audio_files) sorted by index. Raises SystemExit on mismatch.
    """
    # Try Slidev-style first (with .png extension), then Marp-style (no extension)
    images = sorted(temp_dir.glob("slides.[0-9][0-9][0-9].png"))
    if not images:
        images = sorted(temp_dir.glob("slides.[0-9][0-9][0-9]"))

    audio_files = sorted(temp_dir.glob("audio_[0-9][0-9][0-9].wav"))

    if not images:
        print(f"Error: no slide images found in {temp_dir}", file=sys.stderr)
        sys.exit(1)
    if not audio_files:
        print(f"Error: no audio files found in {temp_dir}", file=sys.stderr)
        sys.exit(1)
    if len(images) != len(audio_files):
        print(
            f"Error: found {len(images)} images but {len(audio_files)} audio files in {temp_dir}",
            file=sys.stderr,
        )
        sys.exit(1)

    return images, audio_files


def _parse_slide_list(slide_list_str: str) -> list[int]:
    """Parse a comma-separated list of slide numbers (1-based) into sorted ints."""
    try:
        indices = [int(s.strip()) for s in slide_list_str.split(",")]
    except ValueError:
        print(f"Error: invalid slide list '{slide_list_str}'. Use comma-separated numbers, e.g. 2,3,7",
              file=sys.stderr)
        sys.exit(1)
    if any(i < 1 for i in indices):
        print("Error: slide numbers must be >= 1.", file=sys.stderr)
        sys.exit(1)
    return sorted(set(indices))


def _resolve_videos_and_fps(
    slides: list,
    input_path: Path,
    explicit_fps: int | None,
) -> tuple[list[Path | None], int]:
    """Resolve video paths from slides and auto-detect FPS.

    Returns (video_paths, fps). Exits on path traversal or missing files.
    """
    input_dir = input_path.parent
    video_paths: list[Path | None] = []
    for slide in slides:
        if slide.video:
            vp = (input_dir / slide.video).resolve()
            if not str(vp).startswith(str(input_dir.resolve()) + "/"):
                print(f"Error: video path escapes input directory: {slide.video}", file=sys.stderr)
                sys.exit(1)
            if not vp.exists():
                print(f"Error: video file not found: {vp}", file=sys.stderr)
                sys.exit(1)
            video_paths.append(vp)
            print(f"  Slide {slide.index}: screencast → {vp.name}")
        else:
            video_paths.append(None)

    if explicit_fps is not None:
        fps = explicit_fps
    else:
        screencast_fps = [
            get_video_fps(vp) for vp in video_paths if vp is not None
        ]
        fps = int(max(screencast_fps)) if screencast_fps else 24
    return video_paths, fps


def _parse_slides(input_path: Path, fmt: str) -> list:
    """Parse slides using the appropriate parser for the detected format."""
    if fmt == "slidev":
        return parse_slidev(str(input_path))
    else:
        return parse_marp(str(input_path))


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="deck2video",
        description="Convert a Marp or Slidev markdown presentation into a narrated MP4 video.",
    )
    parser.add_argument("input", help="Path to the Marp or Slidev .md file")
    parser.add_argument("--output", help="Output MP4 path (default: <input>.mp4)")
    parser.add_argument("--voice", help="Path to a reference WAV for Chatterbox voice cloning")
    parser.add_argument("--device", default="auto",
                        help="Torch device: auto, cpu, cuda, or mps (default: auto)")
    parser.add_argument("--exaggeration", type=float, default=0.5,
                        help="Chatterbox exaggeration level (default: 0.5)")
    parser.add_argument("--cfg-weight", type=float, default=0.5,
                        help="Chatterbox CFG weight (default: 0.5)")
    parser.add_argument("--temperature", type=float, default=0.8,
                        help="Chatterbox sampling temperature (default: 0.8)")
    parser.add_argument("--hold-duration", type=float, default=3.0,
                        help="Seconds to hold slides with no speaker notes (default: 3)")
    parser.add_argument("--fps", type=int, default=None,
                        help="Output framerate (default: auto-detected from screencasts, or 24)")
    parser.add_argument("--temp-dir", help="Where to write intermediate files (default: system temp)")
    parser.add_argument("--pronunciations",
                        help="Path to a JSON file mapping words to phonetic respellings")
    parser.add_argument("--audio-padding", type=int, default=0,
                        help="Milliseconds of silence before and after each slide's audio (default: 0)")
    parser.add_argument("--keep-temp", action="store_true",
                        help="Don't delete intermediate files after rendering")
    parser.add_argument("--format", choices=["auto", "marp", "slidev"], default="auto",
                        help="Presentation format: auto, marp, or slidev (default: auto)")
    parser.add_argument("--interactive", "-i", action="store_true",
                        help="Review and approve each slide's TTS audio before continuing")

    rerun_group = parser.add_mutually_exclusive_group()
    rerun_group.add_argument("--reassemble", action="store_true",
                             help="Skip parse/render/TTS; assemble MP4 from existing temp dir files. "
                                  "Requires --temp-dir.")
    rerun_group.add_argument("--redo-slides", type=str, default=None, metavar="SLIDES",
                             help="Regenerate TTS audio for the listed slides (e.g. 2,3,7), "
                                  "then reassemble. Requires --temp-dir and the input .md file.")

    args = parser.parse_args()

    # Validate --reassemble / --redo-slides requirements
    if args.reassemble or args.redo_slides:
        if not args.temp_dir:
            print("Error: --reassemble and --redo-slides require --temp-dir.", file=sys.stderr)
            sys.exit(1)

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: {input_path} not found.", file=sys.stderr)
        sys.exit(1)

    output_path = Path(args.output) if args.output else input_path.with_suffix(".mp4")

    # Load pronunciation overrides
    pronunciations = None
    if args.pronunciations:
        pron_path = Path(args.pronunciations)
        if not pron_path.exists():
            print(f"Error: pronunciations file {pron_path} not found.", file=sys.stderr)
            sys.exit(1)
        pronunciations = load_pronunciations(pron_path)
        print(f"Loaded {len(pronunciations)} pronunciation override(s)")

    # Pre-flight checks
    check_ffmpeg()

    # Set up temp directory
    if args.temp_dir:
        temp_dir = Path(args.temp_dir)
        temp_dir.mkdir(parents=True, exist_ok=True)
        user_temp = True
    else:
        temp_dir = Path(tempfile.mkdtemp(prefix="deck2video_"))
        user_temp = False

    # Configure logging to file in the temp directory
    log_path = temp_dir / "deck2video.log"
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
    logging.getLogger("deck2video").setLevel(logging.DEBUG)
    logging.getLogger("deck2video").addHandler(file_handler)

    logger.info("CLI arguments: %s", vars(args))
    logger.info("Input: %s, Output: %s, Temp dir: %s", input_path, output_path, temp_dir)

    try:
        # --- Reassemble-only mode ---
        if args.reassemble:
            print("[reassemble] Discovering existing temp files…")
            images, audio_files = _discover_temp_files(temp_dir)

            # Parse markdown to resolve video paths and auto-detect FPS
            fmt = args.format
            if fmt == "auto":
                fmt = detect_format(str(input_path))
            slides = _parse_slides(input_path, fmt)
            video_paths, fps = _resolve_videos_and_fps(slides, input_path, args.fps)
            print(f"  Found {len(images)} slides, output framerate: {fps} fps")

            print("[reassemble] Assembling video…")
            t0 = time.monotonic()
            assemble_video(
                images,
                audio_files,
                output_path,
                temp_dir=temp_dir,
                fps=fps,
                videos=video_paths,
                audio_padding_ms=args.audio_padding,
            )
            logger.info("[reassemble] Assembly completed in %.2fs", time.monotonic() - t0)
            print(f"\nDone! Reassembled {len(images)} slides.")
            print(f"Output: {output_path}")

        # --- Redo-slides mode ---
        elif args.redo_slides:
            slide_indices = _parse_slide_list(args.redo_slides)

            # Parse to get speaker notes
            fmt = args.format
            if fmt == "auto":
                fmt = detect_format(str(input_path))
            print(f"  Format: {fmt}")

            print("[redo] Parsing slides…")
            slides = _parse_slides(input_path, fmt)
            print(f"  Found {len(slides)} slides")

            # Validate requested indices
            max_index = max(s.index for s in slides)
            for idx in slide_indices:
                if idx > max_index:
                    print(f"Error: slide {idx} requested but only {max_index} slides exist.",
                          file=sys.stderr)
                    sys.exit(1)

            # Discover existing files
            images, audio_files = _discover_temp_files(temp_dir)

            # Regenerate audio for selected slides only
            redo_slides = [s for s in slides if s.index in slide_indices]
            print(f"[redo] Regenerating audio for slide(s): {','.join(str(i) for i in slide_indices)}")
            t0 = time.monotonic()
            generate_audio_for_slides(
                redo_slides,
                temp_dir=temp_dir,
                voice_path=args.voice,
                device=args.device,
                exaggeration=args.exaggeration,
                cfg_weight=args.cfg_weight,
                temperature=args.temperature,
                hold_duration=args.hold_duration,
                pronunciations=pronunciations,
                interactive=args.interactive,
            )
            logger.info("[redo] Audio regeneration completed in %.2fs", time.monotonic() - t0)

            # Re-discover audio (files were overwritten in place)
            _, audio_files = _discover_temp_files(temp_dir)
            video_paths, fps = _resolve_videos_and_fps(slides, input_path, args.fps)

            print("[redo] Assembling video…")
            t0 = time.monotonic()
            assemble_video(
                images,
                audio_files,
                output_path,
                temp_dir=temp_dir,
                fps=fps,
                videos=video_paths,
                audio_padding_ms=args.audio_padding,
            )
            logger.info("[redo] Assembly completed in %.2fs", time.monotonic() - t0)
            print(f"\nDone! Redid {len(redo_slides)} slide(s), reassembled {len(images)} total.")
            print(f"Output: {output_path}")

        # --- Normal full pipeline ---
        else:
            # Detect format
            fmt = args.format
            if fmt == "auto":
                fmt = detect_format(str(input_path))
            print(f"  Format: {fmt}")

            # Step 1: Parse
            print("[1/4] Parsing slides…")
            t0 = time.monotonic()
            slides = _parse_slides(input_path, fmt)
            logger.info("[1/4] Parse completed in %.2fs — %d slides", time.monotonic() - t0, len(slides))
            print(f"  Found {len(slides)} slides")

            # Resolve video paths and auto-detect FPS from screencasts
            video_paths, fps = _resolve_videos_and_fps(slides, input_path, args.fps)
            print(f"  Output framerate: {fps} fps")

            # Step 2: Render images
            print("[2/4] Rendering slide images…")
            t0 = time.monotonic()
            if fmt == "slidev":
                images = render_slidev_slides(str(input_path), temp_dir, expected_count=len(slides))
            else:
                images = render_slides(str(input_path), temp_dir, expected_count=len(slides))
            logger.info("[2/4] Render completed in %.2fs", time.monotonic() - t0)

            # Step 3: Generate audio
            print("[3/4] Generating audio…")
            t0 = time.monotonic()
            audio_files = generate_audio_for_slides(
                slides,
                temp_dir=temp_dir,
                voice_path=args.voice,
                device=args.device,
                exaggeration=args.exaggeration,
                cfg_weight=args.cfg_weight,
                temperature=args.temperature,
                hold_duration=args.hold_duration,
                pronunciations=pronunciations,
                interactive=args.interactive,
            )
            logger.info("[3/4] Audio generation completed in %.2fs", time.monotonic() - t0)

            # Step 4: Assemble video
            print("[4/4] Assembling video…")
            t0 = time.monotonic()
            assemble_video(
                images,
                audio_files,
                output_path,
                temp_dir=temp_dir,
                fps=fps,
                videos=video_paths,
                audio_padding_ms=args.audio_padding,
            )
            logger.info("[4/4] Assembly completed in %.2fs", time.monotonic() - t0)

            # Summary
            tts_count = sum(1 for s in slides if s.notes)
            silent_count = len(slides) - tts_count
            video_count = sum(1 for v in video_paths if v is not None)
            parts = [f"{tts_count} narrated", f"{silent_count} silent"]
            if video_count:
                parts.append(f"{video_count} with screencast")
            logger.info("Done: %d slides (%s), output=%s", len(slides), ", ".join(parts), output_path)
            print(f"\nDone! {len(slides)} slides processed ({', '.join(parts)}).")
            print(f"Output: {output_path}")

    except Exception:
        logger.exception("Pipeline failed")
        print(f"\nError encountered. Temp files preserved at: {temp_dir}", file=sys.stderr)
        raise

    else:
        # Cleanup on success
        if not args.keep_temp and not user_temp:
            logger.info("Cleaning up temp dir: %s", temp_dir)
            shutil.rmtree(temp_dir, ignore_errors=True)
        elif args.keep_temp:
            logger.info("Temp files preserved at: %s", temp_dir)
            print(f"Temp files kept at: {temp_dir}")


if __name__ == "__main__":
    main()
