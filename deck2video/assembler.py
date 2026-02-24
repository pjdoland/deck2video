"""Assemble per-slide video segments and concatenate into the final MP4."""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

from .utils import get_audio_duration, get_video_duration

logger = logging.getLogger(__name__)


_SCALE_PAD_FILTER = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2"

# For screencasts: only scale down if larger than 1920x1080, otherwise keep
# original size and center on a black 1920x1080 canvas.
_VIDEO_SCALE_PAD_FILTER = (
    "scale='min(iw,1920)':'min(ih,1080)':force_original_aspect_ratio=decrease,"
    "pad=1920:1080:(ow-iw)/2:(oh-ih)/2"
)


def _make_segment(
    index: int,
    image: Path,
    audio: Path,
    temp_dir: Path,
    fps: int,
    audio_padding_ms: int = 0,
) -> Path:
    """Create a single .ts segment: image looped for the audio duration + audio."""
    duration = get_audio_duration(audio)
    pad_s = audio_padding_ms / 1000
    duration += 2 * pad_s
    segment = temp_dir / f"segment_{index:03d}.ts"

    af_parts: list[str] = []
    if audio_padding_ms > 0:
        af_parts.append(f"adelay={audio_padding_ms}|{audio_padding_ms}")

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-framerate", str(fps),
        "-i", str(image),
        "-i", str(audio),
        "-t", f"{duration:.4f}",
        "-c:v", "libx264",
        "-tune", "stillimage",
        "-pix_fmt", "yuv420p",
        "-vf", _SCALE_PAD_FILTER,
        "-c:a", "aac",
        "-b:a", "192k",
        *(["-af", ",".join(af_parts)] if af_parts else []),
        "-shortest",
        "-f", "mpegts",
        str(segment),
    ]
    logger.debug("Segment %d command: %s", index, " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    logger.debug("Segment %d stdout: %s", index, result.stdout)
    logger.debug("Segment %d stderr: %s", index, result.stderr)
    if result.returncode != 0:
        print(f"ffmpeg segment error (slide {index}):", result.stderr, file=sys.stderr)
        raise RuntimeError(f"ffmpeg failed on segment {index}")
    return segment


def _make_video_segment(
    index: int,
    video: Path,
    audio: Path,
    temp_dir: Path,
    fps: int,
    audio_padding_ms: int = 0,
) -> Path:
    """Create a .ts segment from a screencast video + TTS audio.

    The screencast's own audio is stripped.  Duration is the longer of the
    video or the TTS audio.  If the audio is longer, the last video frame
    is frozen (tpad stop_mode=clone).
    """
    audio_dur = get_audio_duration(audio)
    video_dur = get_video_duration(video)
    pad_s = audio_padding_ms / 1000
    target_dur = max(audio_dur, video_dur) + 2 * pad_s
    segment = temp_dir / f"segment_{index:03d}.ts"

    # Build the video filter chain.  If audio (with padding) outlasts the
    # video we need tpad to freeze the last frame for the remaining time.
    vf_parts: list[str] = []
    padded_audio_dur = audio_dur + 2 * pad_s
    if padded_audio_dur > video_dur:
        freeze_seconds = padded_audio_dur - video_dur
        vf_parts.append(f"tpad=stop_mode=clone:stop_duration={freeze_seconds:.4f}")
    vf_parts.append(_VIDEO_SCALE_PAD_FILTER)
    vf = ",".join(vf_parts)

    af_parts: list[str] = []
    if audio_padding_ms > 0:
        af_parts.append(f"adelay={audio_padding_ms}|{audio_padding_ms}")

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video),
        "-i", str(audio),
        "-t", f"{target_dur:.4f}",
        "-map", "0:v",
        "-map", "1:a",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-r", str(fps),
        "-vf", vf,
        *(["-af", ",".join(af_parts)] if af_parts else []),
        "-c:a", "aac",
        "-b:a", "192k",
        "-f", "mpegts",
        str(segment),
    ]
    logger.debug("Video segment %d command: %s", index, " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    logger.debug("Video segment %d stdout: %s", index, result.stdout)
    logger.debug("Video segment %d stderr: %s", index, result.stderr)
    if result.returncode != 0:
        print(f"ffmpeg video-segment error (slide {index}):", result.stderr, file=sys.stderr)
        raise RuntimeError(f"ffmpeg failed on video segment {index}")
    return segment


def assemble_video(
    images: list[Path],
    audio_files: list[Path],
    output: Path,
    *,
    temp_dir: Path,
    fps: int,
    videos: list[Path | None] | None = None,
    audio_padding_ms: int = 0,
) -> None:
    """Build per-slide segments and concatenate into the final MP4."""
    if videos is None:
        videos = [None] * len(images)

    segments: list[Path] = []
    for i, (img, aud, vid) in enumerate(zip(images, audio_files, videos), start=1):
        if vid is not None:
            print(f"  Encoding video segment {i}/{len(images)} ({vid.name})…")
            seg = _make_video_segment(i, vid, aud, temp_dir, fps, audio_padding_ms)
        else:
            print(f"  Encoding segment {i}/{len(images)}…")
            seg = _make_segment(i, img, aud, temp_dir, fps, audio_padding_ms)
        segments.append(seg)

    # Write concat list
    concat_file = temp_dir / "concat.txt"
    with open(concat_file, "w") as f:
        for seg in segments:
            f.write(f"file '{seg.name}'\n")
    logger.debug("Concat file contents:\n%s", "\n".join(f"file '{seg}'" for seg in segments))

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-c", "copy",
        str(output),
    ]
    logger.debug("Concat command: %s", " ".join(cmd))
    print(f"  Concatenating {len(segments)} segments…")
    result = subprocess.run(cmd, capture_output=True, text=True)
    logger.debug("Concat stdout: %s", result.stdout)
    logger.debug("Concat stderr: %s", result.stderr)
    if result.returncode != 0:
        print("ffmpeg concat error:", result.stderr, file=sys.stderr)
        raise RuntimeError("ffmpeg concat failed")

    file_size = output.stat().st_size
    logger.info("Output file: %s (%d bytes, %.1f MB)", output, file_size, file_size / 1024 / 1024)
    print(f"  Output: {output} ({file_size / 1024 / 1024:.1f} MB)")
