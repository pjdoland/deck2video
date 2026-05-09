"""Tests for deck2video.assembler — ffmpeg video assembly."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from deck2video.assembler import (
    _SCALE_PAD_FILTER,
    _VIDEO_SCALE_PAD_FILTER,
    _make_segment,
    _make_video_segment,
    assemble_video,
)


def _ok_result():
    r = MagicMock()
    r.returncode = 0
    r.stderr = ""
    return r


def _fail_result():
    r = MagicMock()
    r.returncode = 1
    r.stderr = "ffmpeg error"
    return r


# ---------------------------------------------------------------------------
# _make_segment (static image + audio)
# ---------------------------------------------------------------------------

class TestMakeSegment:
    @patch("deck2video.assembler.get_audio_duration", return_value=5.0)
    @patch("deck2video.assembler.subprocess.run", return_value=_ok_result())
    def test_creates_segment_file(self, mock_run, mock_dur, tmp_path):
        img = tmp_path / "slide.001"
        img.touch()
        audio = tmp_path / "audio.wav"
        audio.touch()

        seg = _make_segment(1, img, audio, tmp_path, fps=24)
        assert seg == tmp_path / "segment_001.ts"

    @patch("deck2video.assembler.get_audio_duration", return_value=5.0)
    @patch("deck2video.assembler.subprocess.run", return_value=_ok_result())
    def test_ffmpeg_command_structure(self, mock_run, mock_dur, tmp_path):
        img = tmp_path / "slide.001"
        img.touch()
        audio = tmp_path / "audio.wav"
        audio.touch()

        _make_segment(1, img, audio, tmp_path, fps=24)
        cmd = mock_run.call_args[0][0]

        assert cmd[0] == "ffmpeg"
        assert "-loop" in cmd
        assert "-framerate" in cmd
        # fps formatted with 6 decimals to preserve fractional rates (29.97)
        assert "24.000000" in cmd
        assert "-c:v" in cmd
        assert "libx264" in cmd
        assert "-tune" in cmd
        assert "stillimage" in cmd
        assert "-c:a" in cmd
        assert "aac" in cmd
        assert "-f" in cmd
        assert "mpegts" in cmd
        assert _SCALE_PAD_FILTER in cmd

    @patch("deck2video.assembler.get_audio_duration", return_value=5.0)
    @patch("deck2video.assembler.subprocess.run", return_value=_ok_result())
    def test_duration_passed_to_ffmpeg(self, mock_run, mock_dur, tmp_path):
        img = tmp_path / "slide.001"
        img.touch()
        audio = tmp_path / "audio.wav"
        audio.touch()

        _make_segment(1, img, audio, tmp_path, fps=24)
        cmd = mock_run.call_args[0][0]

        t_idx = cmd.index("-t")
        assert cmd[t_idx + 1] == "5.0000"

    @patch("deck2video.assembler.get_audio_duration", return_value=5.0)
    @patch("deck2video.assembler.subprocess.run", return_value=_fail_result())
    def test_ffmpeg_failure_raises(self, mock_run, mock_dur, tmp_path):
        img = tmp_path / "slide.001"
        img.touch()
        audio = tmp_path / "audio.wav"
        audio.touch()

        with pytest.raises(RuntimeError, match="ffmpeg failed on segment"):
            _make_segment(1, img, audio, tmp_path, fps=24)


# ---------------------------------------------------------------------------
# _make_segment — audio padding
# ---------------------------------------------------------------------------

class TestMakeSegmentPadding:
    @patch("deck2video.assembler.get_audio_duration", return_value=5.0)
    @patch("deck2video.assembler.subprocess.run", return_value=_ok_result())
    def test_no_adelay_when_padding_zero(self, mock_run, mock_dur, tmp_path):
        img = tmp_path / "slide.001"
        img.touch()
        audio = tmp_path / "audio.wav"
        audio.touch()

        _make_segment(1, img, audio, tmp_path, fps=24, audio_padding_ms=0)
        cmd = mock_run.call_args[0][0]
        assert "-af" not in cmd

    @patch("deck2video.assembler.get_audio_duration", return_value=5.0)
    @patch("deck2video.assembler.subprocess.run", return_value=_ok_result())
    def test_adelay_present_when_padding_set(self, mock_run, mock_dur, tmp_path):
        img = tmp_path / "slide.001"
        img.touch()
        audio = tmp_path / "audio.wav"
        audio.touch()

        _make_segment(1, img, audio, tmp_path, fps=24, audio_padding_ms=500)
        cmd = mock_run.call_args[0][0]
        af_idx = cmd.index("-af")
        assert "adelay=500|500" in cmd[af_idx + 1]

    @patch("deck2video.assembler.get_audio_duration", return_value=5.0)
    @patch("deck2video.assembler.subprocess.run", return_value=_ok_result())
    def test_duration_extended_by_double_padding(self, mock_run, mock_dur, tmp_path):
        img = tmp_path / "slide.001"
        img.touch()
        audio = tmp_path / "audio.wav"
        audio.touch()

        _make_segment(1, img, audio, tmp_path, fps=24, audio_padding_ms=500)
        cmd = mock_run.call_args[0][0]
        t_idx = cmd.index("-t")
        # 5.0 + 2 * 0.5 = 6.0
        assert cmd[t_idx + 1] == "6.0000"


# ---------------------------------------------------------------------------
# _make_video_segment (screencast + TTS audio)
# ---------------------------------------------------------------------------

class TestMakeVideoSegment:
    @patch("deck2video.assembler.get_video_duration", return_value=10.0)
    @patch("deck2video.assembler.get_audio_duration", return_value=5.0)
    @patch("deck2video.assembler.subprocess.run", return_value=_ok_result())
    def test_creates_segment(self, mock_run, mock_adur, mock_vdur, tmp_path):
        video = tmp_path / "demo.mov"
        video.touch()
        audio = tmp_path / "audio.wav"
        audio.touch()

        seg = _make_video_segment(1, video, audio, tmp_path, fps=30)
        assert seg == tmp_path / "segment_001.ts"

    @patch("deck2video.assembler.get_video_duration", return_value=10.0)
    @patch("deck2video.assembler.get_audio_duration", return_value=5.0)
    @patch("deck2video.assembler.subprocess.run", return_value=_ok_result())
    def test_uses_video_duration_when_longer(self, mock_run, mock_adur, mock_vdur, tmp_path):
        video = tmp_path / "demo.mov"
        video.touch()
        audio = tmp_path / "audio.wav"
        audio.touch()

        _make_video_segment(1, video, audio, tmp_path, fps=30)
        cmd = mock_run.call_args[0][0]

        # Duration should be max(10, 5) = 10
        t_idx = cmd.index("-t")
        assert cmd[t_idx + 1] == "10.0000"

    @patch("deck2video.assembler.get_video_duration", return_value=5.0)
    @patch("deck2video.assembler.get_audio_duration", return_value=12.0)
    @patch("deck2video.assembler.subprocess.run", return_value=_ok_result())
    def test_tpad_when_audio_longer(self, mock_run, mock_adur, mock_vdur, tmp_path):
        """When audio is longer than video, tpad should freeze last frame."""
        video = tmp_path / "demo.mov"
        video.touch()
        audio = tmp_path / "audio.wav"
        audio.touch()

        _make_video_segment(1, video, audio, tmp_path, fps=30)
        cmd = mock_run.call_args[0][0]

        # Duration = max(12, 5) = 12
        t_idx = cmd.index("-t")
        assert cmd[t_idx + 1] == "12.0000"

        # Video filter should contain tpad
        vf_idx = cmd.index("-vf")
        vf_value = cmd[vf_idx + 1]
        assert "tpad" in vf_value
        assert "stop_mode=clone" in vf_value
        assert "7.0000" in vf_value  # 12 - 5 = 7

    @patch("deck2video.assembler.get_video_duration", return_value=10.0)
    @patch("deck2video.assembler.get_audio_duration", return_value=5.0)
    @patch("deck2video.assembler.subprocess.run", return_value=_ok_result())
    def test_no_tpad_when_video_longer(self, mock_run, mock_adur, mock_vdur, tmp_path):
        video = tmp_path / "demo.mov"
        video.touch()
        audio = tmp_path / "audio.wav"
        audio.touch()

        _make_video_segment(1, video, audio, tmp_path, fps=30)
        cmd = mock_run.call_args[0][0]

        vf_idx = cmd.index("-vf")
        vf_value = cmd[vf_idx + 1]
        assert "tpad" not in vf_value

    @patch("deck2video.assembler.get_video_duration", return_value=10.0)
    @patch("deck2video.assembler.get_audio_duration", return_value=5.0)
    @patch("deck2video.assembler.subprocess.run", return_value=_ok_result())
    def test_maps_video_and_audio_streams(self, mock_run, mock_adur, mock_vdur, tmp_path):
        video = tmp_path / "demo.mov"
        video.touch()
        audio = tmp_path / "audio.wav"
        audio.touch()

        _make_video_segment(1, video, audio, tmp_path, fps=30)
        cmd = mock_run.call_args[0][0]

        # Should map video from input 0, audio from input 1
        map_indices = [i for i, x in enumerate(cmd) if x == "-map"]
        assert len(map_indices) == 2
        assert cmd[map_indices[0] + 1] == "0:v"
        assert cmd[map_indices[1] + 1] == "1:a"

    @patch("deck2video.assembler.get_video_duration", return_value=10.0)
    @patch("deck2video.assembler.get_audio_duration", return_value=5.0)
    @patch("deck2video.assembler.subprocess.run", return_value=_fail_result())
    def test_ffmpeg_failure_raises(self, mock_run, mock_adur, mock_vdur, tmp_path):
        video = tmp_path / "demo.mov"
        video.touch()
        audio = tmp_path / "audio.wav"
        audio.touch()

        with pytest.raises(RuntimeError, match="ffmpeg failed on video segment"):
            _make_video_segment(1, video, audio, tmp_path, fps=30)


# ---------------------------------------------------------------------------
# _make_video_segment — audio padding
# ---------------------------------------------------------------------------

class TestMakeVideoSegmentPadding:
    @patch("deck2video.assembler.get_video_duration", return_value=10.0)
    @patch("deck2video.assembler.get_audio_duration", return_value=5.0)
    @patch("deck2video.assembler.subprocess.run", return_value=_ok_result())
    def test_adelay_present_when_padding_set(self, mock_run, mock_adur, mock_vdur, tmp_path):
        video = tmp_path / "demo.mov"
        video.touch()
        audio = tmp_path / "audio.wav"
        audio.touch()

        _make_video_segment(1, video, audio, tmp_path, fps=30, audio_padding_ms=300)
        cmd = mock_run.call_args[0][0]
        af_idx = cmd.index("-af")
        assert "adelay=300|300" in cmd[af_idx + 1]

    @patch("deck2video.assembler.get_video_duration", return_value=10.0)
    @patch("deck2video.assembler.get_audio_duration", return_value=5.0)
    @patch("deck2video.assembler.subprocess.run", return_value=_ok_result())
    def test_no_adelay_when_padding_zero(self, mock_run, mock_adur, mock_vdur, tmp_path):
        video = tmp_path / "demo.mov"
        video.touch()
        audio = tmp_path / "audio.wav"
        audio.touch()

        _make_video_segment(1, video, audio, tmp_path, fps=30, audio_padding_ms=0)
        cmd = mock_run.call_args[0][0]
        assert "-af" not in cmd

    @patch("deck2video.assembler.get_video_duration", return_value=10.0)
    @patch("deck2video.assembler.get_audio_duration", return_value=5.0)
    @patch("deck2video.assembler.subprocess.run", return_value=_ok_result())
    def test_duration_extended_by_double_padding(self, mock_run, mock_adur, mock_vdur, tmp_path):
        video = tmp_path / "demo.mov"
        video.touch()
        audio = tmp_path / "audio.wav"
        audio.touch()

        _make_video_segment(1, video, audio, tmp_path, fps=30, audio_padding_ms=500)
        cmd = mock_run.call_args[0][0]
        t_idx = cmd.index("-t")
        # max(5+1, 10) + 0 ... wait: max(5,10) + 2*0.5 = 11
        # Actually: target_dur = max(audio_dur, video_dur) + 2*pad_s = max(5,10) + 1 = 11
        assert cmd[t_idx + 1] == "11.0000"

    @patch("deck2video.assembler.get_video_duration", return_value=5.0)
    @patch("deck2video.assembler.get_audio_duration", return_value=3.0)
    @patch("deck2video.assembler.subprocess.run", return_value=_ok_result())
    def test_tpad_triggered_by_padding(self, mock_run, mock_adur, mock_vdur, tmp_path):
        """Padding can cause padded audio to exceed video duration, triggering tpad."""
        video = tmp_path / "demo.mov"
        video.touch()
        audio = tmp_path / "audio.wav"
        audio.touch()

        # audio=3, video=5, padding=2000ms -> padded_audio=3+4=7 > video=5 -> tpad needed
        _make_video_segment(1, video, audio, tmp_path, fps=30, audio_padding_ms=2000)
        cmd = mock_run.call_args[0][0]
        vf_idx = cmd.index("-vf")
        vf_value = cmd[vf_idx + 1]
        assert "tpad" in vf_value
        assert "stop_mode=clone" in vf_value


# ---------------------------------------------------------------------------
# assemble_video (full pipeline)
# ---------------------------------------------------------------------------

@patch("deck2video.assembler._verify_concat_compatibility", lambda segments: None)
class TestAssembleVideo:
    def _make_files(self, tmp_path, count):
        images = []
        audios = []
        for i in range(1, count + 1):
            img = tmp_path / f"slide.{i:03d}"
            img.touch()
            images.append(img)
            aud = tmp_path / f"audio_{i:03d}.wav"
            aud.touch()
            audios.append(aud)
        return images, audios

    @patch("deck2video.assembler.get_audio_duration", return_value=3.0)
    @patch("deck2video.assembler.subprocess.run", return_value=_ok_result())
    def test_creates_concat_file(self, mock_run, mock_dur, tmp_path):
        images, audios = self._make_files(tmp_path, 2)
        output = tmp_path / "out.mp4"
        output.touch()  # assemble_video reads its size at the end

        assemble_video(images, audios, output, temp_dir=tmp_path, fps=24)

        concat = tmp_path / "concat.txt"
        assert concat.exists()
        content = concat.read_text()
        assert "segment_001.ts" in content
        assert "segment_002.ts" in content

    @patch("deck2video.assembler.get_audio_duration", return_value=3.0)
    @patch("deck2video.assembler.subprocess.run", return_value=_ok_result())
    def test_calls_ffmpeg_for_each_segment_plus_concat(self, mock_run, mock_dur, tmp_path):
        images, audios = self._make_files(tmp_path, 3)
        output = tmp_path / "out.mp4"
        output.touch()

        assemble_video(images, audios, output, temp_dir=tmp_path, fps=24)

        # 3 segment calls + 1 concat call = 4 total
        assert mock_run.call_count == 4

    @patch("deck2video.assembler.get_video_duration", return_value=10.0)
    @patch("deck2video.assembler.get_audio_duration", return_value=3.0)
    @patch("deck2video.assembler.subprocess.run", return_value=_ok_result())
    def test_mixed_image_and_video_segments(self, mock_run, mock_adur, mock_vdur, tmp_path):
        images, audios = self._make_files(tmp_path, 3)
        vid = tmp_path / "demo.mov"
        vid.touch()
        videos = [None, vid, None]
        output = tmp_path / "out.mp4"
        output.touch()

        assemble_video(images, audios, output, temp_dir=tmp_path, fps=30, videos=videos)

        # 3 segment calls + 1 concat = 4
        assert mock_run.call_count == 4

        # Second call should be a video segment (uses -map)
        second_call_cmd = mock_run.call_args_list[1][0][0]
        assert "-map" in second_call_cmd

        # First and third should be image segments (use -loop)
        first_cmd = mock_run.call_args_list[0][0][0]
        third_cmd = mock_run.call_args_list[2][0][0]
        assert "-loop" in first_cmd
        assert "-loop" in third_cmd

    @patch("deck2video.assembler.get_audio_duration", return_value=3.0)
    @patch("deck2video.assembler.subprocess.run")
    def test_concat_failure_raises(self, mock_run, mock_dur, tmp_path):
        images, audios = self._make_files(tmp_path, 1)
        output = tmp_path / "out.mp4"

        # Segments succeed, concat fails
        def side_effect(*args, **kwargs):
            cmd = args[0]
            if "-f" in cmd and "concat" in cmd:
                return _fail_result()
            return _ok_result()

        mock_run.side_effect = side_effect

        with pytest.raises(RuntimeError, match="ffmpeg concat failed"):
            assemble_video(images, audios, output, temp_dir=tmp_path, fps=24)

    @patch("deck2video.assembler.get_audio_duration", return_value=3.0)
    @patch("deck2video.assembler.subprocess.run", return_value=_ok_result())
    def test_videos_default_none(self, mock_run, mock_dur, tmp_path):
        """When videos param omitted, all segments should be image-based."""
        images, audios = self._make_files(tmp_path, 2)
        output = tmp_path / "out.mp4"
        output.touch()

        assemble_video(images, audios, output, temp_dir=tmp_path, fps=24)

        # All segment calls should use -loop (image-based)
        for c in mock_run.call_args_list[:-1]:  # exclude concat call
            cmd = c[0][0]
            assert "-loop" in cmd

    @patch("deck2video.assembler.get_audio_duration", return_value=3.0)
    @patch("deck2video.assembler.subprocess.run", return_value=_ok_result())
    def test_audio_padding_passed_to_segments(self, mock_run, mock_dur, tmp_path):
        images, audios = self._make_files(tmp_path, 2)
        output = tmp_path / "out.mp4"
        output.touch()

        assemble_video(images, audios, output, temp_dir=tmp_path, fps=24, audio_padding_ms=250)

        # Each segment call (not the concat) should include adelay
        for c in mock_run.call_args_list[:-1]:
            cmd = c[0][0]
            af_idx = cmd.index("-af")
            assert "adelay=250|250" in cmd[af_idx + 1]

    @patch("deck2video.assembler.get_audio_duration", return_value=3.0)
    @patch("deck2video.assembler.subprocess.run", return_value=_ok_result())
    def test_per_step_padding_list(self, mock_run, mock_dur, tmp_path):
        """Per-step padding list applies a different value to each segment."""
        images, audios = self._make_files(tmp_path, 3)
        output = tmp_path / "out.mp4"
        output.touch()

        assemble_video(images, audios, output, temp_dir=tmp_path, fps=24,
                       audio_padding_ms=[500, 0, 500])

        calls = mock_run.call_args_list[:-1]  # exclude concat
        # Segment 1: padding=500 → adelay present
        cmd0 = calls[0][0][0]
        af0 = cmd0.index("-af")
        assert "adelay=500|500" in cmd0[af0 + 1]

        # Segment 2: padding=0 → no adelay
        cmd1 = calls[1][0][0]
        assert "-af" not in cmd1

        # Segment 3: padding=500 → adelay present
        cmd2 = calls[2][0][0]
        af2 = cmd2.index("-af")
        assert "adelay=500|500" in cmd2[af2 + 1]


# ---------------------------------------------------------------------------
# E40 / B36 — segment duration is rounded up to whole frame; -shortest is gone
# ---------------------------------------------------------------------------

class TestFrameAlignment:
    @patch("deck2video.assembler.get_audio_duration", return_value=5.01)
    @patch("deck2video.assembler.subprocess.run", return_value=_ok_result())
    def test_duration_rounded_up_to_whole_frame(self, mock_run, mock_dur, tmp_path):
        """5.01s @ 24fps → 121 frames → 5.0417s (rounded up, never down)."""
        img = tmp_path / "slide.001"
        img.touch()
        audio = tmp_path / "audio.wav"
        audio.touch()

        _make_segment(1, img, audio, tmp_path, fps=24)
        cmd = mock_run.call_args[0][0]

        t_idx = cmd.index("-t")
        # 121 / 24 = 5.041666… → "5.0417"
        assert cmd[t_idx + 1] == f"{121/24:.4f}"

    @patch("deck2video.assembler.get_audio_duration", return_value=5.0)
    @patch("deck2video.assembler.subprocess.run", return_value=_ok_result())
    def test_no_shortest_flag(self, mock_run, mock_dur, tmp_path):
        """-shortest is removed in favor of an explicit -t to prevent pad clipping."""
        img = tmp_path / "slide.001"
        img.touch()
        audio = tmp_path / "audio.wav"
        audio.touch()

        _make_segment(1, img, audio, tmp_path, fps=24)
        cmd = mock_run.call_args[0][0]
        assert "-shortest" not in cmd

    @patch("deck2video.assembler.get_audio_duration", return_value=5.0)
    @patch("deck2video.assembler.subprocess.run", return_value=_ok_result())
    def test_apad_uses_whole_dur(self, mock_run, mock_dur, tmp_path):
        """apad must include whole_dur so it doesn't produce infinite audio."""
        img = tmp_path / "slide.001"
        img.touch()
        audio = tmp_path / "audio.wav"
        audio.touch()

        _make_segment(1, img, audio, tmp_path, fps=24, audio_padding_ms=500)
        cmd = mock_run.call_args[0][0]
        af_idx = cmd.index("-af")
        af_value = cmd[af_idx + 1]
        # Bare `apad` would be `apad,` or `apad$` — must be `apad=whole_dur=...`
        assert "apad=whole_dur=" in af_value


