"""Chatterbox TTS wrapper — synthesises speaker notes to WAV files."""

from __future__ import annotations

import gc
import json
import platform
import re
import subprocess
import sys
import warnings
from pathlib import Path

from .utils import generate_silent_wav


def load_pronunciations(path: Path) -> dict[str, str]:
    """Load a pronunciation mapping from a JSON file.

    The file should be a flat object mapping words/phrases to their
    phonetic respellings, e.g. ``{"kubectl": "cube control"}``.
    """
    with open(path) as f:
        mapping = json.load(f)
    if not isinstance(mapping, dict):
        raise ValueError(f"Pronunciations file must be a JSON object, got {type(mapping).__name__}")
    return mapping


def apply_pronunciations(text: str, mapping: dict[str, str]) -> str:
    """Replace words in *text* using the pronunciation mapping.

    Matching is case-insensitive and restricted to whole words so that,
    e.g., replacing "SQL" won't mangle "MySQL".  Longer keys are matched
    first so that multi-word phrases take priority.
    """
    if not mapping:
        return text
    # Sort by descending length so longer phrases match first.
    for word in sorted(mapping, key=len, reverse=True):
        pattern = re.compile(re.escape(word), re.IGNORECASE)
        text = pattern.sub(mapping[word], text)
    return text


def _play_audio(path: Path) -> None:
    """Play a WAV file using the platform's native audio command."""
    system = platform.system()
    if system == "Darwin":
        cmd = ["afplay", str(path)]
    elif system == "Linux":
        cmd = ["aplay", str(path)]
    elif system == "Windows":
        cmd = ["cmd", "/c", "start", "", str(path)]
    else:
        print(f"  Warning: don't know how to play audio on {system}", file=sys.stderr)
        return
    subprocess.run(cmd, capture_output=True)


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences, keeping punctuation attached."""
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    return [p for p in parts if p]


def _resolve_device(device: str) -> str:
    """Pick a torch device, respecting the user's choice or auto-detecting."""
    import torch

    if device != "auto":
        print(f"  Using device: {device}")
        return device

    if torch.cuda.is_available():
        print("  Using CUDA for TTS")
        return "cuda"
    if torch.backends.mps.is_available():
        print("  Using MPS (Apple Silicon) for TTS")
        return "mps"

    print(
        "  WARNING: No GPU available — using CPU for TTS. "
        "This will be much slower.",
        file=sys.stderr,
    )
    return "cpu"


def _load_model(device: str = "auto"):
    """Load ChatterboxTTS once."""
    import torchaudio  # noqa: F401 — ensure it's importable early
    from chatterbox.tts import ChatterboxTTS

    resolved = _resolve_device(device)
    model = ChatterboxTTS.from_pretrained(device=resolved)
    return model


def _move_model_to_cpu(model):
    """Move all TTS model components to CPU and free GPU memory."""
    import torch

    model.t3.to("cpu")
    model.s3gen.to("cpu")
    model.ve.to("cpu")
    if model.conds is not None:
        model.conds.to("cpu")
    model.device = "cpu"

    gc.collect()
    if torch.backends.mps.is_available():
        torch.mps.empty_cache()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    print("  Moved model to CPU due to GPU memory pressure")


def _generate_slide_audio(
    model,
    slide,
    *,
    voice_path: str | None,
    exaggeration: float,
    cfg_weight: float,
    temperature: float,
    flush_fn,
):
    """Generate and return concatenated audio for a single slide's notes.

    Returns the combined waveform tensor (on CPU) and sample rate.
    Raises on failure so the caller can handle fallback.
    """
    import torch

    sentences = _split_sentences(slide.notes)
    sentence_groups = [
        " ".join(sentences[i:i + 3])
        for i in range(0, len(sentences), 3)
    ]

    chunks: list = []
    try:
        for j, group in enumerate(sentence_groups):
            with torch.no_grad(), warnings.catch_warnings():
                warnings.filterwarnings("ignore", message=".*sdp_kernel.*", category=FutureWarning)
                wav = model.generate(
                    group,
                    audio_prompt_path=voice_path,
                    exaggeration=exaggeration,
                    cfg_weight=cfg_weight,
                    temperature=temperature,
                )
            chunks.append(wav.cpu())
            del wav
            flush_fn()
            if len(sentence_groups) > 1:
                print(f"  Slide {slide.index}: chunk {j + 1}/{len(sentence_groups)} OK")

        combined = torch.cat(chunks, dim=1)
        del chunks
        flush_fn()
        return combined, model.sr, len(sentences), len(sentence_groups)
    except Exception:
        del chunks
        flush_fn()
        raise


