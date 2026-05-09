# Examples

## Minimal Marp deck

The simplest possible Marp presentation with narration:

**slides.md:**

```markdown
---
marp: true
---

# Welcome

<!-- Hello and welcome to this presentation. -->

---

# Key Point

<!-- Here is the main thing I want you to take away from this talk. -->

---

# Thank You
```

**Command:**

```bash
python -m deck2video slides.md
```

This produces `slides.mp4` with the default Chatterbox voice. The "Thank You" slide has no notes, so it's held silently for 3 seconds.

## Minimal Slidev deck

**slides.md:**

```markdown
---
transition: slide-left
---

# Welcome

<!-- Hello and welcome to this presentation. -->

---
layout: center
---

# Key Point

<!-- Here is the main thing I want you to take away from this talk. -->

---

# Thank You
```

**Command:**

```bash
python -m deck2video slides.md
```

The `transition` key in frontmatter triggers Slidev auto-detection. Per-slide frontmatter like `layout: center` is stripped from the body before rendering.

Note: since the video is a sequence of static PNGs, slide transitions from Slidev are not captured in the output.

## Slidev click animations

Use `[click]` markers in your speaker notes to sync narration with progressive reveal animations:

**slides.md:**

```markdown
---
transition: fade
---

# What We'll Cover

<v-clicks>

- Background and motivation
- The core algorithm
- Benchmarks and results

</v-clicks>

<!--
Today I'll walk you through three topics.
[click]
First, some background on why this problem matters.
[click]
Then the core algorithm — the heart of the approach.
[click]
And finally, the benchmarks that show it actually works.
-->

---

# Summary

<!-- That covers everything. Questions welcome. -->
```

**Command:**

```bash
python -m deck2video slides.md --format slidev --voice voice.wav
```

**What happens:**

deck2video detects the `[click]` markers and expands the first slide into four steps:

```
[1/4] Parsing slides…
  Found 2 slides → 5 steps (click expansion)
```

The Slidev CLI is called with `--with-clicks`, producing `slides/1.png`, `slides/1-1.png`, `slides/1-2.png`, `slides/1-3.png`, and `slides/2.png`. Each gets its own narration segment and they're assembled into a single MP4 where the bullet points appear in sync with the spoken narration.

**Redoing a click slide:**

```bash
# Regenerates all 4 steps of slide 1 (initial + 3 clicks)
python -m deck2video slides.md --format slidev \
    --redo-slides 1 --temp-dir ./build --voice voice.wav
```

## Voice cloning with tuned parameters

Record a 10-20 second WAV of yourself speaking naturally, then:

```bash
python -m deck2video deck.md \
    --voice ~/recordings/my-voice.wav \
    --exaggeration 0.6 \
    --cfg-weight 0.3 \
    --temperature 0.6 \
    --output talk.mp4
```

Slightly higher exaggeration (0.6) for a more animated delivery. Lower cfg-weight (0.3) to lean toward matching the voice reference. Lower temperature (0.6) for more consistent output across sentences.

## Screencast-embedded presentation

A presentation where one slide shows a live demo recording:

**slides.md:**

```markdown
---
marp: true
---

# Architecture Overview

<!-- Our system has three main services communicating over gRPC. -->

---

# Live Demo

<!-- video: assets/deploy-demo.mov -->

<!-- Watch as we deploy the updated service. The process takes about thirty seconds and includes automated health checks. -->

---

# Summary

<!-- That's the deployment pipeline. Let's recap what we saw. -->
```

**Directory structure:**

```
project/
├── slides.md
└── assets/
    └── deploy-demo.mov
```

**Command:**

```bash
python -m deck2video slides.md --voice voice.wav --audio-padding 200
```

What happens:
- Slide 1: static PNG with narration
- Slide 2: `deploy-demo.mov` plays with TTS narration replacing the original audio. If the narration is longer than the video, the last frame freezes.
- Slide 3: static PNG with narration
- The output framerate is auto-detected from the screencast (e.g., 30 fps).
- 200ms of silence is added before and after each slide's audio.

## Pronunciation overrides for a tech talk

**pronunciations.json:**

