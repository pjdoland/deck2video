"""Assemble per-slide video segments and concatenate into the final MP4."""

from __future__ import annotations

import json
import logging
import math
import subprocess
import sys
from pathlib import Path

from .utils import FFPROBE_TIMEOUT_S, get_audio_duration, get_video_duration

logger = logging.getLogger(__name__)

# Per-segment ffmpeg encode budget. A 10-minute screencast slide is plausible;
# anything longer than this almost certainly means ffmpeg has wedged.
FFMPEG_SEGMENT_TIMEOUT_S = 600
# Concat is essentially a copy; should finish in seconds.
FFMPEG_CONCAT_TIMEOUT_S = 120


_SCALE_PAD_FILTER = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2"

# For screencasts: only scale down if larger than 1920x1080, otherwise keep
# original size and center on a black 1920x1080 canvas.
_VIDEO_SCALE_PAD_FILTER = (
    "scale='min(iw,1920)':'min(ih,1080)':force_original_aspect_ratio=decrease,"
    "pad=1920:1080:(ow-iw)/2:(oh-ih)/2"
)


def _frame_aligned_duration(duration_s: float, fps: float) -> float:
    """Round a duration up to the nearest whole frame at ``fps``.

    Whole-frame boundaries prevent per-segment fractional truncation that
    accumulates into A/V drift over long videos. We round *up* so audio
    pads are never clipped. Always emits at least one frame.
    """
    if fps <= 0:
        return duration_s
    n_frames = max(1, math.ceil(duration_s * fps))
    return n_frames / fps


def _make_segment(
    index: int,
    image: Path,
    audio: Path,
    temp_dir: Path,
    fps: float,
    audio_padding_ms: int = 0,
) -> Path:
    """Create a single .ts segment: image looped for the audio duration + audio."""
    audio_dur = get_audio_duration(audio)
    pad_s = audio_padding_ms / 1000
    target_dur = _frame_aligned_duration(audio_dur + 2 * pad_s, fps)
    segment = temp_dir / f"segment_{index:03d}.ts"

    af_parts: list[str] = []
    if audio_padding_ms > 0:
        af_parts.append(f"adelay={audio_padding_ms}|{audio_padding_ms}")
        # apad with whole_dur extends audio to exactly target_dur — bare
        # `apad` produces infinite audio that only `-t` would bound.
        af_parts.append(f"apad=whole_dur={target_dur:.4f}")

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-framerate", f"{fps:.6f}",
        "-i", str(image),
        "-i", str(audio),
        "-t", f"{target_dur:.4f}",
        "-c:v", "libx264",
        "-tune", "stillimage",
        "-pix_fmt", "yuv420p",
        "-vf", _SCALE_PAD_FILTER,
        "-c:a", "aac",
        "-b:a", "192k",
        *(["-af", ",".join(af_parts)] if af_parts else []),
        "-f", "mpegts",
        str(segment),
    ]
    logger.debug("Segment %d command: %s", index, " ".join(cmd))
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=FFMPEG_SEGMENT_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"ffmpeg timed out after {FFMPEG_SEGMENT_TIMEOUT_S}s on segment {index}"
        ) from exc
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
    fps: float,
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
    target_dur = _frame_aligned_duration(max(audio_dur, video_dur) + 2 * pad_s, fps)
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
        af_parts.append(f"apad=whole_dur={target_dur:.4f}")

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video),
        "-i", str(audio),
        "-t", f"{target_dur:.4f}",
        "-map", "0:v",
        "-map", "1:a",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-r", f"{fps:.6f}",
        "-vf", vf,
        *(["-af", ",".join(af_parts)] if af_parts else []),
        "-c:a", "aac",
        "-b:a", "192k",
        "-f", "mpegts",
        str(segment),
    ]
    logger.debug("Video segment %d command: %s", index, " ".join(cmd))
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=FFMPEG_SEGMENT_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"ffmpeg timed out after {FFMPEG_SEGMENT_TIMEOUT_S}s on video segment {index}"
        ) from exc
    logger.debug("Video segment %d stdout: %s", index, result.stdout)
    logger.debug("Video segment %d stderr: %s", index, result.stderr)
    if result.returncode != 0:
        print(f"ffmpeg video-segment error (slide {index}):", result.stderr, file=sys.stderr)
        raise RuntimeError(f"ffmpeg failed on video segment {index}")
    return segment


