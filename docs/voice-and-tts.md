# Voice and TTS

deck2video uses [Chatterbox TTS](https://github.com/resemble-ai/chatterbox) for speech synthesis. Chatterbox is a neural TTS model that supports zero-shot voice cloning from a short audio sample. deck2video loads the model once and synthesizes all slides sequentially.

The model and its dependencies (torch, torchaudio, chatterbox) are lazy-loaded. They're only imported when at least one slide has speaker notes. If your deck has no notes at all, the TTS model is never loaded.

## Voice cloning

Pass a reference WAV file with `--voice` to clone a speaker's voice:

```bash
python -m deck2video deck.md --voice ~/recordings/my-voice.wav
```

### What makes a good reference WAV

5-30 seconds of clear speech works best. Too short and the model has less to work with; too long and you get diminishing returns.

Use clean audio with minimal background noise. Avoid recordings with music, other speakers, or room echo. The content should be natural, conversational speech. The model captures tone, pace, and vocal qualities; the actual words don't matter. Any WAV sample rate is accepted (the model resamples internally).

### Without a voice reference

If you omit `--voice`, Chatterbox uses its default voice. This is fine for testing but will sound generic.

## Generation parameters

Three parameters control the style and quality of generated speech:

### `--exaggeration` (default: 0.5)

Controls how expressive and dynamic the speech sounds. Higher values produce more animated, energetic delivery; lower values are more flat and neutral.

| Value | Effect |
|-------|--------|
| 0.0 | Very flat, monotone |
| 0.3 | Calm, understated |
| 0.5 | Natural, balanced (default) |
| 0.7 | Expressive, engaging |
| 1.0+ | Very animated (may sound exaggerated) |

### `--cfg-weight` (default: 0.5)

Classifier-free guidance weight. Controls how closely the output follows the text prompt vs. the voice reference. Higher values produce more consistent but potentially less natural speech.

| Value | Effect |
|-------|--------|
| 0.0 | Relies heavily on the voice reference, less text adherence |
| 0.3 | Balanced toward voice similarity |
| 0.5 | Default balance |
| 0.7 | Stronger text adherence |
| 1.0+ | Very strong guidance (may reduce naturalness) |

### `--temperature` (default: 0.8)

Sampling temperature for the model's output distribution. Higher values introduce more randomness (varied intonation, pacing); lower values produce more deterministic, consistent output.

| Value | Effect |
|-------|--------|
| 0.3 | Very consistent, potentially robotic |
| 0.5 | Consistent with some variation |
| 0.8 | Natural variation (default) |
| 1.0+ | More varied (may introduce artifacts) |

### Tuning tips

Start with defaults and use [interactive mode](interactive-mode.md) to evaluate. If speech sounds too flat, increase `--exaggeration` (try 0.6-0.7). If speech sounds inconsistent between sentences, lower `--temperature` (try 0.5-0.6). If the voice doesn't sound enough like your reference, lower `--cfg-weight` (try 0.2-0.3).

Each regeneration produces different output because the model is stochastic. If a slide sounds bad, regenerating with the same parameters may fix it.

## Device selection

deck2video auto-detects the best available compute device for TTS:

1. CUDA (NVIDIA GPU), checked first
2. MPS (Apple Silicon GPU)
3. CPU, used as fallback

Override with `--device`:

```bash
python -m deck2video deck.md --device cpu
python -m deck2video deck.md --device cuda
python -m deck2video deck.md --device mps
```

When auto-detecting, the tool prints which device was selected:

```
  Using MPS (Apple Silicon) for TTS
```

If no GPU is available, a warning is printed to stderr:

```
  WARNING: No GPU available — using CPU for TTS. This will be much slower.
```

## GPU out-of-memory fallback

If the TTS model runs out of GPU memory during generation, deck2video automatically moves the model to CPU, frees GPU memory, retries the failed slide, and continues processing all remaining slides on CPU.

If the CPU retry also fails, the slide gets a silent WAV of `--hold-duration` seconds, and the pipeline continues with the next slide.

You'll see:

```
  Moved model to CPU due to GPU memory pressure
```

No user intervention required.

## GPU memory release on exit

deck2video wraps the model load in a context manager that guarantees `model.cpu()` and a torch allocator flush when the pipeline finishes (success, failure, or Ctrl-C). Without this, the model stayed resident in GPU memory until the Python process exited — fine for one-shot CLI runs but a real leak for back-to-back `--redo-slides` invocations in the same process or anyone calling `generate_audio_for_slides` from a longer-lived host. Cleanup is best-effort: a torch internal failure during teardown is logged but not propagated, so the original exception (if any) reaches the user.

## Sentence splitting

Long speaker notes are split into sentences before synthesis. Sentences are then grouped into chunks of 3 for each TTS call, and the resulting audio is concatenated.

### How splitting works

The splitter uses a regex that breaks on `.`, `!`, or `?` followed by whitespace:

```
"First sentence. Second sentence! Third sentence?"
→ ["First sentence.", "Second sentence!", "Third sentence?"]
```

### Known edge cases

Abbreviations containing periods cause premature splits:

```
"Use e.g. this approach."
→ ["Use e.g.", "this approach."]  ← split in the wrong place
```

Spell out abbreviations in your speaker notes. Write "for example" instead of "e.g.", "that is" instead of "i.e.", "and so on" instead of "etc."

### Chunking

After splitting, sentences are grouped into chunks of 3:

```
6 sentences → ["S1 S2 S3", "S4 S5 S6"]
7 sentences → ["S1 S2 S3", "S4 S5 S6", "S7"]
```

Each chunk is passed to the TTS model as a single string. The resulting audio tensors are concatenated with `torch.cat` into one WAV per slide.

Progress is reported for multi-chunk slides:

```
  Slide 4: chunk 1/3 OK
  Slide 4: chunk 2/3 OK
  Slide 4: chunk 3/3 OK
  Slide 4: TTS OK (8 sentences in 3 chunks)
```

## Pronunciation overrides

The TTS engine sometimes mispronounces technical terms, acronyms, or proper nouns. You can fix this with a JSON pronunciation mapping.

### JSON format

Create a JSON file with a flat object mapping words/phrases to their phonetic respellings:

```json
{
  "kubectl": "cube control",
  "nginx": "engine X",
  "PostgreSQL": "post gress Q L",
  "Kubernetes": "koo ber net eez",
  "API": "A P I",
  "gRPC": "gee R P C",
  "OAuth": "oh auth",
  "YAML": "yam ul"
}
```

Pass it with `--pronunciations`:

```bash
python -m deck2video deck.md --pronunciations pronunciations.json
```

### Matching rules

**Case-insensitive.** `"kubectl"` matches "kubectl", "Kubectl", "KUBECTL", etc.

**Longer keys first.** Keys are sorted by length (descending) before replacement. So `"Visual Studio Code"` matches before `"Code"` alone.

**Not word-boundary restricted.** The current implementation uses simple regex substitution without word-boundary anchors. `"SQL"` will match inside `"MySQL"`, replacing it with `"MyS Q L"` or similar. To avoid this, add both `"SQL": "sequel"` and `"MySQL": "my sequel"`.

**Greedy replacement.** Replacements are applied sequentially (longer keys first). A replacement's output text can be matched by a subsequent shorter key. If you have `"gRPC": "gee R P C"` and `"PC": "personal computer"`, the output of the first replacement could be matched by the second.

### Gotchas

- The pronunciation file must be valid JSON. Keys and values must be strings; non-string values are rejected at load time with a clear error.
- Empty keys are rejected. Keys and values are capped at 200 characters each, and the file is capped at 1000 entries — pathological inputs that would otherwise hang regex compilation are rejected up front.
- If the file doesn't exist, the pipeline exits with an error before starting.
- The number of loaded overrides is printed at startup: `Loaded 8 pronunciation override(s)`.
- Replacements are applied to each slide's notes text before it's sent to the TTS model. The original `Slide.notes` field is left untouched, so retries and `--redo-slides` re-runs don't double-apply substitutions.

## Multilingual TTS

deck2video supports [Chatterbox's multilingual model](https://github.com/resemble-ai/chatterbox#chatterbox-and-chatterbox-multilingual), which covers 23 languages. Pass a BCP-47 language code with `--language`:

```bash
python -m deck2video deck.md --language fr --voice voice.wav
python -m deck2video deck.md --language zh
python -m deck2video deck.md --language de --voice voice.wav
```

When `--language` is set, deck2video loads `ChatterboxMultilingualTTS` instead of `ChatterboxTTS`. Voice cloning (`--voice`) is supported with the multilingual model.

### Supported language codes

Common codes: `en` (English), `fr` (French), `de` (German), `es` (Spanish), `it` (Italian), `pt` (Portuguese), `zh` (Chinese), `ja` (Japanese), `ko` (Korean), `nl` (Dutch), `pl` (Polish), `ru` (Russian). See the [Chatterbox README](https://github.com/resemble-ai/chatterbox) for the full list of 23 supported languages.

### Notes

- Omitting `--language` always uses the standard `ChatterboxTTS` model (English-optimised, slightly smaller).
- The multilingual model is a separate download from the standard model; expect a longer first-run load.
- All other flags (`--exaggeration`, `--cfg-weight`, `--temperature`, `--pronunciations`, `--interactive`) work the same way with both models.

## Lazy model loading

The TTS model is only loaded when needed. If no slides have speaker notes, the model is never loaded. Heavy imports (`torch`, `torchaudio`, `chatterbox`) happen at model load time, not at startup, so the parse and render steps stay fast even on machines without GPU support.

## Silent slides

Slides with `notes=None` (no HTML comments, or only directive/video comments) get a silent WAV file generated with pure Python, no TTS model needed. The silence duration is controlled by `--hold-duration` (default: 3.0 seconds).

The silent WAV is a minimal valid PCM file: 1 channel, 16-bit, 24000 Hz sample rate.
