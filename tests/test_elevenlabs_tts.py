"""Tests for deck2video.elevenlabs_tts — ElevenLabs API TTS backend.

The ``elevenlabs`` SDK is mocked via ``sys.modules`` so these tests run
without the package installed and without making any network calls.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from deck2video.elevenlabs_tts import generate_audio_for_slides_elevenlabs
from deck2video.tts import compile_pronunciations


def _make_slide(index, notes=None, video=None):
    from deck2video.models import Slide
    return Slide(index=index, body="body", notes=notes, video=video)


def _fake_sdk(convert_side_effect):
    """Build fake elevenlabs modules + return (sys.modules dict, client mock)."""
    client_instance = MagicMock()
    client_instance.text_to_speech.convert.side_effect = convert_side_effect
    client_cls = MagicMock(return_value=client_instance)

    client_mod = MagicMock()
    client_mod.ElevenLabs = client_cls
    pkg = MagicMock()

    modules = {"elevenlabs": pkg, "elevenlabs.client": client_mod}
    return modules, client_instance, client_cls


def _run(slides, tmp_path, *, convert, **kwargs):
    modules, client_instance, client_cls = _fake_sdk(convert)
    with patch.dict("sys.modules", modules):
        paths = generate_audio_for_slides_elevenlabs(
            slides,
            temp_dir=tmp_path,
            voice_id=kwargs.pop("voice_id", "voice123"),
            api_key=kwargs.pop("api_key", "key-abc"),
            **kwargs,
        )
    return paths, client_instance, client_cls


# ---------------------------------------------------------------------------
# Basic synthesis
# ---------------------------------------------------------------------------

class TestSynthesis:
    def test_notes_slide_writes_valid_wav(self, tmp_path):
        slides = [_make_slide(1, notes="Hello world.")]
        pcm = b"\x01\x02\x03\x04" * 100

        paths, _, _ = _run(
            slides, tmp_path,
            convert=lambda **kw: iter([pcm]),
            hold_duration=2.0,
        )

        assert len(paths) == 1
        assert paths[0].name == "audio_001.wav"
        data = paths[0].read_bytes()
        assert data[:4] == b"RIFF"
        assert data[8:12] == b"WAVE"
        # PCM payload should be present after the 44-byte header.
        assert data[44:] == pcm

    def test_convert_called_with_expected_args(self, tmp_path):
        slides = [_make_slide(1, notes="Hello.")]
        _, client, _ = _run(
            slides, tmp_path,
            convert=lambda **kw: iter([b"\x00\x00"]),
            hold_duration=2.0,
            voice_id="my-voice",
            model_id="eleven_turbo_v2_5",
        )

        kwargs = client.text_to_speech.convert.call_args.kwargs
        assert kwargs["voice_id"] == "my-voice"
        assert kwargs["text"] == "Hello."
        assert kwargs["model_id"] == "eleven_turbo_v2_5"
        assert kwargs["output_format"] == "pcm_24000"

    def test_api_key_passed_to_client(self, tmp_path):
        slides = [_make_slide(1, notes="Hi.")]
        _, _, client_cls = _run(
            slides, tmp_path,
            convert=lambda **kw: iter([b"\x00\x00"]),
            hold_duration=2.0,
            api_key="secret-key",
        )
        assert client_cls.call_args.kwargs["api_key"] == "secret-key"

    def test_convert_returning_raw_bytes_handled(self, tmp_path):
        """convert() may return bytes directly rather than an iterator."""
        slides = [_make_slide(1, notes="Hi.")]
        pcm = b"\xaa\xbb" * 50
        paths, _, _ = _run(
            slides, tmp_path,
            convert=lambda **kw: pcm,
            hold_duration=2.0,
        )
        assert paths[0].read_bytes()[44:] == pcm


# ---------------------------------------------------------------------------
# Silent slides
# ---------------------------------------------------------------------------

class TestSilentSlides:
    def test_slide_without_notes_gets_silence_no_api_call(self, tmp_path):
        slides = [_make_slide(1, notes=None)]
        paths, client, _ = _run(
            slides, tmp_path,
            convert=lambda **kw: iter([b"\x00"]),
            hold_duration=2.0,
        )

        assert paths[0].read_bytes()[:4] == b"RIFF"
        client.text_to_speech.convert.assert_not_called()

    def test_mixed_slides(self, tmp_path):
        slides = [_make_slide(1, notes="Talk."), _make_slide(2, notes=None)]
        paths, client, _ = _run(
            slides, tmp_path,
            convert=lambda **kw: iter([b"\x01\x02"]),
            hold_duration=1.5,
        )
        assert [p.name for p in paths] == ["audio_001.wav", "audio_002.wav"]
        # Only the slide with notes hits the API.
        assert client.text_to_speech.convert.call_count == 1


# ---------------------------------------------------------------------------
# Pronunciations
# ---------------------------------------------------------------------------

class TestPronunciations:
    def test_pronunciations_applied_before_synthesis(self, tmp_path):
        slides = [_make_slide(1, notes="Use kubectl now.")]
        patterns = compile_pronunciations({"kubectl": "cube control"})

        _, client, _ = _run(
            slides, tmp_path,
            convert=lambda **kw: iter([b"\x00\x00"]),
            hold_duration=2.0,
            pronunciations=patterns,
        )
        sent_text = client.text_to_speech.convert.call_args.kwargs["text"]
        assert sent_text == "Use cube control now."

    def test_notes_not_mutated(self, tmp_path):
        slide = _make_slide(1, notes="Run kubectl.")
        patterns = compile_pronunciations({"kubectl": "cube control"})
        _run(
            [slide], tmp_path,
            convert=lambda **kw: iter([b"\x00\x00"]),
            hold_duration=2.0,
            pronunciations=patterns,
        )
        assert slide.notes == "Run kubectl."


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------

class TestFailureHandling:
    def test_api_failure_substitutes_silence(self, tmp_path):
        slides = [_make_slide(1, notes="This breaks.")]

        def boom(**kw):
            raise RuntimeError("network exploded")

        paths, _, _ = _run(
            slides, tmp_path,
            convert=boom,
            hold_duration=3.0,
        )
        assert len(paths) == 1
        # Silent WAV fallback is still a valid RIFF file.
        assert paths[0].read_bytes()[:4] == b"RIFF"

    def test_missing_sdk_raises_helpful_error(self, tmp_path):
        slides = [_make_slide(1, notes="Hi.")]
        # Setting the module entries to None makes `import elevenlabs.client`
        # raise ImportError.
        with patch.dict("sys.modules", {"elevenlabs": None, "elevenlabs.client": None}):
            with pytest.raises(RuntimeError, match="pip install elevenlabs"):
                generate_audio_for_slides_elevenlabs(
                    slides,
                    temp_dir=tmp_path,
                    voice_id="v",
                    api_key="k",
                    hold_duration=2.0,
                )

    def test_one_failure_does_not_abort_others(self, tmp_path):
        slides = [_make_slide(1, notes="ok"), _make_slide(2, notes="boom")]

        calls = {"n": 0}

        def convert(**kw):
            calls["n"] += 1
            if kw["text"] == "boom":
                raise RuntimeError("fail")
            return iter([b"\x01\x02"])

        paths, _, _ = _run(slides, tmp_path, convert=convert, hold_duration=2.0)
        assert len(paths) == 2
        assert all(p.read_bytes()[:4] == b"RIFF" for p in paths)


# ---------------------------------------------------------------------------
# Interactive mode
# ---------------------------------------------------------------------------

class TestInteractive:
    def test_accept_keeps_audio(self, tmp_path):
        slides = [_make_slide(1, notes="Hello.")]
        with patch("deck2video.tts._play_audio") as mock_play, \
             patch("builtins.input", return_value="y"):
            paths, client, _ = _run(
                slides, tmp_path,
                convert=lambda **kw: iter([b"\x01\x02"]),
                hold_duration=2.0,
                interactive=True,
            )
        assert len(paths) == 1
        mock_play.assert_called_once()
        assert client.text_to_speech.convert.call_count == 1

    def test_regenerate_then_accept(self, tmp_path):
        slides = [_make_slide(1, notes="Hello.")]
        with patch("deck2video.tts._play_audio") as mock_play, \
             patch("builtins.input", side_effect=["n", "y"]):
            _, client, _ = _run(
                slides, tmp_path,
                convert=lambda **kw: iter([b"\x01\x02"]),
                hold_duration=2.0,
                interactive=True,
            )
        # Original + one regeneration.
        assert client.text_to_speech.convert.call_count == 2
        assert mock_play.call_count == 2

    def test_quit_exits(self, tmp_path):
        slides = [_make_slide(1, notes="Hello.")]
        with patch("deck2video.tts._play_audio"), \
             patch("builtins.input", return_value="q"):
            with pytest.raises(SystemExit):
                _run(
                    slides, tmp_path,
                    convert=lambda **kw: iter([b"\x01\x02"]),
                    hold_duration=2.0,
                    interactive=True,
                )

    def test_silent_slide_skips_interactive(self, tmp_path):
        slides = [_make_slide(1, notes=None)]
        with patch("deck2video.tts._play_audio") as mock_play, \
             patch("builtins.input") as mock_input:
            _run(
                slides, tmp_path,
                convert=lambda **kw: iter([b"\x01"]),
                hold_duration=2.0,
                interactive=True,
            )
        mock_play.assert_not_called()
        mock_input.assert_not_called()
