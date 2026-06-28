"""deck2video — Convert a Marp or Slidev markdown presentation into a narrated MP4 video."""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

from . import process
from .assembler import assemble_video
from .detect import detect_format
from .elevenlabs_tts import generate_audio_for_slides_elevenlabs
from .marp_parser import parse_marp
from .marp_renderer import render_slides
from .models import expand_slides_to_steps
from .slidev_parser import parse_slidev
from .slidev_renderer import _parse_image_stem, render_slidev_slides
from .tts import compile_pronunciations, generate_audio_for_slides, load_pronunciations
from .utils import check_ffmpeg, get_video_fps

logger = logging.getLogger(__name__)

# Minimum free disk space required before starting a render. A single
# 10-min 1080p screencast .ts segment can be 150–300 MB, and concat
# doubles peak usage briefly, so 5 GB is a realistic floor for typical decks.
MIN_FREE_DISK_GB = 5.0

# Markdown size cap. A real-world Marp/Slidev deck is well under this.
# Anything larger is almost certainly a misuse (or an attacker trying to
# starve the renderer for memory).
MAX_INPUT_BYTES = 10 * 1024 * 1024  # 10 MiB

# Default upper bound on slide count to keep accidental runs from kicking
# off multi-hour renders. Override with --max-slides.
DEFAULT_MAX_SLIDES = 500

# Flags whose value is only meaningful when the TTS phase actually runs.
# Used by --reassemble to warn about ignored input.
TTS_ONLY_FLAGS = {
    "--voice", "--device", "--exaggeration", "--cfg-weight",
    "--temperature", "--pronunciations", "--interactive", "-i",
    "--language", "--hold-duration",
    "--tts-engine", "--elevenlabs-voice-id", "--elevenlabs-model",
}


def _ranged_int(min_val: int, max_val: int, name: str):
    """Return an argparse type-converter that enforces ``min_val <= v <= max_val``."""
    def parse(value: str) -> int:
        try:
            n = int(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                f"{name} must be an integer, got {value!r}"
            ) from exc
        if n < min_val or n > max_val:
            raise argparse.ArgumentTypeError(
                f"{name} must be between {min_val} and {max_val}, got {n}"
            )
        return n
    return parse


def _ranged_float(min_val: float, max_val: float, name: str):
    """Return an argparse type-converter that enforces ``min_val <= v <= max_val``."""
    def parse(value: str) -> float:
        try:
            x = float(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                f"{name} must be a number, got {value!r}"
            ) from exc
        if x < min_val or x > max_val:
            raise argparse.ArgumentTypeError(
                f"{name} must be between {min_val} and {max_val}, got {x}"
            )
        return x
    return parse


