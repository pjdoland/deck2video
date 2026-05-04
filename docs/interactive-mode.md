# Interactive mode

Interactive mode lets you listen to each slide's TTS audio and decide whether to keep it, regenerate it, or quit. This catches bad output early instead of waiting for the full pipeline to finish.

## Enabling interactive mode

```bash
python -m deck2video deck.md --voice voice.wav --interactive
# or
python -m deck2video deck.md --voice voice.wav -i
```

## How it works

The pipeline runs normally through parsing and rendering. During TTS generation (step 3), after each slide's audio is synthesized, the audio plays automatically, you're prompted with keyboard controls, and the pipeline pauses until you respond.

Slides without speaker notes (silent holds) are skipped. For Slidev decks with [click animations](writing-slides.md#slidev-click-animations), each click step is reviewed individually.

## Keyboard controls

After each slide's audio plays, you see a prompt that includes the slide label:

```
  Slide 3: (y) keep  (n) regenerate  (r) replay  (q) quit:
```

For Slidev click steps, the label includes click context:

```
  Slide 3 click 2: (y) keep  (n) regenerate  (r) replay  (q) quit:
```

| Key | Action |
|-----|--------|
| **y** or **Enter** | Accept the audio and move to the next slide |
| **n** | Discard the audio and regenerate with a new TTS pass |
| **r** | Replay the current audio without regenerating |
| **q** | Quit the pipeline immediately (exit code 0) |

### Regeneration

When you press `n`:

1. The existing audio file is discarded.
2. A new TTS pass generates fresh audio (same parameters, different random seed).
3. The new audio plays automatically.
4. You're prompted again with the same controls.

You can regenerate as many times as you like. Each pass produces different output because the model is stochastic.

If regeneration fails (e.g., a TTS error), the previous audio is kept and you're moved to the next slide:

```
  Regeneration failed (error details), keeping previous audio.
```

### Replaying

Press `r` to hear the current audio again without regenerating. Useful if you weren't paying attention or want to listen more carefully.

### Quitting

Press `q` to stop the pipeline. The process exits with code 0 (clean exit). No video is produced. Temp files may be preserved depending on the error handling path.

## Platform audio playback

Interactive mode plays audio using your platform's native command:

| Platform | Command |
|----------|---------|
| macOS | `afplay` |
| Linux | `aplay` |
| Windows | `cmd /c start` |

If the platform isn't recognized, a warning is printed and playback is skipped. You can still approve/reject based on inspecting the WAV file manually.

Audio playback runs synchronously. The prompt appears after playback finishes.

## Step-by-step walkthrough

A typical interactive session:

```
[3/4] Generating audio...
  Using MPS (Apple Silicon) for TTS
  Slide 1: TTS OK (2 sentences in 1 chunk)
  (audio plays automatically)
  Slide 1: (y) keep  (n) regenerate  (r) replay  (q) quit: y
  Slide 2: TTS OK (1 sentence in 1 chunk)
  (audio plays automatically)
  Slide 2: (y) keep  (n) regenerate  (r) replay  (q) quit: n
  Regenerating Slide 2...
  Slide 2: TTS OK (1 sentence in 1 chunk)
  (new audio plays automatically)
  Slide 2: (y) keep  (n) regenerate  (r) replay  (q) quit: y
  Slide 3: silent (3.0s)
  Slide 4: TTS OK (3 sentences in 1 chunk)
  (audio plays automatically)
  Slide 4: (y) keep  (n) regenerate  (r) replay  (q) quit: y
```

For a Slidev deck with click animations, click steps appear individually:

```
  Slide 2: TTS OK (1 sentence in 1 chunk)
  Slide 2: (y) keep  (n) regenerate  (r) replay  (q) quit: y
  Slide 2 click 1: TTS OK (2 sentences in 1 chunk)
  Slide 2 click 1: (y) keep  (n) regenerate  (r) replay  (q) quit: y
  Slide 2 click 2: TTS OK (1 sentence in 1 chunk)
  Slide 2 click 2: (y) keep  (n) regenerate  (r) replay  (q) quit: y
```

## Tips

Use headphones. Small audio artifacts are easier to catch.

Tune parameters first. Before reviewing a full deck, run a quick test with 2-3 slides to find good values for `--exaggeration`, `--cfg-weight`, and `--temperature`. See [Voice and TTS](voice-and-tts.md#tuning-tips).

Focus on problem slides. If you know certain slides have tricky technical terms, pay extra attention. Use [pronunciation overrides](voice-and-tts.md#pronunciation-overrides) for terms that are consistently wrong.

Don't over-regenerate. The model is stochastic, so regenerating the same text gives different results each time. If the output is consistently bad, the issue is probably the text itself (too complex, abbreviations, etc.) rather than bad luck with the random seed.

Combine with `--keep-temp` or `--temp-dir` so you can inspect the individual WAV files after the run. If you later find a slide that needs fixing, use `--redo-slides` instead of re-running the full pipeline. See [Examples](examples.md#redo-bad-slides-without-re-running-the-full-pipeline).