```json
{
    "Kubernetes": "koo ber net eez",
    "kubectl": "cube control",
    "k8s": "kates",
    "nginx": "engine X",
    "PostgreSQL": "post gress Q L",
    "MySQL": "my sequel",
    "SQL": "sequel",
    "gRPC": "gee R P C",
    "OAuth": "oh auth",
    "YAML": "yam ul",
    "TOML": "tom ul",
    "API": "A P I",
    "CLI": "C L I",
    "AWS": "A W S",
    "GCP": "G C P"
}
```

**Command:**

```bash
python -m deck2video deck.md \
    --voice voice.wav \
    --pronunciations pronunciations.json
```

Note: longer keys are matched first, so `"MySQL"` → `"my sequel"` is applied before `"SQL"` → `"sequel"`, preventing "MySQL" from becoming "my sequel" via two separate replacements.

## Interactive review workflow

Review each slide's audio before committing:

```bash
python -m deck2video deck.md \
    --voice voice.wav \
    --interactive \
    --keep-temp
```

Walk through each slide:

```
  Slide 1: TTS OK (2 sentences in 1 chunk)
  (audio plays)
  (y) keep  (n) regenerate  (r) replay  (q) quit: y

  Slide 2: TTS OK (1 sentence in 1 chunk)
  (audio plays)
  (y) keep  (n) regenerate  (r) replay  (q) quit: n
  Regenerating slide 2...
  Slide 2: TTS OK (1 sentence in 1 chunk)
  (new audio plays)
  (y) keep  (n) regenerate  (r) replay  (q) quit: y
```

The `--keep-temp` flag ensures you can inspect individual WAV files after the run.

## Full production pipeline

```bash
python -m deck2video presentation.md \
    --voice ~/recordings/my-voice.wav \
    --pronunciations pronunciations.json \
    --exaggeration 0.6 \
    --cfg-weight 0.3 \
    --temperature 0.6 \
    --audio-padding 300 \
    --hold-duration 4.0 \
    --fps 30 \
    --interactive \
    --keep-temp \
    --output final-talk.mp4
```

## Redo bad slides without re-running the full pipeline

After a full run, suppose slides 3 and 6 had bad TTS output. Rather than
re-running the entire pipeline:

```bash
# First run with a named temp directory
python -m deck2video deck.md \
    --voice voice.wav \
    --temp-dir ./build \
    --output talk.mp4

# Listen to individual slides
afplay ./build/audio_003.wav   # sounds bad
afplay ./build/audio_006.wav   # also bad

# Redo just those slides (single numbers, ranges, or both)
python -m deck2video deck.md \
    --redo-slides 3,6 \
    --temp-dir ./build \
    --voice voice.wav \
    --output talk.mp4

# Or redo a contiguous range plus an individual slide:
python -m deck2video deck.md \
    --redo-slides 3-6,10 \
    --temp-dir ./build \
    --voice voice.wav
```

This re-parses the markdown, regenerates audio for the listed slides only, then
reassembles the full video. All other slides keep their existing audio.
Regeneration is deterministic per slide/click — re-running with the same notes
and TTS settings produces bit-identical audio.

## Reassemble after manual edits

If you've manually edited audio WAV files in the temp directory (e.g., trimmed
silence, applied noise reduction), you can reassemble without touching TTS:

```bash
python -m deck2video deck.md \
    --reassemble \
    --temp-dir ./build \
    --audio-padding 200 \
    --output talk.mp4
```

This picks up whatever `slides.*` and `audio_*.wav` files exist in `./build`
and assembles a new MP4. You can also change `--fps` or `--audio-padding`
without regenerating anything.

## CPU-only mode

If you don't have a GPU or want to avoid GPU memory issues:

```bash
python -m deck2video deck.md --voice voice.wav --device cpu
```

This is significantly slower but works on any machine. You'll see:

```
  Using device: cpu
```

## Custom temp directory

Keep build artifacts in a known location:

```bash
python -m deck2video deck.md \
    --voice voice.wav \
    --temp-dir ./build \
    --output output.mp4
```

The `./build` directory is created if it doesn't exist and is never automatically cleaned up, so you can inspect all intermediate files at any time.