def _probe_segment_streams(segment: Path) -> dict:
    """Return the parsed ffprobe stream info for a segment."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_streams",
                str(segment),
            ],
            capture_output=True,
            text=True,
            timeout=FFPROBE_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"ffprobe timed out after {FFPROBE_TIMEOUT_S}s on {segment}"
        ) from exc
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {segment}: {result.stderr}")
    return json.loads(result.stdout)


def _verify_concat_compatibility(segments: list[Path]) -> None:
    """Assert all segments share pix_fmt, video timebase, and AAC profile.

    The concat demuxer with ``-c copy`` (used in :func:`assemble_video`)
    silently produces A/V drift if these don't match across segments. We
    catch the divergence here with a clear error rather than letting users
    discover it after a long render.
    """
    if len(segments) <= 1:
        return

    def _video_audio(seg: Path) -> tuple[dict | None, dict | None]:
        info = _probe_segment_streams(seg)
        v = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
        a = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)
        return v, a

    ref_v, ref_a = _video_audio(segments[0])
    if ref_v is None:
        raise RuntimeError(f"Segment {segments[0].name} has no video stream")

    def _video_key(v: dict) -> tuple:
        # r_frame_rate matters: two segments at 29.97 vs 30 fps will concat-copy
        # and silently drift. width/height matter even though SCALE_PAD_FILTER
        # forces 1920x1080 — defensive against future segment-builder changes.
        return (
            v.get("pix_fmt"), v.get("time_base"), v.get("codec_name"),
            v.get("r_frame_rate"), v.get("width"), v.get("height"),
        )

    def _audio_key(a: dict | None) -> tuple:
        if a is None:
            return (None, None, None, None)
        # channels matters: a stereo screencast mixed with mono TTS segments
        # produces silence on the seam under -c copy.
        return (a.get("codec_name"), a.get("profile"),
                a.get("sample_rate"), a.get("channels"))

    ref_v_key = _video_key(ref_v)
    ref_a_key = _audio_key(ref_a)

    mismatches: list[str] = []
    for seg in segments[1:]:
        v, a = _video_audio(seg)
        if v is None:
            mismatches.append(f"  {seg.name}: missing video stream")
            continue
        if _video_key(v) != ref_v_key:
            mismatches.append(
                f"  {seg.name}: video {_video_key(v)} != reference {ref_v_key}"
            )
        if _audio_key(a) != ref_a_key:
            mismatches.append(
                f"  {seg.name}: audio {_audio_key(a)} != reference {ref_a_key}"
            )

    if mismatches:
        msg = (
            "Concat segments are not bit-identical; concatenating with -c copy would "
            "cause A/V drift. Mismatches:\n" + "\n".join(mismatches)
        )
        raise RuntimeError(msg)


def assemble_video(
    images: list[Path],
    audio_files: list[Path],
    output: Path,
    *,
    temp_dir: Path,
    fps: float,
    videos: list[Path | None] | None = None,
    audio_padding_ms: int | list[int] = 0,
) -> None:
    """Build per-slide segments and concatenate into the final MP4.

    ``audio_padding_ms`` can be a scalar (applied to every segment) or a list
    of per-segment values (must match the number of images).
    """
    if videos is None:
        videos = [None] * len(images)

    if isinstance(audio_padding_ms, list):
        padding_per_step = audio_padding_ms
    else:
        padding_per_step = [audio_padding_ms] * len(images)

    segments: list[Path] = []
    for i, (img, aud, vid, pad) in enumerate(zip(images, audio_files, videos, padding_per_step), start=1):
        if vid is not None:
            print(f"  Encoding video segment {i}/{len(images)} ({vid.name})…")
            seg = _make_video_segment(i, vid, aud, temp_dir, fps, pad)
        else:
            print(f"  Encoding segment {i}/{len(images)}…")
            seg = _make_segment(i, img, aud, temp_dir, fps, pad)
        segments.append(seg)

    # Verify codec/timebase compatibility before concat -c copy
    _verify_concat_compatibility(segments)

    # Write concat list. ffmpeg's concat demuxer treats single-quote as a
    # literal quote, so any embedded "'" must be escaped as "'\''".
    concat_file = temp_dir / "concat.txt"
    with open(concat_file, "w", encoding="utf-8") as f:
        for seg in segments:
            escaped = seg.name.replace("'", r"'\''")
            f.write(f"file '{escaped}'\n")
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
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=FFMPEG_CONCAT_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"ffmpeg concat timed out after {FFMPEG_CONCAT_TIMEOUT_S}s"
        ) from exc
    logger.debug("Concat stdout: %s", result.stdout)
    logger.debug("Concat stderr: %s", result.stderr)
    if result.returncode != 0:
        print("ffmpeg concat error:", result.stderr, file=sys.stderr)
        raise RuntimeError("ffmpeg concat failed")

    file_size = output.stat().st_size
    logger.info("Output file: %s (%d bytes, %.1f MB)", output, file_size, file_size / 1024 / 1024)
    print(f"  Output: {output} ({file_size / 1024 / 1024:.1f} MB)")
