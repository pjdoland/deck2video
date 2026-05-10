"""Utility helpers: silent WAV generation, ffprobe duration queries."""

from __future__ import annotations

import json
import logging
import shutil
import struct
import subprocess
import sys
from pathlib import Path

from . import process

logger = logging.getLogger(__name__)

# ffprobe is fast; if it takes more than this, something is wrong.
FFPROBE_TIMEOUT_S = 30


def check_ffmpeg() -> None:
    """Exit with helpful instructions if ffmpeg / ffprobe are missing."""
    missing = [
        tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None
    ]
    if not missing:
        logger.debug("ffmpeg/ffprobe found on PATH")
    if missing:
        print(
            f"Error: {', '.join(missing)} not found on PATH.\n"
            "Install ffmpeg:\n"
            "  macOS:   brew install ffmpeg\n"
            "  Ubuntu:  sudo apt install ffmpeg\n"
            "  Windows: https://ffmpeg.org/download.html\n",
            file=sys.stderr,
        )
        sys.exit(1)


def generate_silent_wav(path: Path, duration: float, sample_rate: int = 24000) -> None:
    """Write a silent WAV file of the given duration (pure Python, no deps)."""
    num_channels = 1
    bits_per_sample = 16
    num_samples = int(sample_rate * duration)
    data_size = num_samples * num_channels * (bits_per_sample // 8)

    with open(path, "wb") as f:
        # RIFF header
        f.write(b"RIFF")
        f.write(struct.pack("<I", 36 + data_size))
        f.write(b"WAVE")
        # fmt chunk
        f.write(b"fmt ")
        f.write(struct.pack("<I", 16))  # chunk size
        f.write(struct.pack("<H", 1))   # PCM
        f.write(struct.pack("<H", num_channels))
        f.write(struct.pack("<I", sample_rate))
        f.write(struct.pack("<I", sample_rate * num_channels * bits_per_sample // 8))
        f.write(struct.pack("<H", num_channels * bits_per_sample // 8))
        f.write(struct.pack("<H", bits_per_sample))
        # data chunk
        f.write(b"data")
        f.write(struct.pack("<I", data_size))
        f.write(b"\x00" * data_size)


def _wav_duration_from_header(path: Path) -> float | None:
    """Read a WAV's data-chunk size and compute exact duration from samples.

    Only supports uncompressed PCM (format tag 0x0001) and IEEE float
    (0x0003) — for anything else (μ-law, ADPCM, WAVE_FORMAT_EXTENSIBLE)
    we return None and the caller falls back to ffprobe. RIFF requires
    odd-sized chunks to be word-padded; we honor that when skipping
    unknown chunks so subsequent headers stay aligned.
    """
    PCM = 0x0001
    IEEE_FLOAT = 0x0003
    try:
        with open(path, "rb") as f:
            riff = f.read(12)
            if len(riff) < 12 or riff[0:4] != b"RIFF" or riff[8:12] != b"WAVE":
                return None
            sample_rate = None
            num_channels = None
            bits_per_sample = None
            data_size = None
            while True:
                header = f.read(8)
                if len(header) < 8:
                    break
                chunk_id = header[0:4]
                chunk_size = struct.unpack("<I", header[4:8])[0]
                if chunk_id == b"fmt ":
                    fmt = f.read(chunk_size)
                    if len(fmt) < 16:
                        return None
                    audio_format = struct.unpack("<H", fmt[0:2])[0]
                    if audio_format not in (PCM, IEEE_FLOAT):
                        return None  # let ffprobe handle non-trivial formats
                    num_channels = struct.unpack("<H", fmt[2:4])[0]
                    sample_rate = struct.unpack("<I", fmt[4:8])[0]
                    bits_per_sample = struct.unpack("<H", fmt[14:16])[0]
                    if chunk_size & 1:
                        f.seek(1, 1)  # word-pad for odd-sized chunk
                elif chunk_id == b"data":
                    data_size = chunk_size
                    break
                else:
                    # Word-pad odd-sized chunks so the next header is aligned.
                    f.seek(chunk_size + (chunk_size & 1), 1)
            if not (sample_rate and num_channels and bits_per_sample and data_size):
                return None
            bytes_per_sample = bits_per_sample // 8
            if bytes_per_sample == 0:
                return None
            num_samples = data_size // (num_channels * bytes_per_sample)
            return num_samples / sample_rate
    except (OSError, struct.error):
        return None


def get_audio_duration(path: Path) -> float:
    """Get duration of an audio file in seconds.

    For WAV files we read the RIFF header directly so the answer is sample-
    accurate. For other formats we fall back to ffprobe (container duration,
    which can drift on AAC/MP3 due to frame-boundary rounding).
    """
    if path.suffix.lower() == ".wav":
        wav_dur = _wav_duration_from_header(path)
        if wav_dur is not None:
            logger.debug("Duration of %s (WAV header): %.6fs", path, wav_dur)
            return wav_dur
    return _get_duration(path)


def get_video_duration(path: Path) -> float:
    """Get duration of a video file in seconds using ffprobe."""
    return _get_duration(path)


def get_video_fps(path: Path) -> float:
    """Get the framerate of a video file using ffprobe.

    Returns frames per second as a float (e.g. 29.97 from 30000/1001).
    Raises ``RuntimeError`` with a clear message on malformed input,
    audio-only containers, or zero-denominator rates.
    """
    try:
        result = process.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-select_streams", "v:0",
                "-show_streams",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=FFPROBE_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"ffprobe timed out after {FFPROBE_TIMEOUT_S}s on {path}"
        ) from exc
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {path}: {result.stderr}")
    try:
        info = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"ffprobe returned invalid JSON for {path}: {exc}") from exc

    streams = info.get("streams") or []
    if not streams:
        raise RuntimeError(
            f"No video stream found in {path}. "
            "Audio-only or malformed file? Remove the screencast directive or supply a file with video."
        )
    rate_str = streams[0].get("r_frame_rate")
    if not rate_str or "/" not in rate_str:
        raise RuntimeError(f"ffprobe did not report a frame rate for {path} (got {rate_str!r})")

    num_str, _, den_str = rate_str.partition("/")
    try:
        num = float(num_str)
        den = float(den_str)
    except ValueError as exc:
        raise RuntimeError(f"ffprobe returned non-numeric frame rate for {path}: {rate_str!r}") from exc
    if den == 0:
        raise RuntimeError(f"ffprobe returned zero-denominator frame rate for {path}: {rate_str!r}")
    return num / den


def _get_duration(path: Path) -> float:
    """Get duration of a media file in seconds using ffprobe."""
    try:
        result = process.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=FFPROBE_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"ffprobe timed out after {FFPROBE_TIMEOUT_S}s on {path}"
        ) from exc
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {path}: {result.stderr}")
    info = json.loads(result.stdout)
    duration = float(info["format"]["duration"])
    logger.debug("Duration of %s: %.4fs", path, duration)
    return duration