def generate_audio_for_slides(
    slides,
    *,
    temp_dir: Path,
    voice_path: str | None,
    device: str = "auto",
    exaggeration: float = 0.5,
    cfg_weight: float = 0.5,
    temperature: float = 0.8,
    hold_duration: float,
    pronunciations: dict[str, str] | None = None,
    interactive: bool = False,
) -> list[Path]:
    """Generate a WAV file for every slide. Returns list of audio paths.

    Slides with speaker notes get TTS synthesis; slides without notes get a
    silent WAV of ``hold_duration`` seconds.

    If an out-of-memory error occurs on GPU, the model is automatically
    moved to CPU and the failed slide is retried.
    """
    # Only import the heavy model when we actually need TTS.
    need_tts = any(s.notes for s in slides)
    model = _load_model(device) if need_tts else None

    import torch
    import torchaudio

    is_gpu = torch.backends.mps.is_available() or torch.cuda.is_available()

    def _flush_gpu():
        """Force Python GC then flush the GPU allocator."""
        if is_gpu:
            gc.collect()
            if torch.backends.mps.is_available():
                torch.mps.empty_cache()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

    def _is_oom(exc: Exception) -> bool:
        """Check whether an exception is an out-of-memory error."""
        msg = str(exc).lower()
        return "out of memory" in msg or "mps backend out of memory" in msg

    on_gpu = model is not None and str(getattr(model, "device", "cpu")) != "cpu"

    audio_paths: list[Path] = []

    for slide in slides:
        out_path = temp_dir / f"audio_{slide.index:03d}.wav"

        if slide.notes is None:
            generate_silent_wav(out_path, hold_duration)
            print(f"  Slide {slide.index}: silent ({hold_duration}s)")
        else:
            if pronunciations:
                slide.notes = apply_pronunciations(slide.notes, pronunciations)

            tts_kwargs = dict(
                voice_path=voice_path,
                exaggeration=exaggeration,
                cfg_weight=cfg_weight,
                temperature=temperature,
                flush_fn=_flush_gpu,
            )
            try:
                combined, sr, n_sent, n_chunks = _generate_slide_audio(
                    model, slide, **tts_kwargs,
                )
            except Exception as exc:
                if on_gpu and _is_oom(exc):
                    # Fall back to CPU and retry this slide
                    _move_model_to_cpu(model)
                    on_gpu = False
                    try:
                        combined, sr, n_sent, n_chunks = _generate_slide_audio(
                            model, slide, **tts_kwargs,
                        )
                    except Exception as retry_exc:
                        msg = f"Slide {slide.index}: TTS failed on CPU ({retry_exc}), substituting silence"
                        print(f"  {msg}", file=sys.stderr)
                        generate_silent_wav(out_path, hold_duration)
                        audio_paths.append(out_path)
                        continue
                else:
                    msg = f"Slide {slide.index}: TTS failed ({exc}), substituting silence"
                    print(f"  {msg}", file=sys.stderr)
                    generate_silent_wav(out_path, hold_duration)
                    audio_paths.append(out_path)
                    continue

            torchaudio.save(str(out_path), combined, sr)
            del combined
            _flush_gpu()
            print(f"  Slide {slide.index}: TTS OK ({n_sent} sentence{'s' if n_sent != 1 else ''} in {n_chunks} chunk{'s' if n_chunks != 1 else ''})")

            if interactive:
                _play_audio(out_path)
                while True:
                    choice = input("  (y) keep  (n) regenerate  (r) replay  (q) quit: ").strip().lower()
                    if choice in ("", "y"):
                        break
                    if choice == "r":
                        _play_audio(out_path)
                        continue
                    if choice == "q":
                        print("  Quitting pipeline.")
                        sys.exit(0)
                    # choice == "n" or anything else: regenerate
                    print(f"  Regenerating slide {slide.index}…")
                    try:
                        combined, sr, n_sent, n_chunks = _generate_slide_audio(
                            model, slide, **tts_kwargs,
                        )
                    except Exception as regen_exc:
                        print(f"  Regeneration failed ({regen_exc}), keeping previous audio.", file=sys.stderr)
                        break
                    torchaudio.save(str(out_path), combined, sr)
                    del combined
                    _flush_gpu()
                    print(f"  Slide {slide.index}: TTS OK ({n_sent} sentence{'s' if n_sent != 1 else ''} in {n_chunks} chunk{'s' if n_chunks != 1 else ''})")
                    _play_audio(out_path)

        audio_paths.append(out_path)

    return audio_paths
