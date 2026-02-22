"""Tests for marp2video.tts — TTS synthesis, pronunciation, sentence splitting."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from marp2video.tts import (
    _play_audio,
    _split_sentences,
    apply_pronunciations,
    load_pronunciations,
)


# ---------------------------------------------------------------------------
# load_pronunciations
# ---------------------------------------------------------------------------

class TestLoadPronunciations:
    def test_loads_valid_json(self, tmp_path):
        p = tmp_path / "pron.json"
        p.write_text(json.dumps({"kubectl": "cube control", "nginx": "engine X"}))
        result = load_pronunciations(p)
        assert result == {"kubectl": "cube control", "nginx": "engine X"}

    def test_rejects_non_object(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text(json.dumps(["not", "an", "object"]))
        with pytest.raises(ValueError, match="JSON object"):
            load_pronunciations(p)

    def test_empty_object(self, tmp_path):
        p = tmp_path / "empty.json"
        p.write_text("{}")
        result = load_pronunciations(p)
        assert result == {}

    def test_invalid_json_raises(self, tmp_path):
        p = tmp_path / "broken.json"
        p.write_text("{not valid json")
        with pytest.raises(json.JSONDecodeError):
            load_pronunciations(p)


# ---------------------------------------------------------------------------
# apply_pronunciations
# ---------------------------------------------------------------------------

class TestApplyPronunciations:
    def test_simple_replacement(self):
        result = apply_pronunciations("Use kubectl to deploy.", {"kubectl": "cube control"})
        assert result == "Use cube control to deploy."

    def test_case_insensitive(self):
        result = apply_pronunciations("Run KUBECTL now.", {"kubectl": "cube control"})
        assert result == "Run cube control now."

    def test_longer_phrases_matched_first(self):
        mapping = {"SQL": "sequel", "PostgreSQL": "post gress sequel"}
        result = apply_pronunciations("Use PostgreSQL and SQL.", mapping)
        assert "post gress sequel" in result
        # "SQL" at end should also be replaced
        assert result == "Use post gress sequel and sequel."

    def test_empty_mapping_returns_unchanged(self):
        text = "Nothing changes."
        assert apply_pronunciations(text, {}) == text

    def test_no_match_returns_unchanged(self):
        text = "Hello world."
        assert apply_pronunciations(text, {"kubectl": "cube control"}) == text

    def test_multiple_occurrences(self):
        result = apply_pronunciations(
            "nginx serves nginx well.",
            {"nginx": "engine X"},
        )
        assert result == "engine X serves engine X well."

    def test_overlapping_keys(self):
        # "Visual Studio Code" is longer, so it matches first and gets
        # replaced with "VS Code".  Then the shorter "Code" key matches
        # the "Code" inside "VS Code" and replaces it too.  This is the
        # expected behavior of the current greedy replacement strategy.
        mapping = {"Visual Studio Code": "VS Code", "Code": "code editor"}
        result = apply_pronunciations("Open Visual Studio Code now.", mapping)
        assert "VS code editor" in result


# ---------------------------------------------------------------------------
# _play_audio
# ---------------------------------------------------------------------------

class TestPlayAudio:
    def test_macos_uses_afplay(self, tmp_path):
        p = tmp_path / "test.wav"
        p.write_bytes(b"fake")
        with patch("marp2video.tts.platform.system", return_value="Darwin"), \
             patch("marp2video.tts.subprocess.run") as mock_run:
            _play_audio(p)
        mock_run.assert_called_once_with(["afplay", str(p)], capture_output=True)

    def test_linux_uses_aplay(self, tmp_path):
        p = tmp_path / "test.wav"
        p.write_bytes(b"fake")
        with patch("marp2video.tts.platform.system", return_value="Linux"), \
             patch("marp2video.tts.subprocess.run") as mock_run:
            _play_audio(p)
        mock_run.assert_called_once_with(["aplay", str(p)], capture_output=True)

    def test_windows_uses_start(self, tmp_path):
        p = tmp_path / "test.wav"
        p.write_bytes(b"fake")
        with patch("marp2video.tts.platform.system", return_value="Windows"), \
             patch("marp2video.tts.subprocess.run") as mock_run:
            _play_audio(p)
        mock_run.assert_called_once_with(["cmd", "/c", "start", "", str(p)], capture_output=True)


# ---------------------------------------------------------------------------
# _split_sentences
# ---------------------------------------------------------------------------

class TestSplitSentences:
    def test_single_sentence(self):
        assert _split_sentences("Hello world.") == ["Hello world."]

    def test_multiple_sentences(self):
        result = _split_sentences("First. Second. Third.")
        assert result == ["First.", "Second.", "Third."]

    def test_question_marks(self):
        result = _split_sentences("What? Really! Yes.")
        assert result == ["What?", "Really!", "Yes."]

    def test_preserves_punctuation(self):
        result = _split_sentences("End. Start again.")
        assert result[0].endswith(".")
        assert result[1].endswith(".")

    def test_strips_whitespace(self):
        result = _split_sentences("  Hello world.  ")
        assert result == ["Hello world."]

    def test_empty_string(self):
        assert _split_sentences("") == []

    def test_no_terminal_punctuation(self):
        result = _split_sentences("No period here")
        assert result == ["No period here"]

    def test_abbreviations_may_split(self):
        # The sentence splitter uses a simple regex that splits on
        # punctuation followed by whitespace — "e.g. " triggers a split.
        # This is a known limitation of the simple approach.
        result = _split_sentences("Use e.g. Python.")
        assert len(result) == 2
        assert result[0] == "Use e.g."
        assert result[1] == "Python."

    def test_multiple_spaces_between_sentences(self):
        result = _split_sentences("First.   Second.")
        assert result == ["First.", "Second."]


# ---------------------------------------------------------------------------
# _resolve_device (mocked torch)
# ---------------------------------------------------------------------------

class TestResolveDevice:
    def _import_resolve(self):
        from marp2video.tts import _resolve_device
        return _resolve_device

    def test_explicit_device_returned(self):
        resolve = self._import_resolve()
        mock_torch = MagicMock()
        with patch.dict("sys.modules", {"torch": mock_torch}):
            assert resolve("cpu") == "cpu"
            assert resolve("cuda") == "cuda"
            assert resolve("mps") == "mps"

    def test_auto_selects_cuda(self):
        resolve = self._import_resolve()
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True
        with patch.dict("sys.modules", {"torch": mock_torch}):
            assert resolve("auto") == "cuda"

    def test_auto_selects_mps_when_no_cuda(self):
        resolve = self._import_resolve()
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False
        mock_torch.backends.mps.is_available.return_value = True
        with patch.dict("sys.modules", {"torch": mock_torch}):
            assert resolve("auto") == "mps"

    def test_auto_falls_back_to_cpu(self):
        resolve = self._import_resolve()
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False
        mock_torch.backends.mps.is_available.return_value = False
        with patch.dict("sys.modules", {"torch": mock_torch}):
            assert resolve("auto") == "cpu"


# ---------------------------------------------------------------------------
# generate_audio_for_slides — high-level orchestration (heavy mocking)
# ---------------------------------------------------------------------------

class TestGenerateAudioForSlides:
    """Test the orchestration logic with fully mocked TTS model."""

    def _make_slide(self, index, notes=None, video=None):
        from marp2video.parser import Slide
        return Slide(index=index, body="body", notes=notes, video=video)

    def test_all_silent_slides_skip_model_load(self, tmp_path):
        """When no slide has notes, _load_model should not be called."""
        slides = [self._make_slide(1), self._make_slide(2)]

        mock_torch = MagicMock()
        mock_torch.backends.mps.is_available.return_value = False
        mock_torch.cuda.is_available.return_value = False
        mock_torchaudio = MagicMock()

        with patch.dict("sys.modules", {
            "torch": mock_torch,
            "torchaudio": mock_torchaudio,
        }):
            with patch("marp2video.tts._load_model") as mock_load:
                from marp2video.tts import generate_audio_for_slides
                paths = generate_audio_for_slides(
                    slides,
                    temp_dir=tmp_path,
                    voice_path=None,
                    hold_duration=2.0,
                )
                mock_load.assert_not_called()

        assert len(paths) == 2
        for p in paths:
            assert p.exists()

    def test_silent_slides_get_correct_paths(self, tmp_path):
        slides = [self._make_slide(1), self._make_slide(2)]

        mock_torch = MagicMock()
        mock_torch.backends.mps.is_available.return_value = False
        mock_torch.cuda.is_available.return_value = False
        mock_torchaudio = MagicMock()

        with patch.dict("sys.modules", {
            "torch": mock_torch,
            "torchaudio": mock_torchaudio,
        }):
            with patch("marp2video.tts._load_model"):
                from marp2video.tts import generate_audio_for_slides
                paths = generate_audio_for_slides(
                    slides,
                    temp_dir=tmp_path,
                    voice_path=None,
                    hold_duration=2.0,
                )

        assert paths[0].name == "audio_001.wav"
        assert paths[1].name == "audio_002.wav"

    def test_pronunciation_applied_before_synthesis(self, tmp_path):
        """Verify pronunciations are applied to slide notes."""
        slides = [self._make_slide(1, notes="Use kubectl now.")]
        pronunciations = {"kubectl": "cube control"}

        mock_torch = MagicMock()
        mock_torch.backends.mps.is_available.return_value = False
        mock_torch.cuda.is_available.return_value = False
        mock_torchaudio = MagicMock()

        # Create a mock model that records what text it receives
        mock_model = MagicMock()
        mock_model.sr = 24000
        mock_model.device = "cpu"
        generated_texts = []

        def fake_generate(text, **kwargs):
            generated_texts.append(text)
            return mock_torch.zeros(1, 24000)

        mock_model.generate.side_effect = fake_generate

        with patch.dict("sys.modules", {
            "torch": mock_torch,
            "torchaudio": mock_torchaudio,
        }):
            mock_torch.cat.return_value = mock_torch.zeros(1, 24000)
            mock_torch.zeros.return_value.cpu.return_value = mock_torch.zeros(1, 24000)

            with patch("marp2video.tts._load_model", return_value=mock_model):
                from marp2video.tts import generate_audio_for_slides
                generate_audio_for_slides(
                    slides,
                    temp_dir=tmp_path,
                    voice_path=None,
                    hold_duration=2.0,
                    pronunciations=pronunciations,
                )

        # The text passed to model.generate should have the substitution
        assert any("cube control" in t for t in generated_texts)
        assert not any("kubectl" in t for t in generated_texts)

    def test_tts_failure_substitutes_silence(self, tmp_path):
        """When TTS raises a non-OOM error, fall back to silent WAV."""
        slides = [self._make_slide(1, notes="This will fail.")]

        mock_torch = MagicMock()
        mock_torch.backends.mps.is_available.return_value = False
        mock_torch.cuda.is_available.return_value = False
        mock_torchaudio = MagicMock()

        mock_model = MagicMock()
        mock_model.sr = 24000
        mock_model.device = "cpu"
        mock_model.generate.side_effect = RuntimeError("something broke")

        with patch.dict("sys.modules", {
            "torch": mock_torch,
            "torchaudio": mock_torchaudio,
        }):
            with patch("marp2video.tts._load_model", return_value=mock_model):
                from marp2video.tts import generate_audio_for_slides
                paths = generate_audio_for_slides(
                    slides,
                    temp_dir=tmp_path,
                    voice_path=None,
                    hold_duration=3.0,
                )

        assert len(paths) == 1
        assert paths[0].exists()
        # Verify it's a valid WAV (silent fallback)
        assert paths[0].read_bytes()[:4] == b"RIFF"


# ---------------------------------------------------------------------------
# Interactive mode
# ---------------------------------------------------------------------------

class TestInteractiveMode:
    """Test the interactive TTS review loop."""

    def _make_slide(self, index, notes=None, video=None):
        from marp2video.parser import Slide
        return Slide(index=index, body="body", notes=notes, video=video)

    def _setup_mocks(self):
        mock_torch = MagicMock()
        mock_torch.backends.mps.is_available.return_value = False
        mock_torch.cuda.is_available.return_value = False
        mock_torchaudio = MagicMock()

        mock_model = MagicMock()
        mock_model.sr = 24000
        mock_model.device = "cpu"
        mock_model.generate.return_value = mock_torch.zeros(1, 24000)
        mock_torch.zeros.return_value.cpu.return_value = mock_torch.zeros(1, 24000)
        mock_torch.cat.return_value = mock_torch.zeros(1, 24000)

        return mock_torch, mock_torchaudio, mock_model

    def test_accept_with_y(self, tmp_path):
        """Pressing 'y' keeps the audio and moves on."""
        slides = [self._make_slide(1, notes="Hello world.")]
        mock_torch, mock_torchaudio, mock_model = self._setup_mocks()

        with patch.dict("sys.modules", {"torch": mock_torch, "torchaudio": mock_torchaudio}):
            with patch("marp2video.tts._load_model", return_value=mock_model), \
                 patch("marp2video.tts._play_audio") as mock_play, \
                 patch("builtins.input", return_value="y"):
                from marp2video.tts import generate_audio_for_slides
                paths = generate_audio_for_slides(
                    slides, temp_dir=tmp_path, voice_path=None,
                    hold_duration=2.0, interactive=True,
                )

        assert len(paths) == 1
        mock_play.assert_called_once()
        # Model generate called only once (no regeneration)
        assert mock_model.generate.call_count == 1

    def test_accept_with_empty_input(self, tmp_path):
        """Pressing Enter (empty input) keeps the audio."""
        slides = [self._make_slide(1, notes="Hello world.")]
        mock_torch, mock_torchaudio, mock_model = self._setup_mocks()

        with patch.dict("sys.modules", {"torch": mock_torch, "torchaudio": mock_torchaudio}):
            with patch("marp2video.tts._load_model", return_value=mock_model), \
                 patch("marp2video.tts._play_audio"), \
                 patch("builtins.input", return_value=""):
                from marp2video.tts import generate_audio_for_slides
                paths = generate_audio_for_slides(
                    slides, temp_dir=tmp_path, voice_path=None,
                    hold_duration=2.0, interactive=True,
                )

        assert len(paths) == 1
        assert mock_model.generate.call_count == 1

    def test_reject_then_accept(self, tmp_path):
        """Pressing 'n' regenerates, then 'y' keeps."""
        slides = [self._make_slide(1, notes="Hello world.")]
        mock_torch, mock_torchaudio, mock_model = self._setup_mocks()

        with patch.dict("sys.modules", {"torch": mock_torch, "torchaudio": mock_torchaudio}):
            with patch("marp2video.tts._load_model", return_value=mock_model), \
                 patch("marp2video.tts._play_audio") as mock_play, \
                 patch("builtins.input", side_effect=["n", "y"]):
                from marp2video.tts import generate_audio_for_slides
                paths = generate_audio_for_slides(
                    slides, temp_dir=tmp_path, voice_path=None,
                    hold_duration=2.0, interactive=True,
                )

        assert len(paths) == 1
        # generate called twice: original + regeneration
        assert mock_model.generate.call_count == 2
        # play called twice: once for original, once after regeneration
        assert mock_play.call_count == 2

    def test_replay_then_accept(self, tmp_path):
        """Pressing 'r' replays audio without regenerating, then 'y' keeps."""
        slides = [self._make_slide(1, notes="Hello world.")]
        mock_torch, mock_torchaudio, mock_model = self._setup_mocks()

        with patch.dict("sys.modules", {"torch": mock_torch, "torchaudio": mock_torchaudio}):
            with patch("marp2video.tts._load_model", return_value=mock_model), \
                 patch("marp2video.tts._play_audio") as mock_play, \
                 patch("builtins.input", side_effect=["r", "y"]):
                from marp2video.tts import generate_audio_for_slides
                paths = generate_audio_for_slides(
                    slides, temp_dir=tmp_path, voice_path=None,
                    hold_duration=2.0, interactive=True,
                )

        assert len(paths) == 1
        # generate called only once (no regeneration)
        assert mock_model.generate.call_count == 1
        # play called twice: initial + replay
        assert mock_play.call_count == 2

    def test_quit_exits(self, tmp_path):
        """Pressing 'q' exits the pipeline via SystemExit."""
        slides = [self._make_slide(1, notes="Hello world.")]
        mock_torch, mock_torchaudio, mock_model = self._setup_mocks()

        with patch.dict("sys.modules", {"torch": mock_torch, "torchaudio": mock_torchaudio}):
            with patch("marp2video.tts._load_model", return_value=mock_model), \
                 patch("marp2video.tts._play_audio"), \
                 patch("builtins.input", return_value="q"):
                from marp2video.tts import generate_audio_for_slides
                with pytest.raises(SystemExit):
                    generate_audio_for_slides(
                        slides, temp_dir=tmp_path, voice_path=None,
                        hold_duration=2.0, interactive=True,
                    )

    def test_silent_slides_skip_interactive(self, tmp_path):
        """Silent slides (no notes) should not trigger the interactive prompt."""
        slides = [self._make_slide(1)]  # no notes
        mock_torch, mock_torchaudio, mock_model = self._setup_mocks()

        with patch.dict("sys.modules", {"torch": mock_torch, "torchaudio": mock_torchaudio}):
            with patch("marp2video.tts._load_model", return_value=mock_model), \
                 patch("marp2video.tts._play_audio") as mock_play, \
                 patch("builtins.input") as mock_input:
                from marp2video.tts import generate_audio_for_slides
                paths = generate_audio_for_slides(
                    slides, temp_dir=tmp_path, voice_path=None,
                    hold_duration=2.0, interactive=True,
                )

        assert len(paths) == 1
        mock_play.assert_not_called()
        mock_input.assert_not_called()