def _discover_temp_files(temp_dir: Path) -> tuple[list[Path], list[Path]]:
    """Find existing slide images and audio files in a temp directory.

    Returns (images, audio_files) sorted by index. Raises SystemExit on mismatch.
    """
    # Try Slidev v52+ style first (slides/1.png, slides/2.png, …)
    # With --with-clicks, click steps appear as slides/2-1.png, slides/2-2.png, etc.
    slides_subdir = temp_dir / "slides"
    if slides_subdir.is_dir():
        images = sorted(slides_subdir.glob("*.png"), key=lambda p: _parse_image_stem(p.stem))
    else:
        # Older Slidev style (slides.001.png) then Marp-style (no extension)
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
    """Parse a slide list (1-based) into sorted unique ints.

    Accepts comma-separated numbers and inclusive ranges, e.g.
    ``"2,5,7"`` → ``[2, 5, 7]`` and ``"2-5,8"`` → ``[2, 3, 4, 5, 8]``.
    Warns on duplicates rather than dropping them silently.
    """
    indices: list[int] = []
    for part in slide_list_str.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            try:
                start_str, end_str = part.split("-", 1)
                start_n = int(start_str)
                end_n = int(end_str)
            except ValueError:
                print(
                    f"Error: invalid range '{part}' in slide list. Use e.g. '2-5'.",
                    file=sys.stderr,
                )
                sys.exit(1)
            if end_n < start_n:
                print(
                    f"Error: descending range '{part}' is not allowed.",
                    file=sys.stderr,
                )
                sys.exit(1)
            indices.extend(range(start_n, end_n + 1))
        else:
            try:
                indices.append(int(part))
            except ValueError:
                print(
                    f"Error: invalid slide number '{part}'. "
                    "Use comma-separated numbers and ranges, e.g. 2,3,7 or 2-5,8.",
                    file=sys.stderr,
                )
                sys.exit(1)

    if not indices:
        print(f"Error: empty slide list '{slide_list_str}'.", file=sys.stderr)
        sys.exit(1)
    if any(i < 1 for i in indices):
        print("Error: slide numbers must be >= 1.", file=sys.stderr)
        sys.exit(1)

    deduped = sorted(set(indices))
    if len(deduped) != len(indices):
        dups = sorted(i for i, c in Counter(indices).items() if c > 1)
        print(
            f"  Note: duplicates removed from --redo-slides: {','.join(map(str, dups))}",
            file=sys.stderr,
        )
    return deduped


def _resolve_videos_and_fps(
    slides: list,
    input_path: Path,
    explicit_fps: int | None,
) -> tuple[list[Path | None], float]:
    """Resolve video paths from slides and auto-detect FPS.

    Returns (video_paths, fps). FPS is a float so fractional rates like
    29.97 are preserved end-to-end (truncating to int causes A/V drift).
    Exits on path traversal or missing files.
    """
    input_dir = input_path.parent.resolve()
    video_paths: list[Path | None] = []
    for slide in slides:
        if slide.video:
            vp = (input_dir / slide.video).resolve()
            try:
                vp.relative_to(input_dir)
            except ValueError:
                print(f"Error: video path escapes input directory: {slide.video}", file=sys.stderr)
                sys.exit(1)
            if not vp.exists():
                print(f"Error: video file not found: {vp}", file=sys.stderr)
                sys.exit(1)
            video_paths.append(vp)
            display_idx = slide.slide_index if hasattr(slide, "slide_index") else slide.index
            print(f"  Slide {display_idx}: screencast → {vp.name}")
        else:
            video_paths.append(None)

    if explicit_fps is not None:
        fps: float = float(explicit_fps)
    else:
        screencast_fps = [
            get_video_fps(vp) for vp in video_paths if vp is not None
        ]
        fps = max(screencast_fps) if screencast_fps else 24.0
    return video_paths, fps


def _build_padding_list(steps: list, audio_padding_ms: int, with_clicks_padding_ms: int) -> list[int]:
    """Return a per-step padding list.

    Steps that start a new slide (click == 0) use ``audio_padding_ms``.
    Steps that are within a slide (click > 0) use ``with_clicks_padding_ms``.
    Plain ``Slide`` objects (Marp, no click attribute) always use ``audio_padding_ms``.
    """
    result = []
    for step in steps:
        click = getattr(step, "click", 0)
        result.append(audio_padding_ms if click == 0 else with_clicks_padding_ms)
    return result


def _write_manifest(steps: list, temp_dir: Path) -> None:
    """Write steps.json recording the flat Slidev step structure.

    Captures {index, slide_index, click} for every step so that a future
    --redo-slides run can detect click-count changes and remap audio files.
    Only called for Slidev format.
    """
    entries = [
        {"index": s.index, "slide_index": s.slide_index, "click": s.click}
        for s in steps
    ]
    manifest_path = temp_dir / "steps.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)
    logger.debug("Wrote manifest with %d steps to %s", len(entries), manifest_path)


