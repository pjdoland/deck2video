# CLI reference

## Synopsis

```
python -m deck2video <input> [options]
python -m deck2video doctor
```

## Subcommands

### `doctor`

Run preflight checks (ffmpeg, ffprobe, marp, slidev, GPU, disk space, model cache) and exit. Useful before kicking off a long render or after a fresh install. Returns 0 when all required checks pass, 1 otherwise.

```
$ python -m deck2video doctor
deck2video doctor — preflight checks

  ✓  python            Python 3.11.14
  ✓  ffmpeg            ffmpeg version 8.0.1
  ✓  ffprobe           ffprobe available
  !  marp-cli          marp-cli not installed globally; will fall back to npx
  ✓  gpu               Apple MPS available
  ✓  disk              42.1 GB free in /tmp
  !  chatterbox cache  No chatterbox snapshot — model will download on first run
```

The doctor takes no arguments. On Windows or `LANG=C` terminals the unicode sigils fall back to `OK / WARN / FAIL`.

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

### `--dark`

Render Slidev slides in dark mode.

- **Type:** flag (no argument)
- **Default:** off
- **Details:** Passes `--dark` to `slidev export`, producing images using Slidev's dark theme. Has no effect when rendering Marp presentations.
- **Example:** `--dark`

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
- **Range:** 0.0–2.0 (practical range: 0.0–1.0; values outside the range are rejected at parse time)
- **Details:** See [Voice and TTS](voice-and-tts.md#--exaggeration-default-05) for tuning guidance.
- **Example:** `--exaggeration 0.7`

### `--cfg-weight`

Chatterbox classifier-free guidance weight.

- **Type:** float
- **Default:** `0.5`
- **Range:** 0.0–1.0 (values outside the range are rejected at parse time)
- **Details:** See [Voice and TTS](voice-and-tts.md#--cfg-weight-default-05) for tuning guidance.
- **Example:** `--cfg-weight 0.3`

### `--temperature`

Chatterbox sampling temperature.

- **Type:** float
- **Default:** `0.8`
- **Range:** 0.0–2.0 (practical range: 0.3–1.2; values outside the range are rejected at parse time)
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
- **Range:** 0.1–300 (values outside the range are rejected at parse time)
- **Example:** `--hold-duration 5.0`

### `--fps`

Output video framerate.

- **Type:** integer
- **Default:** Auto-detected from screencast videos, or 24 fps if no screencasts
- **Range:** 1–120 (values outside the range are rejected at parse time)
- **Details:** When auto-detected from screencasts, the source's fractional rate (e.g. `30000/1001` = 29.97) is preserved end-to-end rather than truncated to int. See [Video Assembly](video-assembly.md#framerate) for auto-detection behavior.
- **Example:** `--fps 30`

### `--audio-padding`

Milliseconds of silence added before and after each slide's audio.

- **Type:** integer
- **Default:** `0`
- **Range:** 0–60000 (values outside the range are rejected at parse time)
- **Details:** A value of 300 adds 300ms before and 300ms after, extending each slide by 600ms total. See [Video Assembly](video-assembly.md#audio-padding).
- **Example:** `--audio-padding 300`

### `--max-slides`

Refuse to render decks with more than N slides.

- **Type:** integer
- **Default:** `500`
- **Range:** 1–100000
- **Details:** Acts as a guardrail against accidental multi-hour renders from a misformatted or runaway deck. Override with a higher value if you genuinely need to render a long deck. Markdown files larger than 10 MiB are rejected outright before parse.
- **Example:** `--max-slides 1000`

### `--with-clicks-audio-padding`

Milliseconds of silence before and after each click-step's audio (Slidev only).

- **Type:** integer
- **Default:** `0`
- **Range:** 0–60000
- **Details:** Applies only to per-step audio for click animations. Slide-boundary steps (the initial reveal of each slide) use `--audio-padding`; subsequent click steps within a slide use this value. Lets you keep tight pacing within a slide (e.g. `0`) while still adding breathing room between slides (`--audio-padding 300`).
- **Example:** `--with-clicks-audio-padding 0 --audio-padding 300`

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
- **Details:** Discovers `slides.*` image files and `audio_*.wav` files in the temp directory. Validates that the counts match. Then runs only the assembly step. Useful after manually editing audio WAV files, or after changing `--audio-padding` or `--fps` without wanting to regenerate everything. If you also pass TTS-only flags (`--voice`, `--pronunciations`, `--interactive`, `--language`, etc.), a `Note: ... ignored in --reassemble mode` is printed to stderr — those flags only take effect when TTS actually runs.
- **Example:** `--reassemble --temp-dir ./build`

### `--redo-slides`

Regenerate TTS audio for specific slides, then reassemble the full video.

- **Type:** string (comma-separated slide numbers and/or ranges, 1-based)
- **Default:** none
- **Requires:** `--temp-dir` pointing to a directory from a previous run, plus the original input `.md` file
- **Mutually exclusive with:** `--reassemble`
- **Details:** Re-parses the markdown to get current speaker notes, regenerates audio for only the listed slides (overwriting the existing WAV files in place), then reassembles the full video. Slide numbers are 1-based original slide numbers (not step indices). Accepts both single numbers and inclusive ranges: `2,5,7` or `2-5,8` or `1-3,7,10-12`. Duplicates are deduplicated with a one-line note to stderr; descending ranges (`5-3`) are rejected. All TTS options (`--voice`, `--exaggeration`, etc.) apply to the regenerated slides. Regeneration is now deterministic per slide/click — if you re-run with the same notes and TTS settings you get bit-identical audio. For Slidev decks with [click animations](writing-slides.md#slidev-click-animations), specifying a slide number regenerates **all** click steps for that slide (e.g., `--redo-slides 3` regenerates the initial state plus every click step of slide 3).
- **Example:** `--redo-slides 2-5,8 --temp-dir ./build`

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error: input file not found, pronunciations file not found, ffmpeg/marp/slidev not found, slide count mismatch, or other pipeline failure |
| 0 | User quit during interactive mode (`q` key) |

Note: quitting during interactive mode exits with code 0 (clean exit via `sys.exit(0)`).
