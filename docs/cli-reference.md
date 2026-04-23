# CLI reference

## Synopsis

```
python -m deck2video <input> [options]
```

## Positional arguments

### `input`

Path to the Marp or Slidev markdown file.

- **Required:** yes
- **Example:** `python -m deck2video slides.md`

## Input / output options

### `--output`

Output MP4 file path.

- **Type:** string (file path)
- **Default:** Input filename with `.mp4` extension (e.g., `slides.md` → `slides.mp4`)
- **Example:** `--output talk.mp4`

### `--format`

Presentation format. Controls which parser and renderer are used.

- **Type:** choice
- **Choices:** `auto`, `marp`, `slidev`
- **Default:** `auto`
- **Details:** When set to `auto`, the format is [detected from the file content](format-detection.md). Set explicitly to skip detection or override a wrong guess.
- **Example:** `--format slidev`

### `--temp-dir`

Directory for intermediate files (rendered PNGs, audio WAVs, video segments, log file).

- **Type:** string (directory path)
- **Default:** System temp directory (a `deck2video_` prefixed directory in `/tmp` or equivalent)
- **Details:** If the directory doesn't exist, it's created. When using a custom temp dir, it is **never** automatically cleaned up (even without `--keep-temp`), since you've explicitly chosen its location.
- **Example:** `--temp-dir ./build`

### `--keep-temp`

Preserve intermediate files after a successful run.

- **Type:** flag (no argument)
- **Default:** off (temp files are cleaned up on success)
- **Details:** On failure, temp files are always preserved regardless of this flag. When using a custom `--temp-dir`, files are always preserved.
- **Example:** `--keep-temp`

## TTS options

### `--voice`

Path to a reference WAV file for Chatterbox voice cloning.

- **Type:** string (file path)
- **Default:** none (uses the default Chatterbox voice)
- **Details:** See [Voice and TTS](voice-and-tts.md) for recommendations on reference audio quality and duration.
- **Example:** `--voice ~/recordings/my-voice.wav`

### `--language`

Language code for multilingual TTS synthesis.

- **Type:** string (BCP-47 language code)
- **Default:** none (uses the standard English-optimised `ChatterboxTTS` model)
- **Details:** When set, loads `ChatterboxMultilingualTTS` instead of `ChatterboxTTS` and passes the code as `language_id` to every generate call. Voice cloning (`--voice`) works with the multilingual model. Common codes: `en`, `fr`, `de`, `es`, `it`, `pt`, `zh`, `ja`, `ko`. See [Voice and TTS](voice-and-tts.md#multilingual-tts) for the full language list.
- **Example:** `--language fr`

### `--device`

Compute device for the TTS model.

- **Type:** choice
- **Choices:** `auto`, `cpu`, `cuda`, `mps`
- **Default:** `auto`
- **Details:** Auto-detection order: CUDA → MPS → CPU. See [Voice and TTS](voice-and-tts.md#device-selection) for details.
- **Example:** `--device cpu`

### `--exaggeration`

Chatterbox vocal exaggeration level. Controls how expressive the speech sounds.

- **Type:** float
- **Default:** `0.5`
- **Range:** 0.0 and up (practical range: 0.0–1.0)
- **Details:** See [Voice and TTS](voice-and-tts.md#--exaggeration-default-05) for tuning guidance.
- **Example:** `--exaggeration 0.7`

### `--cfg-weight`

Chatterbox classifier-free guidance weight.

- **Type:** float
- **Default:** `0.5`
- **Range:** 0.0 and up (practical range: 0.0–1.0)
- **Details:** See [Voice and TTS](voice-and-tts.md#--cfg-weight-default-05) for tuning guidance.
- **Example:** `--cfg-weight 0.3`

### `--temperature`

Chatterbox sampling temperature.

- **Type:** float
- **Default:** `0.8`
- **Range:** 0.0 and up (practical range: 0.3–1.2)
- **Details:** See [Voice and TTS](voice-and-tts.md#--temperature-default-08) for tuning guidance.
- **Example:** `--temperature 0.6`

### `--pronunciations`

Path to a JSON file mapping words/phrases to phonetic respellings.

- **Type:** string (file path)
- **Default:** none
- **Details:** See [Voice and TTS](voice-and-tts.md#pronunciation-overrides) for format and matching rules.
- **Example:** `--pronunciations pronunciations.json`

## Video options

### `--hold-duration`

Duration (in seconds) to hold slides that have no speaker notes.

- **Type:** float
- **Default:** `3.0`
- **Example:** `--hold-duration 5.0`

### `--fps`

Output video framerate.

- **Type:** integer
- **Default:** Auto-detected from screencast videos, or 24 fps if no screencasts
- **Details:** See [Video Assembly](video-assembly.md#framerate) for auto-detection behavior.
- **Example:** `--fps 30`

### `--audio-padding`

Milliseconds of silence added before and after each slide's audio.

- **Type:** integer
- **Default:** `0`
- **Details:** A value of 300 adds 300ms before and 300ms after, extending each slide by 600ms total. See [Video Assembly](video-assembly.md#audio-padding).
- **Example:** `--audio-padding 300`

## Workflow options

### `--interactive`, `-i`

Review and approve each slide's TTS audio before continuing.

- **Type:** flag (no argument)
- **Default:** off
- **Details:** See [Interactive Mode](interactive-mode.md) for a full walkthrough.
- **Example:** `--interactive` or `-i`

### `--reassemble`

Skip parsing, rendering, and TTS. Assemble the final MP4 directly from existing slide images and audio files in the temp directory.

- **Type:** flag (no argument)
- **Default:** off
- **Requires:** `--temp-dir` pointing to a directory from a previous run
- **Mutually exclusive with:** `--redo-slides`
- **Details:** Discovers `slides.*` image files and `audio_*.wav` files in the temp directory. Validates that the counts match. Then runs only the assembly step. Useful after manually editing audio WAV files, or after changing `--audio-padding` or `--fps` without wanting to regenerate everything.
- **Example:** `--reassemble --temp-dir ./build`

### `--redo-slides`

Regenerate TTS audio for specific slides, then reassemble the full video.

- **Type:** string (comma-separated slide numbers, 1-based)
- **Default:** none
- **Requires:** `--temp-dir` pointing to a directory from a previous run, plus the original input `.md` file
- **Mutually exclusive with:** `--reassemble`
- **Details:** Re-parses the markdown to get current speaker notes, regenerates audio for only the listed slides (overwriting the existing WAV files in place), then reassembles the full video. Slide numbers are 1-based original slide numbers (not step indices). All TTS options (`--voice`, `--exaggeration`, etc.) apply to the regenerated slides. For Slidev decks with [click animations](writing-slides.md#slidev-click-animations), specifying a slide number regenerates **all** click steps for that slide (e.g., `--redo-slides 3` regenerates the initial state plus every click step of slide 3).
- **Example:** `--redo-slides 2,5,7 --temp-dir ./build`

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error: input file not found, pronunciations file not found, ffmpeg/marp/slidev not found, slide count mismatch, or other pipeline failure |
| 0 | User quit during interactive mode (`q` key) |

Note: quitting during interactive mode exits with code 0 (clean exit via `sys.exit(0)`).