def _read_manifest(temp_dir: Path) -> list[dict] | None:
    """Load steps.json from temp_dir. Returns None if the file doesn't exist."""
    manifest_path = temp_dir / "steps.json"
    if not manifest_path.exists():
        return None
    with open(manifest_path, encoding="utf-8") as f:
        return json.load(f)


def _build_audio_remap(
    old_steps: list[dict],
    new_steps: list,
    redo_slide_indices: set[int],
) -> dict[int, int]:
    """Build a map of old audio step index → new audio step index for unchanged steps.

    Steps belonging to redo'd slides are excluded (their audio will be regenerated).
    Only steps whose position has actually shifted are included.
    """
    old_lookup: dict[tuple[int, int], int] = {
        (s["slide_index"], s["click"]): s["index"]
        for s in old_steps
        if s["slide_index"] not in redo_slide_indices
    }
    rename_map: dict[int, int] = {}
    for new_step in new_steps:
        if new_step.slide_index not in redo_slide_indices:
            key = (new_step.slide_index, new_step.click)
            old_idx = old_lookup.get(key)
            if old_idx is not None and old_idx != new_step.index:
                rename_map[old_idx] = new_step.index
    return rename_map


def _apply_audio_renames(
    rename_map: dict[int, int],
    old_steps: list[dict],
    redo_slide_indices: set[int],
    temp_dir: Path,
) -> None:
    """Rename audio files for shifted unchanged steps; delete audio for redo'd steps.

    Uses two-pass staging (rename to .tmp first, then to final names) to avoid
    collisions when file A must move to position B while B moves to position C.
    """
    # Pass 1: Stage files that need renaming to .tmp names
    for old_idx in rename_map:
        src = temp_dir / f"audio_{old_idx:03d}.wav"
        if src.exists():
            src.rename(temp_dir / f"audio_{old_idx:03d}.wav.tmp")
            logger.debug("Staged audio_%03d.wav → .tmp", old_idx)

    # Delete audio files belonging to redo'd steps (TTS will create fresh ones)
    for s in old_steps:
        if s["slide_index"] in redo_slide_indices:
            old_file = temp_dir / f"audio_{s['index']:03d}.wav"
            if old_file.exists():
                old_file.unlink()
                logger.debug("Deleted redo'd audio_%03d.wav", s["index"])

    # Pass 2: Move staged files to their final positions
    for old_idx, new_idx in rename_map.items():
        tmp = temp_dir / f"audio_{old_idx:03d}.wav.tmp"
        if tmp.exists():
            tmp.rename(temp_dir / f"audio_{new_idx:03d}.wav")
            logger.debug("Moved audio_%03d.wav.tmp → audio_%03d.wav", old_idx, new_idx)


def _generate_audio(
    steps: list,
    *,
    args,
    temp_dir: Path,
    pronunciations,
    elevenlabs_api_key: str | None,
) -> list[Path]:
    """Dispatch TTS to the selected engine.

    Both backends produce ``audio_NNN.wav`` files in ``temp_dir`` and return
    the paths in step order, so every call site is engine-agnostic.
    """
    common = dict(
        temp_dir=temp_dir,
        hold_duration=args.hold_duration,
        pronunciations=pronunciations,
        interactive=args.interactive,
    )
    if args.tts_engine == "elevenlabs":
        return generate_audio_for_slides_elevenlabs(
            steps,
            voice_id=args.elevenlabs_voice_id,
            api_key=elevenlabs_api_key,
            model_id=args.elevenlabs_model,
            **common,
        )
    return generate_audio_for_slides(
        steps,
        voice_path=args.voice,
        device=args.device,
        exaggeration=args.exaggeration,
        cfg_weight=args.cfg_weight,
        temperature=args.temperature,
        language=args.language,
        **common,
    )


def _parse_slides(input_path: Path, fmt: str) -> list:
    """Parse slides using the appropriate parser for the detected format."""
    if fmt == "slidev":
        return parse_slidev(str(input_path))
    else:
        return parse_marp(str(input_path))


