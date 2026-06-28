"""ElevenLabs TTS backend — synthesises speaker notes to WAV files.

A drop-in alternative to :mod:`deck2video.tts` (Chatterbox). Selected with
``--tts-engine elevenlabs``. Where Chatterbox runs a local model on
CPU/GPU, this calls the hosted ElevenLabs API: one request per slide,
requesting raw ``pcm_24000`` audio that we wrap in a WAV header so the
rest of the pipeline (ffprobe, the assembler) treats it identically to
Chatterbox output.

The heavy ``elevenlabs`` SDK is imported lazily inside
:func:`generate_audio_for_slides_elevenlabs` so that nothing is required
unless this backend is actually used.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Reuse the shared helpers from the Chatterbox backend so behaviour (labels,
# interactive prompts, pronunciation substitution) stays consistent across
# engines.
from .tts import _interactive_review, _label, apply_pronunciations
from .utils import generate_silent_wav, write_pcm_wav

logger = logging.getLogger(__name__)

# ElevenLabs ``pcm_24000`` is signed 16-bit little-endian mono PCM, which
# matches the WAV parameters our silent-WAV writer uses, so the assembled
# audio stays at a single sample rate end-to-end.
ELEVENLABS_SAMPLE_RATE = 24000
ELEVENLABS_OUTPUT_FORMAT = "pcm_24000"

DEFAULT_MODEL = "eleven_multilingual_v2"


def _synthesize(client, *, text: str, voice_id: str, model_id: str) -> bytes:
    """Call ElevenLabs text-to-speech and return raw PCM bytes.

    ``client.text_to_speech.convert`` streams the audio back as an iterable
    of byte chunks; we join them into a single buffer.
    """
    audio = client.text_to_speech.convert(
        voice_id=voice_id,
        text=text,
        model_id=model_id,
        output_format=ELEVENLABS_OUTPUT_FORMAT,
    )
    if isinstance(audio, bytes):
        return audio
    if isinstance(audio, bytearray):
        return bytes(audio)
    return b"".join(audio)


def generate_audio_for_slides_elevenlabs(
    slides,
    *,
    temp_dir: Path,
    voice_id: str,
    api_key: str,
    model_id: str = DEFAULT_MODEL,
    hold_duration: float,
    pronunciations=None,
    interactive: bool = False,
) -> list[Path]:
    """Generate a WAV file for every slide via the ElevenLabs API.

    Mirrors :func:`deck2video.tts.generate_audio_for_slides`: slides with
    speaker notes are synthesised; slides without notes get a silent WAV of
    ``hold_duration`` seconds. On a per-slide API failure we log the error
    and substitute silence so one bad slide doesn't abort the whole render.

    Returns the list of audio paths in slide order.
    """
    try:
        from elevenlabs.client import ElevenLabs
    except ImportError as exc:
        raise RuntimeError(
            "The 'elevenlabs' package is required for --tts-engine elevenlabs. "
            "Install it with: pip install elevenlabs"
        ) from exc

    client = ElevenLabs(api_key=api_key)
    logger.debug("ElevenLabs client ready (model=%s, voice=%s)", model_id, voice_id)

    audio_paths: list[Path] = []

    for slide in slides:
        out_path = temp_dir / f"audio_{slide.index:03d}.wav"

        if slide.notes is None:
            logger.debug("%s: no notes, generating %ss silence", _label(slide), hold_duration)
            generate_silent_wav(out_path, hold_duration)
            print(f"  {_label(slide)}: silent ({hold_duration}s)")
            audio_paths.append(out_path)
            continue

        text = slide.notes
        if pronunciations:
            substituted = apply_pronunciations(text, pronunciations)
            if substituted != text:
                logger.debug("%s: after pronunciations=%r", _label(slide), substituted)
            text = substituted

        try:
            pcm = _synthesize(client, text=text, voice_id=voice_id, model_id=model_id)
        except Exception as exc:
            msg = f"{_label(slide)}: ElevenLabs TTS failed ({exc}), substituting silence"
            logger.error(msg, exc_info=True)
            print(f"  {msg}", file=sys.stderr)
            generate_silent_wav(out_path, hold_duration)
            audio_paths.append(out_path)
            continue

        write_pcm_wav(out_path, pcm, sample_rate=ELEVENLABS_SAMPLE_RATE)
        print(f"  {_label(slide)}: TTS OK ({len(text)} chars)")

        if interactive:
            def _regen() -> bool:
                try:
                    pcm = _synthesize(client, text=text, voice_id=voice_id, model_id=model_id)
                except Exception as regen_exc:
                    print(
                        f"  Regeneration failed ({regen_exc}), keeping previous audio.",
                        file=sys.stderr,
                    )
                    return False
                write_pcm_wav(out_path, pcm, sample_rate=ELEVENLABS_SAMPLE_RATE)
                print(f"  {_label(slide)}: TTS OK ({len(text)} chars)")
                return True

            _interactive_review(out_path, _label(slide), _regen)

        audio_paths.append(out_path)

    return audio_paths