# ---------------------------------------------------------------------------
# subprocess timeout wrapping — TimeoutExpired surfaces as RuntimeError, not raw traceback
# ---------------------------------------------------------------------------

class TestTimeoutWrapping:
    @patch("deck2video.assembler.get_audio_duration", return_value=3.0)
    def test_segment_timeout_raises_runtime_error(self, mock_dur, tmp_path):
        import subprocess
        img = tmp_path / "slide.001"
        img.touch()
        audio = tmp_path / "audio.wav"
        audio.touch()

        with patch(
            "deck2video.assembler.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["ffmpeg"], timeout=600),
        ):
            with pytest.raises(RuntimeError, match="timed out"):
                _make_segment(1, img, audio, tmp_path, fps=24)


# ---------------------------------------------------------------------------
# E15 — _verify_concat_compatibility
# ---------------------------------------------------------------------------

class TestVerifyConcatCompatibility:
    def _video_stream(self, **overrides):
        base = {"codec_type": "video", "codec_name": "h264",
                "pix_fmt": "yuv420p", "time_base": "1/90000"}
        base.update(overrides)
        return base

    def _audio_stream(self, **overrides):
        base = {"codec_type": "audio", "codec_name": "aac",
                "profile": "LC", "sample_rate": "48000"}
        base.update(overrides)
        return base

    def _ffprobe(self, video, audio):
        result = MagicMock()
        result.returncode = 0
        result.stdout = json.dumps({"streams": [video, audio]})
        result.stderr = ""
        return result

    def test_single_segment_short_circuits(self, tmp_path):
        from deck2video.assembler import _verify_concat_compatibility
        # Should not even call ffprobe with a single segment.
        with patch("deck2video.assembler.subprocess.run") as mock_run:
            _verify_concat_compatibility([tmp_path / "segment_001.ts"])
        mock_run.assert_not_called()

    def test_matching_segments_pass(self, tmp_path):
        from deck2video.assembler import _verify_concat_compatibility
        seg1 = tmp_path / "segment_001.ts"
        seg2 = tmp_path / "segment_002.ts"
        result = self._ffprobe(self._video_stream(), self._audio_stream())
        with patch("deck2video.assembler.subprocess.run", return_value=result):
            _verify_concat_compatibility([seg1, seg2])  # no exception

    def test_mismatched_pix_fmt_raises(self, tmp_path):
        from deck2video.assembler import _verify_concat_compatibility
        seg1 = tmp_path / "segment_001.ts"
        seg2 = tmp_path / "segment_002.ts"

        def fake_run(cmd, **kw):
            r = MagicMock()
            r.returncode = 0
            r.stderr = ""
            # Last arg is the segment path
            seg_path = cmd[-1]
            if seg_path.endswith("segment_002.ts"):
                r.stdout = json.dumps({
                    "streams": [self._video_stream(pix_fmt="yuv422p"),
                                self._audio_stream()]
                })
            else:
                r.stdout = json.dumps({
                    "streams": [self._video_stream(), self._audio_stream()]
                })
            return r

        with patch("deck2video.assembler.subprocess.run", side_effect=fake_run):
            with pytest.raises(RuntimeError, match="not bit-identical"):
                _verify_concat_compatibility([seg1, seg2])

    def test_mismatched_audio_sample_rate_raises(self, tmp_path):
        from deck2video.assembler import _verify_concat_compatibility
        seg1 = tmp_path / "segment_001.ts"
        seg2 = tmp_path / "segment_002.ts"

        def fake_run(cmd, **kw):
            r = MagicMock()
            r.returncode = 0
            r.stderr = ""
            seg_path = cmd[-1]
            if seg_path.endswith("segment_002.ts"):
                r.stdout = json.dumps({
                    "streams": [self._video_stream(),
                                self._audio_stream(sample_rate="44100")]
                })
            else:
                r.stdout = json.dumps({
                    "streams": [self._video_stream(), self._audio_stream()]
                })
            return r

        with patch("deck2video.assembler.subprocess.run", side_effect=fake_run):
            with pytest.raises(RuntimeError, match="not bit-identical"):
                _verify_concat_compatibility([seg1, seg2])


# ---------------------------------------------------------------------------
# B09 / concat-list quoting — apostrophes in segment names must be escaped
# per ffmpeg's concat-demuxer rules: ' becomes '\''.
# ---------------------------------------------------------------------------

class TestConcatListQuoting:
    def test_apostrophe_escape_rule(self):
        # The escape used inside assembler.py for concat-list entries.
        name = "segment_001'_001.ts"
        escaped = name.replace("'", r"'\''")
        assert escaped == r"segment_001'\''_001.ts"
        # Multiple apostrophes are each escaped.
        assert "weird''name.ts".replace("'", r"'\''") == r"weird'\'''\''name.ts"