def _enforce_max_slides(slides: list, max_slides: int) -> None:
    """Refuse to proceed if the parsed deck exceeds ``--max-slides``.

    Prevents accidental multi-hour renders from a runaway / misformatted
    deck. The cap also bounds memory use during step expansion and PNG
    rendering. Override with ``--max-slides``.
    """
    if len(slides) > max_slides:
        print(
            f"Error: parsed {len(slides)} slides; --max-slides is {max_slides}. "
            "If this is intentional, raise the limit with --max-slides N.",
            file=sys.stderr,
        )
        sys.exit(1)


def main() -> None:
    # Catch Ctrl-C and SIGTERM so subprocess process groups (marp/slidev/
    # ffmpeg/Chromium) are reaped cleanly instead of orphaned.
    process.install_signal_cleanup()

    # Subcommand routing: `doctor` is the only special case today.
    # Detected before argparse so the positional `input` arg doesn't
    # require restructuring into a full subparser tree. We require an
    # exact `["deck2video", "doctor"]` so a deck named "doctor.md" still
    # routes to the normal pipeline, and stray flags like `doctor --help`
    # don't get silently swallowed.
    if sys.argv[1:] == ["doctor"]:
        from .doctor import run_doctor
        sys.exit(run_doctor())
    if len(sys.argv) >= 2 and sys.argv[1] == "doctor":
        print(
            "Error: 'doctor' takes no arguments. Run as 'deck2video doctor'.",
            file=sys.stderr,
        )
        sys.exit(2)

    parser = argparse.ArgumentParser(
        prog="deck2video",
        description="Convert a Marp or Slidev markdown presentation into a narrated MP4 video. "
                    "Use 'deck2video doctor' to verify your environment before rendering.",
    )
    parser.add_argument("input", help="Path to the Marp or Slidev .md file")
    parser.add_argument("--output", help="Output MP4 path (default: <input>.mp4)")
    parser.add_argument("--tts-engine", choices=["chatterbox", "elevenlabs"], default="chatterbox",
                        help="Text-to-speech engine: chatterbox (local model, default) or "
                             "elevenlabs (hosted API; needs ELEVENLABS_API_KEY and "
                             "--elevenlabs-voice-id)")
    parser.add_argument("--elevenlabs-voice-id", default=None, metavar="ID",
                        help="ElevenLabs voice ID to narrate with (required when "
                             "--tts-engine elevenlabs)")
    parser.add_argument("--elevenlabs-model", default="eleven_multilingual_v2", metavar="MODEL",
                        help="ElevenLabs model ID (default: eleven_multilingual_v2)")
    parser.add_argument("--voice", help="Path to a reference WAV for Chatterbox voice cloning")
    parser.add_argument("--language", default=None, metavar="LANG",
                        help="Language code for multilingual TTS, e.g. en, fr, de, zh, es. "
                             "Loads ChatterboxMultilingualTTS instead of ChatterboxTTS.")
    parser.add_argument("--device", default="auto",
                        help="Torch device: auto, cpu, cuda, or mps (default: auto)")
    parser.add_argument("--exaggeration", type=_ranged_float(0.0, 2.0, "--exaggeration"), default=0.5,
                        help="Chatterbox exaggeration level, 0.0–2.0 (default: 0.5)")
    parser.add_argument("--cfg-weight", type=_ranged_float(0.0, 1.0, "--cfg-weight"), default=0.5,
                        help="Chatterbox CFG weight, 0.0–1.0 (default: 0.5)")
    parser.add_argument("--temperature", type=_ranged_float(0.0, 2.0, "--temperature"), default=0.8,
                        help="Chatterbox sampling temperature, 0.0–2.0 (default: 0.8)")
    parser.add_argument("--hold-duration", type=_ranged_float(0.1, 300.0, "--hold-duration"), default=3.0,
                        help="Seconds to hold slides with no speaker notes, 0.1–300 (default: 3)")
    parser.add_argument("--fps", type=_ranged_int(1, 120, "--fps"), default=None,
                        help="Output framerate, 1–120 (default: auto-detected from screencasts, or 24)")
    parser.add_argument("--temp-dir", help="Where to write intermediate files (default: system temp)")
    parser.add_argument("--pronunciations",
                        help="Path to a JSON file mapping words to phonetic respellings")
    parser.add_argument("--audio-padding", type=_ranged_int(0, 60000, "--audio-padding"), default=0,
                        help="Milliseconds of silence before and after each slide's audio, 0–60000 (default: 0)")
    parser.add_argument("--with-clicks-audio-padding",
                        type=_ranged_int(0, 60000, "--with-clicks-audio-padding"), default=0,
                        help="Milliseconds of silence before and after each click-step's audio, 0–60000 "
                             "(default: 0; only applies when Slidev click animation steps are present)")
    parser.add_argument("--keep-temp", action="store_true",
                        help="Don't delete intermediate files after rendering")
    parser.add_argument("--format", choices=["auto", "marp", "slidev"], default="auto",
                        help="Presentation format: auto, marp, or slidev (default: auto)")
    parser.add_argument("--interactive", "-i", action="store_true",
                        help="Review and approve each slide's TTS audio before continuing")
    parser.add_argument("--dark", action="store_true",
                        help="Render Slidev slides in dark mode (passes --dark to slidev export; "
                             "ignored for Marp presentations)")
    parser.add_argument("--max-slides", type=_ranged_int(1, 100000, "--max-slides"),
                        default=DEFAULT_MAX_SLIDES, metavar="N",
                        help=f"Refuse to render more than N slides (default: {DEFAULT_MAX_SLIDES}). "
                             "Prevents runaway renders from a misformatted deck or an attacker.")

    rerun_group = parser.add_mutually_exclusive_group()
    rerun_group.add_argument("--reassemble", action="store_true",
                             help="Skip parse/render/TTS; assemble MP4 from existing temp dir files. "
                                  "Requires --temp-dir.")
    rerun_group.add_argument("--redo-slides", type=str, default=None, metavar="SLIDES",
                             help="Regenerate TTS audio for the listed slides (e.g. 2,3,7 or 2-5,8), "
                                  "then reassemble. Slide numbers are 1-based and refer to original "
                                  "slides — for Slidev decks with click animations, all click steps "
                                  "for a slide are regenerated together. Requires --temp-dir and the "
                                  "input .md file.")

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

    # Cap markdown size — anything larger than a few MB is almost certainly
    # a misuse and would starve the parser/renderer for memory.
    input_size = input_path.stat().st_size
    if input_size > MAX_INPUT_BYTES:
        print(
            f"Error: {input_path} is {input_size / (1024**2):.1f} MiB; "
            f"max supported size is {MAX_INPUT_BYTES // (1024**2)} MiB.",
            file=sys.stderr,
        )
        sys.exit(1)

    output_path = Path(args.output) if args.output else input_path.with_suffix(".mp4")

    # Load pronunciation overrides
    pronunciations = None
    if args.pronunciations:
        pron_path = Path(args.pronunciations)
        if not pron_path.exists():
            print(f"Error: pronunciations file {pron_path} not found.", file=sys.stderr)
            sys.exit(1)
        raw_pronunciations = load_pronunciations(pron_path)
        pronunciations = compile_pronunciations(raw_pronunciations)
        print(f"Loaded {len(raw_pronunciations)} pronunciation override(s)")

    # Resolve and validate ElevenLabs configuration. Only required when the
    # TTS phase will actually run (i.e. not --reassemble), and the API key
    # comes from the environment so it never lands in shell history or logs.
    elevenlabs_api_key = None
    if args.tts_engine == "elevenlabs" and not args.reassemble:
        elevenlabs_api_key = os.environ.get("ELEVENLABS_API_KEY")
        if not elevenlabs_api_key:
            print(
                "Error: --tts-engine elevenlabs requires the ELEVENLABS_API_KEY "
                "environment variable to be set.",
                file=sys.stderr,
            )
            sys.exit(1)
        if not args.elevenlabs_voice_id:
            print(
                "Error: --tts-engine elevenlabs requires --elevenlabs-voice-id.",
                file=sys.stderr,
            )
            sys.exit(1)

    # Pre-flight checks
    check_ffmpeg()

    # Warn if TTS-only flags are passed alongside --reassemble (they're ignored).
    # argparse accepts both `--voice foo` and `--voice=foo`; the latter lands
    # in sys.argv as a single token so we strip the trailing `=value`.
    if args.reassemble:
        present = {tok.split("=", 1)[0] for tok in sys.argv}
        ignored = sorted(TTS_ONLY_FLAGS & present)
        if ignored:
            print(
                f"  Note: {', '.join(ignored)} ignored in --reassemble mode "
                "(TTS phase is skipped).",
                file=sys.stderr,
            )

    # Set up temp directory
    if args.temp_dir:
        temp_dir = Path(args.temp_dir)
        temp_dir.mkdir(parents=True, exist_ok=True)
        user_temp = True
    else:
        temp_dir = Path(tempfile.mkdtemp(prefix="deck2video_"))
        user_temp = False

    # Pre-flight: ensure enough free disk for intermediates and the final MP4
    free_gb = shutil.disk_usage(temp_dir).free / (1024 ** 3)
    if free_gb < MIN_FREE_DISK_GB:
        print(
            f"Error: only {free_gb:.2f} GB free in {temp_dir}; "
            f"need at least {MIN_FREE_DISK_GB} GB for intermediates and output.",
            file=sys.stderr,
        )
        sys.exit(1)

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
            _enforce_max_slides(slides, args.max_slides)
            # Expand Slidev slides to steps so video_paths length matches image count
            items = expand_slides_to_steps(slides) if fmt == "slidev" else slides
            video_paths, fps = _resolve_videos_and_fps(items, input_path, args.fps)
            print(f"  Found {len(images)} slides, output framerate: {fps:g} fps")

            print("[reassemble] Assembling video…")
            t0 = time.monotonic()
            assemble_video(
                images,
                audio_files,
                output_path,
                temp_dir=temp_dir,
                fps=fps,
                videos=video_paths,
                audio_padding_ms=_build_padding_list(
                    items, args.audio_padding, args.with_clicks_audio_padding
                ),
            )
            logger.info("[reassemble] Assembly completed in %.2fs", time.monotonic() - t0)
            print(f"\nDone! Reassembled {len(images)} slides.")
            print(f"Output: {output_path}")

        # --- Redo-slides mode ---
        elif args.redo_slides:
            slide_indices = _parse_slide_list(args.redo_slides)
            slide_indices_set = set(slide_indices)

            # Parse to get speaker notes
            fmt = args.format
            if fmt == "auto":
                fmt = detect_format(str(input_path))
            print(f"  Format: {fmt}")

            print("[redo] Parsing slides…")
            slides = _parse_slides(input_path, fmt)
            _enforce_max_slides(slides, args.max_slides)
            print(f"  Found {len(slides)} slides")

            # For Slidev, expand to steps so indices align with temp files
            if fmt == "slidev":
                all_steps = expand_slides_to_steps(slides)
            else:
                all_steps = slides

            # Validate requested indices against original slide numbers
            max_index = max(s.index for s in slides)
            for idx in slide_indices:
                if idx > max_index:
                    print(f"Error: slide {idx} requested but only {max_index} slides exist.",
                          file=sys.stderr)
                    sys.exit(1)

            # For Slidev: detect click-count changes via manifest
            if fmt == "slidev":
                manifest = _read_manifest(temp_dir)
                click_changed = False
                if manifest is not None:
                    old_counts: dict[int, int] = {}
                    for s in manifest:
                        si = s["slide_index"]
                        if si in slide_indices_set:
                            old_counts[si] = old_counts.get(si, 0) + 1
                    new_counts: dict[int, int] = {}
                    for s in all_steps:
                        if s.slide_index in slide_indices_set:
                            new_counts[s.slide_index] = new_counts.get(s.slide_index, 0) + 1
                    click_changed = old_counts != new_counts

                if click_changed:
                    print(f"[redo] Click structure changed for slide(s) {','.join(str(i) for i in slide_indices)} — remapping audio and re-rendering images…")

                    # Remap unchanged audio files to their new positions; delete redo'd ones
                    rename_map = _build_audio_remap(manifest, all_steps, slide_indices_set)
                    _apply_audio_renames(rename_map, manifest, slide_indices_set, temp_dir)

                    # Clean and re-render all slide images (Slidev always exports the full deck)
                    slides_dir = temp_dir / "slides"
                    if slides_dir.exists():
                        shutil.rmtree(slides_dir)
                    has_clicks = len(all_steps) > len(slides)
                    print("[redo] Re-rendering slide images…")
                    t0 = time.monotonic()
                    images = render_slidev_slides(
                        str(input_path), temp_dir,
                        expected_count=len(all_steps),
                        with_clicks=has_clicks,
                        dark=args.dark,
                    )
                    logger.info("[redo] Re-render completed in %.2fs", time.monotonic() - t0)

                    # Regenerate TTS for all steps of the redo'd slides
                    redo_steps = [s for s in all_steps if s.slide_index in slide_indices_set]
                    print(f"[redo] Regenerating audio for slide(s): {','.join(str(i) for i in slide_indices)}")
                    t0 = time.monotonic()
                    _generate_audio(
                        redo_steps,
                        args=args,
                        temp_dir=temp_dir,
                        pronunciations=pronunciations,
                        elevenlabs_api_key=elevenlabs_api_key,
                    )
                    logger.info("[redo] Audio regeneration completed in %.2fs", time.monotonic() - t0)

                    # All files now in place — discover and assemble
                    images, audio_files = _discover_temp_files(temp_dir)
                    video_paths, fps = _resolve_videos_and_fps(all_steps, input_path, args.fps)

                    print("[redo] Assembling video…")
                    t0 = time.monotonic()
                    assemble_video(
                        images,
                        audio_files,
                        output_path,
                        temp_dir=temp_dir,
                        fps=fps,
                        videos=video_paths,
                        audio_padding_ms=_build_padding_list(
                            all_steps, args.audio_padding, args.with_clicks_audio_padding
                        ),
                    )
                    logger.info("[redo] Assembly completed in %.2fs", time.monotonic() - t0)

                    _write_manifest(all_steps, temp_dir)
                    print(f"\nDone! Redid {len(redo_steps)} step(s) for slide(s) {','.join(str(i) for i in slide_indices)} (click structure changed), reassembled {len(images)} total.")
                    print(f"Output: {output_path}")
                    return

                elif manifest is None:
                    print("  Note: no steps.json manifest found; cannot detect click-count changes. Re-run the full pipeline if click counts have changed.")

            # --- Original redo path (no click change, or Marp) ---
            # Discover existing files
            images, audio_files = _discover_temp_files(temp_dir)

            # Regenerate audio for selected steps only
            # For Slidev, filter by slide_index; for Marp, filter by index
            if fmt == "slidev":
                redo_steps = [s for s in all_steps if s.slide_index in slide_indices_set]
            else:
                redo_steps = [s for s in all_steps if s.index in slide_indices_set]
            print(f"[redo] Regenerating audio for slide(s): {','.join(str(i) for i in slide_indices)}")
            t0 = time.monotonic()
            _generate_audio(
                redo_steps,
                args=args,
                temp_dir=temp_dir,
                pronunciations=pronunciations,
                elevenlabs_api_key=elevenlabs_api_key,
            )
            logger.info("[redo] Audio regeneration completed in %.2fs", time.monotonic() - t0)

            # Re-discover audio (files were overwritten in place)
            _, audio_files = _discover_temp_files(temp_dir)
            video_paths, fps = _resolve_videos_and_fps(all_steps, input_path, args.fps)

            print("[redo] Assembling video…")
            t0 = time.monotonic()
            assemble_video(
                images,
                audio_files,
                output_path,
                temp_dir=temp_dir,
                fps=fps,
                videos=video_paths,
                audio_padding_ms=_build_padding_list(
                    all_steps, args.audio_padding, args.with_clicks_audio_padding
                ),
            )
            logger.info("[redo] Assembly completed in %.2fs", time.monotonic() - t0)

            # Update manifest for Slidev (creates it if the original run pre-dated this feature)
            if fmt == "slidev":
                _write_manifest(all_steps, temp_dir)

            print(f"\nDone! Redid {len(redo_steps)} step(s) for slide(s) {','.join(str(i) for i in slide_indices)}, reassembled {len(images)} total.")
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
            _enforce_max_slides(slides, args.max_slides)
            logger.info("[1/4] Parse completed in %.2fs — %d slides", time.monotonic() - t0, len(slides))

            # For Slidev, expand slides into per-click steps
            if fmt == "slidev":
                steps = expand_slides_to_steps(slides)
                has_clicks = len(steps) > len(slides)
                if has_clicks:
                    print(f"  Found {len(slides)} slides → {len(steps)} steps (click expansion)")
                else:
                    print(f"  Found {len(slides)} slides")
                _write_manifest(steps, temp_dir)
            else:
                steps = slides
                has_clicks = False
                print(f"  Found {len(slides)} slides")

            # Resolve video paths and auto-detect FPS from screencasts
            video_paths, fps = _resolve_videos_and_fps(steps, input_path, args.fps)
            print(f"  Output framerate: {fps:g} fps")

            # Step 2: Render images
            print("[2/4] Rendering slide images…")
            t0 = time.monotonic()
            if fmt == "slidev":
                images = render_slidev_slides(
                    str(input_path), temp_dir,
                    expected_count=len(steps),
                    with_clicks=has_clicks,
                    dark=args.dark,
                )
            else:
                images = render_slides(str(input_path), temp_dir, expected_count=len(steps))
            logger.info("[2/4] Render completed in %.2fs", time.monotonic() - t0)

            # Step 3: Generate audio
            print("[3/4] Generating audio…")
            t0 = time.monotonic()
            audio_files = _generate_audio(
                steps,
                args=args,
                temp_dir=temp_dir,
                pronunciations=pronunciations,
                elevenlabs_api_key=elevenlabs_api_key,
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
                audio_padding_ms=_build_padding_list(
                    steps, args.audio_padding, args.with_clicks_audio_padding
                ),
            )
            logger.info("[4/4] Assembly completed in %.2fs", time.monotonic() - t0)

            # Summary
            tts_count = sum(1 for s in steps if s.notes)
            silent_count = len(steps) - tts_count
            video_count = sum(1 for v in video_paths if v is not None)
            parts = [f"{tts_count} narrated", f"{silent_count} silent"]
            if video_count:
                parts.append(f"{video_count} with screencast")
            if fmt == "slidev" and has_clicks:
                logger.info("Done: %d slides (%d steps, %s), output=%s", len(slides), len(steps), ", ".join(parts), output_path)
                print(f"\nDone! {len(slides)} slides ({len(steps)} steps) processed ({', '.join(parts)}).")
                print(
                    "  Tip: --redo-slides takes 1-based slide numbers (not step indices). "
                    "Regenerating a slide redoes all of its click steps."
                )
            else:
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
